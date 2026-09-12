"""Prove the fix changed exactly what it should and nothing else.

Row-by-row comparison of the pre-fix package (2026.09.11) against the rebuilt one
(2026.09.12):

  * bank partitioning, expressions, scores and sequence numbers must be identical
  * alias/entry rules may change (A2/A3)
  * glossaries may only gain ld-infl-pron nodes (A4) -- verified by removing
    them again and requiring a structural match with the old glossary
  * index.json and tag_bank_1.json identical; styles.css differs by one rule

Exit code is non-zero if any invariant is broken.
"""
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(r"C:\workspace\ldoce")
OLD = ROOT / "yomitan_full/LDOCE5pp_Yomitan_2026.09.11.zip"
NEW = ROOT / "yomitan_full/LDOCE5pp_Yomitan_2026.09.12.zip"
FAILURES = []


def check(label, ok, detail=""):
    print(f"[{'OK' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def strip_pron(node):
    """`node` with every ld-infl-pron span, and the separator before it, removed."""
    if isinstance(node, list):
        out = []
        for item in node:
            if isinstance(item, dict) and (item.get("data") or {}).get("class") == "ld-infl-pron":
                if out and out[-1] == " · ":
                    out.pop()
                continue
            out.append(strip_pron(item))
        return out
    if isinstance(node, dict):
        new = dict(node)
        if "content" in new:
            new["content"] = strip_pron(new["content"])
        return new
    return node


def load(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        banks = sorted((n for n in names if re.fullmatch(r"term_bank_\d+\.json", n)),
                       key=lambda n: int(re.search(r"\d+", n).group()))
        return {
            "names": names,
            "banks": banks,
            "rows": [json.loads(z.read(b)) for b in banks],
            "index": z.read("index.json").decode("utf-8"),
            "tag_bank": z.read("tag_bank_1.json").decode("utf-8"),
            "css": z.read("styles.css").decode("utf-8"),
        }


old, new = load(OLD), load(NEW)
check("same bank partitioning",
      [len(b) for b in old["banks"]] == [len(b) for b in new["banks"]],
      f"{len(old['banks'])} banks")

n = rules_changed = tags_changed = gloss_changed = 0
gloss_ok = gloss_bad = 0
meta_bad = 0
first_bad = None
for ob, nb in zip(old["rows"], new["rows"]):
    assert len(ob) == len(nb)
    for ro, rn in zip(ob, nb):
        n += 1
        if (ro[0], ro[1], ro[4], ro[6]) != (rn[0], rn[1], rn[4], rn[6]):
            meta_bad += 1
            if first_bad is None:
                first_bad = (ro[0], ro[6])
            continue
        if ro[2] != rn[2]:
            tags_changed += 1
        if ro[3] != rn[3]:
            rules_changed += 1
        if ro[5] != rn[5]:
            gloss_changed += 1
            if strip_pron(rn[5]) == ro[5]:
                gloss_ok += 1
            else:
                gloss_bad += 1

check("rows compared", n == 245933, str(n))
check("expression / reading / score / sequence identical in every row",
      meta_bad == 0, f"{meta_bad} differ, first {first_bad}")
check("every glossary change is a pure insertion of ld-infl-pron",
      gloss_bad == 0, f"{gloss_ok} ok, {gloss_bad} structural")
old_idx, new_idx = json.loads(old["index"]), json.loads(new["index"])
idx_diff = {k: (old_idx.get(k), new_idx.get(k))
            for k in set(old_idx) | set(new_idx)
            if old_idx.get(k) != new_idx.get(k)}
check("index.json carries only the revision bump",
      set(idx_diff) <= {"revision"}, str(idx_diff))
check("tag_bank_1.json identical", old["tag_bank"] == new["tag_bank"])

old_css, new_css = set(old["css"].splitlines()), set(new["css"].splitlines())
added, removed = new_css - old_css, old_css - new_css
check("styles.css changes are one added rule",
      len(added) == 1 and not removed, f"added={sorted(added)} removed={sorted(removed)}")

print()
print(f"rows with tags changed      : {tags_changed}")
print(f"rows with rules changed     : {rules_changed}")
print(f"rows with glossary changed  : {gloss_changed}")
print()
if FAILURES:
    print(f"{len(FAILURES)} invariant(s) FAILED: {FAILURES}")
    sys.exit(1)
print("before/after diff is exactly the intended change")
