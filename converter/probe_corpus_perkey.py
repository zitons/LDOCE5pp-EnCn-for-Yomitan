"""Per-KEY comparison (the previous probe compared a single source record
against only the first package row, which is wrong for the 269 keys that have
several records).

For every key: total .asset.corpus blocks across ALL its source records, vs
total ld-panel-corpus across ALL its package rows.
    panels == assets  -> faithful (the original draws one badge per .asset)
    panels >  assets  -> merge logic failed (consecutive assetlinks not merged,
                         or orphan assetlinks each opening their own panel)
    panels <  assets  -> content lost
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

z = zipfile.ZipFile(ZIP)
rowmap = {}
for n in z.namelist():
    if re.fullmatch(r"term_bank_\d+\.json", n):
        for r in json.loads(z.read(n)):
            if r[4] > 0:
                rowmap.setdefault(r[0], []).append(r)


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


src_assets = Counter()      # key -> total asset.corpus blocks
src_links = Counter()       # key -> total assetlink.corpus blocks
records = Counter()
for key, content in M.iter_records(SIDE):
    k = M.strip_invisible(key).strip()
    if not k or k not in rowmap:
        continue
    kind, _ = M.classify_record(k, content)
    if kind != "entry":
        continue
    records[k] += 1
    soup = BeautifulSoup(content, "lxml")
    for a in soup.find_all("div"):
        cls = set(a.get("class") or [])
        if "asset" in cls and "corpus" in cls:
            src_assets[k] += 1
        elif "assetlink" in cls and "corpus" in cls:
            src_links[k] += 1

out_panels = Counter()
for k, rs in rowmap.items():
    for r in rs:
        out_panels[k] += count_panels(r[5])

dist = Counter()
bad_more = []
bad_less = []
for k in src_assets:
    a, p = src_assets[k], out_panels.get(k, 0)
    dist[(a, p)] += 1
    if p > a:
        bad_more.append((k, a, p, src_links[k], records[k]))
    elif p < a:
        bad_less.append((k, a, p, src_links[k], records[k]))

print(f"keys with corpus content: {len(src_assets)}")
print("\n(assets, panels) -> keys")
for (a, p), c in sorted(dist.items()):
    flag = "   <== panels > assets" if p > a else ("   <== panels < assets" if p < a else "")
    print(f"  assets={a:>3} panels={p:>3} : {c:>6}{flag}")

print(f"\npanels > assets : {len(bad_more)} keys")
for k, a, p, l, rec in sorted(bad_more, key=lambda x: -(x[2] - x[1]))[:20]:
    print(f"  {k!r:42} assets={a} panels={p} links={l} records={rec}")
print(f"\npanels < assets : {len(bad_less)} keys")
for k, a, p, l, rec in sorted(bad_less, key=lambda x: (x[2] - x[1]))[:20]:
    print(f"  {k!r:42} assets={a} panels={p} links={l} records={rec}")
