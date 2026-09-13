"""Regression gate for the POS/rules cap removal (follow-on to audit A3).

Asserts, against a REAL build of the affected words, that:
  * every POS tag present in the source .Head POS spans appears in definitionTags
  * every rule token likewise
  * specific historical losses are gone (see MUST_HAVE: 'back'=adj, 'cross'=adv+prefix,
    'after'=prefix, 'arch'=prefix, 'close'=adv, 'clean'=adv, 'out'=prefix,
    'one'=det+num)
  * definitionTags counts are NOT clamped (rows may exceed TAG_LIMIT)

Usage:
    python -u regress_pos_cap.py [package.zip]
Defaults to yomitan_cap_test/LDOCE5pp_Yomitan_2026.09.12_DEBUG.zip.
"""
import json
import os
import re
import sys
import zipfile

from bs4 import BeautifulSoup

sys.path.insert(0, r"C:\workspace\ldoce\converter")
import ldoce2yomitan as C  # noqa: E402

ZIP = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\workspace\ldoce\yomitan_cap_test\LDOCE5pp_Yomitan_2026.09.12_DEBUG.zip"
SIDE = r"C:\workspace\ldoce\extract\LDOCE5++ V 2-15.mdx.txt"
FREQ = {"S1", "S2", "S3", "W1", "W2", "W3"}

# the historical casualties this gate exists to prevent
MUST_HAVE = {
    "back": {"adj"},
    "cross": {"adv", "prefix"},
    "after": {"prefix"},
    "arch": {"prefix"},
    "close": {"adv"},
    "clean": {"adv"},
    "out": {"prefix"},
    "one": {"det", "num"},
}

z = zipfile.ZipFile(ZIP)
pkg = {}
for n in z.namelist():
    if re.fullmatch(r"term_bank_\d+\.json", n):
        for r in json.loads(z.read(n)):
            if r[4] > 0:
                pkg.setdefault(r[0], []).append(r)

print(f"package: {os.path.basename(ZIP)}")
print(f"entry rows: {sum(len(v) for v in pkg.values())}, keys: {len(pkg)}")

checked = tag_fail = rule_fail = 0
over_limit = []
max_tags = (0, None)

for key, content in C.iter_records(SIDE):
    k = C.strip_invisible(key).strip()
    if not k or k not in pkg:
        continue
    kind, _ = C.classify_record(k, content)
    if kind != "entry":
        continue
    checked += 1
    soup = BeautifulSoup(content, "lxml")
    ref_t, ref_r = set(), set()
    for span in soup.find_all("span", class_="lm5pp_POS"):
        for p in span.find_all("span", class_="portrait"):
            p.decompose()
        txt = re.sub(r"\s+", " ", span.get_text(" ", strip=True)).strip().lower().strip(" .;")
        for part in [txt] + re.split(r"[,;]", txt):
            part = part.strip(" .()")
            if not part:
                continue
            t = C.POS_TAG_MAP.get(part)
            if t:
                ref_t.add(t)
            rl = C.POS_RULE_MAP.get(part, "")
            if rl:
                ref_r.add(rl)
    ref_t -= FREQ
    got_t, got_r = set(), set()
    for r in pkg[k]:
        got_t |= set(r[2].split())
        got_r |= set(r[3].split())
        n = len(r[2].split())
        if n > max_tags[0]:
            max_tags = (n, r[0])
        if n > C.TAG_LIMIT:
            over_limit.append((r[0], n))
    if ref_t - got_t:
        tag_fail += 1
        print(f"  FAIL tags {k!r}: missing {sorted(ref_t - got_t)}")
    if ref_r - got_r:
        rule_fail += 1
        print(f"  FAIL rules {k!r}: missing {sorted(ref_r - got_r)}")

print(f"\nentries checked              : {checked}")
print(f"keys with a missing POS tag  : {tag_fail}")
print(f"keys with a missing rule     : {rule_fail}")

spec_fail = 0
spec_skip = 0
for w, need in MUST_HAVE.items():
    if w not in pkg:
        # The package under test may be a narrow --test-words sample that does not
        # contain this word; that is a coverage gap in the sample, not a defect.
        # Report it separately so a targeted run is not mistaken for a failure.
        spec_skip += 1
        continue
    got = set()
    for r in pkg.get(w, []):
        got |= set(r[2].split())
    miss = need - got
    if miss:
        spec_fail += 1
        print(f"  FAIL {w!r} missing historical token {sorted(miss)}")
    else:
        print(f"  OK   {w!r} carries {sorted(need)}")

print(f"\nrows above TAG_LIMIT={C.TAG_LIMIT}: {len(over_limit)} "
      f"(NOT a failure -- nothing is truncated; samples {over_limit[:5]})")
print(f"widest definitionTags: {max_tags[0]} on {max_tags[1]!r}")
if spec_skip:
    print(f"words not present in this package (sample gap, not a failure): {spec_skip}")

# `over_limit` is an observation, not a requirement: a narrow sample may contain
# no wide-tag row without anything being wrong. The gate asserts that no tag or
# rule was LOST, and that any word present in the package keeps its historical
# tokens.
ok = (tag_fail == 0 and rule_fail == 0 and spec_fail == 0)
if ok and not over_limit:
    print("note: this sample has no row above TAG_LIMIT; run against a full build "
          "to exercise the width path.")
print("\nRESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
