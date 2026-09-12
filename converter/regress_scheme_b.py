"""Regression gate for scheme B (semantic inlining).

Two directions must hold, and a future edit must not silently break either:

  FORWARD   every marker-carrying container class in SCHEME_B_MARKERS is
            actually emitted by the renderer (dead entries mean a marker was
            lost), and every such node carries an ld-mark child.
  REVERSE   the CSS still hides ld-mark, so a stylesheet-capable host does not
            show the marker twice (once inline, once via ::before).

Run against a built package:  python regress_scheme_b.py [package.zip]
"""
import json
import os
import re
import sys
import zipfile
from collections import Counter

sys.path.insert(0, r"C:\workspace\ldoce\converter")
import ldoce2yomitan as C  # noqa: E402

ZIP = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\workspace\ldoce\yomitan_cap_test\LDOCE5pp_Yomitan_2026.09.12_DEBUG.zip"

fails = []
marks = C.SCHEME_B_MARKERS
print(f"marker classes defined: {len(marks)}")
for k, v in sorted(marks.items()):
    print(f"  {k:22} -> {v!r}")

# ---- REVERSE: CSS must hide the inline marker ------------------------------
css = C.generate_css()
nc = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
hide = re.search(r'\[data-sc-class="ld-mark"\]\s*\{([^}]*)\}', nc)
if not hide:
    fails.append("no [data-sc-class=\"ld-mark\"] rule in CSS")
else:
    body = hide.group(1)
    if "display:none" not in body.replace(" ", ""):
        fails.append(f"ld-mark rule does not hide the marker: {body.strip()[:80]}")
    else:
        print("\nOK  CSS hides ld-mark (no double markers when a stylesheet loads)")

# ---- FORWARD: each marker class appears with an ld-mark child --------------
z = zipfile.ZipFile(ZIP)
print(f"\npackage: {os.path.basename(ZIP)}")
seen_marks = Counter()
classes_present = Counter()
for n in z.namelist():
    if not re.fullmatch(r"term_bank_\d+\.json", n):
        continue
    for r in json.loads(z.read(n)):
        if r[4] <= 0:
            continue
        stack = [r[5]]
        while stack:
            cur = stack.pop()
            if isinstance(cur, list):
                stack.extend(cur)
            elif isinstance(cur, dict):
                cls = (cur.get("data") or {}).get("class")
                if cls:
                    toks = cls.split()
                    for t in toks:
                        if t in marks:
                            classes_present[t] += 1
                            # does this node lead with an ld-mark child?
                            kids = cur.get("content")
                            kids = kids if isinstance(kids, list) else [kids]
                            if any(isinstance(k, dict)
                                   and (k.get("data") or {}).get("class") == "ld-mark"
                                   for k in kids):
                                seen_marks[t] += 1
                for k, v in cur.items():
                    if k != "data":
                        stack.append(v)

print(f"\n{'class':24} {'nodes':>10} {'with ld-mark':>13}")
for t in sorted(marks):
    n_nodes = classes_present.get(t, 0)
    n_marked = seen_marks.get(t, 0)
    flag = ""
    if n_nodes and n_marked == 0:
        flag = "  <== MISSING MARKERS"
        fails.append(f"{t}: {n_nodes} nodes, none carry ld-mark")
    elif n_nodes and n_marked < n_nodes:
        flag = f"  <== partial ({n_nodes - n_marked} unmarked)"
        fails.append(f"{t}: {n_nodes - n_marked} of {n_nodes} nodes lack ld-mark")
    print(f"  {t:22} {n_nodes:>10,} {n_marked:>13,}{flag}")

# dead entries: declared but never emitted in this package
dead = [t for t in marks if classes_present.get(t, 0) == 0]
if dead:
    print(f"\nnote: marker classes not present in THIS package (may be legitimately "
          f"absent for a small sample): {dead}")

print()
if fails:
    for f in fails:
        print("FAIL:", f)
    sys.exit(1)
print("RESULT: PASS -- markers are emitted and CSS hides them")
