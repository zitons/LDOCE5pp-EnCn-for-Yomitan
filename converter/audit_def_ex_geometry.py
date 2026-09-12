"""Do 释义 (ld-def/ld-defcn) and 例句 (ld-ex/ld-excn) get any structural
separation without CSS?

They are all <div> (block) in raw HTML, so they DO break lines -- but with no
stylesheet there is no margin, so they stack with zero spacing:
    缩略语，缩写            <- ld-defcn
    – abbreviation of/for   <- ld-ex, no gap above
Two different questions, measured separately:

  A. LINE BREAKING   -- do def / defcn / ex / excn each start on their own line?
                        (must be true; block elements)
  B. SPACING         -- is there ANY vertical gap between them? (CSS provides
                        margin; with no stylesheet there is none)
  C. INDENT/MARKER   -- can the reader tell where an example begins? Only the
                        – marker distinguishes it (scheme B added it inline).

Measured in real Chrome over CDP, no stylesheet, on the final package.
"""
import json
import os
import re
import subprocess
import sys
import zipfile

ZIP = r"C:\workspace\ldoce\yomitan_cap_test\LDOCE5pp_Yomitan_2026.09.12_DEBUG.zip"
SCGEN = r"C:\workspace\ldoce\scgen_test"
WORDS = ["abandon", "abbreviation", "child", "improve"]

z = zipfile.ZipFile(ZIP)
sc = {}
for n in z.namelist():
    if re.fullmatch(r"term_bank_\d+\.json", n):
        for r in json.loads(z.read(n)):
            if r[4] > 0 and r[0] in WORDS and r[0] not in sc:
                for it in r[5]:
                    if isinstance(it, dict) and it.get("type") == "structured-content":
                        sc[r[0]] = it["content"]
print(f"loaded {len(sc)} entries", flush=True)

sc_path = os.path.join(SCGEN, "_defex_sc.json")
json.dump(sc, open(sc_path, "w", encoding="utf-8"), ensure_ascii=False)

# build a page that renders each entry AND measures geometry per class
open(os.path.join(SCGEN, "_defex_page.mjs"), "w", encoding="utf-8").write("""
import fs from 'node:fs';
import {JSDOM} from 'jsdom';
const scByWord = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const genMod = await import('./js/display/structured-content-generator.js');
let body = '';
for (const [w, s] of Object.entries(scByWord)) {
    const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>');
    const win = dom.window;
    globalThis.location = win.location;
    class F { prepareLink(n,h){n.setAttribute('href',h);} prepareScripts(){} prepareHTML(){} loadMedia(){} openMediaInTab(){} }
    const gen = new genMod.StructuredContentGenerator(new F(), win.document, win);
    const el = gen.createStructuredContent(s, 'LDOCE5pp (LM5pp)');
    body += '<div data-word="' + w + '">' + el.innerHTML + '</div>';
}
fs.writeFileSync(process.argv[3],
    '<!doctype html><html><head><meta charset="utf-8">'
  + '<style>body{margin:0;padding:0;font-family:sans-serif}</style>'
  + '</head><body>' + body + '</body></html>');
console.log('page built');
""")
page = r"C:\workspace\ldoce\_defex.html"
r = subprocess.run(["node", os.path.join(SCGEN, "_defex_page.mjs"), sc_path, page],
                   capture_output=True, text=True, encoding="utf-8", cwd=SCGEN)
print(r.stdout.strip() or r.stderr[:400], flush=True)

open(os.path.join(SCGEN, "_defex_expr.js"), "w", encoding="utf-8").write("""
(() => {
  const CLASSES = ['ld-sense','ld-def','ld-defcn','ld-ex','ld-excn','ld-gram','ld-act'];
  const out = {};
  for (const d of document.querySelectorAll('div[data-word]')) {
    const w = d.dataset.word;
    const rows = [];
    for (const cls of CLASSES) {
      for (const e of d.querySelectorAll('[data-sc-class="'+cls+'"]')) {
        const r = e.getBoundingClientRect();
        rows.push({cls, top: Math.round(r.top*100)/100, bottom: Math.round(r.bottom*100)/100,
                   left: Math.round(r.left*100)/100, h: Math.round(r.height*100)/100,
                   text: e.innerText.replace(/\\s+/g,' ').slice(0,30)});
      }
    }
    rows.sort((a,b) => a.top - b.top || a.left - b.left);
    out[w] = rows;
  }
  return JSON.stringify(out);
})()
""")
out = subprocess.run(["node", "cdp.mjs", "file:///" + page.replace("\\", "/"),
                      "_defex_expr.js"],
                     capture_output=True, text=True, encoding="utf-8", cwd=SCGEN)
if out.returncode != 0:
    print("cdp failed:", out.stderr[:600])
    sys.exit(2)
data = json.loads(json.loads(out.stdout.strip()))

print("\n=== geometry per class (no CSS) ===")
for w in list(data)[:4]:
    print(f"\n--- {w} ---")
    rows = data[w]
    prev = None
    for r in rows[:16]:
        gap = ""
        if prev is not None:
            same_line = abs(r["top"] - prev["top"]) < 1
            gapval = r["top"] - prev["bottom"]
            gap = f"  gap={gapval:+.2f}" + ("  (SAME LINE)" if same_line else "")
        print(f"  {r['cls']:10} top={r['top']:>9.2f} h={r['h']:>7.2f} left={r['left']:>7.2f}"
              f"  {r['text']!r:34}{gap}")
        prev = r
