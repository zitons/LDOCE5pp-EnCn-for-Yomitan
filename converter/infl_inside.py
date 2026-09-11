"""Precise: is the region label / 'same pronunciation' note INSIDE the
Inflections span, or a sibling (GEO) that render_head handles anyway?"""
import re
import sys

from bs4 import BeautifulSoup

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"

inside_same = 0
inside_region = 0
infl_total = 0
ex_same = []
ex_region = []
for key, content in M.iter_records(SIDE):
    k = M.strip_invisible(key).strip()
    if not k:
        continue
    kind, _ = M.classify_record(k, content)
    if kind != "entry":
        continue
    soup = BeautifulSoup(content, "lxml")
    head = soup.find("span", class_="Head")
    if head is None:
        continue
    for infl in head.find_all("span", class_="Inflections"):
        infl_total += 1
        txt = re.sub(r"\s+", " ", infl.get_text(" ", strip=True))
        if "same pronunciation" in txt:
            inside_same += 1
            if len(ex_same) < 4:
                ex_same.append((k, txt[:100]))
        if re.search(r"\b(BrE|AmE|British English|American English)\b", txt):
            inside_region += 1
            if len(ex_region) < 6:
                ex_region.append((k, txt[:120]))

print(f"Inflections spans (bs4, inside Head)  = {infl_total}")
print(f"  'same pronunciation' INSIDE span    = {inside_same}")
print(f"  region label INSIDE span            = {inside_region}")
print()
print("--- same pronunciation (inside) ---")
for k, t in ex_same:
    print(f"  {k!r}: {t!r}")
print("--- region label (inside) ---")
for k, t in ex_region:
    print(f"  {k!r}: {t!r}")
