"""Triage the no-CSS glue patterns: which are REAL defects and which are my
detector firing on legitimate text?

For each pattern, print several real hits with enough context to judge, and say
which structural boundary produced them.
"""
import json
import re
import sys
import zipfile
from collections import Counter

ZIP = r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.12.zip"


def flatten(node, acc):
    if isinstance(node, str):
        acc.append(node)
    elif isinstance(node, list):
        for x in node:
            flatten(x, acc)
    elif isinstance(node, dict):
        flatten(node.get("content", ""), acc)
    return acc


CHECKS = [
    ("A camel-glue", re.compile(r"[a-z]\d*[A-Z][a-z]")),
    ("B bracket-glue", re.compile(r"[A-Za-z\u2019'-]\d*\[")),
    ("C paren-glue", re.compile(r"\)[A-Za-z]")),
    ("E slash-glue", re.compile(r"[a-z\u2019']\d*/")),
    ("G pos-glue", re.compile(
        r"[a-z](noun|verb|adjective|adverb|preposition|conjunction|determiner|"
        r"pronoun|exclamation|prefix|suffix|article)")),
]

z = zipfile.ZipFile(ZIP)
shown = Counter()
samples = {name: [] for name, _ in CHECKS}

for n in z.namelist():
    if not re.fullmatch(r"term_bank_\d+\.json", n):
        continue
    for r in json.loads(z.read(n)):
        if r[4] <= 0:
            continue
        txt = "".join(flatten(r[5], []))
        for name, pat in CHECKS:
            if len(samples[name]) >= 6:
                continue
            m = pat.search(txt)
            if m:
                s = max(0, m.start() - 60)
                samples[name].append((r[0], txt[s:m.end() + 60]))

for name, _ in CHECKS:
    print("=" * 100)
    print(name)
    print("=" * 100)
    for w, frag in samples[name]:
        print(f"  {w!r}:")
        print(f"     ...{re.sub(chr(92)+'s+', ' ', frag)}...")
    print()
