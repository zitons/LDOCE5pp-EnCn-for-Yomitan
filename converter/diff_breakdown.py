"""Break the 29,066 changed entry rows down by WHAT changed."""
import json
import re
import zipfile
from collections import Counter

OLD = r"C:\workspace\ldoce\_baseline\LDOCE5pp_Yomitan_2026.09.11.PRE_FIX.zip"
NEW = r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.11.zip"


def banks(path):
    z = zipfile.ZipFile(path)
    return z, sorted((n for n in z.namelist() if re.fullmatch(r"term_bank_\d+\.json", n)),
                     key=lambda n: int(re.search(r"\d+", n).group()))


z1, b1 = banks(OLD)
z2, b2 = banks(NEW)

GRAM = re.compile(r'"class": "ld-gram"\}, "content": "([^"]*)"')
kinds = Counter()
gram_rows = 0
gram_tokens_added = 0
only_gram = 0

for n in b1:
    r1 = json.loads(z1.read(n))
    r2 = json.loads(z2.read(n))
    for a, b in zip(r1, r2):
        if a == b:
            continue
        sa = json.dumps(a[5], ensure_ascii=False)
        sb = json.dumps(b[5], ensure_ascii=False)
        tags_a, tags_b = a[2], b[2]
        hit = set()
        if sb.count('"ld-panel-online"') > sa.count('"ld-panel-online"'):
            hit.add("LDOCE Online 面板")
        if sb.count('"ld-wf-opp"') > sa.count('"ld-wf-opp"'):
            hit.add("词族反义词 ≠")
        if sb.count('"ld-infl-region"') > sa.count('"ld-infl-region"'):
            hit.add("变形区域标签")
        if sb.count('"ld-infl-ann"') > sa.count('"ld-infl-ann"'):
            hit.add("变形注解")
        if sb.count('"ld-panel-sub"') > sa.count('"ld-panel-sub"'):
            hit.add("义项分组标签")
        if tags_a != tags_b or a[3] != b[3]:
            hit.add("频率/词性标签")
        ga = set(GRAM.findall(sa))
        gb = set(GRAM.findall(sb))
        if ga != gb:
            gram_rows += 1
            gram_tokens_added += sum(len(x) for x in gb) - sum(len(x) for x in ga)
            if not hit:
                only_gram += 1
                hit.add("词头语法标签加方括号/限定词")
        if not hit:
            hit.add("其它（同一行内多处小改）")
        for h in hit:
            kinds[h] += 1

print(f"changed entry rows = {sum(1 for _ in ())}", end="")
print("  (see below)")
print("\nchanged rows by change type (a row can have several):")
for k, c in kinds.most_common():
    print(f"  {c:>7}  {k}")
print(f"\nrows whose ld-gram content changed      = {gram_rows}")
print(f"  of those, GRAM was the ONLY change    = {only_gram}")
print(f"net characters added to ld-gram labels  = {gram_tokens_added:+,}")
