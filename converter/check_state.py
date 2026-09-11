"""Independent state check (2026-09-11): code<->artifact consistency for the
current working tree + package internals. Does not trust the existing logs."""
import glob
import io
import json
import os
import re
import sys
import zipfile
from collections import Counter

sys.path.insert(0, r"C:\workspace\ldoce\converter")
import ldoce2yomitan as C  # noqa: E402

FULL = r"C:\workspace\ldoce\yomitan_full"

print("=== converter identity ===")
print("VERSION", C.VERSION, "| AUTHOR", C.AUTHOR)
src = io.open(r"C:\workspace\ldoce\converter\ldoce2yomitan.py", encoding="utf-8").read()
print("source lines:", src.count("\n") + 1, "| md5:",
      __import__("hashlib").md5(src.encode("utf-8")).hexdigest()[:12])

zips = sorted(glob.glob(os.path.join(FULL, "*.zip")), key=os.path.getmtime)
print("\n=== zips in yomitan_full ===")
for z in zips:
    import datetime
    print(f"  {os.path.basename(z)}  {os.path.getsize(z)/1048576:.2f} MB  "
          f"{datetime.datetime.fromtimestamp(os.path.getmtime(z)):%Y-%m-%d %H:%M:%S}")

target = None
for z in reversed(zips):
    if "DEBUG" not in os.path.basename(z):
        target = z
        break
print(f"\n=== newest non-debug zip: {os.path.basename(target)} ===")
zf = zipfile.ZipFile(target)
names = zf.namelist()
print("members:", len(names))
banks = sorted((n for n in names if re.fullmatch(r"term_bank_\d+\.json", n)),
               key=lambda n: int(re.search(r"\d+", n).group()))
print("term banks:", len(banks), "| other:", [n for n in names if not n.startswith("term_bank_")])

idx = json.loads(zf.read("index.json"))
print("\nindex.json:", json.dumps(idx, ensure_ascii=False))

# ---- code <-> artifact: styles.css must equal current generate_css() ----
css_in_zip = zf.read("styles.css").decode("utf-8")
css_now = C.generate_css()
print("\n=== code<->artifact ===")
print("zip styles.css bytes:", len(css_in_zip), "| current generate_css():", len(css_now))
print("IDENTICAL:", css_in_zip == css_now)
if css_in_zip != css_now:
    import difflib
    d = list(difflib.unified_diff(css_in_zip.splitlines(), css_now.splitlines(),
                                  "zip", "code", lineterm="", n=1))
    print("\n".join(d[:40]))
print("text-indent:0 occurrences in zip css:", css_in_zip.count("text-indent:0"))
print("revision in index:", idx.get("revision"), "| zip filename year:",
      re.search(r"\d{4}\.\d{2}\.\d{2}", os.path.basename(target)).group())

# ---- run the converter's own validator (full/strict mode) ----
print("\n=== converter validator (strict, full_rows=True) ===")
errors, vstats = C.validate_package(target, C.TermIndex(), idx.get("revision"),
                                    "bilingual", full_rows=True)
print("stats:", dict(vstats))
if errors:
    print("ERRORS:", len(errors))
    for e in errors[:25]:
        print("   -", e)
else:
    print("PASS: 0 errors")

# ---- independent structural scan ----
print("\n=== independent structural scan ===")
all_expr = set()
seqs = set()
freq_tokens = Counter()
tags_used = Counter()
ld_defcn = 0
ld_def = 0
see_pic = 0
hyp = 0
blob_bytes = 0
tiny = []
for bn in banks:
    for r in zf.read(bn).decode("utf-8") and json.loads(zf.read(bn)):
        expr, tags, rules, score, gloss, seq = r[0], r[2], r[3], r[4], r[5], r[6]
        all_expr.add(expr)
        seqs.add(seq)
        for t in tags.split():
            tags_used[t] += 1
            if t in ("S1", "S2", "S3", "W1", "W2", "W3"):
                freq_tokens[t] += 1
        if score > 0:
            blob = json.dumps(gloss, ensure_ascii=False)
            blob_bytes += len(blob)
            ld_defcn += blob.count('"ld-defcn"')
            ld_def += blob.count('"ld-def"')
            see_pic += blob.count("ld-xref-dead")
print("rows:", len(all_expr), "| seq min/max/unique:",
      min(seqs), max(seqs), len(seqs),
      "| contiguous:", len(seqs) == max(seqs) + 1)
print("freq tag rows:", dict(freq_tokens), "total", sum(freq_tokens.values()))
print("ld-defcn occurrences:", ld_defcn, "| ld-def:", ld_def)
print("ld-xref-dead (demoted links):", see_pic)
