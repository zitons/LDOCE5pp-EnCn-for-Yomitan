"""R1 verification: exactly which spaces did the seam fix add or remove?

Aligns the 2026.09.12 package (R1 broken) against the rebuilt one, per content row,
after structurally removing the ld-mark spans so only the separator changes remain.

  removed spaces  -- the R1 fix. Each must join letters back into a token that the
                     OLD package carried intact (i.e. it really was a split word),
                     or be a headword+superscript join like 'SUM1'.
  inserted spaces -- must be 0: narrowing the rule can only take separators away.

    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -u converter/audit_2026_09_13/diff_seams.py
"""
import collections
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(r"C:\workspace\ldoce")
OLD = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "yomitan_full/LDOCE5pp_Yomitan_2026.09.12.zip"
NEW = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip"
WS = " \t\r\n\u00a0"
ALNUM = re.compile(r"[A-Za-z0-9]")


def banks(z):
    return sorted((n for n in z.namelist() if re.fullmatch(r"term_bank_\d+\.json", n)),
                  key=lambda n: int(re.search(r"\d+", n).group()))


def flat(o, drop_marks=True, acc=None):
    if acc is None:
        acc = []
    if isinstance(o, str):
        acc.append(o)
    elif isinstance(o, list):
        for x in o:
            flat(x, drop_marks, acc)
    elif isinstance(o, dict):
        cls = ((o.get("data") or {}).get("class") or "").split()
        if drop_marks and "ld-mark" in cls:
            return "".join(acc)
        if drop_marks and {"ld-hyp", "ld-stress"} & set(cls):
            return "".join(acc)          # pure decoration, never carries a space
        flat(o.get("content", ""), drop_marks, acc)
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
print(f"content rows: old {sum(len(v) for v in old.values()):,}  "
      f"new {sum(len(v) for v in new.values()):,}")

# every whole-word token the OLD package carried, for judging a join
old_tokens = set()
for rows in old.values():
    for r in rows:
        for t in re.findall(r"[A-Za-z]{2,}", flat(r[5])):
            old_tokens.add(t)
print(f"old-package word tokens: {len(old_tokens):,}")

removed = collections.Counter()
inserted = collections.Counter()
removed_samples = collections.defaultdict(list)
inserted_samples = collections.defaultdict(list)
splits = []
rows_touched = 0
missing = 0

for expr, orows in old.items():
    nrows = new.get(expr, [])
    if len(nrows) < len(orows):
        missing += 1
        continue
    for i, ro in enumerate(orows):
        O, N = flat(ro[5]), flat(nrows[i][5])
        if O == N:
            continue
        rows_touched += 1
        a = b = 0
        while a < len(O) and b < len(N):
            if O[a] in WS and N[b] in WS:
                a += 1
                b += 1
            elif O[a] in WS:                     # space only in OLD -> removed
                k = a
                while k < len(O) and O[k] in WS:
                    k += 1
                L, R = run_left(O, a), run_right(O, k)
                if L and R and L[-1].isalpha() and R[0].isalpha():
                    key = "LETTER+letter"
                    joined = L + R
                    splits.append((expr, L, R, joined in old_tokens))
                elif R[:1].isdigit() and L[-1:].isalpha():
                    key = "word+digit"
                else:
                    key = "other"
                removed[key] += 1
                if len(removed_samples[key]) < 10:
                    removed_samples[key].append((expr, L[-8:], R[:8]))
                a = k
            elif N[b] in WS:                     # space only in NEW -> inserted
                k = b
                while k < len(N) and N[k] in WS:
                    k += 1
                inserted["all"] += 1
                if len(inserted_samples["all"]) < 10:
                    inserted_samples["all"].append(
                        (expr, run_left(N, b)[-8:], run_right(N, k)[:8]))
                b = k
            else:
                a += 1
                b += 1

print(f"\nrows whose text changed: {rows_touched:,}   expressions lost: {missing}")
print("\n== removed spaces (the R1 fix) ==")
for k, v in removed.most_common():
    print(f"  {k:16} {v:>7,}   e.g. {removed_samples[k][:6]}")

word_splits = [s for s in splits if s[3]]
not_words = [s for s in splits if not s[3]]
print(f"\n  letter+letter removals: {len(splits):,}")
print(f"    joined form was a real word in the old package : {len(word_splits):,}")
print(f"    joined form was NOT a package word              : {len(not_words):,}")
print(f"    distinct words repaired: {len({s[1] + s[2] for s in word_splits}):,}")
for s in word_splits[:14]:
    print(f"      {s[0]!r:16} {s[1]!r} + {s[2]!r} -> {s[1] + s[2]!r}")
if not_words:
    print("    samples that were NOT verified as words:")
    for s in not_words[:10]:
        print(f"      {s[0]!r:16} {s[1]!r} + {s[2]!r}")

print("\n== inserted spaces (must be 0) ==")
print(f"  total {inserted['all']:,}   e.g. {inserted_samples['all'][:6]}")
