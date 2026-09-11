"""Check Inflections fidelity: every surface form in the source Inflections span
should appear in the rendered row (the '·' separator and dropped parentheses are
deliberate styling, but no FORM may go missing)."""
import json
import re
import sys

from bs4 import BeautifulSoup

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"
LIMIT = 4000

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
    if len(recs) >= LIMIT:
        break

r = M.LdoceRenderer(ti)
checked = 0
bad = 0
examples = []
for k, c in recs:
    s = BeautifulSoup(c, "lxml")
    head = s.find("span", class_="Head")
    if head is None:
        continue
    infl = head.find("span", class_="Inflections")
    if infl is None:
        continue
    checked += 1
    blob = json.dumps(r.render_record(k, c) or [], ensure_ascii=False)
    src = re.sub(r"\s+", " ", infl.get_text(" ", strip=True))
    forms = [f for f in re.findall(r"[A-Za-z][A-Za-z\u2019'-]{2,}", src)
             if f.lower() not in ("plural", "singular", "also", "and")]
    miss = [f for f in forms if f not in blob and f.lower() not in blob.lower()]
    if miss:
        bad += 1
        if len(examples) < 12:
            examples.append((k, src[:80], miss[:6]))

print(f"entries with Head>Inflections = {checked}")
print(f"with a missing surface form  = {bad} ({bad*100.0/max(checked,1):.2f}%)")
for k, src, miss in examples:
    print(f"  {k!r:16} src={src!r}")
    print(f"  {'':16} MISSING {miss}")
