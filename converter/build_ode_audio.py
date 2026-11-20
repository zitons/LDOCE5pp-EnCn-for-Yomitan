"""Build the Oxford Dictionary of English 2024 (opus) source into the Hoshi db.

Why this source exists
----------------------
The TLD (The little dict) packs are seven different dictionaries glued together,
and some of their clips are mislabelled at the source: TLD.6.mdd ships
`ukl30144.mp3` as the "four" pronunciation, but the actual recording says
"four by four". Nothing in the mdd lets you detect that -- only listening does.
ODE 2024 is a single dictionary whose audio the user already trusts, and its
clips are already Opus, so importing it costs one pass and no transcoding.

What it does
------------
1. Parse the .mdx and keep only audio refs that belong to the entry itself.
   An entry page also links the audio of neighbouring entries ("improve" links
   improver / improvable / improvability), and importing those under the entry
   makes the same word play a *different* word's clip -- the exact bug the TLD
   packs show. The ref's word part must normalise to the headword.
2. Stream the .1.mdd, match keys by stem, keep payloads that look like audio.
3. Insert `entries` + `android` rows under one source, speaker UK/US.

Usage
-----
    venv/Scripts/python.exe converter/build_ode_audio.py \
        --ode "C:\\baidunetdiskdownload\\ODE now opus\\2024" \
        --out yomitan_audio/tld.db [--limit N] [--dry-run]
"""
import argparse
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_tld_audio_db as B

SOURCE = "ode2024"
AUDIO_SRC = re.compile(
    r'(?:src|href)\s*=\s*["\']([^"\']+\.(?:opus|mp3|spx|ogg|wav|m4a))["\']', re.I)
# four_gb_3 / 2_0_us_1 / four_gb_3_abbr / water_us_1_rr, and the very common
# 3d_printer_1_gb_1 form that carries an entry index before the accent
STEM_RE = re.compile(r"^(?P<base>.+)_(?P<acc>gb|us)_(?P<n>\d+)(?:_(?P<tag>abbr|rr))?$")
HOMO_RE = re.compile(r"^(?P<w>.+)_\d+$")
NONWORD = re.compile(r"[^a-z0-9]+")


def norm(s):
    """'four by four' / 'four-by-four' / 'four_by_four' -> 'four_by_four'."""
    return NONWORD.sub("_", s.lower()).strip("_")


def canon(stem):
    """'four__gb_3' and 'four_gb_3' are the same clip; collapse the underscore run."""
    return re.sub(r"_+", "_", stem)


def split_key(stem):
    """-> (candidate headwords, 'UK'|'US') or None.

    The pack puts an entry index before the accent for many words
    (`3d_printer_1_gb_1`) and omits it for others (`improve_gb_1`), so both
    readings are offered and the caller keeps the stem if either one is the
    headword that referenced it.
    """
    m = STEM_RE.match(stem)
    if not m:
        return None
    base = m.group("base")
    forms = {norm(base)}
    homo = HOMO_RE.match(base)
    if homo:
        forms.add(norm(homo.group("w")))
    forms.discard("")
    return forms, ("UK" if m.group("acc") == "gb" else "US")


def build_index(mdx_path):
    """headword -> set of clip stems that the entry itself names."""
    from mdict_utils.reader import MDX
    word_files = {}
    kept = dropped = 0
    for key, val in MDX(mdx_path).items():
        w = key.decode("utf-8", "replace") if isinstance(key, bytes) else str(key)
        hw = norm(w)
        if not hw:
            continue
        txt = val.decode("utf-8", "replace") if isinstance(val, bytes) else str(val)
        stems = {os.path.splitext(os.path.basename(u.replace("\\", "/")))[0]
                 for u in AUDIO_SRC.findall(txt)}
        mine = set()
        for s in stems:
            c = canon(s)
            parts = split_key(c)
            if parts is None:
                continue
            if hw in parts[0]:
                mine.add(c)
                kept += 1
            else:
                dropped += 1
        if mine:
            word_files.setdefault(hw, set()).update(mine)
    return word_files, kept, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ode", default=r"C:\baidunetdiskdownload\ODE now opus\2024")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    mdx = os.path.join(args.ode, "Oxford Dictionary of English 2024.mdx")
    mdd = os.path.join(args.ode, "Oxford Dictionary of English 2024.1.mdd")
    t0 = time.time()
    print(f"[1/3] indexing {os.path.basename(mdx)} ...", flush=True)
    word_files, kept, dropped = build_index(mdx)
    print(f"      {len(word_files):,} headwords, {kept:,} own-clip refs kept, "
          f"{dropped:,} refs dropped as another entry's audio "
          f"({time.time() - t0:.0f}s)", flush=True)
    stem_words = {}
    for w, stems in word_files.items():
        for s in stems:
            stem_words.setdefault(s, []).append(w)
    print(f"      {len(stem_words):,} distinct clips to look for")

    con = sqlite3.connect(args.out, timeout=120)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    if not args.dry_run:
        con.executescript(B.SCHEMA)
        n_old = con.execute("select count(*) from entries where source=?",
                            (SOURCE,)).fetchone()[0]
        con.execute("DELETE FROM entries WHERE source=?", (SOURCE,))
        con.execute("DELETE FROM android WHERE source=?", (SOURCE,))
        con.commit()
        print(f"      cleared previous {SOURCE} rows ({n_old:,} entries)", flush=True)

    found = 0
    inserted = 0
    bad = 0
    missing = 0
    t1 = time.time()
    print("[2/3] streaming the .mdd ...", flush=True)
    seen_stems = set()
    pending = []
    for offsets, keylist, base, size, raw in B.blocks_of(mdd):
        if args.limit and inserted >= args.limit:
            break
        if raw is None:
            continue
        lo = B.bisect.bisect_left(offsets, base)
        hi = B.bisect.bisect_left(offsets, base + size)
        for idx in range(lo, hi):
            k = keylist[idx][1]
            kk = k.decode("utf-8", "replace") if isinstance(k, bytes) else str(k)
            fname = os.path.basename(kk.replace("\\", "/"))
            stem = canon(os.path.splitext(fname)[0])
            words = stem_words.get(stem)
            if not words or stem in seen_stems:
                continue
            seen_stems.add(stem)
            rel = offsets[idx] - base
            end = offsets[idx + 1] - base if idx + 1 < len(offsets) else len(raw)
            payload = raw[max(0, rel):min(end, len(raw))]
            if not B.looks_audio(payload):
                bad += 1
                continue
            parts = split_key(stem)
            speaker = parts[1] if parts else None
            if args.dry_run:
                inserted += len(words)
            else:
                for w in words:
                    con.execute(
                        "INSERT INTO entries (expression, reading, source, speaker, "
                        "display, file) VALUES (?,?,?,?,?,?)",
                        (w, None, SOURCE, speaker, None, fname))
                    con.execute(
                        "INSERT INTO android (file, source, data) VALUES (?,?,?)",
                        (fname, SOURCE, sqlite3.Binary(payload)))
                    inserted += 1
            found += 1
        if seen_stems and not args.dry_run and found % 20000 < 200:
            con.commit()
            print(f"      {found:,} clips / {inserted:,} rows "
                  f"({time.time() - t1:.0f}s)", flush=True)
    missing = len(set(stem_words) - seen_stems)
    con.commit()
    if args.dry_run:
        con.rollback()
    print()
    print(f"[3/3] clips written      : {found:,}")
    print(f"      entries rows        : {inserted:,}")
    print(f"      indexed but absent  : {missing:,} (mdd has no such key)")
    print(f"      payload rejected    : {bad:,} (not audio)")
    print(f"      db size             : {os.path.getsize(args.out):,} B")
    con.close()
    if bad:
        raise SystemExit("REFUSED: some payloads are not audio")


if __name__ == "__main__":
    main()
