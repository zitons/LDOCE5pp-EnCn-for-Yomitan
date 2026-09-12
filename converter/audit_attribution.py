"""Correct attribution of the 09.11 -> 09.12R2 content deltas.

The earlier run compared against 09.11 PRE_FIX, which predates the whole A/D13-D19
round, so every change from that round showed up as "structural". This version
classifies each changed row by WHICH known fix explains it, and asserts that
nothing falls outside the known set.

Known fixes between 09.11 PRE_FIX and 09.12 R2:
  D11  word-family opp markers / loose text        -> ld-wf-opp nodes appear
  D13  LDOCE Online panel                           -> ld-panel-online appears
  D14  head GRAM brackets                           -> ld-gram content gains [ ]
  D17  inflection region/annotation                 -> ld-infl-region / ld-infl-ann
  D29  POS/rules cap removal                        -> tags/rules widened
  B    semantic markers                             -> ld-mark spans appear
  box  sense-group labels                           -> ld-panel-sub appears
"""
import json
import re
import sys
import zipfile
from collections import Counter

R2 = r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.12.zip"
PRE = r"C:\workspace\ldoce\_baseline\LDOCE5pp_Yomitan_2026.09.11.PRE_FIX.zip"


def load(path):
    z = zipfile.ZipFile(path)
    names = sorted((n for n in z.namelist()
                    if re.fullmatch(r"term_bank_\d+\.json", n)),
                   key=lambda n: int(re.search(r"\d+", n).group()))
    rows = []
    for n in names:
        rows.extend(json.loads(z.read(n)))
    return z, rows


zr, r2 = load(R2)
zp, pre = load(PRE)

# Every element kind a KNOWN fix can introduce or restructure. The first audit run
# omitted ld-infl-lab / ld-infl-pron and reported 14 phantom "unexplained" rows:
#   * ld-infl-lab  - D17 split "plural X" into a separate label node
#   * ld-infl-pron - A4 added the inflection pronunciation blocks
#   * ld-pos       - D21 widened a multi-POS head ("adjective" -> "noun, adjective")
MARKERS = ("ld-wf-opp", "ld-panel-online", "ld-infl-region", "ld-infl-ann",
           "ld-mark", "ld-panel-sub", "ld-infl-lab", "ld-infl-pron",
           "ld-pos")
GRAM_RE = re.compile(r'"class": "ld-gram"\}, "content": "([^"]*)"')

kinds = Counter()
unexplained = []
tag_only = rule_only = 0

for a, b in zip(pre, r2):
    ga, gb = json.dumps(a[5], ensure_ascii=False), json.dumps(b[5], ensure_ascii=False)
    ta, tb = set(a[2].split()), set(b[2].split())
    ra, rb = set(a[3].split()), set(b[3].split())

    hit = set()
    if ga != gb:
        for m in MARKERS:
            if gb.count(m) > ga.count(m):
                hit.add(m)
        # A fix can also change a node's TEXT without changing any count (D21:
        # '4-F' head POS went from "adjective" to "noun, adjective", still one
        # ld-pos node). Compare the extracted per-class text too.
        pos_a = re.findall(r'"class": "ld-pos"\}, "content": "([^"]*)"', ga)
        pos_b = re.findall(r'"class": "ld-pos"\}, "content": "([^"]*)"', gb)
        if pos_a != pos_b:
            hit.add("ld-pos-text")
        if set(GRAM_RE.findall(gb)) != set(GRAM_RE.findall(ga)):
            hit.add("ld-gram-brackets")
    if tb - ta:
        hit.add("tags-widened")
    if rb - ra:
        hit.add("rules-widened")

    if not hit:
        if ga != gb or ta != tb or ra != rb:
            unexplained.append((b[0], bool(ga != gb), sorted(tb - ta), sorted(ra - rb)))
        continue
    for h in hit:
        kinds[h] += 1

print("changed rows by EXPLAINING FIX (a row may have several):")
for k, n in kinds.most_common():
    print(f"  {n:>7,}  {k}")

total_changed = sum(1 for a, b in zip(pre, r2)
                    if a[5] != b[5] or a[2] != b[2] or a[3] != b[3])
print(f"\nrows with any content/tag/rule change : {total_changed:,}")
print(f"rows NOT explained by a known fix     : {len(unexplained):,}")
for w, g, t, r in unexplained[:12]:
    print(f"   {w!r}: gloss_changed={g} tags+={t} rules+={r}")

# tabulate the marker totals for the record
print("\nmarker node totals in 09.12 R2:")
for m in MARKERS:
    zr_ = json.loads  # noqa: F841
    tot = 0
    for b in r2:
        tot += b[5].__str__().count(m)
    print(f"  {m:20} {tot:>10,}")

print("\n=== VERDICT ===")
print("ALL CHANGES EXPLAINED BY KNOWN FIXES" if not unexplained
      else "UNEXPLAINED CHANGES PRESENT")
sys.exit(0 if not unexplained else 1)
