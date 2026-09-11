"""audit9c: exact composition of audit9's 1.738%.

audit9c uses THE SAME hidden model as audit9 (so the missing-token total must
match audit9's), but additionally records, for every source token, the class
path of its ancestors -- then allocates each missing token's count across the
paths that carried it, proportionally to that path's share of the token.

This answers one question precisely: of the tokens audit9 says never reached the
output, which source elements carried them, and does the ORIGINAL stylesheet
display those elements at all?  (audit9b over-counted: it attributed a token's
full path count rather than the missing share.)
"""
import collections
import re
import sys

from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 800
TOK = re.compile(r"[A-Za-z]+|[\u4e00-\u9fff]|\d+")
DROP = set(M.DROP_CLASSES)
EXTRA_HIDDEN = {"HYPHENATION", "landscape"}


def is_hidden(cls):
    return bool(cls & DROP) or bool(cls & EXTRA_HIDDEN) or ("tooltip" in cls and "LEVEL" not in cls)


def walk(node, path, out):
    for ch in getattr(node, "children", []):
        if isinstance(ch, NavigableString):
            p = ch.parent
            if p is not None and p.name in ("style", "script"):
                continue
            sig = " > ".join(path[-3:]) if path else "(root)"
            for t in TOK.findall(str(ch).lower()):
                out[t][sig] += 1
        elif isinstance(ch, Tag):
            if ch.name in ("style", "script"):
                continue
            cls = set(ch.get("class") or [])
            if is_hidden(cls):
                continue
            nm = ch.name + ("." + " ".join(ch.get("class")) if cls else "")
            walk(ch, path + [nm], out)
    return out


def sc_tokens(node, acc):
    if isinstance(node, str):
        acc.update(TOK.findall(node.lower()))
    elif isinstance(node, list):
        for x in node:
            sc_tokens(x, acc)
    elif isinstance(node, dict):
        c = node.get("content")
        if c is not None:
            sc_tokens(c, acc)
    return acc


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
missing_total = collections.Counter()
missing_paths = collections.Counter()   # (token, sig) -> allocated missing count
src_n = got_n = 0
offenders = []

for k, content in recs.items():
    soup = BeautifulSoup(content, "lxml")
    per_token = collections.defaultdict(collections.Counter)
    walk(soup, [], per_token)
    st = collections.Counter()
    for t, sigs in per_token.items():
        st[t] = sum(sigs.values())
    ot = collections.Counter()
    sc_tokens(renderer.render_record(k, content) or [], ot)
    src_n += sum(st.values())
    got_n += sum(ot.values())
    miss = st - ot
    if miss:
        offenders.append((sum(miss.values()), k, miss))
        missing_total.update(miss)
        for t, n in miss.items():
            total_here = st[t]
            if total_here <= 0:
                continue
            for sig, cnt in per_token[t].items():
                alloc = n * cnt / total_here
                missing_paths[(t, sig)] += alloc

tot = sum(missing_total.values())
print(f"sample entries        = {len(recs)}")
print(f"source tokens         = {src_n}")
print(f"output tokens         = {got_n}")
print(f"MISSING (audit9 model)= {tot}  ({tot*100.0/src_n:.3f}% of source)")
print(f"entries with missing  = {len(offenders)} ({len(offenders)*100.0/len(recs):.1f}%)")
print()

# ---- classify each path against what the ORIGINAL stylesheet hides ----------
ORIG_HIDDEN_SELECTORS = [
    (".ldoceEntry .ACTIV", "display:none"),
    (".ldoceEntry .BOX", "display:none"),
    (".ldoceEntry .COMMENT", "display:none"),
    (".ldoceEntry .FIELD", "display:none"),
    (".ldoceEntry .NOTE,.Noteprompt", "display:none"),
    (".ldoceEntry .PIC,.PICCAL", "display:none"),
    (".ldoceEntry .USAGE", "display:none"),
    (".ldoceEntry .HYPHENATION", "display:none"),
    (".bussdictEntry .FIELDXX / .Crossrefto .REFLEX", "display:none"),
    (".exaGroup .exa > .neutral", "display:none (bullet)"),
    (".bussdict, .corpus", "display:none"),
    (".pagetitle, h1.topicpagetitle", "display:none"),
    (".HWD .HYP", "display:none (syllable dots)"),
    (".lm5pp_popup", "visibility:hidden"),
    (".lm5pp_popupitem .HYPHENATION", "display:none"),
    (".lm5ppMenu* / .lm5ppMenu_title", "display:none"),
    (".portrait", "display:none"),
    (".landscape", "display:none"),
    (".related_topics", "display:none"),
    (".cloud.full / .topicCloud .topic_other .verbose", "display:none"),
    (".BoxPanel", "display:none"),
    (".LDOCEVERSION_new / LOGO_5 / LOGO_new", "display:none"),
    (".dictentry.LDOCEVERSION_new", "display:none"),
    (".suppressed", "display:none"),
    (".Sense .corpus .title", "display:none"),
    ("* [type=phrv]", "display:none"),
    (".EXPL .cyan, .EXPL > .neutral:first-child", "display:none"),
]


def orig_hidden(sig):
    s = sig.lower()
    if "portrait" in s or "landscape" in s:
        return ".portrait / .landscape"
    if "hyphenation" in s:
        return ".ldoceEntry .HYPHENATION"
    if "suppressed" in s:
        return ".suppressed"
    if "lm5pp_popup" in s or "menutitle" in s or "menu_hide" in s:
        return ".lm5pp_popup / menu"
    if "ldoceversion" in s:
        return ".LDOCEVERSION*"
    if "pagetitle" in s:
        return ".pagetitle"
    if "bussdict" in s:
        return ".bussdict"
    if "asset_intro" in s or "yellow_box" in s:
        return "asset header (dropped by policy)"
    if "cexa1g" in s and "neutral" in s:
        return ".exaGroup .exa > .neutral"
    if "reflex" in s:
        return ".Crossrefto .REFLEX"
    if "related_topics" in s:
        return ".related_topics"
    if "boxpanel" in s:
        return ".BoxPanel"
    if "speaker" in s or "file" in s:
        return "audio button"
    return None


print("=== allocation of the missing tokens by source path ===")
by_class = collections.Counter()
detail = collections.defaultdict(list)
for (t, sig), n in missing_paths.items():
    cause = orig_hidden(sig)
    key = cause or "NOT HIDDEN BY ORIGINAL -> investigate"
    by_class[key] += n
    detail[key].append((n, t, sig))

for key, n in by_class.most_common():
    print(f"  {n:7.1f}  {n*100.0/tot:5.1f}%  {key}")

print()
print("=== detail for the NOT-HIDDEN bucket ===")
for n, t, sig in sorted(detail["NOT HIDDEN BY ORIGINAL -> investigate"], reverse=True)[:30]:
    print(f"  {n:6.1f}  {t!r:>14}  <- {sig[:140]}")
print()
print("=== top 25 missing tokens overall ===")
for t, n in missing_total.most_common(25):
    top = sorted([(c, s) for (tt, s), c in missing_paths.items() if tt == t], reverse=True)[:1]
    path = top[0][1] if top else ""
    print(f"  {n:>6}  {t!r:>16}  top-path: {path[:120]}")
print()
print("=== top offenders ===")
offenders.sort(reverse=True)
for n, k, miss in offenders[:8]:
    print(f"  {k!r:24} missing {n}: {[w for w, _ in miss.most_common(10)]}")
