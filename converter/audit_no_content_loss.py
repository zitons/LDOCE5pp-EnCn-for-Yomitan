"""DEPRECATED -- DO NOT TRUST THE NUMBERS THIS PRINTS.

judgement error: the 'letter/digit run' content test reports the FIXES as
losses (old glued text 'nouncountable1' no longer exists once separated).
Use audit_subsequence_loss.py (whitespace-stripped subsequence test).

Kept only as a record of the investigation. See REVIEW.md D33 and
HANDOVER.md pitfall 63.
"""
import json
import re
import sys
import zipfile
from collections import Counter

NEW = r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.12.zip"
OLD = r"C:\workspace\ldoce\_baseline\LDOCE5pp_Yomitan_2026.09.11.PRE_FIX.zip"

STRIP = re.compile(r"[\s\u00a0\u2013\u2014\u00b7\u2022\-\u2019'\[\](){}]")


def rows_of(path):
    z = zipfile.ZipFile(path)
    out = {}
    for n in z.namelist():
        if not re.fullmatch(r"term_bank_\d+\.json", n):
            continue
        for r in json.loads(z.read(n)):
            out.setdefault(r[0], {})[r[1]] = r
    return out


def flat(node, acc):
    if isinstance(node, str):
        acc.append(node)
    elif isinstance(node, list):
        for x in node:
            flat(x, acc)
    elif isinstance(node, dict):
        flat(node.get("content", ""), acc)
    return acc


def residue(node):
    t = "".join(flat(node, []))
    return STRIP.sub("", t)


def word_runs(node):
    """Ordered alphanumeric runs (letters+digits), CJK included as single chars.

    Compares CONTENT rather than exact strings: the new build legitimately inserts
    separators, scheme-B markers and restored operators such as the word-family
    antonym sign, so an exact match is the wrong test. Every run present in the old
    text must still be present in the new text."""
    t = "".join(flat(node, []))
    runs = re.findall(r"[A-Za-z0-9]+", t)
    runs += re.findall(r"[\u4e00-\u9fff]", t)
    return runs


new_rows = rows_of(NEW)
old_rows = rows_of(OLD)
shared = set(new_rows) & set(old_rows)
print(f"shared expressions: {len(shared):,}")

same = 0
added_only = Counter()
lost = []
for expr in shared:
    for reading in set(new_rows[expr]) & set(old_rows[expr]):
        ro = residue(old_rows[expr][reading][5])
        rn = residue(new_rows[expr][reading][5])
        if rn == ro:
            same += 1
            continue
        if ro in rn:
            # new text contains the old: pure insertion (separators / markers)
            added_only[expr] = len(rn) - len(ro)
            continue
        # content test: every alphanumeric run of the OLD text must survive
        runs_old = word_runs(old_rows[expr][reading][5])
        runs_new = Counter(word_runs(new_rows[expr][reading][5]))
        missing_runs = []
        pool = Counter(runs_new)
        for w in runs_old:
            if pool[w] > 0:
                pool[w] -= 1
            else:
                missing_runs.append(w)
        if not missing_runs:
            added_only[expr] = len(rn) - len(ro)
            continue
        lost.append((expr, reading, "MISSING:" + ",".join(missing_runs[:5]),
                     ro[:80], rn[:80]))

print(f"identical after stripping separators/markers : {same:,}")
print(f"pure INSERTION (old is a subsequence)        : {len(added_only):,}")
print(f"shrunk or changed (potential content loss)   : {len(lost):,}")
print()
if added_only:
    print("largest insertions:")
    for expr, delta in added_only.most_common(6):
        print(f"  +{delta:>3} chars  {expr!r}")
print()
for expr, reading, kind, ro, rn in lost[:10]:
    print(f"  {kind} {expr!r} [{reading}]")
    print(f"     old: {ro!r}")
    print(f"     new: {rn!r}")
print()
print("VERDICT:", "NO CONTENT LOSS -- all differences are separators/markers"
      if not lost else f"{len(lost)} row(s) need inspection")
