"""Decisive R1 check: did any separator the SOURCE has get removed?

For every space that exists in the 2026.09.12 package but not in the new one, look
at the words on either side (`L`, `R`) and ask the SOURCE whether it ever writes
them as a separated pair:

    source contains  "coal mines"   -> the removal is a REGRESSION
    source contains  "terrorists"   -> the removal is the FIX (it used to be split)

The source's own text is read with get_text("") -- no separator invented between
tags -- so a suffix that abuts a closing tag (`<a>terrorist</a></span>s`) reads as
one word, while a real space between tags (`coal</a> <span>mines</span>`) survives.

    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -u converter/audit_2026_09_13/check_glue.py OLD.zip NEW.zip
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

OLD = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "yomitan_full/LDOCE5pp_Yomitan_2026.09.12.zip"
NEW = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip"
SRC = ROOT / "extract/LDOCE5++ V 2-15.mdx.txt"
WS = " \t\r\n\u00a0"
ALNUM = re.compile(r"[A-Za-z0-9]")


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
changed = {}
for expr, orows in old.items():
    nrows = new.get(expr, [])
    for i, ro in enumerate(orows):
        if i >= len(nrows):
            continue
        O, N = flat(ro[5]), flat(nrows[i][5])
        if O == N:
            continue
        removals = []
        a = b = 0
        while a < len(O) and b < len(N):
            if O[a] in WS and N[b] in WS:
                a += 1
                b += 1
            elif O[a] in WS:
                k = a
                while k < len(O) and O[k] in WS:
                    k += 1
                L, R = run_left(O, a), run_right(O, k)
                if L and R:
                    removals.append((L, R))
                a = k
            elif N[b] in WS:
                k = b
                while k < len(N) and N[k] in WS:
                    k += 1
                b = k
            else:
                a += 1
                b += 1
        if removals:
            changed.setdefault(expr, []).extend(removals)

print(f"expressions with a removed space: {len(changed):,}   "
      f"removals: {sum(len(v) for v in changed.values()):,}")

# Source text per expression. get_text("") -- i.e. strip the tags WITHOUT inserting
# a separator -- is what makes the test decisive: a suffix abutting a closing tag
# reads as one word, while a real space between tags survives. Implemented with a
# regex rather than BeautifulSoup because this runs over ~285k records; the two are
# equivalent here (only entities differ, and the pairs tested are alphanumeric).
TAG_RE = re.compile(r"<[^>]+>")
src_text = {}
missing_src = 0
for key, content in M.iter_records(SRC):
    k = M.strip_invisible(key).strip()
    if k not in changed or k in src_text:
        continue
    txt = unescape(TAG_RE.sub("", content))
    src_text[k] = re.sub(r"\s+", " ", txt)
print(f"source text resolved for {len(src_text):,} expressions")

regressions = []
splits = []
unresolved = 0
for expr, removals in changed.items():
    txt = src_text.get(expr)
    if txt is None:
        unresolved += len(removals)
        continue
    for L, R in removals:
        pat = rf"(?<![A-Za-z0-9]){re.escape(L)} {re.escape(R)}(?![A-Za-z0-9])"
        if re.search(pat, txt):
            regressions.append((expr, L, R))
        else:
            splits.append((expr, L, R))

print()
print(f"REGRESSIONS (source writes 'L R' but the new package glues it): {len(regressions):,}")
for row in regressions[:25]:
    print(f"   {row[0]!r:34} {row[1]!r} + {row[2]!r}")
print()
print(f"genuine fixes (source glues, we used to split): {len(splits):,}")
fixed_words = collections.Counter(L + R for _e, L, R in splits)
print(f"   distinct joins: {len(fixed_words):,}   top: {fixed_words.most_common(10)}")
print(f"removals not checkable (expression absent from the source): {unresolved:,}")
