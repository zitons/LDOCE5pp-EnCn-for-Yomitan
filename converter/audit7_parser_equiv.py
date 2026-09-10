"""Audit #7: is `lxml` a drop-in replacement for `html.parser`?

Renders a stratified sample of entries with BOTH parsers (identical renderer
code, only the bs4 tree builder differs) and diffs the resulting term rows
byte-for-byte. Must be run before switching the production parser.

Usage:
    python audit7_parser_equiv.py [sample_size]
Exit code 0 = byte-identical (safe to switch), 1 = differences found.
"""
import json
import random
import sys
from collections import Counter

sys.path.insert(0, r"C:\workspace\ldoce\converter")
from bs4 import BeautifulSoup  # noqa: E402
from ldoce2yomitan import (  # noqa: E402
    TermIndex, LdoceRenderer, classify_record, iter_records, strip_invisible,
    extract_tags, pos_tags_rules, sc, merge_adjacent_text, sanitize_strings,
    ENTRY_SCORE,
)

SIDE = r"C:\workspace\ldoce\extract\LDOCE5++ V 2-15.mdx.txt"
N_RANDOM = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
random.seed(5)

NAMED = ["seeing", "second class", "abandon", "run", "get", "the", "A", "improve",
         "child", "18-wheeler", "2", "3-D", "99", "a", "be", "have", "make", "take",
         "money of account", "A1, the", "BBC", "DNA", "Mr", "sb's", "x-ray"]


class ParserSelectableRenderer(LdoceRenderer):
    """Mirrors LdoceRenderer.render_record exactly, but with a switchable parser."""

    def __init__(self, *args, parser="html.parser", **kwargs):
        super().__init__(*args, **kwargs)
        self.parser = parser

    def render_record(self, key, content):
        self.current_key = key
        soup = BeautifulSoup(content, self.parser)
        for h1 in soup.find_all("h1"):
            h1.decompose()
        root = (soup.find("div", class_="entry_content")
                or soup.find("span", class_="lm5ppbody")
                or soup)
        nodes = self._children_blocks(root)
        return merge_adjacent_text(nodes)


print(f"[*] Pass A over the source ({N_RANDOM} random + largest + named) ...")
term_index = TermIndex()
alias_rows = []
want = set(NAMED)
contents = {}
sizes = []
for key, content in iter_records(SIDE):
    k = strip_invisible(key).strip()
    if not k:
        continue
    kind, target = classify_record(k, content)
    if kind == "entry":
        term_index.add(k)
        sizes.append((len(content), k, content))
        if k in want:
            contents[k] = content
    elif kind == "redirect":
        alias_rows.append((k, target))

print(f"[*] entries={len(term_index.exact)}; picking sample ...")
sizes.sort()
largest = [(k, c) for _, k, c in sizes[-120:]]
smallest = [(k, c) for _, k, c in sizes[:120]]
pool = [(k, c) for _, k, c in sizes]
rnd = random.sample(pool, min(N_RANDOM, len(pool)))
sample = {}
for k, c in largest + smallest + rnd + [(k, c) for k, c in contents.items()]:
    sample.setdefault(k, c)
print(f"[*] sample = {len(sample)} entries "
      f"({len(largest)} largest, {len(smallest)} smallest, {len(rnd)} random)")

# ---- render with both parsers ----
tags_cache = {}
for k, c in sample.items():
    tags_cache[k] = extract_tags(c)


def render_all(parser):
    r = ParserSelectableRenderer(term_index, mode="bilingual", parser=parser)
    out = {}
    errs = []
    for k, c in sample.items():
        try:
            nodes = r.render_record(k, c)
        except Exception as exc:                                    # noqa: BLE001
            errs.append((k, repr(exc)))
            continue
        pos_tokens, freq_tokens = tags_cache[k]
        tags, rules = pos_tags_rules(pos_tokens, freq_tokens)
        gloss = [{"type": "structured-content", "content": sc("div", nodes, cls="ld")}]
        out[k] = json.dumps(sanitize_strings([k, "", tags, rules, ENTRY_SCORE, gloss, 0, ""]),
                            ensure_ascii=False)
    return out, errs


print("[*] rendering with html.parser ...")
hp, hp_err = render_all("html.parser")
print("[*] rendering with lxml ...")
lx, lx_err = render_all("lxml")

same = diff = 0
diffs = []
for k in sample:
    a, b = hp.get(k), lx.get(k)
    if a is None or b is None:
        continue
    if a == b:
        same += 1
    else:
        diff += 1
        if len(diffs) < 8:
            # locate first differing offset for a readable report
            i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            diffs.append((k, a[max(0, i - 90):i + 130], b[max(0, i - 90):i + 130]))

print(f"\n== parser equivalence ==")
print(f"  identical rows : {same}")
print(f"  different rows : {diff}")
print(f"  html.parser exceptions : {len(hp_err)}  {hp_err[:3]}")
print(f"  lxml exceptions        : {len(lx_err)}  {lx_err[:3]}")
tot_a = sum(len(v) for v in hp.values())
tot_b = sum(len(v) for v in lx.values())
print(f"  total serialized bytes: html.parser={tot_a}  lxml={tot_b}  ({(tot_b - tot_a) * 100 / max(tot_a, 1):+.2f}%)")
for k, a, b in diffs:
    print(f"\n  --- {k!r}\n      html.parser: {a}\n      lxml       : {b}")

sys.exit(1 if diff or lx_err else 0)
