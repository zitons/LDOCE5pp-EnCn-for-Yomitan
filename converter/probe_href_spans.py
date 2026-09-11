"""Corpus-wide: (a) count span[href] (link-carrying spans that are not <a>),
grouped by class; (b) count elements with class token 'w'/'rootword'/'crossRef'
that live OUTSIDE an LDOCE_word_family, to explain the build's unknown-class
counts."""
import re
import sys
from collections import Counter

from bs4 import BeautifulSoup

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"
LIMIT = 8000

span_href = Counter()
span_href_in_wf = Counter()
outside_wf = Counter()
outside_samples = {}
n = 0
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
    for el in soup.find_all("span"):
        cls = " ".join(sorted(el.get("class") or []))
        if el.get("href"):
            span_href[cls] += 1
            if el.find_parent("span", class_="LDOCE_word_family") is not None:
                span_href_in_wf[cls] += 1
        toks = set(el.get("class") or [])
        if toks & {"w", "rootword", "crossRef"}:
            if el.find_parent("span", class_="LDOCE_word_family") is None:
                outside_wf[cls] += 1
                if cls not in outside_samples:
                    outside_samples[cls] = (k, el.get_text(" ", strip=True)[:44])

print(f"entries scanned: {n}")
print()
print("=== span[href] (non-anchor links), by class ===")
for c, cnt in span_href.most_common(12):
    print(f"  {cnt:>6}  {c!r}   (in word family: {span_href_in_wf.get(c, 0)})")
print()
print("=== class w/rootword/crossRef spans OUTSIDE LDOCE_word_family ===")
for c, cnt in outside_wf.most_common(12):
    k, t = outside_samples.get(c, ("", ""))
    print(f"  {cnt:>6}  {c!r:44} e.g. {k!r}: {t!r}")
