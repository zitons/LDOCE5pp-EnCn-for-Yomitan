"""Precisely: which w/rootword/crossRef spans inside word families are NOT
direct children of LDOCE_word_family (those are the ones that miss the
render_wordfams branches), and what is their immediate parent?"""
import re
import sys
from collections import Counter

from bs4 import BeautifulSoup

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"
LIMIT = 6000

parents = Counter()
samples = {}
nested = 0
direct = 0
for key, content in M.iter_records(SIDE):
    k = M.strip_invisible(key).strip()
    if not k:
        continue
    kind, _ = M.classify_record(k, content)
    if kind != "entry":
        continue
    if M.__dict__.get("_c", 0) > LIMIT:
        break
    M._c = M.__dict__.get("_c", 0) + 1
    soup = BeautifulSoup(content, "lxml")
    for fam in soup.find_all("span", class_="LDOCE_word_family"):
        for el in fam.find_all("span", recursive=True):
            cls = set(el.get("class") or [])
            if not (cls & {"w", "rootword", "crossRef"}):
                continue
            par = el.parent
            pcls = " ".join(par.get("class") or []) if par is not None else "?"
            if par is not None and par.name == "span" and "LDOCE_word_family" in pcls:
                direct += 1
                continue
            nested += 1
            parents[f"{par.name}.{pcls or '(none)'}"] += 1
            if len(samples) < 400 and pcls not in samples:
                samples[pcls] = (k, " ".join(sorted(cls)),
                                 bool(el.get("href")), el.get_text(" ", strip=True)[:36])

print(f"scanned entries: {M.__dict__.get('_c', 0)}")
print(f"w/rootword/crossRef spans, DIRECT child of LDOCE_word_family : {direct}")
print(f"                                            NESTED (miss hooks) : {nested}")
print()
print("immediate parents of the nested ones:")
for p, n in parents.most_common(15):
    print(f"  {n:>6}  {p!r}")
print()
print("samples:")
for p, (w, cls, href, txt) in list(samples.items())[:14]:
    print(f"  parent={p!r:34} {w!r:14} class={cls!r:34} href={href} text={txt!r}")
