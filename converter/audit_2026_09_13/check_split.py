"""Mirror of check_glue: did we ADD a separator the source does not have?

For every space that exists in the new package but not in 2026.09.12, take the
alnum runs on either side (L, R) and ask the SOURCE:

    source contains "LR" glued and never "L R"  -> wrong insertion (REGRESSION)
    source contains "L R"                        -> justified (we restored it)
    neither                                      -> inconclusive (count + sample)

    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -u converter/audit_2026_09_13/check_split.py
"""
import collections
import json
import re
import sys
import zipfile
from html import unescape
from pathlib import Path

ROOT = Path(r"C:\workspace\ldoce")
sys.path.insert(0, str(ROOT / "converter"))
import ldoce2yomitan as M  # noqa: E402

OLD = ROOT / "yomitan_full/LDOCE5pp_Yomitan_2026.09.12.zip"
NEW = ROOT / "yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip"
SRC = ROOT / "extract/LDOCE5++ V 2-15.mdx.txt"
WS = " \t\r\n\u00a0"
ALNUM = re.compile(r"[A-Za-z0-9]")
TAG_RE = re.compile(r"<[^>]+>")


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


def run_left(s, i):
    j = i
    while j > 0 and ALNUM.match(s[j - 1]):
        j -= 1
    return s[j:i]


def run_right(s, i):
    j = i
    while j < len(s) and ALNUM.match(s[j]):
        j += 1
    return s[i:j]


old, new = load(OLD), load(NEW)
insertions = {}
for expr, orows in old.items():
    nrows = new.get(expr, [])
    for i, ro in enumerate(orows):
        if i >= len(nrows):
            continue
        O, N = flat(ro[5]), flat(nrows[i][5])
        if O == N:
            continue
        found = []
        a = b = 0
        while a < len(O) and b < len(N):
            if O[a] in WS and N[b] in WS:
                a += 1
                b += 1
            elif N[b] in WS:
                k = b
                while k < len(N) and N[k] in WS:
                    k += 1
                L, R = run_left(N, b), run_right(N, k)
                if L and R:
                    found.append((L, R))
                b = k
            elif O[a] in WS:
                k = a
                while k < len(O) and O[k] in WS:
                    k += 1
                a = k
            else:
                a += 1
                b += 1
        if found:
            insertions.setdefault(expr, []).extend(found)

print(f"expressions with an inserted space: {len(insertions):,}   "
      f"insertions: {sum(len(v) for v in insertions.values()):,}")

TAG = TAG_RE
src_text = {}
for key, content in M.iter_records(SRC):
    k = M.strip_invisible(key).strip()
    if k not in insertions or k in src_text:
        continue
    src_text[k] = re.sub(r"\s+", " ", unescape(TAG.sub("", content)))
print(f"source text resolved for {len(src_text):,}")

wrong = []
justified = []
inconclusive = []
for expr, ins in insertions.items():
    txt = src_text.get(expr)
    if txt is None:
        inconclusive.extend((expr, L, R) for L, R in ins)
        continue
    for L, R in ins:
        glued = re.search(rf"(?<![A-Za-z0-9]){re.escape(L)}{re.escape(R)}(?![A-Za-z0-9])", txt)
        spaced = re.search(rf"(?<![A-Za-z0-9]){re.escape(L)} {re.escape(R)}(?![A-Za-z0-9])", txt)
        if glued and not spaced:
            wrong.append((expr, L, R))
        elif spaced:
            justified.append((expr, L, R))
        else:
            inconclusive.append((expr, L, R))

print()
print(f"WRONG (source glues 'LR', we inserted a space): {len(wrong):,}")
for row in wrong[:20]:
    print(f"   {row[0]!r:30} {row[1]!r} | {row[2]!r}")
print(f"justified (source writes 'L R'): {len(justified):,}")
print(f"inconclusive (pair not found in the source text): {len(inconclusive):,}")
print("   samples:", [(e, L, R) for e, L, R in inconclusive[:8]])
