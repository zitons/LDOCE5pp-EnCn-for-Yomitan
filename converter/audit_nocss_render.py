"""DEPRECATED -- DO NOT TRUST THE NUMBERS THIS PRINTS.

judgement error: flattened the SC tree to a single string, so block-level
seams that wrap in raw HTML were counted as missing separation (236,375
false positives). Use audit_nocss_final.py (real generator + real Chrome +
innerText).

Kept only as a record of the investigation. See REVIEW.md D33 and
HANDOVER.md pitfall 63.
"""
import json
import re
import sys
import zipfile
from collections import Counter

sys.path.insert(0, r"C:\workspace\ldoce\converter")
import ldoce2yomitan as C  # noqa: E402

ZIP = r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.12.zip"

# ---- flatten exactly like the generator: only `content` strings, no styles ----
def flatten(node, acc):
    if isinstance(node, str):
        acc.append(node)
    elif isinstance(node, list):
        for x in node:
            flatten(x, acc)
    elif isinstance(node, dict):
        flatten(node.get("content", ""), acc)
    return acc


PATTERNS = [
    ("A camel-glue    (AWLadjective)", re.compile(r"[a-z]\d*[A-Z][a-z]")),
    ("B bracket-glue  (abetting[)", re.compile(r"[A-Za-z\u2019'-]\d*\[")),
    ("C paren-glue    ()adjective)", re.compile(r"\)[A-Za-z]")),
    ("D level-glue    (verb\u25cf)", re.compile(r"[A-Za-z]\d*[\u25cf\u25cb]")),
    ("E slash-glue    (don1/)", re.compile(r"[a-z\u2019']\d*/")),
    ("F freq-glue     (S2W2)", re.compile(r"[SW]\d[SW]\d")),
    ("G pos-glue      (nounadj)", re.compile(
        r"[a-z](noun|verb|adjective|adverb|preposition|conjunction|determiner|"
        r"pronoun|exclamation|prefix|suffix|article)")),
]

z = zipfile.ZipFile(ZIP)
counts = Counter()
examples = {}
scanned = 0
total_glue_rows = 0
text_bytes = 0

for n in z.namelist():
    if not re.fullmatch(r"term_bank_\d+\.json", n):
        continue
    for r in json.loads(z.read(n)):
        if r[4] <= 0:
            continue
        scanned += 1
        txt = "".join(flatten(r[5], []))
        text_bytes += len(txt)
        # normalise the generator's whitespace handling: it keeps text verbatim
        hit_any = False
        for label, pat in PATTERNS:
            m = pat.search(txt)
            if m:
                hit_any = True
                counts[label] += 1
                if label not in examples:
                    s = max(0, m.start() - 40)
                    examples[label] = (r[0], txt[s:m.end() + 40])
        if hit_any:
            total_glue_rows += 1

print(f"package : {ZIP.split(chr(92))[-1]}")
print(f"entries : {scanned:,}   (flattened text {text_bytes/1048576:.1f} MB)")
print(f"rows with at least one glue pattern: {total_glue_rows:,} "
      f"({total_glue_rows*100.0/scanned:.2f}%)")
print()
print(f"{'pattern':42} {'rows':>8}   example")
print("-" * 118)
for label, pat in PATTERNS:
    n = counts.get(label, 0)
    ex = examples.get(label)
    exs = ""
    if ex:
        w, t = ex
        # show the matched fragment in context, compacted
        exs = f"{w!r}: ...{re.sub(chr(92)+'s+', ' ', t)[:58]}..."
    print(f"{label:42} {n:>8,}   {exs}")
