"""Merge audio databases into one Hoshi-compatible `android.db` with multiple sources.

Both inputs use the same two-table shape Hoshi expects (entries / android), but
encode the accent differently:

    LDOCE5 (built by build_audio_db.py)
        source='ldoce_ame' | 'ldoce_bre'      speaker=NULL
    OALD10 (third-party, local_audio_*.db)
        source='oald10'                        speaker='UK' | 'US'

Option A (chosen): keep each producer's own source naming untouched. Nothing in
the third-party rows is rewritten, so any other consumer that reads `source` or
`speaker` keeps working. Hoshi groups by `source`, so its picker will show
ldoce_ame / ldoce_bre / oald10, and `speaker` still records UK vs US per row.

Measured before writing (converter/_merge_probe.py):
    (source, file) intersection between the two dbs : 0
    filenames present in both                        : 0
    non-conforming extensions (mp3/opus/ogg)         : 0
so this is a pure append -- no row can shadow another.

What it does
  1. copies the first db (schema + rows)
  2. ATTACHes each remaining db and appends its two tables verbatim
  3. drops entry rows whose blob is missing (both inputs have a few), so Hoshi
     can never match a word and then fail to produce audio
  4. rebuilds indexes, prunes, VACUUMs
  5. re-runs the integrity invariants itself and refuses to finish otherwise

Usage
    python converter/merge_audio_db.py \
        --db  yomitan_audio/android.db \
        --db  local_audio_1783304412795.db \
        --out yomitan_audio/android_merged.db
"""
import argparse
import os
import sqlite3
import sys
import time

SCHEMA = """
CREATE TABLE entries (
    id integer PRIMARY KEY NOT NULL,
    expression text NOT NULL,
    reading text,
    source text NOT NULL,
    speaker text,
    display text,
    file text NOT NULL
);
CREATE TABLE android (
    id integer PRIMARY KEY NOT NULL,
    file text NOT NULL,
    source text NOT NULL,
    data blob NOT NULL
);
"""

INDEXES = [
    "CREATE INDEX idx_expr_reading ON entries(expression, reading)",
    "CREATE INDEX idx_expr_source  ON entries(expression, reading, source)",
    "CREATE INDEX idx_reading      ON entries(reading)",
    "CREATE INDEX idx_speaker      ON entries(speaker)",
    "CREATE INDEX idx_android_fs   ON android(file, source)",
    "CREATE INDEX idx_android_src  ON android(source)",
]


def table_names(conn):
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def preflight(paths):
    """Verify the inputs are mergeable before writing anything."""
    print("[1/6] preflight on", len(paths), "input(s)", flush=True)
    pairs = {}
    names = {}
    for p in paths:
        if not os.path.isfile(p):
            raise SystemExit(f"missing input: {p}")
        db = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        have = table_names(db)
        for need in ("entries", "android"):
            if need not in have:
                raise SystemExit(f"{p}: no '{need}' table")
        ent = db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        blob = db.execute("SELECT COUNT(*) FROM android").fetchone()[0]
        srcs = [r[0] for r in db.execute("SELECT DISTINCT source FROM entries")]
        bad = db.execute(
            "SELECT COUNT(*) FROM entries WHERE NOT ("
            "lower(file) LIKE '%.mp3' OR lower(file) LIKE '%.opus' "
            "OR lower(file) LIKE '%.ogg')").fetchone()[0]
        pc = set(db.execute("SELECT DISTINCT source, file FROM android"))
        fn = {f for _s, f in pc}
        print(f"   {os.path.basename(p):34} entries {ent:>8,}  blobs {blob:>8,}  "
              f"sources={srcs}  bad_ext={bad}  size={os.path.getsize(p)/1048576:.1f} MiB")
        if bad:
            raise SystemExit(f"{p}: {bad} rows use an extension Hoshi cannot serve")
        pairs[p] = pc
        names[p] = fn
        db.close()

    # collisions between inputs
    keys = list(pairs)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            inter = pairs[a] & pairs[b]
            same = names[a] & names[b]
            print(f"   collision {os.path.basename(a)} x {os.path.basename(b)}: "
                  f"(source,file)={len(inter)}  filename={len(same)}")
            if inter:
                raise SystemExit("input databases collide on (source, file); "
                                 "appending would shadow audio")
    return True


def merge(paths, out_path):
    preflight(paths)
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + ".part"
    for f in (tmp, tmp + "-journal", tmp + "-wal", tmp + "-shm"):
        if os.path.exists(f):
            os.remove(f)

    t0 = time.time()
    print(f"\n[2/6] creating {os.path.basename(out_path)} from the first input", flush=True)
    conn = sqlite3.connect(tmp)
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("ATTACH DATABASE ? AS src", (paths[0],))
    conn.execute("INSERT INTO entries (expression, reading, source, speaker, display, file)"
                 " SELECT expression, reading, source, speaker, display, file FROM src.entries")
    conn.execute("INSERT INTO android (file, source, data)"
                 " SELECT file, source, data FROM src.android")
    conn.commit()
    conn.execute("DETACH DATABASE src")
    print(f"   rows now: entries {conn.execute('SELECT COUNT(*) FROM entries').fetchone()[0]:,}"
          f"  android {conn.execute('SELECT COUNT(*) FROM android').fetchone()[0]:,}",
          flush=True)

    for i, p in enumerate(paths[1:], start=1):
        print(f"[3/6] appending {os.path.basename(p)}", flush=True)
        conn.execute("ATTACH DATABASE ? AS src", (p,))
        before = conn.execute("SELECT COUNT(*) FROM android").fetchone()[0]
        conn.execute("INSERT INTO entries (expression, reading, source, speaker, display, file)"
                     " SELECT expression, reading, source, speaker, display, file FROM src.entries")
        conn.execute("INSERT INTO android (file, source, data)"
                     " SELECT file, source, data FROM src.android")
        conn.commit()
        conn.execute("DETACH DATABASE src")
        after = conn.execute("SELECT COUNT(*) FROM android").fetchone()[0]
        print(f"   added {after-before:,} blobs  (total {after:,})  "
              f"{time.time()-t0:.0f}s", flush=True)

    print("[4/6] dropping entry rows with no blob", flush=True)
    # An entry without a blob makes Hoshi match a word and then fail to play it.
    # Both inputs contain a few of these (LDOCE5: 8 rows referenced files absent
    # from the mdd; OALD10: 661). Compare in Python -- a correlated NOT EXISTS on
    # 200k+ rows is needlessly slow.
    ent_pairs = set(conn.execute("SELECT source, file FROM entries"))
    blob_pairs = set(conn.execute("SELECT source, file FROM android"))
    orphan = ent_pairs - blob_pairs
    dropped = 0
    if orphan:
        conn.executemany("DELETE FROM entries WHERE source=? AND file=?",
                         [(s, f) for s, f in orphan])
        dropped = len(orphan)
        conn.commit()
    print(f"   removed {dropped:,} orphan entry pair(s)", flush=True)

    print("[5/6] indexes + vacuum", flush=True)
    for sql in INDEXES:
        conn.execute(sql)
    conn.commit()
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("VACUUM")
    conn.commit()

    print("[6/6] final invariants", flush=True)
    ent_pairs = set(conn.execute("SELECT source, file FROM entries"))
    blob_pairs = set(conn.execute("SELECT source, file FROM android"))
    left = len(ent_pairs - blob_pairs)
    sources = [r[0] for r in conn.execute("SELECT DISTINCT source FROM entries")]
    payload = conn.execute("SELECT SUM(length(data)) FROM android").fetchone()[0] or 0
    ent = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    blob = conn.execute("SELECT COUNT(*) FROM android").fetchone()[0]
    ic = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()

    os.replace(tmp, out_path)
    size = os.path.getsize(out_path)
    print(f"\n   written : {out_path}")
    print(f"   size    : {size:,} B ({size/1048576:.1f} MiB)")
    print(f"   entries : {ent:,}   blobs: {blob:,}   payload: {payload/1048576:.1f} MiB")
    print(f"   sources : {sorted(sources)}")
    print(f"   integrity_check: {ic}   orphans: {left}   elapsed: {time.time()-t0:.0f}s")

    if ic != "ok" or left:
        raise SystemExit("merged db failed its own invariants")
    return {"path": out_path, "size": size, "entries": ent, "blobs": blob,
            "payload": payload, "sources": sorted(sources), "dropped": dropped}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", action="append", required=True,
                    help="input db, repeatable; the first one seeds the output")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    merge(args.db, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
