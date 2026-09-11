"""Is a multi-panel corpus section expected, or a merge bug?

The source pairs each <div class="asset corpus"> (the yellow "Examples from the
Corpus" header) with the following <div class="assetlink corpus"> body, and the
original stylesheet gives EVERY .asset its own visible badge. So:
    #corpus panels  ==  #asset blocks        -> faithful
    #panels >  #assets                       -> our merge logic failed to merge
                                               consecutive assetlinks (a real bug)

Reports the distribution and every entry where panels > assets.
"""
import json
import re
import sys
import zipfile
from collections import Counter

from bs4 import BeautifulSoup

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"
ZIP = r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.11.zip"
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 0

z = zipfile.ZipFile(ZIP)
rows = {}
for n in z.namelist():
    if re.fullmatch(r"term_bank_\d+\.json", n):
        for r in json.loads(z.read(n)):
            rows.setdefault(r[0], []).append(r)


def count_panels(node):
    n = 0
    if isinstance(node, list):
        for x in node:
            n += count_panels(x)
    elif isinstance(node, dict):
        if (node.get("data") or {}).get("class", "").split() == ["ld-panel-corpus"]:
            n += 1
        for k, v in node.items():
            if k != "data":
                n += count_panels(v)
    return n


dist = Counter()
mismatch = []
checked = 0
for key, content in M.iter_records(SIDE):
    k = M.strip_invisible(key).strip()
    if not k:
        continue
    kind, _ = M.classify_record(k, content)
    if kind != "entry":
        continue
    checked += 1
    if LIMIT and checked > LIMIT:
        break
    if k not in rows:
        continue
    soup = BeautifulSoup(content, "lxml")
    n_assets = 0
    for a in soup.find_all("div", class_="asset"):
        if "corpus" in (a.get("class") or []):
            n_assets += 1
    entry_rows = [r for r in rows[k] if r[4] > 0]
    if not entry_rows:
        continue
    n_panels = count_panels(entry_rows[0][5])
    dist[(n_assets, n_panels)] += 1
    if n_panels > n_assets:
        mismatch.append((k, n_assets, n_panels))

print(f"entries checked: {checked}")
print("\n(#asset blocks, #corpus panels) -> entries")
for (a, p), c in sorted(dist.items()):
    flag = "  <-- MISMATCH (merge bug)" if p > a else ""
    print(f"  assets={a}  panels={p}  :  {c:>6}{flag}")
print(f"\nentries where panels > assets: {len(mismatch)}")
for k, a, p in mismatch[:25]:
    print(f"  {k!r}: assets={a} panels={p}")
