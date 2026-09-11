"""How often does an Inflections span carry an annotation that we drop?
Scan the raw sidecar for Inflections spans containing:
  * 'same pronunciation'
  * region labels (BrE / AmE / British English / American English)
  * other parenthesised notes
"""
import io
import re
import sys

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"

SPAN = re.compile(r'<span class="Inflections">.*?</span>\s*(?=<span|<div|</)', re.S)
same_pron = 0
region = 0
total = 0
samples = {"same": [], "region": []}
keys_seen = set()

for key, content in M.iter_records(SIDE):
    k = M.strip_invisible(key).strip()
    if not k:
        continue
    kind, _ = M.classify_record(k, content)
    if kind != "entry":
        continue
    for m in re.finditer(r'<span class="Inflections">', content):
        seg = content[m.start():m.start() + 600]
        # cut at the closing of the Inflections span by depth counting is overkill;
        # the annotation lives within the first ~400 chars in every observed case
        end = seg.find('</span><span class="GRAM"')
        total += 1
        txt = re.sub(r"<[^>]+>", " ", seg)
        txt = re.sub(r"\s+", " ", txt)
        if "same pronunciation" in txt:
            same_pron += 1
            if len(samples["same"]) < 4 and k not in keys_seen:
                samples["same"].append((k, txt[:110]))
        if re.search(r"\b(BrE|AmE|British English|American English)\b", txt):
            region += 1
            if len(samples["region"]) < 4 and k not in keys_seen:
                samples["region"].append((k, txt[:130]))

print(f"Inflections spans scanned     = {total}")
print(f"  with 'same pronunciation'   = {same_pron}")
print(f"  with a BrE/AmE region label = {region}")
print()
for label, items in samples.items():
    print(f"--- {label} ---")
    for k, t in items:
        print(f"  {k!r}: {t!r}")
