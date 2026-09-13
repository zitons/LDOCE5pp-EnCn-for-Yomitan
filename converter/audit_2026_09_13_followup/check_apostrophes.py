"""Verify the claim 'bilingual output differs from f774b4e only by 74 apostrophe
spaces in 70 records'.

For every content row whose text differs between the two packages:
  * the difference must be pure whitespace (old text with all whitespace removed
    must equal the new text with all whitespace removed), and
  * every extra space in the old text must sit directly after a word-internal
    apostrophe (U+2019 or '), i.e. inside a contraction.
"""
import json
import re
import zipfile

OLD = "yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip"          # f774b4e build
NEW = "yomitan_fixed/verified/bilingual/LDOCE5pp_Yomitan_2026.09.13.zip"
WS = " \t\r\n\u00a0"
APO = "’'"


def banks(z):
    return sorted((n for n in z.namelist() if re.fullmatch(r"term_bank_\d+\.json", n)),
                  key=lambda n: int(re.search(r"\d+", n).group()))


def flat(o, acc=None):
    if acc is None:
        acc = []
    if isinstance(o, str):
        acc.append(o)
    elif isinstance(o, list):
        for x in o:
            flat(x, acc)
    elif isinstance(o, dict):
        cls = ((o.get("data") or {}).get("class") or "").split()
        if "ld-mark" in cls or {"ld-hyp", "ld-stress"} & set(cls):
            return "".join(acc)
        flat(o.get("content", ""), acc)
    return "".join(acc)


def load(path):
    out = {}
    with zipfile.ZipFile(path) as z:
        for n in banks(z):
            for r in json.loads(z.read(n)):
                if r[4] > 0:
                    out.setdefault(r[0], []).append(r)
    return out


def align(old, new):
    """Spaces present in `old` but not `new`, with the character before each."""
    extra = []
    a = b = 0
    while a < len(old) and b < len(new):
        if old[a] == new[b]:
            a += 1
            b += 1
        elif old[a] in WS:
            extra.append(old[a - 1] if a else "")
            a += 1
        else:
            return None                      # non-whitespace difference
    return extra


old, new = load(OLD), load(NEW)
rows_changed = 0
spaces = 0
bad = []
apostrophe = 0
for expr, orows in old.items():
    nrows = new.get(expr, [])
    for i, ro in enumerate(orows):
        if i >= len(nrows):
            continue
        O, N = flat(ro[5]), flat(nrows[i][5])
        if O == N:
            continue
        rows_changed += 1
        extra = align(O, N)
        if extra is None:
            bad.append((expr, "non-whitespace difference", O[:80], N[:80]))
            continue
        for prev in extra:
            spaces += 1
            if prev in APO:
                apostrophe += 1
            else:
                bad.append((expr, f"space after {prev!r}", O[:80], N[:80]))

print(f"rows whose text differs : {rows_changed}")
print(f"removed spaces          : {spaces}")
print(f"  right after an apostrophe: {apostrophe}")
print(f"  anything else            : {spaces - apostrophe}")
for b in bad[:8]:
    print("   BAD:", b)
print()
print("RESULT:", "PASS" if not bad else f"FAIL ({len(bad)})")
