"""Audit #6: before/after diff of two packages.

Reports the metrics that the render_head / cn_only fixes were supposed to move,
plus a regression guard on row counts and structure.

Usage:
    python audit6_diff.py <old.zip> <new.zip>
"""
import json
import re
import sys
import zipfile
from collections import Counter

OLD = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\workspace\ldoce\_baseline\LDOCE5pp_Yomitan_2026.09.10.BASELINE.zip"
NEW = sys.argv[2] if len(sys.argv) > 2 else \
    r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.10.zip"


def load(path):
    z = zipfile.ZipFile(path)
    banks = sorted((n for n in z.namelist() if re.fullmatch(r"term_bank_\d+\.json", n)),
                   key=lambda n: int(re.search(r"\d+", n).group()))
    rows = []
    for bn in banks:
        rows += json.loads(z.read(bn))
    return z, rows


def head_wraps(node, out):
    if isinstance(node, list):
        for x in node:
            head_wraps(x, out)
    elif isinstance(node, dict):
        if (node.get("data") or {}).get("class") == "ld-hwd-wrap":
            out.append(node)
        for k, v in node.items():
            if k != "data":
                head_wraps(v, out)


def metrics(path):
    z, rows = load(path)
    m = Counter()
    m["rows"] = len(rows)
    m["entries"] = sum(1 for r in rows if r[4] > 0)
    m["aliases"] = sum(1 for r in rows if r[4] <= 0)
    m["exprs"] = len({r[0] for r in rows})
    seqs = {r[6] for r in rows}
    m["seq_contiguous"] = int(len(seqs) == max(seqs) + 1)
    polluted = 0
    heads = {}
    raw_counts = Counter()
    for r in rows:
        if r[4] <= 0:
            continue
        blob = json.dumps(r[5], ensure_ascii=False)
        for k in ("ld-defcn", "ld-def", "ld-zh", "ld-excn", "ld-hyp",
                  "ld-register", "ld-geo", "ld-fieldxx", "ld-field", "ld-lexvar",
                  "ld-homophone", "ld-gloss", "ld-refhwd", "ld-collo"):
            raw_counts[k] += blob.count('"%s"' % k)
        wraps = []
        head_wraps(r[5], wraps)
        junk = []
        for w in wraps:
            items = w.get("content") or []
            if not isinstance(items, list):
                items = [items]
            junk += [s.strip() for s in items if isinstance(s, str) and s.strip()]
        if junk:
            polluted += 1
        # first head of the entry, flattened, for spot comparison
        heads[r[0]] = flatten(wraps[0]) if wraps else ""
    m["headword_polluted"] = polluted
    m.update(raw_counts)
    m["css_missing"] = css_missing(z, rows)
    return m, heads


def css_missing(z, rows):
    used = set()

    def walk(n):
        if isinstance(n, list):
            for x in n:
                walk(x)
        elif isinstance(n, dict):
            c = (n.get("data") or {}).get("class")
            if c:
                used.update(c.split())
            for k, v in n.items():
                if k != "data":
                    walk(v)
    for r in rows:
        walk(r[5])
    css = z.read("styles.css").decode("utf-8")
    defined = set()
    for m in re.findall(r'\[data-sc-class="([^"]+)"\]', css):
        defined.update(m.split())
    for m in re.findall(r'\[data-sc-class~="([^"]+)"\]', css):
        defined.update(m.split())
    return sorted(used - defined)


def flatten(n):
    if isinstance(n, str):
        return n
    if isinstance(n, list):
        return "".join(flatten(x) for x in n)
    if isinstance(n, dict):
        c = (n.get("data") or {}).get("class", "")
        if n.get("tag") == "br":
            return " "
        inner = "".join(flatten(x) for x in (n.get("content") or []))
        return f"[{c}:{inner}]" if c else inner
    return ""


old, old_heads = metrics(OLD)
new, new_heads = metrics(NEW)

print(f"old = {OLD}")
print(f"new = {NEW}\n")
print(f"{'metric':<24}{'old':>12}{'new':>12}{'delta':>12}")
for k in ("rows", "entries", "aliases", "exprs", "seq_contiguous",
          "headword_polluted", "ld-defcn", "ld-def", "ld-zh", "ld-excn",
          "ld-hyp", "ld-register", "ld-geo", "ld-fieldxx", "ld-field",
          "ld-lexvar", "ld-homophone", "ld-gloss", "ld-refhwd", "ld-collo"):
    o, n = old.get(k, 0), new.get(k, 0)
    flag = "  <-- changed" if o != n else ""
    print(f"{k:<24}{o:>12}{n:>12}{n - o:>+12}{flag}")
print(f"\nCSS classes missing in new: {new['css_missing'] or 'none'}")

print("\n== headword changes (sampled) ==")
changed = [w for w in old_heads if w in new_heads and old_heads[w] != new_heads[w]]
print(f"heads that changed: {len(changed)} / {len(old_heads)}")
for w in sorted(changed)[:20]:
    print(f"  {w!r}\n     old: {old_heads[w][:150]}\n     new: {new_heads[w][:150]}")

sys.exit(1 if (new["headword_polluted"] or new["css_missing"]) else 0)
