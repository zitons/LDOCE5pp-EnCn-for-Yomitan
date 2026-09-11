"""Independent audit #4: structural checks on the shipped zip, with the style-dict
false positive removed, plus an alias/entry shadowing check."""
import json
import re
import urllib.parse as up
import glob
import os
import zipfile
from collections import Counter, defaultdict

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
STYLE_PROP_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9]*$")


def walk(node, on_dict, on_str=None):
    if isinstance(node, list):
        for x in node:
            walk(x, on_dict, on_str)
    elif isinstance(node, dict):
        on_dict(node)
        for kk, v in node.items():
            if kk in ("data", "style"):
                continue
            walk(v, on_dict, on_str)
    elif isinstance(node, str) and on_str:
        on_str(node)


z = zipfile.ZipFile(ZIP)
banks = sorted((n for n in z.namelist() if re.fullmatch(r"term_bank_\d+\.json", n)),
               key=lambda n: int(re.search(r"\d+", n).group()))

viol = Counter()
bad_style_props = Counter()
entry_exprs = set()
alias_exprs = set()
expr_rows = defaultdict(list)
link_targets = set()
redirect_targets = set()
seqs = []
used_classes = set()
href_bad = 0
titles = 0
langs = Counter()
row_count = 0

for bn in banks:
    for r in json.loads(z.read(bn)):
        row_count += 1
        seqs.append(r[6])
        expr_rows[r[0]].append(r[4])
        (entry_exprs if r[4] > 0 else alias_exprs).add(r[0])
        for it in r[5]:
            if isinstance(it, list):
                redirect_targets.add(it[0])
                continue
            if not (isinstance(it, dict) and it.get("type") == "structured-content"):
                continue

            def on_dict(n):
                global href_bad, titles
                t = n.get("tag")
                if t not in ALLOWED:
                    viol[("bad-tag", t)] += 1
                    return
                for kk in set(n) - ALLOWED[t]:
                    viol[(t, kk)] += 1
                c = (n.get("data") or {}).get("class")
                if c:
                    used_classes.update(c.split())
                if n.get("title"):
                    titles += 1
                if n.get("lang"):
                    langs[n["lang"]] += 1
                st = n.get("style")
                if st is not None:
                    if not isinstance(st, dict):
                        viol[(t, "style-not-object")] += 1
                    else:
                        for pk, pv in st.items():
                            if not STYLE_PROP_RE.match(pk) or not isinstance(pv, str):
                                bad_style_props[(pk, type(pv).__name__)] += 1
                if t == "a":
                    h = n.get("href") or ""
                    if not re.match(r"^(?:\?|https?:)", h):
                        href_bad += 1
                    elif h.startswith("?query="):
                        link_targets.add(up.unquote(h[len("?query="):].split("&")[0]))

            walk(it["content"], on_dict)

print("== structural ==")
print(f"  rows={row_count} seq unique={len(set(seqs))} range={min(seqs)}..{max(seqs)} "
      f"contiguous={len(set(seqs)) == max(seqs)+1}")
print(f"  SC key/tag violations: {dict(viol) if viol else 'NONE'}")
print(f"  style prop violations: {dict(bad_style_props) if bad_style_props else 'NONE'}")
print(f"  <a> href malformed: {href_bad}")
print(f"  link targets={len(link_targets)} not-a-row={len(link_targets - set(expr_rows))}")
print(f"  redirect targets={len(redirect_targets)} not-a-row={len(redirect_targets - set(expr_rows))}")
print(f"  title attrs={titles}  lang usage={dict(langs)}")

print("\n== alias / entry shadowing ==")
both = entry_exprs & alias_exprs
print(f"  exprs with BOTH an entry row and an alias row: {len(both)} sample={sorted(both)[:10]}")
multi = {e: v for e, v in expr_rows.items() if len(v) > 1}
print(f"  duplicated expressions: {len(multi)} sample={sorted(multi)[:8]}")
cross = {e: v for e, v in multi.items() if len(set(v)) > 1}
print(f"  duplicates spanning entry+alias scores: {len(cross)} sample={sorted(cross)[:8]}")

print("\n== expression hygiene ==")
pats = {
    "leading-comma": re.compile(r"^,"),
    "double-space": re.compile(r"\s{2,}"),
    "leading/trailing-space": re.compile(r"^\s|\s$"),
    "contains-tab": re.compile(r"\t"),
    "non-lemma-but-no-target": None,
}
for name, p in pats.items():
    if p is None:
        continue
    hits = [e for e in expr_rows if p.search(e)]
    print(f"  {name:24} {len(hits):>6}  e.g. {hits[:4]}")
empty_alias = [e for e in alias_exprs if not e.strip()]
print(f"  empty/whitespace expressions: {len(empty_alias)}")

css = z.read("styles.css").decode("utf-8")
defined = set()
for m in re.findall(r'\[data-sc-class="([^"]+)"\]', css):
    defined.update(m.split())
for m in re.findall(r'\[data-sc-class~="([^"]+)"\]', css):
    defined.update(m.split())
print(f"\n  CSS used={len(used_classes)} defined={len(defined)} "
      f"missing={sorted(used_classes - defined)} unused={len(defined - used_classes)}")
