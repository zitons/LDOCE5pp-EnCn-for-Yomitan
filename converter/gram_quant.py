"""Quantify head-GRAM fidelity: for every entry whose Head carries a GRAM span,
compare what the source says with what the renderer emits."""
import collections
import json
import re
import sys
import zipfile

from bs4 import BeautifulSoup

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"
ZIP = r"C:\workspace\ldoce\yomitan_wf_test\LDOCE5pp_Yomitan_2026.09.11_DEBUG.zip"
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 1500

z = zipfile.ZipFile(ZIP)
rows = {}
for n in z.namelist():
    if re.fullmatch(r"term_bank_\d+\.json", n):
        for r in json.loads(z.read(n)):
            rows.setdefault(r[0], []).append(r)

n = 0
head_gram = 0
bracket_in_src = 0
bracket_lost = 0
singular_lost = 0
samples = []
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
    head = soup.find("span", class_="Head")
    if head is None:
        continue
    g = head.find("span", class_="GRAM")
    if g is None:
        continue
    head_gram += 1
    src_txt = re.sub(r"\s+", " ", g.get_text(" ", strip=True)).strip()
    has_br = "[" in src_txt or "]" in src_txt
    if has_br:
        bracket_in_src += 1
    if k not in rows:
        continue
    entry_rows = [r for r in rows[k] if r[4] > 0]
    if not entry_rows:
        continue
    blob = json.dumps(entry_rows[0][5], ensure_ascii=False)
    if has_br and ("[" not in blob or "]" not in blob):
        bracket_lost += 1
        if len(samples) < 10:
            samples.append((k, src_txt[:60]))
    if src_txt.lower().startswith("singular") and "singular" not in blob:
        singular_lost += 1

print(f"entries scanned            = {n}")
print(f"entries with Head>GRAM     = {head_gram}")
print(f"  source GRAM has brackets = {bracket_in_src}")
print(f"  brackets LOST in output  = {bracket_lost}")
print(f"  'singular' lost          = {singular_lost}")
print()
print("samples:")
for k, t in samples:
    print(f"  {k!r}: source GRAM = {t!r}")
