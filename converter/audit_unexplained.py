"""Investigate the 14 rows whose glossary changed with no marker/tag/rule
explanation. Show the exact textual delta against the PRE_FIX baseline."""
import difflib
import json
import re
import sys
import zipfile

R2 = r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.12.zip"
PRE = r"C:\workspace\ldoce\_baseline\LDOCE5pp_Yomitan_2026.09.11.PRE_FIX.zip"
WORDS = ["4-F", "coconut shy", "Father of the Church", "heave to", "innings",
         "Lord Lieutenant, the", "M", "mother-to-be", "Nepali", "oarswoman",
         "Orangeman", "steno"]


def index(path):
    z = zipfile.ZipFile(path)
    out = {}
    for n in z.namelist():
        if re.fullmatch(r"term_bank_\d+\.json", n):
            for r in json.loads(z.read(n)):
                if r[4] > 0:
                    out.setdefault(r[0], []).append(r)
    return out


a = index(PRE)
b = index(R2)
for w in WORDS:
    ra = a.get(w)
    rb = b.get(w)
    if not ra or not rb:
        print(f"{w!r}: missing on one side (old={bool(ra)} new={bool(rb)})")
        continue
    sa = json.dumps(ra[0][5], ensure_ascii=False)
    sb = json.dumps(rb[0][5], ensure_ascii=False)
    if sa == sb:
        print(f"{w!r}: glossary identical (difference is in a later duplicate row)")
        continue
    sm = difflib.SequenceMatcher(None, sa, sb)
    ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
    print(f"\n=== {w!r}  ({len(ops)} edit(s), {len(sa)} -> {len(sb)} bytes) ===")
    for tag, i1, i2, j1, j2 in ops[:3]:
        print(f"  {tag}")
        print(f"    OLD ...{sa[max(0,i1-90):i2+90]}...")
        print(f"    NEW ...{sb[max(0,j1-90):j2+90]}...")
