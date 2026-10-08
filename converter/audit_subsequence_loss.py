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
    """All rows keyed by (expression, reading) -> LIST of rows.

    Keying by expression and keeping a single row per reading silently dropped the
    extra rows of an expression that carries more than one (the packages do contain
    duplicated expressions, and an entry + its alias share reading ""). Those rows
    were then never subsequence-tested, so the "no content loss" verdict covered a
    silent subset.
    """
    z = zipfile.ZipFile(path)
    out = {}
    for n in z.namelist():
        if not re.fullmatch(r"term_bank_\d+\.json", n):
            continue
        for r in json.loads(z.read(n)):
            out.setdefault((r[0], r[1]), []).append(r)
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
print(f"shared (expression, reading) keys: {len(shared):,}")
print()

identical = inserted = 0
losses = []
pairs_checked = 0
for key in shared:
    expr, reading = key
    orows = old_rows[key]
    nrows = new_rows[key]
    # Compare every row pair, and report a count divergence: a group whose row
    # count changed between builds is exactly what this gate must not miss.
    if len(orows) != len(nrows):
        losses.append((expr, reading, f"row count {len(orows)} -> {len(nrows)}", ""))
    for o, n in zip(orows, nrows):
        pairs_checked += 1
        so = squeeze(o[5])
        sn = squeeze(n[5])
        if so == sn:
            identical += 1
        elif is_subsequence(so, sn):
            inserted += 1
        else:
            losses.append((expr, reading, so, sn))

print(f"row pairs checked                       : {pairs_checked:,}")
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
