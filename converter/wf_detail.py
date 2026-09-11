"""Print the raw <span class="LDOCE_word_family"> subtree for chosen words, and
the rendered word-family panel, side by side."""
import io
import json
import re
import sys
import zipfile

from bs4 import BeautifulSoup

SIDE = r"C:\workspace\ldoce\extract\LDOCE5++ V 2-15.mdx.txt"
ZIP = r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.11.zip"
words = set(sys.argv[1:]) or {"advantage"}

key = None
buf = []
with io.open(SIDE, encoding="utf-8", newline="") as fh:
    for line in fh:
        line = line.rstrip("\r\n")
        if line == "</>":
            if key in words:
                c = "\n".join(buf)
                soup = BeautifulSoup(c, "lxml")
                print("=" * 76)
                print("SOURCE word-family:", key)
                for wf in soup.select("div.wordfams"):
                    fam = wf.find("span", class_="LDOCE_word_family")
                    if fam is None:
                        continue
                    print("  RAW:", re.sub(r"\s+", " ", str(fam))[:700])
                    print()
                    print("  DIRECT CHILDREN of LDOCE_word_family:")
                    for ch in fam.children:
                        if getattr(ch, "name", None):
                            print(f"     <{ch.name} class={' '.join(ch.get('class') or [])!r}>"
                                  f"  text={ch.get_text(' ', strip=True)[:60]!r}")
                        elif str(ch).strip():
                            print(f"     TEXT NODE: {str(ch).strip()[:60]!r}")
            key = None
            buf = []
        elif key is None and not buf:
            key = line
        else:
            buf.append(line)

print()
print("=" * 76)
print("RENDERED word-family panel from the package:")
z = zipfile.ZipFile(ZIP)
want = words
for n in z.namelist():
    if not re.fullmatch(r"term_bank_\d+\.json", n):
        continue
    for r in json.loads(z.read(n)):
        if r[0] not in want or r[4] <= 0:
            continue
        blob = json.dumps(r[5], ensure_ascii=False)
        if '"ld-panel-wf"' not in blob:
            print(f"  {r[0]!r}: NO word-family panel")
            continue
        # print just the wf group words
        m = re.findall(r'"ld-wf-(?:pos|word|root)","content":"([^"]+)"', blob)
        print(f"  {r[0]!r}: {m[:24]}")
        want = want - {r[0]}
