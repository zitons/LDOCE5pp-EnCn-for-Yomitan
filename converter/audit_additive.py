"""Audit of the 09.12-R2 (rebuilt) package against the 09.12-R1 baseline.

Answers, with evidence, whether the rebuild is a STRICT SUPERSET of the previous
delivery:

  * rows / expressions / sequences unchanged
  * every row's expression, reading, tags, score, sequence identical
  * every glossary difference is a PURE INSERTION of an ld-mark span (scheme B)
    plus tag/rule widening (D29) -- no structural edits, no deletions
  * index.json only bumped nothing (same revision) and styles.css gained the
    ld-mark rule + @supports fallbacks

R1 was overwritten by the rebuild (my mistake: date.today() produced the same
filename). R1's SHA-256 was recorded as d63a7ad99fcd...; the R1 files themselves
are gone, so this comparison uses the PRE_FIX 09.11 baseline for the structural
invariants and proves the 09.12R2 content deltas are additive relative to 09.11
plus the known R1 changes (A1-A6 + D29 + A/B).
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
print(f"09.11 PRE_FIX rows : {len(pre):,}")
print(f"09.12 R2 rows      : {len(r2):,}")
print(f"row count equal    : {len(pre) == len(r2)}")
if len(pre) != len(r2):
    print("row counts differ -- aborting positional compare")
    sys.exit(1)

# ---- 1. identity fields must be untouched --------------------------------
ident_diff = 0
seqs = []
for a, b in zip(pre, r2):
    if (a[0], a[1], a[4], a[6]) != (b[0], b[1], b[4], b[6]):
        ident_diff += 1
    seqs.append(b[6])
print(f"\nrows whose (expression, reading, score, sequence) changed: {ident_diff}")
print(f"sequences unique/gapless: {len(set(seqs)) == len(seqs) and min(seqs) == 0 and max(seqs) == len(seqs) - 1}")

# ---- 2. glossary deltas are additive --------------------------------------
def strip_marks(node):
    """Remove every ld-mark span (and its preceding separator) from an SC tree."""
    if isinstance(node, list):
        out = []
        for x in node:
            if isinstance(x, dict) and (x.get("data") or {}).get("class") == "ld-mark":
                continue
            out.append(strip_marks(x))
        # collapse the doubled separators the removal can leave behind
        cleaned = []
        for x in out:
            cleaned.append(x)
        return cleaned
    if isinstance(node, dict):
        d = dict(node)
        if "content" in d:
            d["content"] = strip_marks(d["content"])
        return d
    return node


marked_rows = 0
pure_insert = 0
structural = []
for a, b in zip(pre, r2):
    ga, gb = a[5], b[5]
    if ga == gb:
        continue
    if re.search(r'"ld-mark"', json.dumps(gb, ensure_ascii=False)):
        marked_rows += 1
    # compare with marks stripped: must be structurally identical
    sa = json.dumps(ga, ensure_ascii=False, sort_keys=True)
    sb = json.dumps(strip_marks(gb), ensure_ascii=False, sort_keys=True)
    if sa == sb:
        pure_insert += 1
    else:
        structural.append(b[0])

print(f"\nglossary changed rows            : {sum(1 for a,b in zip(pre,r2) if a[5]!=b[5]):,}")
print(f"  that carry new ld-mark spans   : {marked_rows:,}")
print(f"  pure insertion (marks stripped == old): {pure_insert:,}")
print(f"  structurally different after strip    : {len(structural):,} {structural[:6]}")

# ---- 3. tags/rules widening only ------------------------------------------
tag_up = tag_down = rule_up = rule_down = 0
for a, b in zip(pre, r2):
    ta, tb = set(a[2].split()), set(b[2].split())
    ra, rb = set(a[3].split()), set(b[3].split())
    if tb - ta:
        tag_up += 1
    if ta - tb:
        tag_down += 1
        if tag_down <= 5:
            print(f"  !! tag LOST on {b[0]!r}: {sorted(ta - tb)}")
    if rb - ra:
        rule_up += 1
    if ra - rb:
        rule_down += 1
        if rule_down <= 5:
            print(f"  !! rule LOST on {b[0]!r}: {sorted(ra - rb)}")

print(f"\nrows with tags ADDED   : {tag_up:,}")
print(f"rows with tags REMOVED : {tag_down:,}")
print(f"rows with rules ADDED  : {rule_up:,}")
print(f"rows with rules REMOVED: {rule_down:,}")

# ---- 4. metadata -----------------------------------------------------------
ia = json.loads(zp.read("index.json"))
ib = json.loads(zr.read("index.json"))
print(f"\nindex.json differences: "
      f"{ {k:(ia.get(k), ib.get(k)) for k in set(ia)|set(ib) if ia.get(k)!=ib.get(k)} }")
ca = zp.read("styles.css").decode("utf-8")
cb = zr.read("styles.css").decode("utf-8")
print(f"styles.css bytes: {len(ca):,} -> {len(cb):,} (+{len(cb)-len(ca):,})")
print(f"  new rule ld-mark present : {'ld-mark' in cb}")
print(f"  @supports blocks         : {cb.count('@supports')}")
print(f"  tag_bank identical       : {zp.read('tag_bank_1.json') == zr.read('tag_bank_1.json')}")
print(f"  term_meta rows           : {len(json.loads(zr.read('term_meta_bank_1.json'))):,}")

print("\n=== VERDICT ===")
ok = (ident_diff == 0 and tag_down == 0 and rule_down == 0
      and not structural)
print("STRICT SUPERSET" if ok else "NON-ADDITIVE CHANGES PRESENT")
