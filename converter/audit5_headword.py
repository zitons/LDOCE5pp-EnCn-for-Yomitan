"""Audit #5: headword pollution check.

render_head()'s fallback branch appends any unrecognised Head child's text into
the headword (<span class="ld-hwd-wrap">), so labels like REGISTERLAB/GEO/FIELD
get glued onto the headword. This reports how many entries are affected and
which classes are responsible, by scanning the shipped package AND the source.

Usage:
    python audit5_headword.py [path\\to\\package.zip]
Exit code is non-zero if any headword pollution is found, so it works as a
regression gate after a rebuild.
"""
import json
import re
import sys
import zipfile
from collections import Counter

sys.path.insert(0, r"C:\workspace\ldoce\converter")
from ldoce2yomitan import (  # noqa: E402
    iter_records, strip_invisible, classify_record,
    DROP_CLASSES, CHIP_MAP, INLINE_MAP,
)

ZIP = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.10.zip"
SIDE = r"C:\workspace\ldoce\extract\LDOCE5++ V 2-15.mdx.txt"

# ---- 1. package side: which headwords have junk glued inside ld-hwd-wrap ----
z = zipfile.ZipFile(ZIP)
banks = sorted((n for n in z.namelist() if re.fullmatch(r"term_bank_\d+\.json", n)),
               key=lambda n: int(re.search(r"\d+", n).group()))
def walk(node, out):
    if isinstance(node, list):
        for x in node:
            walk(x, out)
    elif isinstance(node, dict):
        if (node.get("data") or {}).get("class") == "ld-hwd-wrap":
            out.append(node)
        for k, v in node.items():
            if k != "data":
                walk(v, out)

affected = 0
entries = 0
leaks = Counter()
samples = []
for bn in banks:
    for r in json.loads(z.read(bn)):
        if r[4] <= 0:
            continue
        entries += 1
        wraps = []
        walk(r[5], wraps)
        junk = []
        for node in wraps:
            items = node.get("content") or []
            if not isinstance(items, list):
                items = [items]
            junk += [s.strip() for s in items if isinstance(s, str) and s.strip()]
        if junk:
            affected += 1
            for s in junk:
                leaks[s] += 1
            if len(samples) < 12:
                samples.append((r[0], junk))

print(f"== package: {ZIP}")
print(f"   entries={entries}  headword-polluted={affected} "
      f"({affected * 100 / max(entries, 1):.2f}%)")
print(f"   leaked strings total={sum(leaks.values())} distinct={len(leaks)}")
print("   top leaked text:")
for t, c in leaks.most_common(20):
    print(f"      {c:>6}  {t!r}")
print("   samples:")
for w, j in samples:
    print(f"      {w!r} -> {j}")

# ---- 2. source side: which Head direct children render_head ignores ----
HANDLED = {"HWD", "HOMNUM", "PronCodes", "PRON", "AMEVARPRON", "lm5pp_POS",
           "GRAM", "LEVEL", "FREQ", "tooltip", "Inflections"}
TAGRE = re.compile(r"<(/?)([a-zA-Z0-9]+)([^>]*)>")
CLUS = re.compile(r'class="([^"]*)"')
HEADTAG = re.compile(r'<span class="([^"]*)"')
VOID = {"br", "img", "input", "meta", "link", "hr"}


def head_regions(content):
    out, pos = [], 0
    while True:
        m = HEADTAG.search(content, pos)
        if not m:
            break
        if "Head" not in m.group(1).split():
            pos = m.end()
            continue
        i = m.start()
        depth = 0
        md = None
        for t in TAGRE.finditer(content, i):
            nm = t.group(2).lower()
            if nm in VOID or t.group(3).rstrip().endswith("/"):
                continue
            depth += -1 if t.group(1) == "/" else 1
            if depth == 0:
                md = t
                break
        if md is None:
            break
        out.append(content[i:md.end()])
        pos = i + 1
    return out


unhandled = Counter()
heads = 0
for key, content in iter_records(SIDE):
    k = strip_invisible(key).strip()
    if not k:
        continue
    kind, _ = classify_record(k, content)
    if kind != "entry":
        continue
    for reg in head_regions(content):
        heads += 1
        depth = 0
        for t in TAGRE.finditer(reg):
            nm = t.group(2).lower()
            if nm in VOID or t.group(3).rstrip().endswith("/"):
                continue
            if t.group(1) == "/":
                depth -= 1
                continue
            depth += 1
            if depth != 2:          # direct children of the Head span only
                continue
            cm = CLUS.search(t.group(3))
            for tok in (cm.group(1).split() if cm else []):
                if tok in HANDLED or tok in DROP_CLASSES:
                    continue
                unhandled[tok] += 1

print(f"\n== source: {heads} Head blocks; direct children render_head ignores:")
for t, c in unhandled.most_common(30):
    mapped = ("CHIP_MAP->" + CHIP_MAP[t]) if t in CHIP_MAP else (
        ("INLINE_MAP->" + INLINE_MAP[t][0]) if t in INLINE_MAP else "** NO MAPPING **")
    print(f"   {c:>6}  {t:<14} {mapped}")

sys.exit(1 if affected else 0)
