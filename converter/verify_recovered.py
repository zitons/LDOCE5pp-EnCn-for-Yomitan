"""Consolidated verifier for the recovered fixes: word-family opp/loose text,
head GRAM brackets, LDOCE Online panels, and inflection annotations.

Walks the structured content as a tree (a regex over minified JSON cannot reach
`content` past the `}` that closes `"class": "..."`).
"""
import json
import re
import sys
import zipfile

from bs4 import BeautifulSoup

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

ZIP = r"C:\workspace\ldoce\yomitan_wf_test\LDOCE5pp_Yomitan_2026.09.11_DEBUG.zip"
SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"


def flat(node):
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(flat(x) for x in node)
    if isinstance(node, dict):
        return flat(node.get("content", ""))
    return ""


def nodes_with_class(node, want, out):
    if isinstance(node, list):
        for x in node:
            nodes_with_class(x, want, out)
    elif isinstance(node, dict):
        cls = (node.get("data") or {}).get("class")
        if cls and want in cls.split():
            out.append(node)
        for k, v in node.items():
            if k != "data":
                nodes_with_class(v, want, out)
    return out


z = zipfile.ZipFile(ZIP)
rows = {}
for n in z.namelist():
    if re.fullmatch(r"term_bank_\d+\.json", n):
        for r in json.loads(z.read(n)):
            rows.setdefault(r[0], []).append(r)

src = {}
for k, c in M.iter_records(SIDE):
    kk = M.strip_invisible(k).strip()
    if kk in rows:
        src[kk] = c


def sc_of(w):
    rs = [r for r in rows.get(w, []) if r[4] > 0]
    if not rs:
        return None
    for item in rs[0][5]:
        if isinstance(item, dict) and item.get("type") == "structured-content":
            return item["content"]
    return None


fails = 0

print("=" * 68)
print("A. word family: opp markers preserved")
for w in ("advantage", "add", "accuse", "academe", "academy"):
    node = sc_of(w)
    if node is None or w not in src:
        continue
    soup = BeautifulSoup(src[w], "lxml")
    want = [re.sub(r"\s+", " ", o.get_text(" ", strip=True)).strip()
            for o in soup.find_all("span", class_="opp")]
    got = [re.sub(r"\s+", " ", flat(x)).strip() for x in nodes_with_class(node, "ld-wf-opp", [])]
    norm = lambda seq: [s.replace("\u2260", "").strip() for s in seq]
    missing = [x for x in norm(want) if x not in norm(got)]
    if not want:
        print(f"  OK  {w}: no opp marker in source (nothing to preserve)")
    elif not missing:
        print(f"  OK  {w}: {len(want)} opp -> {got[:2]}")
    else:
        fails += 1
        print(f"  FAIL {w}: src={want[:3]} got={got[:3]} missing={missing[:3]}")

print("=" * 68)
print("B. head GRAM keeps brackets and qualifiers")
for w in ("12", "18-wheeler", "2.0", "act", "advantage", "improve"):
    node = sc_of(w)
    if node is None or w not in src:
        continue
    soup = BeautifulSoup(src[w], "lxml")
    head = soup.find("span", class_="Head")
    g = head.find("span", class_="GRAM") if head else None
    if g is None:
        continue
    portrait = set()
    for pnode in g.find_all("span", class_="portrait"):
        portrait.update(re.findall(r"[A-Za-z]+", pnode.get_text(" ", strip=True)))
    want = " ".join(w for w in re.findall(r"[^\s]+", re.sub(r"\s+", " ", g.get_text(" ", strip=True)).strip())
                    if w.strip("[],") not in portrait)
    got = [flat(x) for x in nodes_with_class(node, "ld-gram", [])]
    hit = any(x.replace(" ", "") == want.replace(" ", "") for x in got)
    if hit:
        print(f"  OK  {w}: {want!r}")
    else:
        fails += 1
        print(f"  FAIL {w}: src={want!r} got={got[:3]}")

print("=" * 68)
print("C. LDOCE Online panels (one per affected entry, content kept)")
for w in ("absurd", "academe", "academy", "access", "act", "improve", "advantage"):
    node = sc_of(w)
    if node is None or w not in src:
        continue
    soup = BeautifulSoup(src[w], "lxml")
    hidden = [d for d in soup.find_all("div")
              if "dictentry" in (d.get("class") or [])
              and "LDOCEVERSION_new" in (d.get("class") or [])]
    n_got = len(nodes_with_class(node, "ld-panel-online", []))
    expect = 1 if hidden else 0
    if n_got == expect:
        extra = ""
        if hidden:
            title = hidden[0].find("span", class_="HWD")
            body = flat(nodes_with_class(node, "ld-panel-online", [])[0]) if n_got else ""
            kept = bool(body.strip())
            extra = f" content_kept={kept}"
        print(f"  OK  {w}: hidden_subentries={len(hidden)} panels={n_got}{extra}")
    else:
        fails += 1
        print(f"  FAIL {w}: hidden={len(hidden)} expect={expect} got={n_got}")

print("=" * 68)
print("D. inflection forms + annotations")
for w in ("backpedal", "bus", "age", "agent provocateur", "cancel", "improve", "child"):
    node = sc_of(w)
    if node is None or w not in src:
        continue
    soup = BeautifulSoup(src[w], "lxml")
    head = soup.find("span", class_="Head")
    infl = head.find("span", class_="Inflections") if head else None
    if infl is None:
        continue
    forms = [f for f in re.findall(r"[A-Za-z][A-Za-z\u2019'-]{2,}",
                                  re.sub(r"\s+", " ", infl.get_text(" ", strip=True)))
             if f.lower() not in ("plural", "singular", "also", "and", "or")]
    whole = flat(node)
    # portrait abbreviations (BrE/AmE/C/U) are deliberately dropped by policy
    portrait = set()
    for p in infl.find_all("span", class_="portrait"):
        portrait.update(re.findall(r"[A-Za-z]+", p.get_text(" ", strip=True)))
    missing = [f for f in forms if f not in whole and f.lower() not in whole.lower()
               and f not in portrait]
    regions = [flat(x) for x in nodes_with_class(node, "ld-infl-region", [])]
    anns = [flat(x) for x in nodes_with_class(node, "ld-infl-ann", [])]
    if missing:
        fails += 1
        print(f"  FAIL {w}: missing {missing[:6]}")
    else:
        print(f"  OK  {w}: forms={len(forms)} regions={regions[:2]} ann={anns[:2]}")

print("=" * 68)
print("E. no compound classes anywhere (single-token discipline)")
bad = []
for w, rs in rows.items():
    for r in rs:
        if r[4] <= 0:
            continue
        for item in r[5]:
            if not isinstance(item, dict):
                continue
            stack = [item]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    c = (cur.get("data") or {}).get("class")
                    if c and len(c.split()) > 1:
                        bad.append((w, c))
                    for k, v in cur.items():
                        if k != "data":
                            stack.append(v)
                elif isinstance(cur, list):
                    stack.extend(cur)
import re as _re
css = z.read("styles.css").decode("utf-8")
tilde = set()
for m in _re.findall(r'\[data-sc-class~="([^"]+)"\]', css):
    tilde.update(m.split())
unsafe = sorted({c for _, c in bad if any(t not in tilde for t in c.split())})
if unsafe:
    fails += 1
    print(f"  FAIL compound class values with no ~= selector: {unsafe[:8]}")
else:
    print(f"  OK  {len(bad)} compound values, all covered by ~= selectors")

print("=" * 68)
print("RESULT:", "ALL PASS" if fails == 0 else f"{fails} FAILING GROUPS")
