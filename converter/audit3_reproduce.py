"""Independent audit #3: does the CURRENT code reproduce the SHIPPED full zip?

Rebuilds the Pass-A index, replays the provisional alias plan exactly as
build() does, then re-renders a stratified sample of expressions taken from the
shipped package and byte-compares the resulting term rows against the shipped
ones. Does not trust or call the converter's own validator.
"""
import io
import json
import random
import re
import sys
import glob
import os
import zipfile
from collections import Counter

sys.path.insert(0, r"C:\workspace\ldoce\converter")
from ldoce2yomitan import (  # noqa: E402
    TermIndex, LdoceRenderer, classify_record, iter_records, strip_invisible,
    extract_tags, pos_tags_rules, sc, norm_target, sanitize_strings,
    ENTRY_SCORE, REDIRECT_SCORE,
)

SIDE = r"C:\workspace\ldoce\extract\LDOCE5++ V 2-15.mdx.txt"
def _find_zip():
    """Newest non-debug package in yomitan_full (an explicit argv[1] wins).

    The zip name carries the revision date, so a hardcoded path silently goes
    stale the moment the dictionary is rebuilt -- which then makes an audit
    report on the WRONG package. Discover it instead.
    """
    import sys as _sys
    if len(_sys.argv) > 1 and _sys.argv[1].endswith('.zip'):
        return _sys.argv[1]
    cands = [p for p in glob.glob(r"C:\\workspace\\ldoce\\yomitan_full\\LDOCE5pp_Yomitan_*.zip")
             if '_DEBUG' not in p]
    if not cands:
        raise SystemExit('no package found in yomitan_full/')
    return max(cands, key=os.path.getmtime)


ZIP = _find_zip()
random.seed(11)

z = zipfile.ZipFile(ZIP)
banks = sorted((n for n in z.namelist() if re.fullmatch(r"term_bank_\d+\.json", n)),
               key=lambda n: int(re.search(r"\d+", n).group()))
shipped = {}
entry_exprs, alias_exprs = [], []
for bn in banks:
    for r in json.loads(z.read(bn)):
        shipped[r[0]] = r
        (entry_exprs if r[4] > 0 else alias_exprs).append(r[0])

named = ["run", "get", "the", "A", "second class", "child", "improve", "begin",
         "decision", "however", "and", "money of account", "children"]
sample = [e for e in named if e in shipped]
topics = [e for e in entry_exprs if e.endswith("-topic")]
sample += random.sample(topics, min(6, len(topics)))
sample += random.sample(entry_exprs, 30)
sample += random.sample(alias_exprs, 15)
sample = list(dict.fromkeys(sample))
want = set(sample)
print(f"sampling {len(sample)} rows: {len([e for e in sample if shipped[e][4]>0])} entries, "
      f"{len([e for e in sample if shipped[e][4]<=0])} aliases")

# ---- replay Pass A + provisional alias plan (identical order to build()) ----
term_index = TermIndex()
alias_rows = []
contents = {}
for key, content in iter_records(SIDE):
    k = strip_invisible(key).strip()
    if not k:
        continue
    kind, target = classify_record(k, content)
    if kind == "entry":
        term_index.add(k)
    elif kind == "redirect":
        alias_rows.append((k, target))
    if k in want:
        contents[k] = content
print("Pass A done: unique entries", len(term_index.exact))

target_map = {}
for word, target in alias_rows:
    if target and target != word:
        target_map.setdefault(word, []).append(target)


def resolve_with(word, reachable, fold, normm):
    out, seen = [], set()
    stack = list(target_map.get(word, []))
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        hit = current
        if hit not in reachable:
            alt = fold.get(hit.casefold()) or normm.get(norm_target(hit))
            if alt:
                hit = alt
        if hit in reachable:
            out.append(hit)
        elif current in target_map:
            stack.extend(target_map[current])
    return list(dict.fromkeys(out))


prov_fold = {k.casefold(): k for k in term_index.exact}
prov_norm = {norm_target(k): k for k in term_index.exact}
for word in target_map:
    if word in term_index.exact:
        continue
    if resolve_with(word, term_index.exact, prov_fold, prov_norm):
        term_index.add_alias_word(word)

# ---- re-render the sample ----
renderer = LdoceRenderer(term_index, mode="bilingual", open_panels=False)
key_rules = {}
rebuilt = {}
for k in sample:
    content = contents.get(k)
    if content is None:
        print("  !! source record missing for", repr(k))
        continue
    kind, _ = classify_record(k, content)
    if kind != "entry":
        continue
    nodes = renderer.render_record(k, content)
    if not nodes:
        print("  !! re-render produced nothing for", repr(k))
        continue
    pos_tokens, freq_tokens = extract_tags(content)
    tags, rules = pos_tags_rules(pos_tokens, freq_tokens)
    key_rules[k] = rules
    gloss = [{"type": "structured-content", "content": sc("div", nodes, cls="ld")}]
    rebuilt[k] = [k, "", tags, rules, ENTRY_SCORE, gloss, 0, ""]

# alias rows: rebuild as build() does, against the re-rendered set
rendered = set(rebuilt)
rf = {k.casefold(): k for k in rendered}
rn = {norm_target(k): k for k in rendered}
for word in sample:
    row = shipped[word]
    if row[4] > 0:
        continue
    targets = resolve_with(word, rendered, rf, rn)
    if not targets:
        print("  !! alias no longer resolvable:", repr(word))
        continue
    rules = " ".join(dict.fromkeys(
        tok for t in targets for tok in (key_rules.get(t) or "").split()))
    rebuilt[word] = [word, "", "non-lemma", rules, REDIRECT_SCORE,
                     [[t, ["redirect"]] for t in targets], 0, ""]

# ---- compare ----
norm = lambda row: json.dumps(sanitize_strings(row[:6] + [row[7]]), ensure_ascii=False, sort_keys=False)
ok = diff = 0
seen_banks = Counter()
for k in sample:
    if k not in rebuilt:
        continue
    got, exp = norm(rebuilt[k]), norm(shipped[k])
    if got == exp:
        ok += 1
    else:
        diff += 1
        if diff <= 3:
            print(f"\n=== MISMATCH {k!r}")
            print("  shipped:", exp[:400])
            print("  rebuilt:", got[:400])
print(f"\nreproducible rows: {ok}  mismatched: {diff}  "
      f"({ok*100//max(ok+diff,1)}% byte-identical)")

# ---- independent structural checks (not the converter's validator) ----
ALLOWED = {
    "br": {"tag", "data"},
    **{t: {"tag", "content", "data", "lang"} for t in
       ("ruby", "rt", "rp", "table", "thead", "tbody", "tfoot", "tr")},
    **{t: {"tag", "content", "data", "colSpan", "rowSpan", "style", "lang"} for t in ("td", "th")},
    **{t: {"tag", "content", "data", "style", "title", "open", "lang"} for t in
       ("span", "div", "ol", "ul", "li", "details", "summary")},
    "img": {"tag", "data", "path", "width", "height", "title", "alt"},
    "a": {"tag", "content", "href", "lang"},
}


def bad_keys(node, out):
    if isinstance(node, list):
        for x in node:
            bad_keys(x, out)
    elif isinstance(node, dict):
        t = node.get("tag")
        if t not in ALLOWED:
            out.append(("tag", t))
        else:
            for kk in set(node) - ALLOWED[t]:
                out.append((t, kk))
        for kk, v in node.items():
            # "style" holds a property dict (fontWeight/...), not an SC node --
            # descending into it produced a false ('tag', None) on every styled span.
            if kk not in ("data", "style"):
                bad_keys(v, out)


all_exprs = set(shipped)
classes = set()
viol = Counter()
link_targets = set()
dangling = 0
redirect_targets = set()
bad_redirect = 0
seqs = []
for bn in banks:
    for r in json.loads(z.read(bn)):
        seqs.append(r[6])
        if r[4] <= 0:
            for it in r[5]:
                if isinstance(it, list):
                    redirect_targets.add(it[0])
                    if it[0] not in all_exprs:
                        bad_redirect += 1
        for it in r[5]:
            if isinstance(it, dict) and it.get("type") == "structured-content":
                bad = []
                bad_keys(it["content"], bad)
                for b in bad:
                    viol[b] += 1
                stack = [it["content"]]
                while stack:
                    n = stack.pop()
                    if isinstance(n, list):
                        stack.extend(n)
                    elif isinstance(n, dict):
                        if n.get("tag") == "a":
                            import urllib.parse as up
                            tgt = up.unquote((n.get("href") or "")[7:].split("&")[0])
                            link_targets.add(tgt)
                        stack.extend(v for kk, v in n.items() if kk != "data")
print(f"\n== independent structural scan ==")
print(f"  rows={len(seqs)}  seq unique={len(set(seqs))} range={min(seqs)}..{max(seqs)} "
      f"contiguous={len(set(seqs))==max(seqs)+1}")
print(f"  SC key violations: {dict(viol) if viol else 'none'}")
print(f"  link targets: {len(link_targets)}  not-a-row: "
      f"{len([t for t in link_targets if t not in all_exprs])}")
print(f"  redirect targets: {len(redirect_targets)}  not-a-row: {bad_redirect}")

css = z.read("styles.css").decode("utf-8")
defined = set()
for m in re.findall(r'\[data-sc-class="([^"]+)"\]', css):
    defined.update(m.split())
for m in re.findall(r'\[data-sc-class~="([^"]+)"\]', css):
    defined.update(m.split())
used = set()
for bn in banks:
    for r in json.loads(z.read(bn)):
        blob = r[5]
        def walk(n):
            if isinstance(n, list):
                for x in n:
                    walk(x)
            elif isinstance(n, dict):
                c = (n.get("data") or {}).get("class")
                if c:
                    used.update(c.split())
                for kk, v in n.items():
                    if kk != "data":
                        walk(v)
        walk(blob)
print(f"  CSS classes used={len(used)} defined={len(defined)} missing={sorted(used-defined)}")
