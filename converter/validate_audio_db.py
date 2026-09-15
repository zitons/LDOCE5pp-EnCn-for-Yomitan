"""Validate the generated audio db by replaying Hoshi's own query logic.

Nothing here is invented: every statement mirrors a line from
app/src/main/java/moe/antimony/hoshi/features/audio/LocalAudioRepository.kt and
LocalAudioResolver.kt.

  findAudio(term, reading)
      reading blank -> SELECT source, expression, reading, file FROM entries
                       WHERE expression = ?
      else          -> ... WHERE (expression = ? OR reading = ?)
  audioSourcesFromDatabase()
      SELECT DISTINCT source FROM entries
      WHERE lower(file) LIKE '%.mp3' OR lower(file) LIKE '%.opus' OR lower(file) LIKE '%.ogg'
  loadAudio(file)
      SELECT data FROM android WHERE source = ? AND file = ?  LIMIT 1
  LocalAudioResolver.resolve()
      rank: expression match with reading null/equal  -> 0
            reading match                            -> 1
            expression match                         -> 2
      then by source order, then source name

The script reports per-word hits for a realistic word list, the source list Hoshi
would discover, and verifies that every entry row has a retrievable blob.
"""
import argparse
import io
import json
import os
import sqlite3
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ldoce2yomitan as C  # noqa: E402


def hoshi_find_audio(db, term, reading):
    """Mirror of LocalAudioRepository.findAudio for reading == ''."""
    normalized = ""      # our dictionary has no readings
    if normalized.strip():
        sel = "(expression = ? OR reading = ?)"
        args = (term, normalized)
    else:
        sel = "expression = ?"
        args = (term,)
    rows = db.execute(
        f"SELECT source, expression, reading, file FROM entries WHERE {sel}",
        args).fetchall()
    order = hoshi_source_order(db)
    rank = {s: i for i, s in enumerate(order)}
    entries = [{"source": r[0], "expression": r[1], "reading": r[2], "file": r[3]}
               for r in rows]

    def match_rank(e):
        reading_matches = bool(normalized) and e["reading"] == normalized
        expr_matches = e["expression"] == term
        if expr_matches and (e["reading"] is None or reading_matches):
            return 0
        if reading_matches:
            return 1
        if expr_matches:
            return 2
        return 3
    entries.sort(key=lambda e: (match_rank(e), rank.get(e["source"], 1 << 30), e["source"]))
    return entries


def hoshi_source_order(db):
    rows = db.execute(
        "SELECT DISTINCT source FROM entries "
        "WHERE lower(file) LIKE '%.mp3' OR lower(file) LIKE '%.opus' "
        "OR lower(file) LIKE '%.ogg'").fetchall()
    srcs = [r[0] for r in rows if r[0]]
    builtin = ["nhk16", "daijisen", "shinmeikai8", "jpod", "jpod_alternate",
               "taas", "ozk5", "forvo", "forvo_ext", "forvo_ext2"]
    def key(s):
        i = builtin.index(s) if s in builtin else len(builtin)
        return (i, s)
    return [s for s in sorted(set(srcs), key=key)]


def hoshi_load_audio(db, source, file):
    cur = db.execute("SELECT data FROM android WHERE source = ? AND file = ? LIMIT 1",
                     (source, file))
    row = cur.fetchone()
    return row[0] if row else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"C:\workspace\ldoce\build\audio_sample.db")
    ap.add_argument("--zip", default=r"C:\workspace\ldoce\yomitan_full"
                                     r"\LDOCE5pp_Yomitan_2026.09.13.zip")
    ap.add_argument("--words", default="improve,abandon,child,run,the,water,happy,"
                                       "computer,government,beautiful,one,time")
    args = ap.parse_args()

    db = sqlite3.connect(args.db)
    sources = hoshi_source_order(db)
    print(f"db: {args.db}  ({os.path.getsize(args.db):,} B)")
    print(f"sources Hoshi would discover: {sources}")
    print(f"entries rows: {db.execute('SELECT COUNT(*) FROM entries').fetchone()[0]:,}")
    print(f"android rows: {db.execute('SELECT COUNT(*) FROM android').fetchone()[0]:,}")
    print()

    # integrity: every (source,file) in entries must resolve to a blob
    missing = db.execute("""
        SELECT COUNT(*) FROM entries e
        WHERE NOT EXISTS (SELECT 1 FROM android a
                          WHERE a.source = e.source AND a.file = e.file)
    """).fetchone()[0]
    print(f"entries without a matching blob: {missing}")
    # and every blob must carry real bytes
    zero = db.execute("SELECT COUNT(*) FROM android WHERE length(data) < 100").fetchone()[0]
    print(f"android rows with <100 bytes : {zero}")
    print()

    words = [w for w in args.words.split(",") if w]
    print(f"{'word':14} {'hits':>5} {'first source':12} {'file':22} {'bytes':>7}  magic")
    print("-" * 82)
    for w in words:
        hits = hoshi_find_audio(db, w, "")
        if not hits:
            print(f"{w:14} {0:>5} {'-':12} {'-':22} {'-':>7}  (no audio)")
            continue
        best = hits[0]
        blob = hoshi_load_audio(db, best["source"], best["file"])
        magic = blob[:3].hex() if blob else "none"
        # mp3 starts with 'ID3' (494433) or an MPEG frame sync (fffb/fff3/fff2)
        ok = "ID3" if magic.startswith("494433") else ("MPEG" if magic[:2] == "ff" else "??")
        print(f"{w:14} {len(hits):>5} {best['source']:12} {best['file']:22} "
              f"{len(blob) if blob else 0:>7}  {ok}")

    # distribution sanity: how many entries / how many bytes
    tot = db.execute("SELECT SUM(length(data)) FROM android").fetchone()[0] or 0
    print(f"\npayload in db: {tot:,} B ({tot/1048576:.1f} MiB)")


if __name__ == "__main__":
    main()
