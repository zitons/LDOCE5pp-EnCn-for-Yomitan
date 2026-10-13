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

# One source tag per .mdd, because they are different origins, not one library:
#   TLD.1  ameProns\*.mp3            American pronunciations
#   TLD.2  media\english\uk_pron\*   British pronunciations
#   TLD.3  COLmp3*.spx               Collins pronunciation library
#   TLD.4  mw_*.spx                  Merriam-Webster style headword clips
#   TLD.5  <numeric>.spx             unnamed ids
#   TLD.6  uk_pron\ca2uk*.mp3        a second British set
#   TLD    snd*.spx                  the default/sound set
# The existing merged DB uses the same convention (ldoce_ame / ldoce_bre / oald10),
# so a per-origin tag is what the merge tool and the audits expect.
MDD_SOURCES = {
    "TLD.1.mdd": "tld_ame",
    "TLD.2.mdd": "tld_uk",
    "TLD.3.mdd": "tld_collins",
    "TLD.4.mdd": "tld_mw",
    "TLD.5.mdd": "tld_ids",
    "TLD.6.mdd": "tld_uk2",
    "TLD.mdd": "tld_snd",
}

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
    with open(path, "rb") as f:
        for i, (cs, ds) in enumerate(pairs):
            f.seek(starts[i])
            blk = f.read(cs)
            if len(blk) != cs:
                continue
            info2 = struct.unpack("<L", blk[:4])[0]
            cm, em = info2 & 0xf, (info2 >> 4) & 0xf
            if em:
                continue
            try:
                raw = zlib.decompress(blk[8:]) if cm == 2 else blk[8:]
            except Exception:
                continue
            yield offsets, keylist, raw


def transcode_batch(ff, items, tmpdir, tag):
    """Transcode several spx payloads to opus in ONE ffmpeg process.

    Measured: 400 rows took 2 s without transcoding and 37 s with it, i.e. ~94%
    of the cost is per-file process startup (~50 ms each on Windows). At that rate
    824k files would need ~20 h purely in fork/exec. Passing N inputs and N
    outputs to a single ffmpeg amortises the startup N-fold.

    items: list of (name, bytes, words). Returns {name: opus_bytes}.
    """
    ins, outs = [], []
    for i, item in enumerate(items):
        name, data = item[0], item[1]
        src = os.path.join(tmpdir, f"b{tag}_{i}.in")
        dst = os.path.join(tmpdir, f"b{tag}_{i}.opus")
        with open(src, "wb") as f:
            f.write(data)
        ins.extend(["-i", src])
        outs.extend(["-c:a", "libopus", "-b:a", OPUS_BITRATE,
                     "-application", OPUS_APP, dst])
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error"] + ins + outs
    r = subprocess.run(cmd, capture_output=True, text=True)
    result = {}
    for i, item in enumerate(items):
        name = item[0]
        dst = os.path.join(tmpdir, f"b{tag}_{i}.opus")
        if os.path.exists(dst):
            with open(dst, "rb") as f:
                result[name] = f.read()
            os.remove(dst)
        src = os.path.join(tmpdir, f"b{tag}_{i}.in")
        if os.path.exists(src):
            os.remove(src)
    return result


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
    args = ap.parse_args()

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

    ff = None if args.keep_spx else ffmpeg()
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
    try:
        for name in mdds:
            path = os.path.join(args.tld, name)
            print(f"[3/4] {name} ...", flush=True)
            base_words = 0
            base = 0
            pending = []          # spx payloads awaiting a batched transcode
            src = MDD_SOURCES.get(name, "tld_" + os.path.splitext(name)[0].lower())
            print(f"      source tag: {src}", flush=True)
            for offsets, keylist, raw in blocks_of(path):
                # records in this block are exactly the keys whose offset lies in
                # [base, base+len(raw)) -- bisect instead of scanning all keys
                lo = bisect.bisect_left(offsets, base)
                hi = bisect.bisect_left(offsets, base + len(raw))
                for idx in range(lo, hi):
                    k = keylist[idx][1]
                    kk = k.decode("utf-8", "replace") if isinstance(k, bytes) else str(k)
                    b = os.path.basename(kk.replace("\\", "/"))
                    words = file_words.get(b.casefold())
                    if not words:
                        continue
                    rel = offsets[idx] - base
                    end = offsets[idx + 1] - base if idx + 1 < len(offsets) else len(raw)
                    payload = raw[max(0, rel):min(end, len(raw))]
                    if not payload:
                        skipped_no_word += 1
                        continue
                    ext = os.path.splitext(b)[1].lower()
                    if ext == ".spx" and ff:
                        # queue it; the whole block is transcoded in one ffmpeg
                        # process after the block's records are collected
                        pending.append((b, payload, words))
                    else:
                        fname = b
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
                base += len(raw)
                # flush the transcode queue once per block: batching amortises
                # ffmpeg's startup cost, which is 94% of the runtime
                if pending:
                    got = transcode_batch(ff, pending, tmpdir, f"{name}:{base}")
                    for pbase, _payload, pwords in pending:
                        data = got.get(pbase)
                        if data is None:
                            transcode_fail += 1
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
    print(f"      db size: {os.path.getsize(args.out):,} B")


if __name__ == "__main__":
    main()

