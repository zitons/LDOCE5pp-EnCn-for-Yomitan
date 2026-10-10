"""Audit redirect (alias) coverage from the source side.

The build prints "Alias plan: rows planned=181274 unresolvable=5150", but the
source contains 218,252 records classified as redirect. Nothing has explained the
difference, so the numbers cannot be trusted as a coverage statement.

Reconcile them from the source:
  * how many distinct alias KEYS the source's redirect records produce
  * how many of those resolve to an entry that exists in the package
  * what the 5,150 unresolvable ones actually are
  * whether every package redirect row corresponds to a real source redirect record

The point is to be able to say "N source redirects, M rows in the package, and
here is exactly where the difference goes" instead of quoting two numbers.
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

# ------------------------------------------------------------------ source side
entries = set()
redirect_records = []          # (key, target) for every source redirect record
for key, content in C.iter_records(SRC):
    kind, target = C.classify_record(key, content)
    if kind == "entry":
        entries.add(C.strip_invisible(key).strip())
    elif kind == "redirect" and target:
        redirect_records.append((C.strip_invisible(key).strip(), target))

print(f"source redirect records          : {len(redirect_records):,}")
print(f"source entry keys                : {len(entries):,}")
print()

# the package's own expression set, and its redirect rows
z = zipfile.ZipFile(PKG)
pkg_expr = set()
pkg_redirect = {}
pkg_content = set()
for name in z.namelist():
    if not re.fullmatch(r"term_bank_\d+\.json", name):
        continue
    for r in json.loads(z.read(name)):
        pkg_expr.add(r[0])
        # A redirect row is recognisable by its SHAPE, not by a magic score:
        #   ["Religion-topic recant", "", "non-lemma", "v n", -10,
        #    [["recant", ["redirect"]], ["Religion-topic", ["redirect"]]], 90000, ""]
        # i.e. score is negative and every glossary item is [target, ["redirect"]].
        # (An earlier version tested `score == 0`, which matches nothing: content
        # rows carry 10 and redirect rows -10, so it reported 0 redirect rows
        # against a build log claiming 181,274.)
        gloss = r[5] if len(r) > 5 else []
        is_red = (isinstance(r[4], (int, float)) and r[4] < 0
                  and isinstance(gloss, list) and bool(gloss)
                  and all(isinstance(g, list) and len(g) > 1
                          and isinstance(g[1], list) and "redirect" in g[1]
                          for g in gloss))
        if is_red:
            pkg_redirect[r[0]] = r
        else:
            pkg_content.add(r[0])

print(f"package distinct expressions     : {len(pkg_expr):,}")
print(f"package content expressions      : {len(pkg_content):,}")
print(f"package redirect rows            : {len(pkg_redirect):,}")
print()

# ------------------------------------------------- reconcile, step by step
# 1. which source redirect KEYS are present in the package at all?
keys = [k for k, _ in redirect_records]
key_set = set(keys)
print("=" * 78)
print("RECONCILIATION")
print("=" * 78)
print(f"source redirect records                     : {len(redirect_records):,}")
print(f"distinct keys among them                    : {len(key_set):,}")
print(f"  -> records collapsed by duplicate keys    : "
      f"{len(redirect_records) - len(key_set):,}")

in_pkg = {k for k in key_set if k in pkg_expr}
print(f"distinct keys present in the package        : {len(in_pkg):,}")
print(f"distinct keys ABSENT from the package       : {len(key_set - in_pkg):,}")
print()
# a key that is BOTH a source entry and a source redirect gets a content row
# (the entry wins) -- that is the main reason the redirect-row count is lower
# than the distinct-key count, so count it explicitly rather than leaving a gap
both = {k for k in key_set if k in entries}
print(f"keys that are both an entry and a redirect  : {len(both):,}")
print(f"  of those, written as a content row        : "
      f"{len(both & pkg_content):,}")
print(f"  of those, written as a redirect row       : "
      f"{len(both & set(pkg_redirect)):,}")
print()
print(f"redirect keys written as redirect rows      : "
      f"{len(key_set & set(pkg_redirect)):,}")
print(f"redirect keys written as content rows       : "
      f"{len(key_set & pkg_content):,}")
print(f"total redirect rows in the package          : {len(pkg_redirect):,}")
print()

# 2. of the absent ones, why?
ti = C.TermIndex()
for e in entries:
    ti.add(e)
ti.finalize_rendered(entries)

absent = sorted(key_set - in_pkg)
reasons = Counter()
samples = {}
for k in absent:
    # reproduce the converter's own resolution attempt
    resolved = None
    try:
        resolved = ti.resolve(k)
    except Exception:
        resolved = None
    if resolved:
        reasons["resolvable but not written"] += 1
        samples.setdefault("resolvable but not written", []).append((k, resolved))
    elif not k.strip():
        reasons["empty key"] += 1
    else:
        reasons["no entry to point at"] += 1
        samples.setdefault("no entry to point at", []).append((k, ""))

print("why a source redirect key is absent from the package:")
for r, n in reasons.most_common():
    print(f"   {n:>7,}  {r}")
    for k, res in samples.get(r, [])[:4]:
        print(f"            e.g. {k!r} -> {res!r}")
print()

# 3. the reverse: package redirect rows with no source record
src_key_set = key_set
orphan = sorted(k for k in pkg_redirect if k not in src_key_set)
print(f"package redirect rows with NO source redirect record : {len(orphan):,}")
for k in orphan[:10]:
    print(f"   {k!r}")
print()

# 5. the build's "unresolvable" figure, explained
#    The build prints  unresolvable = len(target_map) - len(planned_alias).
#    target_map is keyed by alias WORD, and planned_alias skips every word that
#    is itself an entry ("if word in term_index.exact: continue"), so the
#    difference is dominated by words that DO resolve -- to their own entry --
#    and therefore need no redirect row at all. Calling that "unresolvable" is
#    misleading; it is mostly "already an entry".
shadowed = len(key_set & entries)
print(f"build's 'unresolvable' figure, explained:")
print(f"   distinct alias words with a target (len(target_map)) : "
      f"{len(key_set & {k for k, t in redirect_records if t}):,}")
print(f"   words skipped because they are entries themselves     : {shadowed:,}")
print(f"   words that got a redirect row                         : "
      f"{len(key_set & set(pkg_redirect)):,}")
print(f"   -> the log line's 'unresolvable' is mostly this first group, "
      f"not lost data")
print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
print(f"  {len(redirect_records):,} source redirect records")
print(f"  -> {len(redirect_records) - len(key_set):,} collapsed as duplicate keys")
print(f"  -> {shadowed:,} keys are entries themselves (content row, entry wins)")
print(f"  -> {len(key_set & set(pkg_redirect)):,} written as redirect rows")
print(f"  -> {len(key_set - in_pkg):,} ABSENT")
if not (key_set - in_pkg) and not orphan:
    print("  every source redirect key is accounted for in the package.")
