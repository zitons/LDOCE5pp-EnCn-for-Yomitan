"""Rewrite the `entries` table so row order == source priority.

Hoshi's local-audio lookup resolves one row per word. Whichever row a reader
happens to see first wins, and without an explicit priority that is either
alphabetical (`ode2024` < `tld_*`, fine by luck) or plain rowid order, which is
whatever order the sources were appended in. Rebuilding the table in priority
order makes both interpretations agree.

The `android` table (the actual bytes, ~4.6 GB) is untouched.
"""
import argparse
import sqlite3
import sys

# Lower number = tried first. ODE 2024 is a single, verified dictionary, so it
# leads; the TLD packs follow roughly by recording quality (tld_uk is 44.1 kHz
# / 64 kbps mp3).
#
# `tld_uk2` (TLD.6) is gone: removed from the database on 2026-11-11. It was
# last on this list on purpose -- it bought only 2,291 expressions for 649 MB,
# 70% of its files are unverifiable numeric names, and it was the one source
# with a confirmed wrong clip (`four` -> "Four by four."). Do not re-add it
# unless a fresh audit says otherwise.
PRIORITY = {
    "ode2024": 0,
    "ldoce_ame": 1,
    "ldoce_bre": 2,
    "oald10": 3,
    "tld_uk": 4,
    "tld_ame": 5,
    "tld_collins": 6,
    "tld_mw": 7,
    "tld_ids": 8,
    "tld_snd": 9,
}

SCHEMA = """
CREATE TABLE entries_new (
    id integer PRIMARY KEY NOT NULL,
    expression text NOT NULL,
    reading text,
    source text NOT NULL,
    speaker text,
    display text,
    file text NOT NULL
);
"""

DROP = """
DROP TABLE entries;
ALTER TABLE entries_new RENAME TO entries;
CREATE INDEX expr_idx ON entries(expression);
CREATE INDEX src_idx  ON entries(source);
CREATE INDEX idx_entries_expr_read ON entries(expression, reading);
"""


def case_sql():
    whens = " ".join(f"WHEN '{s}' THEN {p}" for s, p in PRIORITY.items())
    return f"CASE source {whens} ELSE 99 END"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"C:\workspace\ldoce\yomitan_audio\tld.db")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="run pragma quick_check at the end. On a 5 GB db this walks "
                         "the whole blob btree page by page and can take 30+ min, so "
                         "it is off by default -- the row counts and orphan checks "
                         "below are enough to know the swap committed")
    args = ap.parse_args()

    con = sqlite3.connect(args.db, timeout=120)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    # 200 MB page cache: the default 2 MB turns the index builds into random I/O
    # over a 5 GB file and multiplies the runtime.
    con.execute("PRAGMA cache_size=-200000")

    rows = con.execute(
        "select source, count(*) from entries group by source order by 2 desc").fetchall()
    print("before:", rows)
    total = sum(n for _s, n in rows)
    print(f"        {total:,} entries")

    if args.dry_run:
        for s, _n in rows:
            if s not in PRIORITY:
                print(f"  NOTE: {s!r} not in PRIORITY, sorts last")
        con.close()
        return

    con.executescript(SCHEMA)
    con.commit()
    # One explicit transaction for the swap: if anything fails, the old table
    # (and its row order) survives instead of being dropped half way.
    con.execute("BEGIN IMMEDIATE")
    con.execute(
        f"INSERT INTO entries_new (expression, reading, source, speaker, display, file) "
        f"SELECT expression, reading, source, speaker, display, file FROM entries "
        f"ORDER BY {case_sql()}, expression")
    con.execute("DROP TABLE entries")
    con.execute("ALTER TABLE entries_new RENAME TO entries")
    con.execute("CREATE INDEX expr_idx ON entries(expression)")
    con.execute("CREATE INDEX src_idx  ON entries(source)")
    con.execute("CREATE INDEX idx_entries_expr_read ON entries(expression, reading)")
    con.commit()
    con.execute("ANALYZE")
    con.commit()

    print("after :",
          con.execute("select source, count(*) from entries group by source "
                      "order by min(id)").fetchall())
    # quick_check walks every blob page; it is opt-in because on the 5 GB db it
    # costs more time than the reorder itself.
    print("quick_check:",
          con.execute("pragma quick_check").fetchone()[0] if args.check else "skipped")
    orphans_a = con.execute(
        "select count(*) from entries e left join android a "
        "on a.file=e.file and a.source=e.source where a.id is null").fetchone()[0]
    orphans_b = con.execute(
        "select count(*) from android a left join entries e "
        "on e.file=a.file and e.source=a.source where e.id is null").fetchone()[0]
    print(f"orphans: entries without blob {orphans_a:,}, blobs without entry {orphans_b:,}")
    print("db size:", f"{__import__('os').path.getsize(args.db):,} B")
    con.close()
    if orphans_a:
        raise SystemExit("REFUSED: entries point at missing audio")


if __name__ == "__main__":
    main()
