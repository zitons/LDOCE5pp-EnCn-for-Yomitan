"""Verify that every SKIPPED source record is legitimately skippable.

The coverage audit reports 0 missing entries, but 2,106 records were classified
"skip". A skip is only legitimate if the record genuinely carries no dictionary
entry -- otherwise the converter is silently dropping content. Dump the content of
every skip category so each one can be judged, rather than trusting the reason
string.
"""
import os
import re
import sys
from collections import Counter

ROOT = r"C:\workspace\ldoce"
sys.path.insert(0, os.path.join(ROOT, "converter"))
import ldoce2yomitan as C  # noqa: E402

SRC = os.path.join(ROOT, "extract", "LDOCE5++ V 2-15.mdx.txt")

groups = {}
for key, content in C.iter_records(SRC):
    kind, target = C.classify_record(key, content)
    if kind != "skip":
        continue
    k = C.strip_invisible(key).strip()
    if C.SKIP_KEY_RE.match(k):
        g = "key matches SKIP_KEY_RE"
    elif not k:
        g = "empty key"
    else:
        g = "no entry_content/ldoceEntry"
    groups.setdefault(g, []).append((k, content))

print(f"total skipped: {sum(len(v) for v in groups.values()):,}")
print()
for g, items in sorted(groups.items(), key=lambda x: -len(x[1])):
    print("=" * 78)
    print(f"{g}  ({len(items):,})")
    print("=" * 78)
    # key shape statistics
    shapes = Counter()
    for k, _ in items:
        if k.startswith("ACTIV:"):
            shapes["ACTIV:<label>"] += 1
        elif k == "ACTIV:":
            shapes["ACTIV: (bare)"] += 1
        elif re.match(r"^ldoce\d+jpg", k, re.I):
            shapes["ldoceNjpg..."] += 1
        else:
            shapes["other"] += 1
    for s, n in shapes.most_common():
        print(f"   {n:>7,}  {s}")
    print()
    print("   --- content of the first few (is there a real entry in there?) ---")
    for k, c in items[:4]:
        print(f"   key={k[:60]!r}")
        print(f"      len={len(c):,}  first 200 chars: {c[:200]!r}")
        print()
