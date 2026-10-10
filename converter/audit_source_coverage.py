"""Source-coverage audit: did any MDX entry fail to reach the package?

The build reports "records scanned / entries / redirects / skipped", but nothing
has ever checked the result against the SOURCE directly -- every conservation gate
so far compares package to package. This one compares package to the MDX.

For every record in the source it records the converter's own classification
(entry / redirect / skip), then checks that every source ENTRY key is present in
the built package, either as a content row or as a redirect target. Anything
missing is reported with the reason it was classified the way it was, so a
genuinely dropped entry is distinguishable from a deliberately skipped one.
"""
import io
import json
import os
import re
import sys
import zipfile
from collections import Counter

ROOT = r"C:\workspace\ldoce"
sys.path.insert(0, os.path.join(ROOT, "converter"))
import ldoce2yomitan as C  # noqa: E402

SRC = os.path.join(ROOT, "extract", "LDOCE5++ V 2-15.mdx.txt")
PKG = os.path.join(ROOT, "yomitan_fixed", "2026-10-09-margin-left", "bilingual",
                   "LDOCE5pp_Yomitan_2026.10.09.zip")

print(f"source: {SRC}  ({os.path.getsize(SRC):,} B)")
print(f"package: {os.path.basename(PKG)}")
print()

# ---------------------------------------------------------------- source side
cls_counts = Counter()
entries = {}          # key -> first 60 chars of content, for the report
redirect_targets = set()
skipped_samples = {}


def why_skip(key, content):
    k = C.strip_invisible(key).strip()
    if not k:
        return "empty key"
    if C.SKIP_KEY_RE.match(k):
        return f"key matches {C.SKIP_KEY_RE.pattern}"
    head = content.lstrip()
    if head.startswith("@@@LINK="):
        return "is a redirect"
    probe = content[:8000]
    if "entry_content" in probe or "ldoceEntry" in probe:
        return "would be an entry"
    return "no entry_content / ldoceEntry in first 8000 chars"


n = 0
for key, content in C.iter_records(SRC):
    n += 1
    kind, target = C.classify_record(key, content)
    cls_counts[kind] += 1
    if kind == "entry":
        k = C.strip_invisible(key).strip()
        entries.setdefault(k, content[:60].replace("\n", " "))
    elif kind == "redirect":
        if target:
            redirect_targets.add(target)
    else:
        r = why_skip(key, content)
        skipped_samples.setdefault(r, []).append(
            C.strip_invisible(key).strip()[:40])

print(f"source records scanned        : {n:,}")
print(f"  classified entry            : {cls_counts['entry']:,}")
print(f"  classified redirect         : {cls_counts['redirect']:,}")
print(f"  classified skip             : {cls_counts['skip']:,}")
print()
print("skip reasons:")
for r, ks in sorted(skipped_samples.items(), key=lambda x: -len(x[1])):
    print(f"   {len(ks):>7,}  {r}")
    for k in ks[:3]:
        print(f"            e.g. {k!r}")
print()

# --------------------------------------------------------------- package side
z = zipfile.ZipFile(PKG)
pkg_expr = set()
pkg_rows = 0
pkg_redirect_rows = 0
for name in z.namelist():
    if not re.fullmatch(r"term_bank_\d+\.json", name):
        continue
    for r in json.loads(z.read(name)):
        pkg_rows += 1
        pkg_expr.add(r[0])
        if len(r) > 4 and r[4] == 0:      # score 0 marks a redirect row
            pkg_redirect_rows += 1

print(f"package rows                  : {pkg_rows:,}")
print(f"  redirect rows (score 0)     : {pkg_redirect_rows:,}")
print(f"  content rows                : {pkg_rows - pkg_redirect_rows:,}")
print(f"  distinct expressions        : {len(pkg_expr):,}")
print()

# ------------------------------------------------------------------ coverage
missing = [k for k in entries if k not in pkg_expr]
print("=" * 78)
print("COVERAGE")
print("=" * 78)
print(f"source entries                : {len(entries):,}")
print(f"present in the package        : {len(entries) - len(missing):,}")
print(f"MISSING from the package      : {len(missing):,}")
print()

if missing:
    print("=== the missing entries (first 40) ===")
    for k in sorted(missing)[:40]:
        print(f"   {k!r}")
        print(f"      content: {entries[k][:70]!r}")
    if len(missing) > 40:
        print(f"   ... and {len(missing) - 40} more")

# also: are there package expressions that are NOT in the source at all?
src_all = set(entries) | redirect_targets
extra = sorted(e for e in pkg_expr if e not in src_all)
print()
print(f"package expressions with no source record : {len(extra):,}")
for e in extra[:15]:
    print(f"   {e!r}")

print()
if not missing:
    print("VERDICT: every source entry reached the package.")
else:
    print(f"VERDICT: {len(missing)} source entries are absent from the package -- "
          f"inspect above.")
