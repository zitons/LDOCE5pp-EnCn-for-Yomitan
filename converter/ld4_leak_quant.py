"""Quantify the LDOCE4-legacy leak.

The original stylesheet hides `.ldoceEntry .LDOCEVERSION_new`,
`.dictentry.LDOCEVERSION_new` and `.LDOCEVERSIONLOGO_5/_new`. In the converter
those class names sit in UNWRAP_CLASSES, so the wrapper is stripped and the
hidden content is emitted as a normal entry/sense instead of being dropped.

Measures, over the whole corpus:
  * how many entry records carry a `.dictentry.LDOCEVERSION_new`
  * how many carry an `Entry.LDOCEVERSION_new`
  * total hidden-entry bodies (the actual leak surface)
"""
import collections
import re
import sys

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"

PAT_NEW = re.compile(r'class="dictentry LDOCEVERSION_new"')
PAT_ENTRY = re.compile(r'class="ldoceEntry Entry LDOCEVERSION_new"')
PAT_LOGO = re.compile(r'class="LDOCEVERSIONLOGO_(?:5|new)"')
PAT_ANY_NEW = re.compile(r'LDOCEVERSION_new')

recs_with = 0
n_new = n_entry = n_logo = n_any = 0
total = 0
keys = []
for key, content in M.iter_records(SIDE):
    k = M.strip_invisible(key).strip()
    if not k:
        continue
    kind, _ = M.classify_record(k, content)
    if kind != "entry":
        continue
    total += 1
    a = len(PAT_NEW.findall(content))
    b = len(PAT_ENTRY.findall(content))
    c = len(PAT_LOGO.findall(content))
    d = len(PAT_ANY_NEW.findall(content))
    n_new += a
    n_entry += b
    n_logo += c
    n_any += d
    if a or b:
        recs_with += 1
        if len(keys) < 15:
            keys.append(k)

print(f"entry records scanned                     = {total}")
print(f"records with an LDOCE4-legacy sub-entry   = {recs_with} "
      f"({recs_with*100.0/total:.2f}%)")
print(f"  dictentry.LDOCEVERSION_new blocks       = {n_new}")
print(f"  ldoceEntry Entry.LDOCEVERSION_new       = {n_entry}")
print(f"  LDOCEVERSIONLOGO_5/_new badges          = {n_logo}")
print(f"  any LDOCEVERSION_new occurrence         = {n_any}")
print()
print("sample affected words:", keys)
