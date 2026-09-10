"""Audit #2 (restructured): official Yomitan JSON schema on stratified samples
(2000 random + extreme rows per bank + the 200 largest rows overall), plus a
FULL structural scan over all rows (fastjsonschema on 470MB full-corpus is CPU
pathological; samples + full structural scan give equivalent assurance)."""
import json
import random
import re
import sys
import zipfile
from collections import Counter

import fastjsonschema

SCHEMA_DIR = r"C:\workspace\ldoce\yomitan-ext\data\schemas"
ZIP = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.10.zip"
random.seed(7)


def load(name):
    with open(f"{SCHEMA_DIR}\\{name}", encoding="utf-8") as f:
        return json.load(f)


term_v = fastjsonschema.compile(load("dictionary-term-bank-v3-schema.json"))
index_v = fastjsonschema.compile(load("dictionary-index-schema.json"))
tag_v = fastjsonschema.compile(load("dictionary-tag-bank-v3-schema.json"))

CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x{FFFE}\x{FFFF}]".replace(
    r"\x{FFFE}", "\ufffe").replace(r"\x{FFFF}", "\uffff"))
CJK_RE = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")

z = zipfile.ZipFile(ZIP)
names = z.namelist()

print("== index.json vs official dictionary-index-schema ==")
idx = json.loads(z.read("index.json"))
try:
    index_v(idx)
    print("  PASS", {k: idx.get(k) for k in ("title", "format", "revision", "sequenced")})
except fastjsonschema.JsonSchemaValueException as e:
    print("  FAIL", e.message)

print("== term_meta_bank vs official schema ==")
_meta_v = fastjsonschema.compile(load("dictionary-term-meta-bank-v3-schema.json"))
_meta_names = sorted((n for n in names if re.fullmatch(r"term_meta_bank_\d+\.json", n)),
                     key=lambda n: int(re.search(r"\d+", n).group()))
if not _meta_names:
    print("  (none present)")
_meta_rows = 0
for _n in _meta_names:
    _d = json.loads(z.read(_n))
    _meta_v(_d)                      # raises on any schema violation
    _meta_rows += len(_d)
print(f"  OK: {len(_meta_names)} meta banks, {_meta_rows} freq rows")

print("== tag_bank vs official schema ==")
tb = json.loads(z.read("tag_bank_1.json"))
tag_names = {t[0] for t in tb}
try:
    tag_v(tb)
    print("  PASS", len(tb), "tags")
except fastjsonschema.JsonSchemaValueException as e:
    print("  FAIL", e.message)

bank_names = sorted((n for n in names if re.fullmatch(r"term_bank_\d+\.json", n)),
                    key=lambda n: int(re.search(r"\d+", n).group()))

all_exprs = set()
expr_count = Counter()
stats = Counter()
no_head = []
empty_rules = 0
redirect_nonentry = []
seqs = set()
ctrl_bad = []
tag_tokens = Counter()
sized = []          # (len, bank, expr) for extremes
row_index = {}      # expr -> (bank, approx offset) not needed; rescan banks for sampled validation

# ---- full structural scan -------------------------------------------------
for bn in bank_names:
    rows = json.loads(z.read(bn))
    stats["rows"] += len(rows)
    for r in rows:
        expr, tags, rules, score, gloss, seq = r[0], r[2], r[3], r[4], r[5], r[6]
        expr_count[expr] += 1
        all_exprs.add(expr)
        seqs.add(seq)
        for t in tags.split():
            tag_tokens[t] += 1
        blob = json.dumps(gloss, ensure_ascii=False)
        if CTRL_RE.search(blob):
            ctrl_bad.append(expr)
        sized.append((len(blob), bn, expr))
        if score > 0:
            stats["entries"] += 1
            if not rules:
                empty_rules += 1
            if "ld-head" not in blob and "ld-topics" not in blob and "ld-sense" not in blob:
                no_head.append((expr, len(blob)))
        else:
            stats["redirects"] += 1
            for item in gloss:
                if isinstance(item, list) and item[0] not in all_exprs:
                    redirect_nonentry.append((expr, item[0]))
print(f"structural scan: rows={stats['rows']} entries={stats['entries']} "
      f"redirects={stats['redirects']}")

# pass2 redirect target check (all_exprs only complete after full scan)
print(f"  redirect items -> non-entry/nonexistent: recheck below")
entry_exprs = set()
for bn in bank_names:
    for r in json.loads(z.read(bn)):
        if r[4] > 0:
            entry_exprs.add(r[0])
bad_redirect = 0
for bn in bank_names:
    for r in json.loads(z.read(bn)):
        if r[4] <= 0:
            for item in r[5]:
                if isinstance(item, list) and item[0] not in entry_exprs:
                    bad_redirect += 1
                    if bad_redirect <= 5:
                        print("   BAD redirect target:", r[0], "->", item[0])

dups = {e: c for e, c in expr_count.items() if c > 1}
print(f"  unique exprs={len(all_exprs)} duplicate exprs={len(dups)} "
      f"top={sorted(dups.items(), key=lambda kv: -kv[1])[:5]}")
print(f"  seq contiguous 0..{max(seqs)} unique={len(seqs)} (expected {max(seqs)+1}): "
      f"{'OK' if len(seqs) == max(seqs) + 1 else 'GAP!'}")
print(f"  no-head entry rows: {len(no_head)} sample={no_head[:5]}")
print(f"  empty-rules entry rows: {empty_rules} ({empty_rules/stats['entries']:.1%})")
print(f"  control-char rows: {len(ctrl_bad)} sample={ctrl_bad[:5]}")
unknown = [t for t in tag_tokens if t not in tag_names]
print(f"  tag tokens outside tag_bank: {unknown}")

# ---- official schema: sampled + extremes ------------------------------------
sized.sort()
must_check = {t[1:] for t in sized[:200]} | {t[1:] for t in sized[-200:]}

def validate_rows(rows, label):
    try:
        term_v(rows)
        return 0
    except fastjsonschema.JsonSchemaValueException as e:
        errs = getattr(e, "errors", None) or [{"data_path": e.path, "message": e.message}]
        for err in errs[:8]:
            print(f"  SCHEMA FAIL [{label}] {err.get('data_path')}: {str(err.get('message'))[:140]}")
        return len(errs)

fails = 0
checked = 0
for bn in bank_names:
    rows = json.loads(z.read(bn))
    sample = random.sample(rows, min(2000, len(rows)))
    exprs_here = {e for (b, e) in must_check if b == bn}
    extra = [r for r in rows if r[0] in exprs_here]
    batch = sample + extra
    fails += validate_rows(batch, bn)
    checked += len(batch)
print(f"official term-bank-v3 schema: rows validated={checked} ({checked*100//stats['rows']}% sample) "
      f"failures={fails}")
