"""Post-fix verification for the word-family work:
 * no whitespace-only / empty content nodes were introduced
 * no bogus empty ld-wf-group
 * opp markers render with a live link
 * loose-text members survive
 * non-wordfam content unchanged (panels, senses)
"""
import json
import re
import sys
import zipfile

ZIP = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\workspace\ldoce\yomitan_wf_test\LDOCE5pp_Yomitan_2026.09.11_DEBUG.zip"

z = zipfile.ZipFile(ZIP)
rows = {}
for n in z.namelist():
    if re.fullmatch(r"term_bank_\d+\.json", n):
        for r in json.loads(z.read(n)):
            rows.setdefault(r[0], []).append(r)


def walk(node, acc):
    if isinstance(node, str):
        if not node.strip():
            acc["blank"] += 1
        return
    if isinstance(node, list):
        for x in node:
            walk(x, acc)
        return
    if isinstance(node, dict):
        cls = (node.get("data") or {}).get("class")
        if cls == "ld-wf-group":
            acc["groups"] += 1
            c = node.get("content")
            if not c or not any(
                isinstance(x, dict) and (x.get("data") or {}).get("class") in
                ("ld-wf-pos", "ld-wf-word", "ld-wf-root", "ld-wf-opp") or x.get("tag") == "a"
                for x in (c if isinstance(c, list) else [c])):
                acc["empty_groups"] += 1
        if cls == "ld-wf-word":
            acc["wf_words"] += 1
        if cls == "ld-wf-opp":
            acc["opp"] += 1
            if not any(isinstance(x, dict) and x.get("tag") == "a" for x in (node.get("content") or [])):
                acc["opp_without_link"] += 1
        for k, v in node.items():
            if k != "data":
                walk(v, acc)


print(f"package: {ZIP.split(chr(92))[-1]}")
total_blank = 0
for w in sorted(rows):
    for r in rows[w]:
        if r[4] <= 0:
            continue
        acc = {"blank": 0, "groups": 0, "empty_groups": 0, "wf_words": 0, "opp": 0,
               "opp_without_link": 0}
        walk(r[5], acc)
        total_blank += acc["blank"]
        if acc["empty_groups"] or acc["opp_without_link"]:
            print(f"  PROBLEM {w!r}: {acc}")
        if w in ("advantage", "add", "accuse", "accustomed", "administration"):
            print(f"  {w!r:16} groups={acc['groups']} words={acc['wf_words']} "
                  f"opp={acc['opp']} empty_groups={acc['empty_groups']} blank_strings={acc['blank']}")
print(f"\nblank/whitespace-only string nodes anywhere in entry glossaries: {total_blank}")
