"""Audit #1: where did the dropped aliases go? Single pass over the sidecar,
reusing the converter's own classification logic (imported, not re-typed)."""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\workspace\ldoce\converter")
from ldoce2yomitan import classify_record, iter_records, strip_invisible  # noqa: E402

SIDECAR = r"C:\workspace\ldoce\extract\LDOCE5++ V 2-15.mdx.txt"

entry_keys = {}          # exact key -> count (records)
alias = {}               # word -> [targets]
redirect_records = 0

for key, content in iter_records(SIDECAR):
    k = strip_invisible(key).strip()
    if not k:
        continue
    kind, target = classify_record(k, content)
    if kind == "entry":
        entry_keys[k] = entry_keys.get(k, 0) + 1
    elif kind == "redirect":
        redirect_records += 1
        if target and target != k:
            alias.setdefault(k, []).append(target)

rendered = set(entry_keys)
rendered_fold = {k.casefold(): k for k in rendered}

def resolve(word):
    out, seen = [], set()
    stack = list(alias.get(word, []))
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        hit = cur if cur in rendered else rendered_fold.get(cur.casefold())
        if hit:
            out.append(hit)
        elif cur in alias:
            stack.extend(alias[cur])
    return out

dropped = []
for word in alias:
    if word in rendered:
        continue
    if not resolve(word):
        dropped.append(word)

print(f"entry records={sum(entry_keys.values())} unique={len(entry_keys)}")
print(f"redirect records={redirect_records} alias words(with distinct target)={len(alias)}")
print(f"alias rows produced={len([w for w in alias if w not in rendered])}")
print(f"dropped alias count={len(dropped)}")

# categorize dropped
def categorize(word):
    targets = alias.get(word, [])
    joined = " ".join(targets).casefold() + " " + word.casefold()
    if word.casefold().endswith("-topic") or "-topic " in word.casefold():
        return "topic-page alias (ACTIV cross refs)"
    if "acti" in joined and "v:" in joined:
        return "points to ACTIV: page"
    if any("ldoce" in t and t.lower().endswith("jpg") for t in targets):
        return "points to image key"
    if "error" in joined:
        return "error page"
    # target wholly absent?
    missing = [t for t in targets if t not in rendered and t.casefold() not in rendered_fold
               and t not in alias]
    if missing:
        return "broken @@@LINK (target key absent)"
    return "other"

buckets = Counter()
samples = {}
for w in dropped:
    cat = categorize(w)
    buckets[cat] += 1
    samples.setdefault(cat, []).append((w, alias.get(w, [])[:2]))

print("\nDROPPED BREAKDOWN:")
for cat, n in buckets.most_common():
    print(f"  {n:>6}  {cat}")
    for w, t in samples[cat][:6]:
        print(f'          e.g. {w!r} -> {t}')

# also categorize skipped keys
print("\nSKIP-KEY SAMPLES (from classify, recount):")
sk = Counter()
sk_sample = []
for key, content in iter_records(SIDECAR):
    k = strip_invisible(key).strip()
    if not k:
        continue
    kind, _ = classify_record(k, content)
    if kind == "skip":
        if k.upper().startswith("ACTIV:"):
            sk["ACTIV:"] += 1
        elif re.match(r"^ldoce\d+jpg", k, re.I):
            sk["ldoceNNNjpg"] += 1
        else:
            sk["other"] += 1
            if len(sk_sample) < 15:
                sk_sample.append((k, content[:60].replace("\n", " ")))
for name, n in sk.items():
    print(f"  {n:>6}  {name}")
print(f"  {sum(sk.values()):>6}  TOTAL skipped")
for k, c in sk_sample:
    print(f"     other sample: {k!r} :: {c!r}")
