"""T10 check: count div.wordfams blocks whose first child is not the sensefold
header (i.e. the blocks the original dictionary leaves collapsed/hidden), and
count ld-panel-wf panels per word in the shipped package."""
import io
import json
import re
import sys
import zipfile
from collections import Counter

SIDE = r"C:\workspace\ldoce\extract\LDOCE5++ V 2-15.mdx.txt"
ZIP = r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.11.zip"

pat = re.compile(r'<div class="wordfams">(.{0,100})', re.S)
tot = 0
headless = 0
keys = []
key = None
buf = []


def scan(k, c):
    global tot, headless
    for m in pat.finditer(c):
        tot += 1
        seg = m.group(1).lstrip()
        if not seg.startswith('<span class="LDOCE5pp_sensefold'):
            headless += 1
            if len(keys) < 15:
                keys.append(k)


with io.open(SIDE, encoding="utf-8", newline="") as fh:
    for line in fh:
        line = line.rstrip("\r\n")
        if line == "</>":
            if key:
                scan(key, "\n".join(buf))
            key = None
            buf = []
        elif key is None and not buf:
            key = line
        else:
            buf.append(line)
    if key:
        scan(key, "\n".join(buf))

print(f"div.wordfams total={tot}  headless(T10)={headless}")
print("headless sample words:", keys)

# how do those words look in the package?
z = zipfile.ZipFile(ZIP)
banks = sorted((n for n in z.namelist() if re.fullmatch(r"term_bank_\d+\.json", n)),
               key=lambda n: int(re.search(r"\d+", n).group()))
want = set(keys)
found = {}
for b in banks:
    for r in json.loads(z.read(b)):
        if r[0] in want and r[0] not in found and r[4] > 0:
            blob = json.dumps(r[5], ensure_ascii=False)
            found[r[0]] = (blob.count('"ld-panel-wf"'), blob.count("Word family"))
for w in keys[:10]:
    if w in found:
        print(f"  {w!r}: ld-panel-wf panels={found[w][0]}  'Word family' headers={found[w][1]}")

# global: how many entry rows carry 2+ word-family panels
multi = 0
for b in banks:
    for r in json.loads(z.read(b)):
        if r[4] > 0:
            blob = json.dumps(r[5], ensure_ascii=False)
            if blob.count('"ld-panel-wf"') >= 2:
                multi += 1
print("entry rows with >=2 word-family panels:", multi)
