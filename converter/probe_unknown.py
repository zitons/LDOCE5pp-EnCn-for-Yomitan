"""Find WHICH code path logs 'w' / 'rootword' / 'crossRef' as unknown classes."""
import sys
import traceback
from collections import Counter

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

WATCH = {"w", "rootword", "crossRef", "newfamily", "notRef"}
hits = {}


class TracingCounter(Counter):
    def __setitem__(self, key, value):
        if key in WATCH and key not in hits:
            stack = [f for f in traceback.extract_stack()[:-1]
                     if "ldoce2yomitan" in f.filename]
            hits[key] = stack[-4:]
        super().__setitem__(key, value)


SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"
ti = M.TermIndex()
recs = []
for k, c in M.iter_records(SIDE):
    kk = M.strip_invisible(k).strip()
    if not kk:
        continue
    kind, _ = M.classify_record(kk, c)
    if kind == "entry":
        ti.add(kk)
        recs.append((kk, c))
    if len(recs) >= 4000:
        break

r = M.LdoceRenderer(ti)
r.unknown_classes = TracingCounter()
for k, c in recs:
    r.render_record(k, c)

print("unknown classes seen:", dict(r.unknown_classes.most_common(8)))
print()
for key, stack in hits.items():
    print(f"=== {key!r} logged from ===")
    for f in stack:
        print(f"   {f.filename.split(chr(92))[-1]}:{f.lineno}  {f.line}")
    print()
