"""Delete blacklisted (source, file, expression) rows from an existing audio db.

`converter/bad_clips.tsv` records clips whose *recording* does not match the
headword it is attached to -- the `four` / "Four by four." case, where the TLD
pack contains a correctly-encoded record for the wrong word. Those cannot be
detected by any structural check (the mdd record is fine, the mdx reference is
fine, only the human ear disagrees), so they are listed by hand and removed
here.

Re-runnable: applies the whole list every time, so it also works as a cleanup
step after a rebuild.

    python converter/apply_blacklist.py            # apply
    python converter/apply_blacklist.py --dry-run  # report only
"""
import argparse
import os
import sqlite3
import sys

TSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bad_clips.tsv")
DB = r"C:\workspace\ldoce\yomitan_audio\tld.db"


def load(path):
    rows = []
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                raise SystemExit(f"bad line in {path}: {line!r}")
            rows.append((parts[0].strip(), parts[1].strip(), parts[2].strip(),
                         parts[3].strip() if len(parts) > 3 else ""))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--tsv", default=TSV)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quick-check", action="store_true",
                    help="run pragma quick_check afterwards; slow (30+ min) "
                         "because it walks every 4.6 GB blob page")
    args = ap.parse_args()

    rules = load(args.tsv)
    print(f"{len(rules)} blacklist rule(s) from {args.tsv}")

    con = sqlite3.connect(args.db, timeout=120)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")

    total_del = 0
    blob_del = 0
    for src, fname, expr, reason in rules:
        n = con.execute(
            "select count(*) from entries where source=? and file=? and expression=?",
            (src, fname, expr)).fetchone()[0]
        print(f"  {src:10s} {fname:28s} {expr:16s} rows={n}  {reason}")
        if not n:
            continue
        if not args.dry_run:
            con.execute(
                "delete from entries where source=? and file=? and expression=?",
                (src, fname, expr))
            total_del += n
            # keep the blob only if some other headword still points at it
            left = con.execute(
                "select count(*) from entries where source=? and file=?",
                (src, fname)).fetchone()[0]
            if left == 0:
                blob_del += con.execute(
                    "delete from android where source=? and file=?",
                    (src, fname)).rowcount

    if args.dry_run:
        print("dry run: nothing written")
    else:
        con.commit()
        con.execute("ANALYZE")
        con.commit()
        print(f"deleted {total_del} entries row(s), {blob_del} orphan blob(s)")
    if args.quick_check:
        print("quick_check:", con.execute("pragma quick_check").fetchone()[0])
    else:
        print("quick_check: skipped (pass --quick-check to run; slow on 5 GB)")
    print("db size:", f"{os.path.getsize(args.db):,} B")
    con.close()


if __name__ == "__main__":
    main()
