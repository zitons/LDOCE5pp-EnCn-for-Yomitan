"""Word-family completeness gate.

For every entry, tokenise the text of the word-family blocks that the renderer
actually keeps (the sensefold-framed ones -- same guard as render_wordfams) and
compare it, as a multiset, with the text carried by the output ld-panel-wf
panels. Any token in the source that never reaches the output is real loss.

This is the guard that would have caught the two regressions introduced while
fixing opp (skipped loose text nodes) before a full rebuild.
"""
import collections
import json
import re
import sys
import zipfile

from bs4 import BeautifulSoup

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"
ZIP = r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.11.zip"
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
TOK = re.compile(r"[A-Za-z]+|[\u4e00-\u9fff]|\d+")

z = zipfile.ZipFile(ZIP)
rows = {}
for n in z.namelist():
    if re.fullmatch(r"term_bank_\d+\.json", n):
        for r in json.loads(z.read(n)):
            rows.setdefault(r[0], []).append(r)


def flatten(node, acc):
    if isinstance(node, str):
        acc.append(node)
    elif isinstance(node, list):
        for x in node:
            flatten(x, acc)
    elif isinstance(node, dict):
        flatten(node.get("content", ""), acc)
    return acc


def wf_text(node, acc):
    """Text inside ld-panel-wf panels only."""
    if isinstance(node, list):
        for x in node:
            wf_text(x, acc)
    elif isinstance(node, dict):
        if (node.get("data") or {}).get("class") == "ld-panel-wf":
            acc.append(flatten(node, []))
            return
        for k, v in node.items():
            if k != "data":
                wf_text(v, acc)
    return acc


n = 0
checked = 0
missing_total = collections.Counter()
missing_entries = 0
skipped = 0
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
    if k not in rows:
        skipped += 1
        continue
    soup = BeautifulSoup(content, "lxml")
    src_tokens = collections.Counter()
    kept = 0
    for wf in soup.find_all("div", class_="wordfams"):
        if wf.find("span", class_="LDOCE5pp_sensefold", recursive=False) is None:
            continue          # the renderer skips these by design
        fam = wf.find("span", class_="LDOCE_word_family")
        if fam is None:
            continue
        kept += 1
        for t in TOK.findall(re.sub(r"\s+", " ", fam.get_text(" ", strip=True)).lower()):
            src_tokens[t] += 1
    if not kept:
        continue
    entry_rows = [r for r in rows[k] if r[4] > 0]
    if not entry_rows:
        continue
    acc = []
    for item in entry_rows[0][5]:
        if isinstance(item, dict):
            wf_text(item, acc)
    # NB: join fragments with a space. Concatenating them glued adjacent tokens
    # together ("abandonwareadjective") and produced a completely false loss report.
    joined = " ".join(" ".join(str(x) for x in a) if isinstance(a, list) else str(a)
                       for a in acc)
    out_tokens = collections.Counter()
    for t in TOK.findall(re.sub(r"\s+", " ", joined).lower()):
        out_tokens[t] += 1
    miss = src_tokens - out_tokens
    checked += 1
    if miss:
        missing_entries += 1
        missing_total.update(miss)
        if len(examples) < 10:
            examples.append((k, dict(miss.most_common(6))))

print(f"entries scanned              = {n}")
print(f"entries with a kept word fam = {checked}  (not in this build: {skipped})")
print(f"entries with missing tokens  = {missing_entries} "
      f"({missing_entries*100.0/max(checked,1):.2f}%)")
print(f"total missing tokens         = {sum(missing_total.values())}")
if missing_total:
    print("top missing:", dict(missing_total.most_common(15)))
    for k, m in examples:
        print(f"  {k!r}: {m}")
print("RESULT:", "PASS" if not missing_total else "LOSS DETECTED")
