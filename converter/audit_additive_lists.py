"""Additive audit for the native-list build.

The previous audit asserted "glossary identical after stripping injected spans",
which no longer holds: senses became <li> inside <ol> and examples became <li>
inside <ul> -- a deliberate structural change (that IS the fix). Comparing tags
would therefore report 64,659 false differences.

What must be preserved is the CONTENT:
  * the same rows, with identical (expression, reading, score, sequence)
  * the same visible TEXT once markup is flattened (allowing for the injected
    separators and the hidden sense-number chip)
  * no tag or rule removals

Usage: python audit_additive_lists.py [new.zip] [old.zip]
"""
import json
import re
import sys
import zipfile
from collections import Counter

NEW = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.12.zip"
OLD = sys.argv[2] if len(sys.argv) > 2 else \
    r"C:\workspace\ldoce\_baseline\LDOCE5pp_Yomitan_2026.09.11.PRE_FIX.zip"


def rows_of(path):
    z = zipfile.ZipFile(path)
    out = {}
    for n in z.namelist():
        if not re.fullmatch(r"term_bank_\d+\.json", n):
            continue
        for r in json.loads(z.read(n)):
            out.setdefault(r[0], []).append(r)
    return out


def flat(node, acc):
    """Visible text: strings only. Injected separators are whitespace and are
    normalised away, so a pure re-tag or space insertion cannot show up here."""
    if isinstance(node, str):
        acc.append(node)
    elif isinstance(node, list):
        for x in node:
            flat(x, acc)
    elif isinstance(node, dict):
        # the hidden sense-number chip contributes nothing visually in the
        # no-CSS case, but DID contribute before; keep its text so the comparison
        # is about content, and normalise whitespace at the end
        flat(node.get("content", ""), acc)
    return acc


def norm(text):
    t = re.sub(r"\s+", " ", text)
    t = t.replace("\u00a0", " ")
    return t.strip()


new_rows = rows_of(NEW)
old_rows = rows_of(OLD)
print(f"new : {NEW.split(chr(92))[-1]}  keys={len(new_rows):,}")
print(f"old : {OLD.split(chr(92))[-1]}  keys={len(old_rows):,}")
print()

only_new = set(new_rows) - set(old_rows)
only_old = set(old_rows) - set(new_rows)
print(f"keys only in new: {len(only_new)}")
print(f"keys only in old: {len(only_old)}")

# structural field comparison
struct_diff = 0
tags_removed = 0
tags_added = 0
text_diff = 0
text_examples = []

for expr in sorted(set(new_rows) & set(old_rows)):
    # match rows pairwise by reading
    n_by_reading = {}
    for r in new_rows[expr]:
        n_by_reading.setdefault(r[1], []).append(r)
    o_by_reading = {}
    for r in old_rows[expr]:
        o_by_reading.setdefault(r[1], []).append(r)
    for reading in set(n_by_reading) & set(o_by_reading):
        n = n_by_reading[reading][0]
        o = o_by_reading[reading][0]
        if (n[2], n[3], n[4], n[6]) != (o[2], o[3], o[4], o[6]):
            struct_diff += 1
        ntags = set(str(n[2]).split())
        otags = set(str(o[2]).split())
        tags_removed += len(otags - ntags)
        tags_added += len(ntags - otags)
        nt = norm("".join(flat(n[5], [])))
        ot = norm("".join(flat(o[5], [])))
        # the sense-number chip is repeated as a native list marker now, so the
        # text may legitimately gain/lose a bare digit; compare with digits in
        # list positions normalised out
        nt2 = re.sub(r"\b(\d)\b(?=\s)", "", nt)
        ot2 = re.sub(r"\b(\d)\b(?=\s)", "", ot)
        if nt2 != ot2:
            text_diff += 1
            if len(text_examples) < 8:
                text_examples.append((expr, ot[:90], nt[:90]))

print(f"rows with changed (tags,rules,score,seq): {struct_diff}")
print(f"tags removed: {tags_removed}   tags added: {tags_added}")
print(f"rows whose flattened TEXT changed       : {text_diff:,}")
for expr, ot, nt in text_examples:
    print(f"  {expr!r}")
    print(f"     old: {ot!r}")
    print(f"     new: {nt!r}")
print()
print("VERDICT:", "ADDITIVE (content preserved)" if
      (struct_diff == 0 and tags_removed == 0 and text_diff == 0 and not only_old)
      else "differences present -- inspect above")
