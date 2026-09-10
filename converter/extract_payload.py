import json
import random
import re
import zipfile

from urllib.parse import unquote

random.seed(42)
out = []
words_taken = set()

SOURCES = [
    r"C:\workspace\ldoce\yomitan_debug\LDOCE5pp_Yomitan_2026.09.10_DEBUG.zip",
    r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.10.zip",
]

rows_pool = []
for zp in SOURCES:
    try:
        z = zipfile.ZipFile(zp)
    except OSError:
        print("skip", zp)
        continue
    for n in z.namelist():
        if not n.startswith("term_bank_"):
            continue
        for r in json.loads(z.read(n).decode("utf-8")):
            if r[4] > 0:
                rows_pool.append(r)
    z.close()

print("entry rows available:", len(rows_pool))


def sc_of(row):
    for item in row[5]:
        if isinstance(item, dict) and item.get("type") == "structured-content":
            return item["content"]
    return None


# big + small + random mix
rows_pool.sort(key=lambda r: -len(json.dumps(r[5], ensure_ascii=False)))
picks = rows_pool[:15] + rows_pool[-15:]
picks += random.sample(rows_pool, min(370, len(rows_pool)))
# specific shapes
for want in ("improve", "child", "begin", "run", "second class", "A", "the", "decision"):
    picks += [r for r in rows_pool if r[0] == want][:1]

seen = set()
for r in picks:
    if r[0] in seen:
        continue
    seen.add(r[0])
    c = sc_of(r)
    if c is not None:
        out.append({"word": r[0], "content": c})

json.dump(out, open(r"C:\workspace\ldoce\scgen_test\payload.json", "w", encoding="utf-8"),
          ensure_ascii=False)
print("payload entries:", len(out),
      "bytes:", round(len(json.dumps(out, ensure_ascii=False)) / 1048576, 1), "MB")
