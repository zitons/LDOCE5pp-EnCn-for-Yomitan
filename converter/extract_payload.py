import glob
import json
import os
import random
import sys
import zipfile

random.seed(42)
out = []
words_taken = set()


def _find_sources():
    """Newest full package + newest debug package (explicit argv wins).

    Was hardcoded to 2026.09.10 and silently went stale on rebuild -- the same
    trap audit2/3/4/5 already guard against with _find_zip(). Keep it dynamic.
    """
    explicit = [a for a in sys.argv[1:] if a.endswith(".zip")]
    if explicit:
        return explicit
    srcs = []
    full = [p for p in glob.glob(r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_*.zip")
            if "_DEBUG" not in p]
    if full:
        srcs.append(max(full, key=os.path.getmtime))
    dbg = glob.glob(r"C:\workspace\ldoce\yomitan_debug*\*_DEBUG.zip")
    if dbg:
        srcs.append(max(dbg, key=os.path.getmtime))
    if not srcs:
        raise SystemExit("no package found under yomitan_full/ or yomitan_debug*/")
    return srcs


SOURCES = _find_sources()
print("payload sources:")
for _s in SOURCES:
    print("   ", _s)

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
