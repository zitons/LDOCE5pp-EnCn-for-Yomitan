"""Definitive: run the real renderer over every entry and capture the exact
element that logs w / rootword / crossRef as an unknown class.

Fast pre-filter: those tokens can only be produced from an entry that contains
an opp or a word family, so everything else is skipped without parsing.
"""
import sys
from collections import Counter

from bs4 import BeautifulSoup

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

WATCH = {"w", "rootword", "crossRef"}
SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"

ti = M.TermIndex()
recs = []
for k, c in M.iter_records(SIDE):
    kk = M.strip_invisible(k).strip()
    if not kk:
        continue
    kind, _ = M.classify_record(kk, c)
    if kind == "entry":
        ti.add(kk)
        recs.append((kk, c))
print(f"entries: {len(recs)}", flush=True)

r = M.LdoceRenderer(ti)
found = []
for k, c in recs:
    if 'class="opp"' not in c and "LDOCE_word_family" not in c:
        continue
    before = {t: r.unknown_classes.get(t, 0) for t in WATCH}
    r.render_record(k, c)
    after = {t: r.unknown_classes.get(t, 0) for t in WATCH}
    if any(after[t] > before[t] for t in WATCH):
        soup = BeautifulSoup(c, "lxml")
        detail = []
        for el in soup.find_all(["span", "a"]):
            cls = set(el.get("class") or [])
            if cls & WATCH:
                par = el.parent
                pcls = " ".join(par.get("class") or []) if par is not None else "?"
                detail.append(f"{el.name}.{' '.join(sorted(cls))} parent={par.name}.{pcls} href={bool(el.get('href'))}")
        found.append((k, detail[:6]))

print(f"entries producing unknown w/rootword/crossRef: {len(found)}")
for k, d in found[:10]:
    print(f"  {k!r}")
    for x in d:
        print(f"      {x}")
print("final counter:", {t: r.unknown_classes.get(t, 0) for t in WATCH})
