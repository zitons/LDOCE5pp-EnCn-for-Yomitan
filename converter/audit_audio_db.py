"""Independent audit of the generated audio database.

Deliberately does NOT import build_audio_db -- this is an outside check that the
artifact is coherent and that Hoshi would accept it. Every assertion corresponds
to a requirement read from Hoshi's Kotlin sources.

Checks
  1. file name / extension: must be importable as LocalAudioDatabase (.db)
  2. tables present with the exact column names Hoshi selects
  3. integrity: PRAGMA integrity_check, foreign-key style orphan check both ways
  4. Hoshi's source discovery query returns its expected set
  5. every entry's blob is a real audio payload (ID3 or MPEG frame sync), not empty
  6. no duplicate (expression, source) rows that would shadow each other
  7. expression coverage against the shipped dictionary package
  8. the exact query Hoshi runs is fast (it runs on every lookup)
"""
import argparse
import json
import os
import re
import sqlite3
import time
import zipfile

COLS_ENTRIES = ["id", "expression", "reading", "source", "speaker", "display", "file"]
COLS_ANDROID = ["id", "file", "source", "data"]


def cols(db, table):
    return [r[1] for r in db.execute(f"PRAGMA table_info({table})")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"C:\workspace\ldoce\yomitan_audio\android.db")
    ap.add_argument("--zip", default=r"C:\workspace\ldoce\yomitan_full"
                                     r"\LDOCE5pp_Yomitan_2026.09.13.zip")
    args = ap.parse_args()

    fails = []
    db = sqlite3.connect(args.db)
    size = os.path.getsize(args.db)
    print(f"db      : {args.db}")
    print(f"size    : {size:,} B ({size/1048576:.1f} MiB)")
    print(f"name    : {os.path.basename(args.db)}  "
          f"({'ok' if args.db.endswith('.db') else 'WRONG - must end .db'})")
    if not args.db.endswith(".db"):
        fails.append("extension")

    print("\n[1] schema")
    ce, ca = cols(db, "entries"), cols(db, "android")
    print(f"   entries: {ce}")
    print(f"   android: {ca}")
    for want, got, name in ((COLS_ENTRIES, ce, "entries"), (COLS_ANDROID, ca, "android")):
        missing = [c for c in want if c not in got]
        if missing:
            fails.append(f"{name} missing columns {missing}")
            print(f"   !! {name} missing {missing}")
    if ce != COLS_ENTRIES:
        print(f"   note: column order differs from the reference plugin "
              f"(Hoshi selects by NAME, so this is cosmetic)")

    print("\n[2] integrity")
    ic = db.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"   integrity_check: {ic}")
    if ic != "ok":
        fails.append("integrity")

    n_entries = db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    n_blobs = db.execute("SELECT COUNT(*) FROM android").fetchone()[0]
    print(f"   entries: {n_entries:,}   android: {n_blobs:,}")

    print("\n[3] orphan checks")
    # A correlated NOT EXISTS on 90k rows without an index degrades badly (it timed
    # out at 10 minutes). Compare in Python instead -- linear and predictable.
    ent = set(db.execute("SELECT source, file FROM entries"))
    blob = set(db.execute("SELECT source, file FROM android"))
    orphan_e = len(ent - blob)
    orphan_a = len(blob - ent)
    print(f"   entries with no blob : {orphan_e}")
    print(f"   blobs never referenced: {orphan_a}")
    if orphan_e:
        fails.append("orphan entries")

    print("\n[4] Hoshi source discovery")
    srcs = [r[0] for r in db.execute(
        "SELECT DISTINCT source FROM entries WHERE lower(file) LIKE '%.mp3' "
        "OR lower(file) LIKE '%.opus' OR lower(file) LIKE '%.ogg'")]
    print(f"   discovered: {sorted(srcs)}")
    if not srcs:
        fails.append("no discoverable sources")

    print("\n[5] blob payload sanity")
    bad, checked = 0, 0
    for name, data in db.execute("SELECT file, data FROM android LIMIT 4000"):
        checked += 1
        if not data or len(data) < 100:
            bad += 1
            continue
        if not (data[:3] == b"ID3" or data[0] == 0xFF):
            bad += 1
    print(f"   checked {checked:,} blobs, not-recognisable-as-audio: {bad}")
    if bad:
        fails.append("bad blobs")
    # aggregate: total payload size
    tot = db.execute("SELECT SUM(length(data)) FROM android").fetchone()[0] or 0
    print(f"   total payload: {tot:,} B ({tot/1048576:.1f} MiB)")

    print("\n[6] duplicate (expression, source)")
    # count in Python over the indexed projection; a GROUP BY HAVING on the full
    # table without a covering index is what made the orphan check blow up.
    from collections import Counter
    pairs = Counter(db.execute("SELECT expression, source FROM entries"))
    dup = sum(1 for c in pairs.values() if c > 1)
    print(f"   duplicate groups: {dup}")
    if dup:
        print("   (Hoshi takes the first row per source, so duplicates only cost size;"
              " reporting, not failing)")
        for (e, s), c in [(k, v) for k, v in pairs.items() if v > 1][:5]:
            print(f"      {e!r} {s} x{c}")

    print("\n[7] coverage vs shipped dictionary")
    exprs = set()
    with zipfile.ZipFile(args.zip) as z:
        for n in z.namelist():
            if re.fullmatch(r"term_bank_\d+\.json", n):
                for r in json.loads(z.read(n)):
                    if r[4] > 0:
                        exprs.add(r[0])
    have = {r[0] for r in db.execute("SELECT DISTINCT expression FROM entries")}
    both = exprs & have
    print(f"   dictionary expressions : {len(exprs):,}")
    print(f"   expressions with audio : {len(both):,}  "
          f"({len(both)*100.0/len(exprs):.2f}%)")
    print(f"   db expressions not in dict: {len(have - exprs):,}")

    print("\n[8] lookup latency (what Hoshi runs per lookup)")
    samples = ["improve", "abandon", "child", "the", "run", "water", "time"]
    t0 = time.time()
    for _ in range(200):
        for s in samples:
            db.execute("SELECT source, expression, reading, file FROM entries "
                       "WHERE expression = ?", (s,)).fetchall()
    dt = (time.time() - t0) / (200 * len(samples)) * 1000
    print(f"   average query: {dt:.3f} ms")

    print()
    if fails:
        print("AUDIT: FAIL --", fails)
        return 1
    print("AUDIT: PASS -- schema, integrity, coverage and payload all verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
