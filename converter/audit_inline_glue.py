"""DEPRECATED -- DO NOT TRUST THE NUMBERS THIS PRINTS.

superseded: inline-only refinement of the same static idea. Still
over-counts and still cannot see what a browser actually renders.
Use audit_nocss_final.py.

Kept only as a record of the investigation. See REVIEW.md D33 and
HANDOVER.md pitfall 63.
"""
import json
import re
import sys
import zipfile
from collections import Counter

ZIP = r"C:\workspace\ldoce\yomitan_cap_test\LDOCE5pp_Yomitan_2026.09.12_DEBUG.zip"

BLOCK_TAGS = {"div", "details", "summary", "ol", "ul", "li", "table", "thead",
              "tbody", "tr", "td", "th", "p", "h1", "h2", "h3"}


def text_of(n):
    if isinstance(n, str):
        return n
    if isinstance(n, list):
        return "".join(text_of(x) for x in n)
    if isinstance(n, dict):
        return text_of(n.get("content", ""))
    return ""


def tag_of(n):
    if isinstance(n, dict):
        return n.get("tag", "span")
    return None


def cls_of(n):
    if isinstance(n, dict):
        c = (n.get("data") or {}).get("class")
        if c:
            return c
        if n.get("tag") == "a":
            return "a"
        return n.get("tag", "?")
    if isinstance(n, str):
        return "TEXT"
    return "?"


def is_block(n):
    t = tag_of(n)
    if t is None:
        return False          # a bare string: inline
    return t in BLOCK_TAGS


# a glue = inline sibling left whose text ends with a word char, and inline
# sibling right whose text starts with a word char, with nothing between
LEFT_RE = re.compile(r"[A-Za-z\u4e00-\u9fff\u2019')\]\u25cf\u25cb\d]$")
RIGHT_RE = re.compile(r"^[A-Za-z\u4e00-\u9fff\u25cf\u25cb(]")

seams = Counter()
samples = {}


def walk(node, parent, word):
    if isinstance(node, list):
        for i in range(len(node) - 1):
            a, b = node[i], node[i + 1]
            # only inline-vs-inline can glue
            if is_block(a) or is_block(b):
                continue
            ta, tb = text_of(a), text_of(b)
            if not ta or not tb:
                continue
            if LEFT_RE.search(ta) and RIGHT_RE.match(tb):
                key = (parent, cls_of(a), cls_of(b))
                seams[key] += 1
                samples.setdefault(key, (word, ta[-26:], tb[:26]))
        for x in node:
            walk(x, parent, word)
    elif isinstance(node, dict):
        walk(node.get("content", ""), cls_of(node), word)


z = zipfile.ZipFile(ZIP)
scanned = 0
rows_with_glue = set()
for n in z.namelist():
    if not re.fullmatch(r"term_bank_\d+\.json", n):
        continue
    for r in json.loads(z.read(n)):
        if r[4] <= 0:
            continue
        scanned += 1
        walk(r[5], "ROOT", r[0])

print(f"entries scanned: {scanned:,}")
print(f"distinct inline-glue seams: {sum(seams.values()):,}")
print(f"\n{'parent':24} {'left':24} {'right':24} {'count':>8}  example")
print("-" * 138)
for (parent, a, b), n in seams.most_common(30):
    w, ta, tb = samples[(parent, a, b)]
    print(f"{parent:24} {a:24} {b:24} {n:>8,}  {w!r}: {ta!r}|{tb!r}")
