"""How much did the fix round actually change?
Row-by-row diff of the pre-fix 09.11 package against the shipped one.

Both builds walk the same source in the same order, so row i of bank k
corresponds; the row counts are identical (245,933), so a positional diff is
sound. Reports: rows changed, entries vs aliases, and what changed inside them.
"""
import json
import re
import sys
import zipfile
from collections import Counter

OLD = r"C:\workspace\ldoce\_baseline\LDOCE5pp_Yomitan_2026.09.11.PRE_FIX.zip"
NEW = r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.11.zip"


def banks(path):
    z = zipfile.ZipFile(path)
    names = sorted((n for n in z.namelist() if re.fullmatch(r"term_bank_\d+\.json", n)),
                   key=lambda n: int(re.search(r"\d+", n).group()))
    return z, names


z1, b1 = banks(OLD)
z2, b2 = banks(NEW)

print(f"banks: old={len(b1)} new={len(b2)}")
tot = changed = 0
changed_entry = changed_alias = 0
added_markers = Counter()
size_delta = 0
by_bank = Counter()
examples = []

for n1, n2 in zip(b1, b2):
    r1 = json.loads(z1.read(n1))
    r2 = json.loads(z2.read(n2))
    if len(r1) != len(r2):
        print(f"  !! length differs in {n1}: {len(r1)} vs {len(r2)}")
    for a, bb in zip(r1, r2):
        tot += 1
        if a == bb:
            continue
        changed += 1
        by_bank[n1] = by_bank.get(n1, 0) + 1
        is_entry = a[4] > 0
        if is_entry:
            changed_entry += 1
        else:
            changed_alias += 1
        sa = json.dumps(a[5], ensure_ascii=False)
        sb = json.dumps(bb[5], ensure_ascii=False)
        size_delta += len(sb) - len(sa)
        for m in ('ld-panel-online', 'ld-wf-opp', 'ld-panel-sub', 'ld-infl-region',
                  'ld-infl-ann', 'ld-panel-wf'):
            d = sb.count(m) - sa.count(m)
            if d:
                added_markers[m] += d
        if a[:3] != bb[:3]:
            added_markers['tags/rules changed'] += 1
        if len(examples) < 12 and is_entry:
            examples.append((a[0], len(sa), len(sb)))

print(f"\nrows compared            = {tot}")
print(f"rows that DIFFER         = {changed}  ({changed*100.0/tot:.2f}% of all rows)")
print(f"  of which entry rows    = {changed_entry}")
print(f"  of which alias rows    = {changed_alias}")
print(f"glossary bytes delta     = {size_delta:+,}")
print(f"\nwhat was ADDED inside changed rows:")
for m, c in added_markers.most_common():
    print(f"  {c:>7}  {m}")
print(f"\nchanged rows per bank: {dict(sorted(by_bank.items(), key=lambda kv: -kv[1])[:6])}")
print("\nexamples (word, old glossary bytes -> new):")
for w, a, b in examples:
    print(f"  {w!r:22} {a:>8} -> {b:>8}  ({b-a:+,})")
