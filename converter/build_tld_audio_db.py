"""Build a Hoshi-Reader audio database from The Little Dict (TLD).

TLD ships 7 .mdd files (3.8 GB) holding 824k audio files, 82% of them .spx, which
Hoshi cannot play. This transcodes the spx to opus at a bitrate at or above the
source's own (~13-15 kbps measured), so nothing the source still carried is lost,
and writes a Hoshi-compatible SQLite database.

Pipeline
  1. TLD.mdx  -> word -> [audio file names]     (the authoritative mapping: the
     entries themselves name the audio they reference, so no key-name guessing)
  2. each .mdd -> payload bytes, decoded by hand (mdict-utils fails on these
     files; the layout is exact, see _tld_* notes in REVIEW/HANDOVER)
  3. mp3 kept as-is, spx -> opus via ffmpeg (imageio-ffmpeg, no system install)
  4. SQLite: entries + android, the contract Hoshi reads

Memory: the word<->file index is the only large structure; payloads are streamed
one block at a time and discarded after insertion.
"""
import argparse
import bisect
import io
import os
import re
import sqlite3
import struct
import subprocess
import sys
import tempfile
import zlib
from collections import defaultdict

# ---------------------------------------------------------------- constants
OPUS_BITRATE = "16k"        # >= the measured source bitrate (13-15 kbps)
OPUS_APP = "voip"
AUDIO_EXT = (".mp3", ".spx", ".ogg", ".wav", ".m4a")
BATCH = 500                 # rows per SQLite transaction
FFBATCH = 100               # inputs per ffmpeg call; Windows caps a command line
                            # at 32,767 chars and each file costs ~160 of them
REJECTED = 0                # transcodes dropped by the duration gate (running total)

# One source tag per .mdd, because they are different origins, not one library:
#   TLD.1  ameProns\*.mp3            American pronunciations
#   TLD.2  media\english\uk_pron\*   British pronunciations
#   TLD.3  COLmp3*.spx               Collins pronunciation library
#   TLD.4  mw_*.spx                  Merriam-Webster style headword clips
#   TLD.5  <numeric>.spx             unnamed ids
#   TLD.6  uk_pron\ca2uk*.mp3        a second British set -> DROPPED, see below
#   TLD    snd*.spx                  the default/sound set
# The existing merged DB uses the same convention (ldoce_ame / ldoce_bre / oald10),
# so a per-origin tag is what the merge tool and the audits expect.
MDD_SOURCES = {
    "TLD.1.mdd": "tld_ame",
    "TLD.2.mdd": "tld_uk",
    "TLD.3.mdd": "tld_collins",
    "TLD.4.mdd": "tld_mw",
    "TLD.5.mdd": "tld_ids",
    # "TLD.6.mdd": "tld_uk2",  -- dropped 2026-11-11, do not re-add.
    #   Health check: 87,549 clips / 649 MB bought only 2,291 expressions
    #   (2,291 of 338,029 = 0.7% of lookups), 70% of its filenames are bare
    #   numbers (`ukl30144.mp3`) so a mismatch cannot be caught structurally,
    #   and it is the only source with a confirmed wrong clip (`four` ->
    #   "Four by four."). The 672 single words it alone covered now have no
    #   audio; that was an accepted trade. Numbers live in AUDIO.md.
    "TLD.mdd": "tld_snd",
}

# Clips whose recording does not match the headword. No structural check can
# find these (the mdd record decodes cleanly and the mdx reference is intact --
# only the audio itself disagrees), so they live in a hand-curated TSV and are
# skipped on insert. Empty set == feature off.
BAD = set()


def load_blacklist(path):
    """Read (source, file, expression) triples; missing file is not an error."""
    if not path or not os.path.exists(path):
        return set()
    out = set()
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                print(f"      WARNING: ignoring malformed blacklist line {line!r}")
                continue
            out.add((parts[0].strip(), parts[1].strip(), parts[2].strip()))
    return out


SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id integer PRIMARY KEY NOT NULL,
    expression text NOT NULL,
    reading text,
    source text NOT NULL,
    speaker text,
    display text,
    file text NOT NULL
);
CREATE INDEX IF NOT EXISTS expr_idx ON entries(expression);
CREATE INDEX IF NOT EXISTS src_idx  ON entries(source);
CREATE TABLE IF NOT EXISTS android (
    id integer PRIMARY KEY NOT NULL,
    file text NOT NULL,
    source text NOT NULL,
    data blob NOT NULL
);
CREATE INDEX IF NOT EXISTS file_idx ON android(file);
"""
# The column list above is deliberately the same as android_merged.db's, because
# this db gets merged into it. reading/speaker/display are NULLABLE there -- LDOCE
# rows carry NULL, OALD10 rows carry 'UK'/'US'. An earlier version declared them
# NOT NULL, which then made the NULL normalisation fail with an IntegrityError
# and forced a table rebuild.


# ------------------------------------------------------------------- helpers
def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def looks_audio(b):
    """True if `b` starts like something Hoshi can play.

    mp3: ID3 tag or an MPEG frame header (0xFFEx). opus/ogg: OggS.
    The check exists because the previous build stored misaligned slices that
    still looked like rows in the db but could never be decoded.
    """
    if not b:
        return False
    if b[:4] == b"OggS" or b[:3] == b"ID3" or b[:4] == b"RIFF":
        return True
    return len(b) >= 2 and b[0] == 0xFF and (b[1] & 0xE0) == 0xE0


def blocks_of(path):
    """Yield (offsets, keylist, raw) for every record block.

    `offsets` is the list of record offsets from keylist, kept separately so the
    caller can bisect it: scanning every key of every block is O(blocks x keys)
    -- 6,423 x 154,737 = ~1e9 iterations, which is what made the first version
    unusably slow.

    mdict-utils cannot read these files, so the layout is parsed directly:
        [4B num_blocks][4B num_entries][4B info_size][4B block_size]   (8-byte ints)
        [record_block_info: num_blocks pairs of (compressed, decompressed)]
        [record blocks]
    Each block is zlib (compression_method 2), never encrypted in practice --
    6,407 of 6,423 blocks in TLD.1.mdd decoded that way.
    """
    from mdict_utils.reader import MDD
    m = MDD(path)
    keylist = list(m._key_list)
    offsets = [k[0] for k in keylist]
    off = m._record_block_offset
    with open(path, "rb") as f:
        f.seek(off)
        nb, ne, isz, bsz = [struct.unpack(">Q", f.read(8))[0] for _ in range(4)]
        info = f.read(isz)
    pairs = [struct.unpack(">QQ", info[i * 16:(i + 1) * 16]) for i in range(nb)]
    starts = []
    acc = off + 32 + isz
    for cs, ds in pairs:
        starts.append(acc)
        acc += cs
    # Yields (offsets, keylist, start, size, raw). `start`/`size` are positions in
    # the decompressed stream, derived from the block-size table, NOT from what we
    # managed to decode. That matters: keylist offsets are absolute, so a block
    # that cannot be decoded still occupies `ds` bytes of that space. The earlier
    # version dropped such blocks silently and never advanced its cursor, which
    # shifted every following record by the missing bytes -- same slice length,
    # garbage content (70% of tld_ame came out unplayable). Now an unusable block
    # yields raw=None and the caller skips exactly its keys, losing 219 of 95,616
    # keys instead of corrupting 69,165.
    pos = 0
    with open(path, "rb") as f:
        for i, (cs, ds) in enumerate(pairs):
            start = pos
            pos += ds
            f.seek(starts[i])
            blk = f.read(cs)
            if len(blk) != cs:
                yield offsets, keylist, start, ds, None
                continue
            info2 = struct.unpack("<L", blk[:4])[0]
            cm, em = info2 & 0xf, (info2 >> 4) & 0xf
            if em:
                yield offsets, keylist, start, ds, None
                continue
            try:
                if cm == 2:
                    raw = zlib.decompress(blk[8:])
                elif cm == 0:
                    raw = blk[8:]
                else:
                    yield offsets, keylist, start, ds, None
                    continue
            except Exception:
                yield offsets, keylist, start, ds, None
                continue
            if len(raw) != ds:
                yield offsets, keylist, start, ds, None
                continue
            yield offsets, keylist, start, ds, raw
    assert pos == sum(ds for _cs, ds in pairs), "layout drifted"


def speex_rate(b):
    """Sample rate from an Ogg Speex header page, or None if it is not one.

    Layout: OggS page header (28 B incl. its segment table) followed by
    "Speex   " + 20-byte version string, then version_id / header_size / rate.
    """
    if b[:4] != b"OggS" or b[28:36] != b"Speex   ":
        return None
    return struct.unpack("<I", b[64:68])[0]


def ogg_granule(b):
    """Granule position of the LAST ogg page (= total samples at stream rate)."""
    pos = b.rfind(b"OggS")
    if pos < 0:
        return None
    return struct.unpack("<q", b[pos + 6:pos + 14])[0]


def opus_duration(b):
    """Seconds of audio in an Ogg Opus blob (granulepos is 48 kHz, pre-skip removed)."""
    g = ogg_granule(b)
    if g is None or b[:4] != b"OggS":
        return None
    pre = struct.unpack("<H", b[38:40])[0] if b[27 + b[26]:27 + b[26] + 8] == b"OpusHead" else 0
    return max(g - pre, 0) / 48000.0


def source_duration(b, rate):
    """Length of a Speex/Opus source, in seconds.

    The granule position of the LAST page is wrong for files that hold several
    chained logical streams (some Collins / snd entries pack the word plus a few
    example sentences): the last page's granule then covers only the final chain,
    e.g. 1.2 s for a 9.9 s clip. Counting packets from the Ogg segment table is
    exact regardless of chaining, so prefer it when the header is readable.

    Every Speex packet is `frames_per_packet * frame_size` samples long; each
    chained stream contributes 1 header packet plus `extra_headers` comment
    packets, which are not audio and must be subtracted.
    """
    if b[:4] == b"OggS":
        nseg0 = b[26]
        p0 = 27 + nseg0
        if b[p0:p0 + 8] == b"Speex   ":
            rate0, = struct.unpack("<i", b[p0 + 36:p0 + 40])
            frame_size, = struct.unpack("<i", b[p0 + 56:p0 + 60])
            fpp, = struct.unpack("<i", b[p0 + 64:p0 + 68])
            extra, = struct.unpack("<i", b[p0 + 68:p0 + 72])
            if rate0 > 0 and frame_size > 0 and fpp > 0:
                packets, chains, i = 0, 0, 0
                while True:
                    i = b.find(b"OggS", i)
                    if i < 0:
                        break
                    nseg = b[i + 26]
                    seg = b[i + 27:i + 27 + nseg]
                    packets += sum(1 for s in seg if s < 255)
                    if b[i + 5] & 0x02:                 # BOS page = new chain
                        chains += 1
                    i += 27 + nseg + sum(seg)
                packets -= chains * (1 + max(0, extra))
                if packets > 0:
                    return packets * fpp * frame_size / float(rate0)
    g = ogg_granule(b)
    if g is None or not rate:
        return None
    return g / float(rate)


def decoded_duration(ff, path):
    """Seconds ffmpeg actually decodes out of `path`, or None.

    Used only to double-check the rare file whose header-based estimate and
    transcoded length disagree: decoding is authoritative but costs a process,
    so it is never run on the whole corpus.
    """
    r = subprocess.run([ff, "-hide_banner", "-nostdin", "-i", path,
                        "-f", "null", "-"], capture_output=True, text=True,
                       errors="replace")
    times = re.findall(r"time=(\d+):(\d+):([\d.]+)", r.stderr)
    if not times:
        return None
    h, m, s = times[-1]
    return int(h) * 3600 + int(m) * 60 + float(s)


def pick_bitrate(rate):
    """Match the source's own bandwidth instead of a fixed 16 kbps.

    TLD ships three very different families: 11 kHz narrowband (mw/ids),
    32 kHz ultra-wideband (snd) and 44.1 kHz ultra-wideband (uk/collins).
    A flat 16 kbps + `voip` throws away everything above ~8 kHz, which is
    audible on the two 44.1 kHz sets, so scale with the source rate.
    """
    if not rate or rate >= 32000:
        return "32k", "audio"
    if rate >= 16000:
        return "24k", "audio"
    return "16k", "voip"


def transcode_batch(ff, items, tmpdir, tag):
    """Transcode several spx payloads to opus in ONE ffmpeg process.

    items: list of (name, bytes, words). Returns {name: opus_bytes}.

    Two things here are load bearing:

    * `-map i:a` on every output.  Without it ffmpeg assigns the "best" audio
      stream of ALL inputs to each output, so every file in a batch ends up
      holding the FIRST file's audio.  That is what shipped in the 2026-10-10
      build: rows were present, decodable and distinct in size, but most of them
      played a different word.
    * the duration gate below.  A mis-mapped output always disagrees with its
      source length, so this turns the whole failure mode into a hard error
      instead of a silent one.
    """
    tag = "".join(c if c.isalnum() else "_" for c in str(tag))
    result = {}
    rejected = 0
    for start in range(0, len(items), FFBATCH):
        chunk = items[start:start + FFBATCH]
        got, bad = _transcode_chunk(ff, chunk, tmpdir, f"{tag}_{start}")
        result.update(got)
        rejected += bad
    global REJECTED
    REJECTED += rejected
    return result


def _transcode_chunk(ff, items, tmpdir, tag):
    ins, outs, meta = [], [], []
    for i, item in enumerate(items):
        name, data = item[0], item[1]
        src = os.path.join(tmpdir, f"b{tag}_{i}.spx")
        dst = os.path.join(tmpdir, f"b{tag}_{i}.opus")
        with open(src, "wb") as f:
            f.write(data)
        rate = speex_rate(data)
        kbps, app = pick_bitrate(rate)
        ins += ["-i", src]
        outs += ["-map", f"{i}:a", "-c:a", "libopus", "-b:a", kbps,
                 "-application", app, dst]
        meta.append((name, data, src, dst, rate))

    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error"] + ins + outs
    proc = subprocess.run(cmd, capture_output=True, text=True)

    result = {}
    rejected = 0
    for name, data, src, dst, rate in meta:
        if os.path.exists(dst):
            with open(dst, "rb") as f:
                blob = f.read()
            os.remove(dst)
            want = source_duration(data, rate)
            got = opus_duration(blob)
            if want and got and abs(want - got) > 0.12 + 0.05 * want:
                # The cheap estimate can be off for files whose chains use
                # different frame sizes, so before dropping a file confirm with a
                # decode: if ffmpeg says the source really is `got` seconds long,
                # the transcode is faithful and only the estimate was wrong.
                real = decoded_duration(ff, src)
                if real and abs(real - got) <= 0.12 + 0.05 * real:
                    result[name] = blob
                else:
                    rejected += 1
            else:
                result[name] = blob
        else:
            rejected += 1
        if os.path.exists(src):
            os.remove(src)
    return result, rejected


# ------------------------------------------------------------------- stage 1
def build_index(mdx_path, cache_path=None):
    """word -> [audio file names] from the MDX entries' own audio references.

    Parsing 4.36 M records costs 60-90 s, which dominates a short smoke test, so
    the result is cached next to the output and reused when the mdx is unchanged.
    """
    from mdict_utils.reader import MDX
    if cache_path and os.path.exists(cache_path):
        stamp = os.path.getmtime(cache_path)
        if stamp >= os.path.getmtime(mdx_path):
            import pickle
            with open(cache_path, "rb") as f:
                wf, seen, n = pickle.load(f)
            print(f"      (index cache hit: {len(wf):,} words)")
            return wf, seen, n
    AUDIO_SRC = re.compile(
        r'(?:src|href)\s*=\s*["\']([^"\']+\.(?:mp3|spx|ogg|wav|m4a))["\']', re.I)
    word_files = defaultdict(list)
    seen_files = set()
    n = 0
    for key, val in MDX(mdx_path).items():
        n += 1
        k = key.decode("utf-8", "replace") if isinstance(key, bytes) else str(k)
        b = val if isinstance(val, bytes) else str(val).encode()
        txt = b.decode("utf-8", "replace")
        for m in AUDIO_SRC.finditer(txt):
            base = os.path.basename(m.group(1).replace("\\", "/"))
            ext = os.path.splitext(base)[1].lower()
            if ext not in AUDIO_EXT:
                continue
            word_files[k].append(base)
            seen_files.add(base.casefold())
    if cache_path:
        import pickle
        with open(cache_path, "wb") as f:
            pickle.dump((word_files, seen_files, n), f, protocol=4)
    return word_files, seen_files, n


# ---------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tld", default=r"C:\workspace\ldoce\The little dict")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default=None,
                    help="process a single .mdd file (for a smoke test)")
    ap.add_argument("--from", dest="start_from", default=None,
                    help="start at this .mdd and continue with the rest "
                         "(resume an interrupted run)")
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after N inserted rows")
    ap.add_argument("--keep-spx", action="store_true",
                    help="store spx as-is instead of transcoding (debug)")
    ap.add_argument("--ffmpeg", default=None,
                    help="path to ffmpeg.exe (default: imageio-ffmpeg's bundled build)")
    ap.add_argument("--missing-only", action="store_true",
                    help="skip files whose stem is already in the target db for this "
                         "source -- used to top up files a stricter gate rejected")
    ap.add_argument("--blacklist", default=os.path.join(
                        os.path.dirname(os.path.abspath(__file__)), "bad_clips.tsv"),
                    help="TSV of (source, file, expression) rows whose recording does "
                         "not match the headword; skipped on insert")
    args = ap.parse_args()

    global BAD
    BAD = load_blacklist(args.blacklist) if args.blacklist else set()
    if BAD:
        print(f"      blacklist: {len(BAD)} (source, file, expression) row(s) skipped")

    mdx = os.path.join(args.tld, "TLD.mdx")
    cache = os.path.join(os.path.dirname(os.path.abspath(args.out)) or ".",
                         "_tld_audio_index.pickle")
    print(f"[1/4] parsing {mdx} for word -> audio ...")
    word_files, seen_files, n_rec = build_index(mdx, cache)
    n_pairs = sum(len(v) for v in word_files.values())
    print(f"      {n_rec:,} records, {len(word_files):,} words, "
          f"{n_pairs:,} word->file pairs, {len(seen_files):,} distinct files")

    # reverse index: file -> [words]
    file_words = defaultdict(list)
    for w, fs in word_files.items():
        for f in fs:
            file_words[f.casefold()].append(w)
    print(f"      reverse index: {len(file_words):,} files with >=1 word")

    mdds = sorted(n for n in os.listdir(args.tld) if n.endswith(".mdd"))
    if args.only:
        mdds = [n for n in mdds if n == args.only or n == args.only + ".mdd"]
    if args.start_from:
        want = args.start_from if args.start_from.endswith(".mdd") else args.start_from + ".mdd"
        if want in mdds:
            mdds = mdds[mdds.index(want):]
        else:
            raise SystemExit(f"--from {args.start_from}: not one of {mdds}")
    print(f"[2/4] {len(mdds)} .mdd file(s): {mdds}")

    ff = None
    if not args.keep_spx:
        if args.ffmpeg:
            ff = args.ffmpeg
        else:
            try:
                ff = ffmpeg()
            except ImportError:
                ff = None
                print("      NOTE: imageio-ffmpeg not installed -- .spx will be skipped")
                print("            (mp3-only sources such as TLD.1.mdd are unaffected)")
    tmpdir = tempfile.mkdtemp(prefix="tldaud_")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    con = sqlite3.connect(args.out, timeout=120)
    # WAL lets a reader (a progress probe, an audit) coexist with this writer.
    # The first full run died with "database is locked" precisely because a
    # read-only probe was made against the live database in rollback-journal
    # mode, which blocks the writer's commit.
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(SCHEMA)
    con.commit()

    inserted = 0
    skipped_no_word = 0
    transcode_fail = 0
    bad_payload = 0
    bad_blocks = 0
    lost_keys = 0
    blacklisted = 0
    try:
        for name in mdds:
            path = os.path.join(args.tld, name)
            print(f"[3/4] {name} ...", flush=True)
            base_words = 0
            pending = []          # spx payloads awaiting a batched transcode
            src = MDD_SOURCES.get(name, "tld_" + os.path.splitext(name)[0].lower())
            print(f"      source tag: {src}", flush=True)
            have = set()
            if args.missing_only:
                have = {os.path.splitext(f)[0].casefold()
                        for f, in con.execute("select file from entries where source=?",
                                              (src,))}
                print(f"      {len(have):,} files already present, topping up the rest",
                      flush=True)
            for offsets, keylist, base, size, raw in blocks_of(path):
                # records in this block are exactly the keys whose offset lies in
                # [base, base+size). `base` comes from the size table, so it stays
                # correct even when this block cannot be decoded.
                lo = bisect.bisect_left(offsets, base)
                hi = bisect.bisect_left(offsets, base + size)
                if raw is None:
                    bad_blocks += 1
                    lost_keys += hi - lo
                    continue
                for idx in range(lo, hi):
                    k = keylist[idx][1]
                    kk = k.decode("utf-8", "replace") if isinstance(k, bytes) else str(k)
                    b = os.path.basename(kk.replace("\\", "/"))
                    words = file_words.get(b.casefold())
                    if not words:
                        continue
                    if BAD:
                        kept = [w for w in words if (src, w, b) not in BAD]
                        if not kept:
                            blacklisted += 1
                            continue
                        words = kept
                    if have and os.path.splitext(b)[0].casefold() in have:
                        continue
                    rel = offsets[idx] - base
                    end = offsets[idx + 1] - base if idx + 1 < len(offsets) else len(raw)
                    payload = raw[max(0, rel):min(end, len(raw))]
                    if not payload:
                        skipped_no_word += 1
                        continue
                    ext = os.path.splitext(b)[1].lower()
                    if ext == ".spx" and not ff:
                        # no transcoder available: better to drop the file than to
                        # store Speex bytes Hoshi's LIKE filter would never find
                        skipped_no_word += 1
                        continue
                    if ext == ".spx" and ff:
                        # queue it; the whole block is transcoded in one ffmpeg
                        # process after the block's records are collected
                        pending.append((b, payload, words))
                    else:
                        fname = b
                        if not looks_audio(payload):
                            # Never store bytes a player cannot decode. This is the
                            # gate that turns the old failure mode (70% of a source
                            # silently unplayable) into a build-time count.
                            bad_payload += 1
                            continue
                        for w in words:
                            con.execute(
                                "INSERT INTO entries (expression, reading, source, "
                                "speaker, display, file) VALUES (?,?,?,?,?,?)",
                                # speaker/display are NULL, not '': the existing
                                # merged db encodes LDOCE rows as NULL and OALD10
                                # rows as 'UK'/'US' + 'US: /er/'. TLD's 7 sources
                                # are different dictionaries (Collins, mw, numeric
                                # ids), not a UK/US pair, so labelling them UK/US
                                # would mislead -- the source name is the
                                # distinction, matching the LDOCE convention.
                                (w, None, src, None, None, fname))
                            con.execute(
                                "INSERT INTO android (file, source, data) VALUES (?,?,?)",
                                (fname, src, sqlite3.Binary(payload)))
                            inserted += 1
                        base_words += 1
                    if args.limit and inserted >= args.limit:
                        raise StopIteration
                # flush the transcode queue once per block: batching amortises
                # ffmpeg's startup cost, which is 94% of the runtime
                if pending:
                    got = transcode_batch(ff, pending, tmpdir, f"{name}:{base}")
                    for pbase, _payload, pwords in pending:
                        data = got.get(pbase)
                        if data is None:
                            transcode_fail += 1
                            continue
                        if not looks_audio(data):
                            bad_payload += 1
                            continue
                        fname = pbase[:-4] + ".opus"
                        for w in pwords:
                            con.execute(
                                "INSERT INTO entries (expression, reading, source, "
                                "speaker, display, file) VALUES (?,?,?,?,?,?)",
                                # speaker/display are NULL, not '': the existing
                                # merged db encodes LDOCE rows as NULL and OALD10
                                # rows as 'UK'/'US' + 'US: /er/'. TLD's 7 sources
                                # are different dictionaries (Collins, mw, numeric
                                # ids), not a UK/US pair, so labelling them UK/US
                                # would mislead -- the source name is the
                                # distinction, matching the LDOCE convention.
                                (w, None, src, None, None, fname))
                            con.execute(
                                "INSERT INTO android (file, source, data) VALUES (?,?,?)",
                                (fname, src, sqlite3.Binary(data)))
                            inserted += 1
                        base_words += 1
                    pending = []
                    con.commit()
                    if args.limit and inserted >= args.limit:
                        raise StopIteration
            con.commit()
            print(f"      {name}: {base_words:,} files matched", flush=True)
            if args.limit and inserted >= args.limit:
                break
    except StopIteration:
        pass
    finally:
        con.commit()
        con.close()

    print()
    print(f"[4/4] inserted {inserted:,} rows into {args.out}")
    print(f"      skipped (no word maps to the file): {skipped_no_word:,}")
    print(f"      transcode failures                : {transcode_fail:,}")
    if BAD:
        print(f"      blacklisted (audio != headword)   : {blacklisted:,}")
    print(f"      duration-gate rejects             : {REJECTED:,}")
    print(f"      undecodable blocks                : {bad_blocks:,}"
          f"  (keys lost: {lost_keys:,})")
    print(f"      payloads rejected (not audio)     : {bad_payload:,}")
    print(f"      db size: {os.path.getsize(args.out):,} B")
    if bad_payload:
        raise SystemExit("REFUSED: some payloads are not audio -- see counts above")


if __name__ == "__main__":
    main()

