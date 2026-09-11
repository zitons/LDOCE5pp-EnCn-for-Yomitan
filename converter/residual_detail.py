"""residual_detail: for each source LEAF text node, is its text present verbatim
in the rendered output?  Substring test -- immune to the multiset/ancestor
double-counting that plagued earlier probes.

Hidden-per-audit9-model nodes are skipped, so anything reported is either real
loss or a deliberate transform we should be able to name.
"""
import collections
import re
import sys

from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 600
DROP = set(M.DROP_CLASSES)
EXTRA_HIDDEN = {"HYPHENATION", "landscape", "portrait"}


def is_hidden(cls):
    return bool(cls & DROP) or bool(cls & EXTRA_HIDDEN) or ("tooltip" in cls and "LEVEL" not in cls)


def out_text(node, acc):
    if isinstance(node, str):
        acc.append(node)
    elif isinstance(node, list):
        for x in node:
            out_text(x, acc)
    elif isinstance(node, dict):
        out_text(node.get("content", ""), acc)
    return acc


def walk(node, path, out):
    for ch in getattr(node, "children", []):
        if isinstance(ch, NavigableString):
            p = ch.parent
            if p is not None and p.name in ("style", "script"):
                continue
            t = re.sub(r"\s+", " ", str(ch)).strip()
            if t:
                out.append((" > ".join(path[-3:]) if path else "(root)", t, p))
        elif isinstance(ch, Tag):
            if ch.name in ("style", "script"):
                continue
            cls = set(ch.get("class") or [])
            if is_hidden(cls):
                continue
            nm = ch.name + ("." + " ".join(ch.get("class")) if cls else "")
            walk(ch, path + [nm], out)
    return out


ti = M.TermIndex()
recs = {}
for key, content in M.iter_records(SIDE):
    k = M.strip_invisible(key).strip()
    if not k:
        continue
    kind, _ = M.classify_record(k, content)
    if kind == "entry":
        ti.add(k)
        recs[k] = content
        if len(recs) >= LIMIT:
            break

renderer = M.LdoceRenderer(ti)
lost_by_path = collections.Counter()
lost_samples = collections.defaultdict(list)
total_leaves = 0
lost_leaves = 0

for k, content in recs.items():
    soup = BeautifulSoup(content, "lxml")
    leaves = []
    walk(soup, [], leaves)
    ot = re.sub(r"\s+", " ", "".join(out_text(renderer.render_record(k, content) or [], [])))
    ot_low = ot.lower()
    for sig, text, parent in leaves:
        total_leaves += 1
        if text.lower() in ot_low:
            continue
        lost_leaves += 1
        lost_by_path[sig] += 1
        if len(lost_samples[sig]) < 5:
            lost_samples[sig].append((k, text[:80]))

print(f"entries       = {len(recs)}")
print(f"source leaves = {total_leaves}")
print(f"leaves whose text is NOT verbatim in output = {lost_leaves} "
      f"({lost_leaves*100.0/max(total_leaves,1):.2f}%)")
print()
print("=== top 30 paths by lost leaves ===")
for sig, n in lost_by_path.most_common(30):
    print(f"  {n:>5}  {sig[:110]}")
    for w, t in lost_samples[sig][:2]:
        print(f"          e.g. {w!r}: {t!r}")
