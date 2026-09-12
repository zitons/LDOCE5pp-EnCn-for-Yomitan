"""Structural validity of the native-list output.

An <li> is only valid inside <ol>/<ul>/<menu>. Because list members are now
emitted as <li> by their own renderers and grouped by group_into_list() in
_children_blocks(), an item that is never grouped would become an ORPHAN <li>
directly under a div -- invalid HTML that browsers render inconsistently.

Checks, on a built package:
  1. every <li> has an <ol>/<ul> parent
  2. every <ol>/<ul> has only <li> children (plus whitespace text)
  3. list items are not nested directly in another list item without a list
  4. report ol/ul/li counts and any orphan examples
"""
import json
import re
import sys
import zipfile
from collections import Counter

ZIP = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\workspace\ldoce\yomitan_cap_test\LDOCE5pp_Yomitan_2026.09.12_DEBUG.zip"

LIST_TAGS = {"ol", "ul", "menu"}
ITEM_TAG = "li"


def walk(node, parent_tag, parent_cls, stats, problems, word):
    if isinstance(node, list):
        for x in node:
            walk(x, parent_tag, parent_cls, stats, problems, word)
        return
    if not isinstance(node, dict):
        return
    tag = node.get("tag")
    cls = (node.get("data") or {}).get("class")
    if tag:
        stats[f"tag:{tag}"] += 1
    if tag == ITEM_TAG:
        if parent_tag not in LIST_TAGS:
            stats["orphan_li"] += 1
            if len(problems) < 12:
                problems.append(("orphan <li>", word, parent_tag, parent_cls, cls))
    if tag in LIST_TAGS:
        kids = node.get("content")
        kids = kids if isinstance(kids, list) else [kids]
        for k in kids:
            if isinstance(k, str):
                continue
            if isinstance(k, dict) and k.get("tag") != ITEM_TAG:
                stats["non_li_in_list"] += 1
                if len(problems) < 12:
                    problems.append(("non-<li> in list", word, tag, cls,
                                     k.get("tag")))
    for k, v in node.items():
        if k != "data":
            walk(v, tag, cls, stats, problems, word)


z = zipfile.ZipFile(ZIP)
stats = Counter()
problems = []
words = 0
for n in z.namelist():
    if not re.fullmatch(r"term_bank_\d+\.json", n):
        continue
    for r in json.loads(z.read(n)):
        if r[4] <= 0:
            continue
        words += 1
        walk(r[5], None, None, stats, problems, r[0])

print(f"package: {ZIP.split(chr(92))[-1]}")
print(f"rows   : {words:,}")
print()
print("tag counts:")
for k in sorted(k for k in stats if k.startswith("tag:")):
    if k.split(":")[1] in ("ol", "ul", "li", "div", "span", "details", "summary"):
        print(f"  {k:14} {stats[k]:>10,}")
print()
print(f"orphan <li> (invalid)      : {stats['orphan_li']:,}")
print(f"non-<li> child of ol/ul    : {stats['non_li_in_list']:,}")
print()
for kind, w, pt, pc, c in problems[:10]:
    print(f"  {kind}: word={w!r} parent=<{pt}.{pc}> child/class={c!r}")
print()
ok = stats["orphan_li"] == 0 and stats["non_li_in_list"] == 0
print("RESULT:", "PASS -- list structure is valid" if ok else "FAIL -- invalid list nesting")
sys.exit(0 if ok else 1)
