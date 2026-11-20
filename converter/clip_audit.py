"""Find clips whose recording probably does not match the headword it is filed under.

This is the tool behind `bad_clips.tsv`. It cannot listen, so it produces two
tiers of candidates and leaves the verdict to a human (or to ASR):

  A  shared  -- one file referenced by >=2 unrelated headwords. At most one of
                them can be right, so every such group hides at least one error.
                (Homophones like for/fore/four share a clip legitimately, so the
                group still needs a look.)
  B  prefix  -- the file stem and the headword disagree at a word boundary:
                `four` filed under a stem `for` (short word's clip, long word's
                entry), or `air` filed under `air_ambulance`. Two patterns are
                benign and filtered out: stems truncated to 14 chars by the pack
                builder, and reduplications (`bling bling` -> `bling`).

Output is a TSV so it can be diffed between builds:

    python converter/clip_audit.py                 # summary + _tmp/clip_audit.tsv
    python converter/clip_audit.py --sample 40     # + export 40 random clips
"""
import argparse
import os
import random
import re
import sqlite3
import sys

DB = r"C:\workspace\ldoce\yomitan_audio\tld.db"
OUT = r"C:\workspace\ldoce\_tmp\clip_audit.tsv"
TRUNC = 14   # the pack builder cuts stems to 14 chars: `absolute_major`


def norm(s):
    s = s.lower().replace("-", " ").replace("_", " ")
    s = re.sub(r"[^a-z0-9 ']", " ", s)
    return " ".join(s.split())


def stem_of(fname, source):
    """Best-effort recovery of the headword encoded in a file name."""
    b = os.path.basename(fname.replace("\\", "/"))
    s = os.path.splitext(b)[0].lower()
    if source == "tld_uk":
        m = re.match(r"mediaenglish(?:uk|us)_pron[a-z0-9]+?_(.+?)(?:_\d+)?_(?:gb|us)_\d+$", s)
        if m:
            return m.group(1)
    if source == "tld_mw" and s.startswith("mw_"):
        return s[3:]
    if source == "tld_snd" and s.startswith("sndffo"):
        return s[6:]
    if source == "tld_ame":
        m = re.match(r"ld\d+(.+)$", s)
        if m:
            return m.group(1)
    if source == "tld_collins":
        m = re.match(r"colmp3en_(?:gb|us)_(.+?)(?:_\d+)?$", s)
        if m:
            return m.group(1)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--sample", type=int, default=0,
                    help="export N random candidate clips for listening / ASR")
    ap.add_argument("--seed", type=int, default=20261023)
    args = ap.parse_args()

    con = sqlite3.connect("file:%s?mode=ro" % args.db, uri=True)

    print("[1/3] shared clips (one file, several headwords)")
    groups = con.execute(
        "select source, file, count(distinct expression) n from entries "
        "group by source, file having n > 1 order by n desc").fetchall()
    print(f"      {len(groups):,} file(s) shared by >=2 headwords, "
          f"{sum(n for _s, _f, n in groups):,} entries involved")

    print("[2/3] stem/headword boundary mismatch")
    # The decisive filter: keep a row only when the stem is *itself* a headword
    # of the same source. Pack-builder truncations (`_absolutely_fa` for
    # "Absolutely Fabulous") produce a stem that is not a word at all, so they
    # drop out; genuine mix-ups (`for` filed under `four`, `air` filed under
    # `air ambulance`) always have the other word in the dictionary.
    vocab = {}
    for src, expr in con.execute("select source, expression from entries"):
        vocab.setdefault(src, set()).add(norm(expr))

    rows = []
    n_parsed = 0
    for expr, f, src in con.execute("select expression, file, source from entries"):
        w = stem_of(f, src)
        if w is None:
            continue
        n_parsed += 1
        a, b = norm(w), norm(expr)
        if not a or not b or a == b:
            continue
        if a == b + " " + b:                     # `bling bling` -> bling
            continue
        if a.startswith(b + " ") or b.startswith(a + " "):
            tier = "B-words"                     # whole-word prefix / extension
        elif a.startswith(b) or b.startswith(a):
            tier = "B-chars"                     # `for` -> four
        else:
            continue
        if a not in vocab.get(src, ()):          # stem is not a word: truncation
            continue
        rows.append((tier, src, f, expr, w))
    # the same (file, expression) shows up once per mdd record; show it once
    rows = sorted(set(rows))
    print(f"      {n_parsed:,} file names parsed, {len(rows):,} suspicious")

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("tier\tsource\tfile\texpression\tstem\n")
        for r in rows:
            fh.write("\t".join(r) + "\n")
    print(f"      -> {args.out}")

    print("[3/3] per-source tally")
    tally = {}
    for t, s, _f, _e, _w in rows:
        tally[(s, t)] = tally.get((s, t), 0) + 1
    for (s, t), n in sorted(tally.items()):
        print(f"      {s:12s} {t:9s} {n:>7,}")

    if args.sample:
        os.makedirs(os.path.join(os.path.dirname(args.out) or ".", "audit_sample"),
                    exist_ok=True)
        rnd = random.Random(args.seed)
        pick = rnd.sample(rows, min(args.sample, len(rows)))
        manifest = os.path.join(os.path.dirname(args.out) or ".", "audit_sample",
                                "manifest.tsv")
        with open(manifest, "w", encoding="utf-8") as mf:
            mf.write("path\tsource\tfile\texpression\tstem\n")
            for t, s, f, e, w in pick:
                d = con.execute("select data from android where source=? and file=? limit 1",
                                (s, f)).fetchone()
                if not d:
                    continue
                p = os.path.join(os.path.dirname(manifest),
                                 "%s__%s" % (s, os.path.basename(f)))
                with open(p, "wb") as fh:
                    fh.write(d[0])
                mf.write(f"{p}\t{s}\t{f}\t{e}\t{w}\n")
        print(f"      sample of {len(pick)} -> {manifest}")
    con.close()


if __name__ == "__main__":
    main()
