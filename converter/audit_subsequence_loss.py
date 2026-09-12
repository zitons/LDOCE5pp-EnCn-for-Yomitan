"""Directional content-preservation audit (correct formulation).

History of wrong tests on this build:
  * comparing tags            -> 64,659 false diffs (div became ol/ul/li, which IS
                                 the fix)
  * comparing text exactly    -> thousands of false diffs (separators inserted)
  * comparing alphanumeric runs -> false diffs because gluing was FIXED:
                                 old 'nouncountable1' becomes 'noun countable 1',
                                 so the old run no longer exists by construction

Correct test: remove only WHITESPACE from both flattened texts, then require the
old string to be a SUBSEQUENCE of the new one. That permits exactly the changes
this series of fixes makes -- inserted spaces, inserted scheme-B markers, and
restored content such as the word-family antonym sign -- while failing loudly if
any character of the original dictionary text was dropped or reordered.

Usage: python audit_subsequence_loss.py [new.zip] [old.zip]
"""
import json
import re
import sys
import zipfile

NEW = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.12.zip"
OLD = sys.argv[2] if len(sys.argv) > 2 else \
    r"C:\workspace\ldoce\_baseline\LDOCE5pp_Yomitan_2026.09.12.R2.zip"

WS = re.compile(r"\s+")


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


def squeeze(node):
    return WS.sub("", "".join(flat(node, [])))


def is_subsequence(needle, hay):
    it = iter(hay)
    return all(ch in it for ch in needle)


new_rows = rows_of(NEW)
old_rows = rows_of(OLD)
shared = set(new_rows) & set(old_rows)
print(f"new: {NEW.split(chr(92))[-1]}")
print(f"old: {OLD.split(chr(92))[-1]}")
print(f"shared expressions: {len(shared):,}")
print()

identical = inserted = 0
losses = []
for expr in shared:
    for reading in set(new_rows[expr]) & set(old_rows[expr]):
        so = squeeze(old_rows[expr][reading][5])
        sn = squeeze(new_rows[expr][reading][5])
        if so == sn:
            identical += 1
        elif is_subsequence(so, sn):
            inserted += 1
        else:
            losses.append((expr, reading, so, sn))

print(f"identical after removing whitespace      : {identical:,}")
print(f"pure insertion / reorder-free superset   : {inserted:,}")
print(f"POTENTIAL CONTENT LOSS                   : {len(losses):,}")
print()
for expr, reading, so, sn in losses[:10]:
    # show where they diverge
    i = 0
    while i < min(len(so), len(sn)) and so[i] == sn[i]:
        i += 1
    print(f"  {expr!r} [{reading}]  diverges at char {i}")
    print(f"     old ...{so[max(0,i-40):i+40]!r}")
    print(f"     new ...{sn[max(0,i-40):i+40]!r}")
print()
print("VERDICT:", "NO CONTENT LOSS" if not losses
      else f"{len(losses)} row(s) lost content -- inspect")
