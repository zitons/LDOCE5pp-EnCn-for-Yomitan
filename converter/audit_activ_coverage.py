"""Check that every ACTIV label in the source reached the package.

ACTIV records are legitimately skipped as standalone entries (they are index pages,
not dictionary entries), but the ACTIV LABELS themselves are inline content: the
source renders them as <span class="_ACTIV_">CODE</span> inside a definition, and
the converter turns each into an ld-act chip. If that mapping dropped any label,
the entry would silently lose part of its definition -- a content loss that the
entry-count check cannot see.

Count them on both sides and diff the sets.
"""
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

# Two different markups exist in the source and they mean different things:
#   class="_ACTIV_"  -> only inside the ACTIV: index pages (which are skipped)
#   class="ACTIV"    -> the label rendered inline inside a real definition
# Only the second one is content that must reach the package. An earlier version
# matched only the first and therefore compared 0 against 0 and "passed".
ACTIV_RE = re.compile(r'<span class="ACTIV"[^>]*>(.*?)</span>', re.S)

src_labels = Counter()
src_entries_with_activ = 0
for key, content in C.iter_records(SRC):
    kind, _ = C.classify_record(key, content)
    if kind != "entry":
        continue
    found = ACTIV_RE.findall(content)
    if found:
        src_entries_with_activ += 1
        for label in found:
            src_labels[C.strip_invisible(label).strip()] += 1

print(f"source entries carrying an ACTIV label : {src_entries_with_activ:,}")
print(f"distinct ACTIV labels in the source    : {len(src_labels):,}")
print(f"total ACTIV label occurrences          : {sum(src_labels.values()):,}")
print()

z = zipfile.ZipFile(PKG)
pkg_labels = Counter()


def walk(node):
    """Collect every ld-act chip's text, by walking the SC tree properly.

    A regex over the serialised JSON cannot do this: the class attribute and the
    content are separated by the closing brace of the `data` object, so a pattern
    like class...ld-act...content never crosses it -- which is how 57,387 real
    chips were first reported as zero.
    """
    if isinstance(node, list):
        for x in node:
            walk(x)
    elif isinstance(node, dict):
        cls = (node.get("data") or {}).get("class") or ""
        if "ld-act" in cls.split():
            c = node.get("content")
            if isinstance(c, str):
                pkg_labels[C.strip_invisible(c).strip()] += 1
            elif isinstance(c, list):
                pkg_labels[C.strip_invisible("".join(
                    t for t in c if isinstance(t, str))).strip()] += 1
        walk(node.get("content", ""))


for name in z.namelist():
    if not re.fullmatch(r"term_bank_\d+\.json", name):
        continue
    for r in json.loads(z.read(name)):
        if len(r) > 4 and r[4] == 0:
            continue
        walk(r[5])

print(f"distinct ld-act chips in the package   : {len(pkg_labels):,}")
print(f"total ld-act chips in the package      : {sum(pkg_labels.values()):,}")
print()

missing = {k: v for k, v in src_labels.items() if k not in pkg_labels}
fewer = {k: (v, pkg_labels[k]) for k, v in src_labels.items()
         if k in pkg_labels and pkg_labels[k] < v}
print("=" * 74)
print("ACTIV LABEL COVERAGE")
print("=" * 74)
print(f"labels absent from the package entirely : {len(missing):,}")
for k, v in list(missing.items())[:15]:
    print(f"   {k!r}  (source had {v})")
print(f"labels present but with fewer copies    : {len(fewer):,}")
for k, (a, b) in list(fewer.items())[:15]:
    print(f"   {k!r}  source {a} -> package {b}")
print()
if not missing and not fewer:
    print("VERDICT: every ACTIV label in the source is in the package, with the "
          "same count.")
else:
    print(f"VERDICT: {len(missing)} label(s) lost entirely, "
          f"{len(fewer)} with fewer copies -- inspect above.")
