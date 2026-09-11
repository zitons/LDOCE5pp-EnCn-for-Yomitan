"""Find word-family blocks where an `opp` subtree (or any part) contains
span.w / span.rootword / span.crossRef that are NOT anchors -- those fall into
the generic inline branch, losing their link and polluting the unknown-class
report. Prints concrete source snippets and compares text with the output."""
import json
import re
import sys
import zipfile

from bs4 import BeautifulSoup, Tag

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"
ZIP = r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.11.zip"
LIMIT = 6000

z = zipfile.ZipFile(ZIP)
rows = {}
for n in z.namelist():
    if re.fullmatch(r"term_bank_\d+\.json", n):
        for r in json.loads(z.read(n)):
            rows.setdefault(r[0], []).append(r)

non_anchor = []          # (word, class, has_href, text)
checked = 0
for key, content in M.iter_records(SIDE):
    k = M.strip_invisible(key).strip()
    if not k:
        continue
    kind, _ = M.classify_record(k, content)
    if kind != "entry":
        continue
    checked += 1
    if checked > LIMIT:
        break
    soup = BeautifulSoup(content, "lxml")
    for fam in soup.find_all("span", class_="LDOCE_word_family"):
        for el in fam.find_all("span", recursive=True):
            cls = set(el.get("class") or [])
            if cls & {"w", "rootword", "crossRef"} and el.find_parent("a") is None:
                non_anchor.append((k, " ".join(sorted(cls)),
                                   bool(el.get("href")),
                                   el.get_text(" ", strip=True)[:40]))

print(f"entries scanned: {checked}")
print(f"non-anchor span with w/rootword/crossRef inside a word family: {len(non_anchor)}")
seen = set()
for w, cls, href, txt in non_anchor:
    sig = (cls, href)
    if sig in seen:
        continue
    seen.add(sig)
    print(f"  {w!r:14} class={cls!r:42} href={href} text={txt!r}")
    if len(seen) > 12:
        break
