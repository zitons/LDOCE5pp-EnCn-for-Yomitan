"""DEPRECATED -- DO NOT TRUST THE NUMBERS THIS PRINTS.

superseded: same correct method, but shipped before the detector was
validated against positive/negative samples. Use audit_nocss_final.py.

Kept only as a record of the investigation. See REVIEW.md D33 and
HANDOVER.md pitfall 63.
"""
import json
import os
import re
import subprocess
import sys
import zipfile
from collections import Counter

ZIP = r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.12.zip"
SCGEN = r"C:\workspace\ldoce\scgen_test"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 150

PRIORITY = ["abbreviation", "improve", "abandon", "the", "A", "run", "get",
            "close", "like", "advantage", "a bag of bones", "abet", "000",
            "3-D", "second class", "able seaman", "child", "back", "cross",
            "one", "out", "second", "clean", "double", "work", "take"]

# ---- single pass: collect priority words, then every Nth word ---------------
z = zipfile.ZipFile(ZIP)
sc_by_word = {}
seen = 0
step = 97          # sample every 97th entry -> well spread across the alphabet
for n in z.namelist():
    if not re.fullmatch(r"term_bank_\d+\.json", n):
        continue
    for r in json.loads(z.read(n)):
        if r[4] <= 0:
            continue
        want = (r[0] in PRIORITY and r[0] not in sc_by_word) or \
               (len(sc_by_word) < N and seen % step == 0)
        if want:
            for item in r[5]:
                if isinstance(item, dict) and item.get("type") == "structured-content":
                    sc_by_word[r[0]] = item["content"]
        seen += 1
print(f"sampled {len(sc_by_word)} entries out of {seen:,}", flush=True)

work = os.path.join(SCGEN, "_nocss_sc.json")
json.dump(sc_by_word, open(work, "w", encoding="utf-8"), ensure_ascii=False)

page_js = """
import fs from 'node:fs';
import {JSDOM} from 'jsdom';
const scByWord = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const genMod = await import('./js/display/structured-content-generator.js');
let body = '';
for (const [w, sc] of Object.entries(scByWord)) {
    const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>');
    const win = dom.window;
    globalThis.location = win.location;
    class F { prepareLink(n,h){n.setAttribute('href',h);} prepareScripts(){} prepareHTML(){} loadMedia(){} openMediaInTab(){} }
    const gen = new genMod.StructuredContentGenerator(new F(), win.document, win);
    const el = gen.createStructuredContent(sc, 'LDOCE5pp (LM5pp)');
    body += '<div data-word="' + w + '">' + el.innerHTML + '</div>';
}
fs.writeFileSync(process.argv[3],
    '<!doctype html><html><head><meta charset="utf-8"></head><body>' + body + '</body></html>');
console.log('page built');
"""
open(os.path.join(SCGEN, "_nocss_page.mjs"), "w", encoding="utf-8").write(page_js)
page_path = r"C:\workspace\ldoce\_nocss_audit.html"
r = subprocess.run(["node", os.path.join(SCGEN, "_nocss_page.mjs"), work, page_path],
                   capture_output=True, text=True, encoding="utf-8", cwd=SCGEN)
print(r.stdout.strip() or r.stderr[:400], flush=True)

open(os.path.join(SCGEN, "_nocss_expr.js"), "w", encoding="utf-8").write(
    "(() => { const o = {};"
    " for (const d of document.querySelectorAll('div[data-word]'))"
    "   o[d.dataset.word] = d.innerText;"
    " return JSON.stringify(o); })()")

out = subprocess.run(["node", "cdp.mjs", "file:///" + page_path.replace("\\", "/"),
                      "_nocss_expr.js"],
                     capture_output=True, text=True, encoding="utf-8", cwd=SCGEN)
if out.returncode != 0:
    print("cdp failed:", out.stderr[:600])
    sys.exit(2)
texts = json.loads(json.loads(out.stdout.strip()))

PATTERNS = [
    ("camel-glue    AWLadjective", re.compile(r"[a-z]\d*[A-Z][a-z]")),
    ("bracket-glue  abetting[", re.compile(r"[A-Za-z\u2019'-]\d*\[")),
    ("paren-glue    )adjective", re.compile(r"\)[A-Za-z]")),
    ("pos-glue      nounadj", re.compile(
        r"[a-z](noun|verb|adjective|adverb|preposition|conjunction|determiner|"
        r"pronoun|exclamation|prefix|suffix|article)")),
    ("level-glue    verb\u25cf", re.compile(r"[A-Za-z]\d*[\u25cf\u25cb]")),
    ("freq-glue     S2W2", re.compile(r"[SW]\d[SW]\d")),
]
counts = Counter()
examples = {}
for w, t in texts.items():
    for label, pat in PATTERNS:
        m = pat.search(t)
        if m:
            counts[label] += 1
            if label not in examples:
                s = max(0, m.start() - 34)
                examples[label] = (w, t[s:m.end() + 34].replace("\n", " / "))

print(f"\nentries rendered: {len(texts)}")
print(f"{'pattern':30} {'entries':>8}  example")
print("-" * 112)
for label, _ in PATTERNS:
    n = counts.get(label, 0)
    ex = examples.get(label)
    print(f"{label:30} {n:>8}  " + (f"{ex[0]!r}: ...{ex[1]}..." if ex else ""))
print()
print("measured on innerText (line-aware): block-level seams that wrap in HTML")
print("are correctly NOT counted as glue.")
