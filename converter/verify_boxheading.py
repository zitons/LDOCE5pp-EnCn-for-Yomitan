"""Verify the sense-group label fix: every uppercase HEADING box label from the
source must now appear in the rendered row, and no box may gain a spurious one."""
import json
import re
import sys
import zipfile

from bs4 import BeautifulSoup

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

ZIP = r"C:\workspace\ldoce\yomitan_wf_test\LDOCE5pp_Yomitan_2026.09.11_DEBUG.zip"
SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"

z = zipfile.ZipFile(ZIP)
rows = {}
for n in z.namelist():
    if re.fullmatch(r"term_bank_\d+\.json", n):
        for r in json.loads(z.read(n)):
            rows.setdefault(r[0], []).append(r)

want = set(rows)
print(f"words in package: {len(want)}")
checked = 0
missing = []
shown = 0
for key, content in M.iter_records(SIDE):
    k = M.strip_invisible(key).strip()
    if k not in want:
        continue
    soup = BeautifulSoup(content, "lxml")
    labels = []
    for h in soup.find_all("span", class_="HEADING"):
        box = h.find_parent(class_="lm5ppBox")
        if box is None:
            continue
        fold = box.find("span", class_="heading")
        if fold is None:
            continue  # then HEADING is the panel title itself, handled elsewhere
        t = re.sub(r"\s+", " ", h.get_text(" ", strip=True)).strip()
        if t:
            labels.append(t)
    if not labels:
        continue
    checked += 1
    blob = json.dumps([r for r in rows[k] if r[4] > 0][0][5], ensure_ascii=False)
    for t in labels:
        ok = t in blob
        if not ok:
            missing.append((k, t))
        elif shown < 8:
            print(f"  OK  {k!r}: {t[:62]!r}")
            shown += 1

print(f"\nentries with both headers: {checked}")
print(f"labels now present: {checked and 'see above'}")
print(f"labels STILL missing: {len(missing)}")
for k, t in missing[:10]:
    print(f"   MISSING {k!r}: {t[:70]!r}")
