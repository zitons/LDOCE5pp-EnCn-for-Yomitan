"""Post-fix content regression: A2 (alias rules), A3 (POS metadata),
A4 (inflection IPA), A5 (mono headings) measured on the REBUILT package.

Mirrors the measurement the audit used, so the before/after numbers are directly
comparable: A2 940 -> 0, A3 281 -> 0, A4 596 words / 816 blocks -> 0,
A5 243 records with CJK -> 0.

    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -u converter/audit_2026_09_12/regress_content.py [package.zip]
"""
import collections
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(r"C:\workspace\ldoce")
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "converter"))
import ldoce2yomitan as M  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

ZIP = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "yomitan_full/LDOCE5pp_Yomitan_2026.09.12.zip")
SRC = ROOT / "extract/LDOCE5++ V 2-15.mdx.txt"
FAILURES = []


def check(label, ok, detail=""):
    print(f"[{'OK' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def text(n):
    if isinstance(n, str):
        return n
    if isinstance(n, list):
        return "".join(map(text, n))
    if isinstance(n, dict):
        return text(n.get("content", ""))
    return ""


def walk(n):
    if isinstance(n, list):
        for c in n:
            yield from walk(c)
    elif isinstance(n, dict):
        yield n
        yield from walk(n.get("content", []))


rows = []
entry_rows = {}
alias_rows = {}
seqs = []
with zipfile.ZipFile(ZIP) as z:
    names = z.namelist()
    check("no duplicate zip members", len(names) == len(set(names)))
    banks = sorted((n for n in names if re.fullmatch(r"term_bank_\d+\.json", n)),
                   key=lambda n: int(re.search(r"\d+", n).group()))
    for name in banks:
        for row in json.loads(z.read(name)):
            rows.append(row)
            seqs.append(row[6])
            (entry_rows if row[4] > 0 else alias_rows).setdefault(row[0], []).append(row)
    css = z.read("styles.css").decode("utf-8")

print(f"package {ZIP.name}: {len(rows)} rows "
      f"({sum(len(v) for v in entry_rows.values())} entries + {len(alias_rows)} aliases)")
check("row count unchanged", len(rows) == 245933, str(len(rows)))
check("sequence unique and 0..N-1 from 0", sorted(seqs) == list(range(len(seqs))))

# ------------------------------------------------------------------- A2 ----
incomplete = []
for word, rs in alias_rows.items():
    for row in rs:
        union = set()
        for item in (row[5] or []):
            if isinstance(item, list) and item and isinstance(item[0], str):
                for tr in entry_rows.get(item[0], []):
                    union.update(str(tr[3]).split())
        if union != set(str(row[3]).split()):
            incomplete.append((word, row[3], sorted(union)))
check("A2 alias rules == union of target rows (was 940)", not incomplete,
      f"{len(incomplete)} bad" + (f" e.g. {incomplete[:2]}" if incomplete else ""))

# ------------------------------------------------------------------- A3 ----
findings = json.loads((OUT / "source_findings.json").read_text(
    encoding="utf-8"))["pos"]
bad = [f["word"] for f in findings
       if not any([r[2], r[3]] == f["reference"] for r in entry_rows.get(f["word"], []))]
check("A3 all 281 reference entries carry reference tags/rules (was 281)", not bad,
      f"{len(bad)} bad" + (f" e.g. {bad[:6]}" if bad else ""))
for w in ("above", "andante", "amen", "the", "A"):
    print(f"      {w!r:10} -> {[ (r[2], r[3]) for r in entry_rows.get(w, []) ]}")

# ------------------------------------------------------------------- A4 ----
src = json.loads((OUT / "source_findings.json").read_text(encoding="utf-8"))
pron_words = {r["word"] for r in src["inflection_pronunciation"]}
head_pair_failures = []
pron_missing = []
gained = 0
occurrence = collections.Counter()
for key, content in M.iter_records(SRC):
    key = M.strip_invisible(key).strip()
    if key not in pron_words or M.classify_record(key, content)[0] != "entry":
        continue
    which = occurrence[key]
    occurrence[key] += 1
    rs = entry_rows.get(key, [])
    if which >= len(rs):
        continue
    row = rs[which]
    blob = json.dumps(row[5], ensure_ascii=False)
    if "ld-infl-pron" in blob:
        gained += 1
    soup = BeautifulSoup(content, M.HTML_PARSER)
    root = (soup.find("div", class_="entry_content")
            or soup.find("span", class_="lm5ppbody") or soup)
    source_heads = [h for h in root.find_all("span", class_="Head")
                    if h.find_parent(class_="etym") is None]
    output_heads = [n for n in walk(row[5])
                    if (n.get("data") or {}).get("class") == "ld-head"]
    if len(source_heads) != len(output_heads):
        head_pair_failures.append([key, len(source_heads), len(output_heads)])
        continue
    for h, out in zip(source_heads, output_heads):
        for infl in h.find_all("span", class_="Inflections"):
            for pron in infl.find_all("span", class_="PronCodes", recursive=False):
                ipa = [M.sc_text(p.get_text("", strip=True)).strip()
                       for p in pron.find_all("span", class_="PRON")]
                miss = [p for p in ipa if p and p not in text(out)]
                if miss:
                    pron_missing.append({"word": key, "missing": miss})
check("A4 no source/ZIP head pairing failures", not head_pair_failures,
      str(head_pair_failures[:5]))
check("A4 no inflection pronunciation block still missing (was 596 words/816)",
      not pron_missing, f"{len(pron_missing)} blocks over "
      f"{len({m['word'] for m in pron_missing})} words")
print(f"      entries in the A4 word list that now carry ld-infl-pron: {gained}"
      f" / {len(pron_words)}")

# ------------------------------------------------------------------- A5 ----
mono_words = {r["word"] for r in src["mono_heading_candidates"]}
ti = M.TermIndex()
for w in entry_rows:
    ti.add(w)
for w in alias_rows:
    ti.add_alias_word(w)
ti.finalize_rendered(set(entry_rows))
renderer = M.LdoceRenderer(ti, mode="mono")
mono_leaks = []
for key, content in M.iter_records(SRC):
    key = M.strip_invisible(key).strip()
    if key not in mono_words or M.classify_record(key, content)[0] != "entry":
        continue
    nodes = renderer.render_record(key, content)
    blob = json.dumps(nodes, ensure_ascii=False)
    hits = list(M.CJK_RE.finditer(blob))
    if hits:
        m = hits[0]
        mono_leaks.append({"word": key, "CJK": len(hits),
                           "example": blob[max(0, m.start() - 70):m.start() + 120]})
check("A5 mono headings free of CJK (was 243 records)",
      not mono_leaks, f"{len(mono_leaks)} leak" + (f" e.g. {mono_leaks[:2]}"
                                                   if mono_leaks else ""))

check("CSS defines ld-infl-pron",
      '[data-sc-class="ld-infl-pron"]' in css)
check("CSS matches current generate_css()", css == M.generate_css())

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
    sys.exit(1)
print("all content regressions passed")
