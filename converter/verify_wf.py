"""Verify the T10 (duplicate word-family panel) and tag-cap fixes.

(a) package side: every T10 word must have exactly ONE ld-panel-wf panel;
(b) source side: the renderer's guard must select exactly the 38 headerless
    blocks (independent bs4 re-check of the predicate, incl. 'Independent, the'
    which --test-words cannot express because it splits on commas);
(c) tag cap: 'about'/'back' must now carry their S/W levels in definitionTags.
"""
import io
import json
import re
import zipfile

from bs4 import BeautifulSoup

ZIP = r"C:\workspace\ldoce\yomitan_wf_test\LDOCE5pp_Yomitan_2026.09.11_DEBUG.zip"
SIDE = r"C:\workspace\ldoce\extract\LDOCE5++ V 2-15.mdx.txt"

T10 = ["close", "cooperate", "cooperation", "cooperative", "definite", "definitely",
       "displace", "displacement", "enable", "explicit", "external", "implication",
       "implicit", "indefinite", "indefinitely", "independence", "insight",
       "insightful", "interaction", "internal", "item", "itemize", "reaction",
       "removal", "remove", "remover", "research", "researcher", "symbol",
       "symbolic", "symbolism", "symbolize", "transform", "transformation",
       "uncooperative", "undertake", "undertaking"]

z = zipfile.ZipFile(ZIP)
rows = {}
for n in z.namelist():
    if re.fullmatch(r"term_bank_\d+\.json", n):
        for r in json.loads(z.read(n)):
            rows.setdefault(r[0], []).append(r)

print("=== (a) T10 words in the rebuilt package ===")
bad = 0
missing = 0
for w in T10:
    rs = rows.get(w)
    if not rs:
        missing += 1
        continue
    counts = []
    tags = []
    for r in rs:
        if r[4] > 0:
            blob = json.dumps(r[5], ensure_ascii=False)
            counts.append(blob.count('"ld-panel-wf"'))
            tags.append(r[2])
    ok = all(c <= 1 for c in counts) and any(c == 1 for c in counts)
    if not ok:
        bad += 1
        print(f"  FAIL {w!r}: panels per entry row = {counts} tags={tags}")
print(f"  checked={len(T10)} present={len(T10)-missing} not-in-this-build={missing} "
      f"with >1 panel={bad}")

print("\n=== (b) source-side re-check of the guard predicate ===")
soup_hits = 0
tot = 0
keys = []
key = None
buf = []
with io.open(SIDE, encoding="utf-8", newline="") as fh:
    for line in fh:
        line = line.rstrip("\r\n")
        if line == "</>":
            if key:
                c = "\n".join(buf)
                if "wordfams" in c:
                    s = BeautifulSoup(c, "lxml")
                    for wf in s.select("div.wordfams"):
                        tot += 1
                        if wf.find("span", class_="LDOCE5pp_sensefold",
                                   recursive=False) is None:
                            soup_hits += 1
                            keys.append(key)
            key = None
            buf = []
        elif key is None and not buf:
            key = line
        else:
            buf.append(line)
print(f"  div.wordfams parsed with bs4: {tot}")
print(f"  without direct-child sensefold (guard skips these): {soup_hits}")
print("  includes 'Independent, the':", "Independent, the" in keys)
print("  sample:", keys[:6])

print("\n=== (c) tag cap fix ===")
for w, want in (("about", "W2"), ("back", "S2"), ("improve", "S2")):
    for r in rows.get(w, []):
        if r[4] > 0:
            print(f"  {w!r}: tags={r[2]!r}  contains {want}: {want in r[2].split()}")
