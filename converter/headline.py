"""Print the ld-head subtree (as readable inline text with class tags) and any
'see picture' cross-reference nodes for given words, straight from a package."""
import json
import re
import sys
import zipfile

ZIP = sys.argv[1]
words = sys.argv[2:]


def find(node, cls, out):
    if isinstance(node, list):
        for x in node:
            find(x, cls, out)
    elif isinstance(node, dict):
        if (node.get("data") or {}).get("class") == cls:
            out.append(node)
        for k, v in node.items():
            if k != "data":
                find(v, cls, out)


def flat(node, parts):
    if isinstance(node, str):
        parts.append(node)
        return
    if isinstance(node, list):
        for x in node:
            flat(x, parts)
        return
    cls = (node.get("data") or {}).get("class")
    tag = node.get("tag")
    if tag == "br":
        parts.append(" ")
        return
    marker = f"<{cls}>" if cls else ""
    if marker:
        parts.append(marker)
    if node.get("href"):
        parts.append("{LINK:")
    flat(node.get("content", ""), parts)
    if node.get("href"):
        parts.append("}")
    if marker:
        parts.append(f"</{cls}>")


zf = zipfile.ZipFile(ZIP)
banks = sorted((n for n in zf.namelist() if re.fullmatch(r"term_bank_\d+\.json", n)),
               key=lambda n: int(re.search(r"\d+", n).group()))
rows = {}
for b in banks:
    for r in json.loads(zf.read(b)):
        if r[0] in words and r[0] not in rows:
            rows[r[0]] = r

for w in words:
    r = rows.get(w)
    print("=" * 70)
    if r is None:
        print(f"{w!r}: NO ROW")
        continue
    print(f"{w!r} tags={r[2]!r} rules={r[3]!r} score={r[4]} seq={r[6]}")
    sc = None
    for item in r[5]:
        if isinstance(item, dict) and item.get("type") == "structured-content":
            sc = item["content"]
    if sc is None:
        print("  (redirect row)", r[5])
        continue
    heads = []
    find(sc, "ld-head", heads)
    for h in heads:
        parts = []
        flat(h, parts)
        print("  HEAD:", re.sub(r"\s+", " ", "".join(parts)).strip()[:300])
    # crossref-ish / picture references anywhere
    for key in ("ld-xref-dead", "ld-crossref", "ld-refhwd"):
        got = []
        find(sc, key, got)
        if got:
            parts = []
            flat(got, parts)
            print(f"  {key}:", re.sub(r"\s+", " ", "".join(parts)).strip()[:200])
    blob = json.dumps(sc, ensure_ascii=False)
    for m in re.finditer(r"[^\"\\]{0,60}See picture[^\"\\]{0,80}", blob):
        print("  PICTURE-REF:", m.group(0))
