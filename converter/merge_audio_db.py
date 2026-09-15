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
  1. creates a fresh database with THIS module's fixed schema and indexes
     (it does NOT copy any input's schema, and no input is privileged -- every
     input, including the first, is attached and appended)
  2. ATTACHes each input and appends its two tables verbatim
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


def column_names(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


# Checked by NAME, not position: a missing column used to surface only at INSERT
# time, by which point the .part file was already half written.
REQUIRED_COLUMNS = {
    "entries": ["expression", "reading", "source", "speaker", "display", "file"],
    "android": ["file", "source", "data"],
}


def preflight(paths):
    """Verify the inputs are mergeable before writing anything.

    Returns [(path, {(source,file)}, {filename})] keyed by POSITION.

    Keying by path was a real bug: passing the same --db twice collapsed the
    collections to a single entry, so the collision loop below never executed and
    the duplicate was appended anyway -- 185,088 entries with 91,559 duplicated
    (source,file) pairs, still reporting integrity ok and exit 0.
    """
    print("[1/6] preflight on", len(paths), "input(s)", flush=True)

    abs_paths = [os.path.abspath(p) for p in paths]
    seen, dupes = set(), []
    for p, ap in zip(paths, abs_paths):
        if ap in seen:
            dupes.append(p)
        seen.add(ap)
    if dupes:
        raise SystemExit(
            f"the same database was passed more than once ({dupes}); merging a "
            f"database with itself duplicates every (source, file) pair and "
            f"breaks the uniqueness Hoshi relies on")

    indexed = []
    for idx, p in enumerate(paths):
        if not os.path.isfile(p):
            raise SystemExit(f"missing input: {p}")
        # read-only, closed on every path including the error ones
        db = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        try:
            have = table_names(db)
            for need, cols in REQUIRED_COLUMNS.items():
                if need not in have:
                    raise SystemExit(f"{p}: no '{need}' table")
                got = column_names(db, need)
                missing = [c for c in cols if c not in got]
                if missing:
                    raise SystemExit(
                        f"{p}: table '{need}' lacks column(s) {missing} "
                        f"(has {got}); writing would fail only at INSERT time, "
                        f"after the .part was created")
            ent = db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            blob = db.execute("SELECT COUNT(*) FROM android").fetchone()[0]
            srcs = [r[0] for r in db.execute("SELECT DISTINCT source FROM entries")]
            bad = db.execute(
                "SELECT COUNT(*) FROM entries WHERE NOT ("
                "lower(file) LIKE '%.mp3' OR lower(file) LIKE '%.opus' "
                "OR lower(file) LIKE '%.ogg')").fetchone()[0]
            pc = set(db.execute("SELECT DISTINCT source, file FROM android"))
            fn = {f for _s, f in pc}
            print(f"   [{idx}] {os.path.basename(p):30} entries {ent:>8,}  "
                  f"blobs {blob:>8,}  sources={srcs}  bad_ext={bad}  "
                  f"size={os.path.getsize(p)/1048576:.1f} MiB")
            if bad:
                raise SystemExit(f"{p}: {bad} rows use an extension Hoshi cannot serve")
            indexed.append((p, pc, fn))
        finally:
            db.close()

    # collisions between inputs -- over positions, so this always runs
    for i in range(len(indexed)):
        for j in range(i + 1, len(indexed)):
            pa, pca, fna = indexed[i]
            pb, pcb, fnb = indexed[j]
            inter = pca & pcb
            same = fna & fnb
            print(f"   collision [{i}]x[{j}] {os.path.basename(pa)} x "
                  f"{os.path.basename(pb)}: (source,file)={len(inter)}  "
                  f"filename={len(same)}")
            if inter:
                raise SystemExit("input databases collide on (source, file); "
                                 "appending would shadow audio")
    assert indexed, "preflight validated nothing"
    return indexed


def merge(paths, out_path):
    indexed = preflight(paths)
    out_path = os.path.abspath(out_path)

    # An output that IS an input would be replaced by its own merge, destroying the
    # source. Reproduced: `--db vA.db --out vA.db` turned a 436 MB two-source db
    # into the 1.6 GB merged one. Reject HERE, before the temporary database
    # exists -- validating before the rename cannot help, because the merge is
    # perfectly valid and would still overwrite the file it just read from.
    for p in paths:
        if os.path.abspath(p) == out_path:
            raise SystemExit(
                f"output {out_path} is also an input; refusing to overwrite a "
                f"source database with its own merge (use a different --out)")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + ".part"
    for f in (tmp, tmp + "-journal", tmp + "-wal", tmp + "-shm"):
        if os.path.exists(f):
            os.remove(f)

    t0 = time.time()
    # ONE loop over every input, including the first: the output always gets this
    # module's SCHEMA/INDEXES, so no input is privileged (the docstring used to
    # claim the first supplied the schema; it never did).
    conn = sqlite3.connect(tmp)
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA journal_mode=OFF")

    print(f"\n[2/6] creating {os.path.basename(out_path)} with the fixed "
          f"schema/indexes (preflight ok: {len(indexed)} input(s))", flush=True)
    for idx, p in enumerate(paths):
        print(f"[3/6] appending [{idx}] {os.path.basename(p)}", flush=True)
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
    # Both inputs contain a few (LDOCE5: rows referencing files absent from the
    # mdd; OALD10: 661 ROWS = 654 (source,file) PAIRS, because 7 pairs span two
    # rows each). Compare in Python: a correlated NOT EXISTS over 200k+ rows is
    # needlessly slow.
    ent_pairs = set(conn.execute("SELECT source, file FROM entries"))
    blob_pairs = set(conn.execute("SELECT source, file FROM android"))
    orphan = ent_pairs - blob_pairs
    dropped_pairs = len(orphan)
    dropped_rows = 0
    if orphan:
        # Count ROWS as well as pairs: reporting only pairs made the arithmetic
        # (217,523 -> 216,862, a difference of 661) fail to reconcile.
        for s, f in orphan:
            dropped_rows += conn.execute(
                "SELECT COUNT(*) FROM entries WHERE source=? AND file=?",
                (s, f)).fetchone()[0]
        conn.executemany("DELETE FROM entries WHERE source=? AND file=?",
                         [(s, f) for s, f in orphan])
        conn.commit()
    print(f"   removed {dropped_pairs:,} orphan (source,file) pair(s) "
          f"covering {dropped_rows:,} row(s)", flush=True)

    print("[5/6] indexes + vacuum", flush=True)
    for sql in INDEXES:
        conn.execute(sql)
    conn.commit()
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("VACUUM")
    conn.commit()

    print("[6/6] final invariants (before publishing)", flush=True)
    ent_pairs = set(conn.execute("SELECT source, file FROM entries"))
    blob_pairs = set(conn.execute("SELECT source, file FROM android"))
    # BOTH directions. ent-blob catches an index row with no audio; blob-ent
    # catches audio nothing points at (dead weight in a >1 GB file). The earlier
    # version checked only the first while the docs claimed "双向孤儿 0/0", so a
    # future input could smuggle in unreachable payloads unnoticed.
    orphan_ent = len(ent_pairs - blob_pairs)
    orphan_blob = len(blob_pairs - ent_pairs)
    # duplicate (source,file) makes Hoshi's first-row pick shadow another copy;
    # preflight prevents it between inputs, this catches an internal mistake
    dup = conn.execute("SELECT COUNT(*) FROM (SELECT source, file FROM android "
                       "GROUP BY source, file HAVING COUNT(*) > 1)").fetchone()[0]
    sources = [r[0] for r in conn.execute("SELECT DISTINCT source FROM entries")]
    payload = conn.execute("SELECT SUM(length(data)) FROM android").fetchone()[0] or 0
    ent = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    blob = conn.execute("SELECT COUNT(*) FROM android").fetchone()[0]
    ic = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()

    # Validate the PRIVATE .part, then rename it into place. The previous order was
    # os.replace first, check second -- so a bad merge overwrote a good
    # android_merged.db and only afterwards raised. Same P1 rule the dictionary
    # converter already follows.
    # Note orphan_ent is guaranteed 0 by step 4; the load-bearing checks here are
    # integrity_check, orphan_blob and dup.
    problems = []
    if ic != "ok":
        problems.append(f"integrity_check={ic!r}")
    if orphan_ent:
        problems.append(f"{orphan_ent} entry pair(s) with no blob")
    if orphan_blob:
        problems.append(f"{orphan_blob} blob pair(s) referenced by no entry")
    if dup:
        problems.append(f"{dup} duplicate (source, file) pair(s)")
    if problems:
        try:
            os.remove(tmp)
        except OSError:
            pass
        print(f"\n   [FAIL] refusing to publish: {'; '.join(problems)}")
        print(f"   the previous {os.path.basename(out_path)} is untouched")
        raise SystemExit("merged db failed its own invariants: " + "; ".join(problems))

    size = os.path.getsize(tmp)
    os.replace(tmp, out_path)          # publish only after every check passed
    print(f"\n   written : {out_path}")
    print(f"   size    : {size:,} B ({size/1048576:.1f} MiB)")
    print(f"   entries : {ent:,}   blobs: {blob:,}   payload: {payload/1048576:.1f} MiB")
    print(f"   sources : {sorted(sources)}")
    print(f"   integrity_check: {ic}   orphan pairs: ent-blob={orphan_ent} "
          f"blob-ent={orphan_blob}   elapsed: {time.time()-t0:.0f}s")
    return {"path": out_path, "size": size, "entries": ent, "blobs": blob,
            "payload": payload, "sources": sorted(sources),
            "dropped_pairs": dropped_pairs, "dropped_rows": dropped_rows}


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
