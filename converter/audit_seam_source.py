"""Locate the STRUCTURAL source of each real no-CSS glue.

A (camel-glue) is the interesting one: it fires on boundaries like
    '...a pop' + 'American English' + ' spoken used when ...'
    '...equipment' + 'Word origin词源' + ' (1200-1300) ...'
    '屠宰场 ' + 'SYN slaughterhouse' + 'Corpus examples语料库例句' + 'abattoir'
i.e. block-level elements rendered back-to-back with no separating character.

This script finds, for each real glue, which two SC nodes are adjacent at the
seam, by walking the tree and recording (parent class, child index i, child i+1)
for every place where child[i] text ends with a letter/digit and child[i+1] text
starts with a letter -- with NO whitespace in between.
"""
import json
import re
import sys
import zipfile
from collections import Counter

ZIP = r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.12.zip"

SEAM = re.compile(r"[a-z\u4e00-\u9fff\u2019')\]]\d*(?=[A-Z\u4e00-\u9fff])")
SEAM2 = re.compile(r"\d(?![\d/:.])(?=[A-Za-z\u4e00-\u9fff])")


def text_of(n):
    if isinstance(n, str):
        return n
    if isinstance(n, list):
        return "".join(text_of(x) for x in n)
    if isinstance(n, dict):
        return text_of(n.get("content", ""))
    return ""


def cls_of(n):
    if not isinstance(n, dict):
        return "TEXT" if isinstance(n, str) else "?"
    c = (n.get("data") or {}).get("class")
    if c:
        return c
    if n.get("tag") == "a":
        return "a"
    return n.get("tag", "?")


seams = Counter()
samples = {}

def walk(node, parent_cls, word):
    if isinstance(node, list):
        for i in range(len(node) - 1):
            a, b = node[i], node[i + 1]
            ta, tb = text_of(a), text_of(b)
            if ta and tb:
                if SEAM.search(ta[-24:]) and re.match(r"[A-Z\u4e00-\u9fff]", tb):
                    key = (parent_cls, cls_of(a), cls_of(b))
                    seams[key] += 1
                    samples.setdefault(key, (word, ta[-30:], tb[:30]))
                elif re.search(r"[a-z\u4e00-\u9fff]\d*$", ta) and re.match(
                        r"[A-Z\u4e00-\u9fff]", tb):
                    key = (parent_cls, cls_of(a), cls_of(b))
                    seams[key] += 1
                    samples.setdefault(key, (word, ta[-30:], tb[:30]))
        for x in node:
            walk(x, parent_cls, word)
    elif isinstance(node, dict):
        walk(node.get("content", ""), cls_of(node), word)


z = zipfile.ZipFile(ZIP)
scanned = 0
for n in z.namelist():
    if not re.fullmatch(r"term_bank_\d+\.json", n):
        continue
    for r in json.loads(z.read(n)):
        if r[4] <= 0:
            continue
        scanned += 1
        walk(r[5], "ROOT", r[0])
        if scanned >= 12000:
            break
    if scanned >= 12000:
        break

print(f"entries scanned: {scanned:,}")
print(f"\n{'parent':22} {'left child':22} {'right child':22} {'count':>7}  example seam")
print("-" * 132)
for (parent, a, b), n in seams.most_common(28):
    w, ta, tb = samples[(parent, a, b)]
    print(f"{parent:22} {a:22} {b:22} {n:>7,}  {w!r}: {ta!r} | {tb!r}")
