"""Full no-CSS audit using the token-based detector and a LARGE sample.

Pipeline: real Yomitan generator -> real Chrome, no stylesheet -> innerText
(line-aware) -> tokenise by whitespace -> a chip token stuck inside a longer token
is a glue.

Usage: python audit_nocss_final.py [n_sample]
"""
import json
import os
import re
import subprocess
import sys
import zipfile
from collections import Counter

sys.path.insert(0, r"C:\workspace\ldoce\converter")
from glue_detect import find_glue  # noqa: E402

ZIP = r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.12.zip"
SCGEN = r"C:\workspace\ldoce\scgen_test"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 400

PRIORITY = ["abbreviation", "improve", "abandon", "the", "A", "run", "get",
            "close", "like", "advantage", "a bag of bones", "abet", "000",
            "3-D", "second class", "able seaman", "child", "back", "cross",
            "one", "out", "second", "clean", "double", "work", "take",
            "accordingly", "advertise", "anon", "artistic", "bitchy"]

# ---- one pass over the banks -------------------------------------------------
z = zipfile.ZipFile(ZIP)
sc_by_word = {}
seen = 0
total = 0
step = 61
for n in z.namelist():
    if not re.fullmatch(r"term_bank_\d+\.json", n):
        continue
    for r in json.loads(z.read(n)):
        if r[4] <= 0:
            continue
        total += 1
        take = (r[0] in PRIORITY and r[0] not in sc_by_word) or \
               (len(sc_by_word) < N and seen % step == 0)
        if take:
            for item in r[5]:
                if isinstance(item, dict) and item.get("type") == "structured-content":
                    sc_by_word[r[0]] = item["content"]
        seen += 1
print(f"sampled {len(sc_by_word)} of {total:,} entries", flush=True)

sc_path = os.path.join(SCGEN, "_final_sc.json")
json.dump(sc_by_word, open(sc_path, "w", encoding="utf-8"), ensure_ascii=False)

open(os.path.join(SCGEN, "_final_page.mjs"), "w", encoding="utf-8").write("""
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
""")
page = r"C:\workspace\ldoce\_final_nocss.html"
r = subprocess.run(["node", os.path.join(SCGEN, "_final_page.mjs"), sc_path, page],
                   capture_output=True, text=True, encoding="utf-8", cwd=SCGEN)
if r.returncode != 0:
    print("page build failed:", r.stderr[:500])
    sys.exit(2)

open(os.path.join(SCGEN, "_final_expr.js"), "w", encoding="utf-8").write(
    "(() => { const o = {};"
    " for (const d of document.querySelectorAll('div[data-word]'))"
    "   o[d.dataset.word] = d.innerText;"
    " return JSON.stringify(o); })()")
out = subprocess.run(["node", "cdp.mjs", "file:///" + page.replace("\\", "/"),
                      "_final_expr.js"],
                     capture_output=True, text=True, encoding="utf-8", cwd=SCGEN)
if out.returncode != 0:
    print("cdp failed:", out.stderr[:500])
    sys.exit(2)
texts = json.loads(json.loads(out.stdout.strip()))

rows_bad = 0
reasons = Counter()
examples = []
for w, t in texts.items():
    hits = find_glue(t)
    if hits:
        rows_bad += 1
        for tok, why in hits:
            reasons[why] += 1
        if len(examples) < 12:
            examples.append((w, hits[:3]))

print(f"\nentries rendered      : {len(texts)}")
print(f"entries with glue     : {rows_bad} ({rows_bad*100.0/len(texts):.2f}%)")
print(f"glue reasons          : {dict(reasons)}")
print()
for w, hits in examples:
    print(f"  {w!r}: {hits}")
print()
if rows_bad == 0:
    print("RESULT: PASS -- no glued chip tokens in the no-CSS rendering")
else:
    print("RESULT: residual glue present (see above)")
