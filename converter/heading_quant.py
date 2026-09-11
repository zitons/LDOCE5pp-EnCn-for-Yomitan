"""Quantify the panel-heading question: how often does a source box heading
carry real content that our generic fallback title would replace?"""
import collections
import re
import sys

from bs4 import BeautifulSoup

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 2500

known = set(M.PANEL_TITLES_ZH.keys())
headings = collections.Counter()
n = 0
examples = []
for key, content in M.iter_records(SIDE):
    k = M.strip_invisible(key).strip()
    if not k:
        continue
    kind, _ = M.classify_record(k, content)
    if kind != "entry":
        continue
    n += 1
    if n > LIMIT:
        break
    soup = BeautifulSoup(content, "lxml")
    for h in soup.find_all(class_="lm5ppBoxHead"):
        txt = re.sub(r"\s+", " ", h.get_text(" ", strip=True)).strip()
        if not txt:
            continue
        headings[txt] += 1
        low = txt.lower().strip(" :：.。")
        if low not in known and len(examples) < 25:
            examples.append((k, txt))

print(f"entries scanned = {n}")
print(f"distinct box headings = {len(headings)}  total = {sum(headings.values())}")
print()
print("=== headings NOT in PANEL_TITLES_ZH (would fall back to the generic title) ===")
weird = [(t, c) for t, c in headings.items()
         if t.lower().strip(" :：.。") not in known]
print(f"distinct = {len(weird)}  occurrences = {sum(c for _, c in weird)}")
for t, c in sorted(weird, key=lambda x: -x[1])[:25]:
    print(f"  {c:>5}  {t[:100]!r}")
print()
print("=== examples with word ===")
for k, t in examples[:20]:
    print(f"  {k!r}: {t[:90]!r}")
print()
print("=== titles that ARE mapped (sanity) ===")
for t, c in sorted(headings.items(), key=lambda x: -x[1])[:12]:
    low = t.lower().strip(" :：.。")
    tag = "mapped->" + str(M.PANEL_TITLES_ZH[low][0]) if low in known else "FALLBACK"
    print(f"  {c:>5}  {t[:60]!r:>64}  {tag}")
