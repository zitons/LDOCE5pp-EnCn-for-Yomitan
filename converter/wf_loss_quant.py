"""Quantify the two render_wordfams losses across the corpus.

(1) <span class="opp"> inside LDOCE_word_family  -> dropped entirely
(2) non-empty text nodes that are DIRECT children of LDOCE_word_family -> dropped
Also: what other element classes appear as direct children of
LDOCE_word_family but are handled by none of the branches?
"""
import collections
import re
import sys

from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 3000

HANDLED = ("pos", "rootword", "crossRef", "w")

n_entries = 0
n_fam = 0
opp_blocks = 0
opp_words = 0
loose_text = 0
loose_examples = []
unhandled = collections.Counter()
unhandled_examples = []
for key, content in M.iter_records(SIDE):
    k = M.strip_invisible(key).strip()
    if not k:
        continue
    kind, _ = M.classify_record(k, content)
    if kind != "entry":
        continue
    n_entries += 1
    if n_entries > LIMIT:
        break
    soup = BeautifulSoup(content, "lxml")
    for fam in soup.find_all("span", class_="LDOCE_word_family"):
        n_fam += 1
        for ch in fam.children:
            if isinstance(ch, NavigableString):
                t = str(ch).strip()
                if t:
                    loose_text += 1
                    if len(loose_examples) < 12:
                        loose_examples.append((k, t[:50]))
                continue
            cls = set(ch.get("class") or [])
            if "opp" in cls:
                opp_blocks += 1
                opp_words += len(ch.find_all(["a", "span"], class_="w")) or 1
                continue
            if not (cls & set(HANDLED)):
                unhandled[" ".join(sorted(cls)) or ch.name] += 1
                if len(unhandled_examples) < 12:
                    unhandled_examples.append((k, " ".join(sorted(cls)), ch.get_text(" ", strip=True)[:50]))

print(f"entries scanned            = {n_entries}")
print(f"LDOCE_word_family blocks   = {n_fam}")
print(f"  span.opp (dropped)       = {opp_blocks}   (~{opp_blocks/max(n_fam,1)*100:.1f}% of blocks)")
print(f"  loose text nodes (dropped)= {loose_text}  (~{loose_text/max(n_fam,1)*100:.1f}%)")
print()
print("loose text examples:")
for k, t in loose_examples:
    print(f"   {k!r}: {t!r}")
print()
print("direct children matched by NO branch:")
for cls, n in unhandled.most_common(15):
    print(f"   {n:>6}  class={cls!r}")
print("examples:")
for k, cls, t in unhandled_examples:
    print(f"   {k!r} [{cls}] {t!r}")
print()
# global count for context
raw = 0
with open(SIDE, "rb") as fh:
    for chunk in iter(lambda: fh.read(1 << 24), b""):
        raw += chunk.count(b'class="opp"')
print(f'global `class="opp"` occurrences in the whole sidecar: {raw}')
