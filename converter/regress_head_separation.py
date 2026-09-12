"""Regression gate for head-atom separation, based on the RENDERED text.

Three rounds of static structural checks produced false positives (they cannot
know which text nodes are separators). The property the user actually reported is
user-visible, so the gate measures that instead:

    render a sample of heads through the REAL Yomitan structured-content
    generator, once with no stylesheet, and assert that no two adjacent head
    atoms are glued together in the resulting text.

Since the generator preserves text nodes verbatim, a glue in its output means the
package genuinely lacks a separator.

Usage: python regress_head_separation.py [package.zip]
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, r"C:\workspace\ldoce\converter")
import ldoce2yomitan as C  # noqa: E402

ZIP = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.12.zip"
SCGEN = r"C:\workspace\ldoce\scgen_test"

# sample: the historically failing words plus a spread of head shapes
SAMPLE = ["12", "000", "A", "abet", "abandon", "improve", "the", "advantage",
          "3-D", "able seaman", "second class", "run", "get", "527",
          "800 number", "A1, the", "child", "close", "cross", "like"]

# ---------------------------------------------------------------- extract SC
z = zipfile.ZipFile(ZIP)
want = set(SAMPLE)
sc_by_word = {}
for n in z.namelist():
    if re.fullmatch(r"term_bank_\d+\.json", n):
        for r in json.loads(z.read(n)):
            if r[4] > 0 and r[0] in want and r[0] not in sc_by_word:
                for item in r[5]:
                    if isinstance(item, dict) and item.get("type") == "structured-content":
                        sc_by_word[r[0]] = item["content"]
print(f"package: {os.path.basename(ZIP)}")
print(f"sampled {len(sc_by_word)} of {len(SAMPLE)} requested words")

work = tempfile.mkdtemp(prefix="sepgate_")
sc_path = os.path.join(work, "sc.json")
json.dump(sc_by_word, open(sc_path, "w", encoding="utf-8"), ensure_ascii=False)

# --------------------------------------------------- render with the real gen
harness = """
import fs from 'node:fs';
import {JSDOM} from 'jsdom';
const scByWord = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const genMod = await import('./js/display/structured-content-generator.js');
const out = {};
for (const [w, sc] of Object.entries(scByWord)) {
    const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>');
    const win = dom.window;
    globalThis.location = win.location;
    class F { prepareLink(n,h){n.setAttribute('href',h);} prepareScripts(){} prepareHTML(){} loadMedia(){} openMediaInTab(){} }
    const gen = new genMod.StructuredContentGenerator(new F(), win.document, win);
    const el = gen.createStructuredContent(sc, 'LDOCE5pp (LM5pp)');
    const head = el.querySelector('[data-sc-class="ld-head"]');
    out[w] = head ? head.textContent.replace(/\\s+/g, ' ').trim() : null;
}
console.log(JSON.stringify(out));
"""
harness_path = os.path.join(SCGEN, "_sepgate.mjs")
open(harness_path, "w", encoding="utf-8").write(harness)

r = subprocess.run(["node", harness_path, sc_path], capture_output=True,
                   text=True, encoding="utf-8", cwd=SCGEN)
if r.returncode != 0:
    print("generator failed:", r.stderr[:600])
    sys.exit(2)
rendered = json.loads(r.stdout.strip())

# ------------------------------------------------------------- check for glue
# A glue is a run of alphabetic/CJK text with no space inside, formed by two
# atoms that should have been separated. [transitive]-style brackets are fine,
# so require an uppercase letter, a digit or a bracket right after a letter.
GLUE_PATTERNS = [
    (re.compile(r"[a-z]\d*[A-Z]"), "letter followed by a capital (S2W2, AWLadjective)"),
    (re.compile(r"[a-z\-·ˈˌ]\d*\["), "word immediately before a bracket (abetting[)"),
    (re.compile(r"\)[A-Za-z]"), "closing paren followed by a word ()/also)adjective"),
    (re.compile(r"[a-z]\d*[●○]"), "word before a level dot (verb●●○)"),
]
fails = []
print(f"\n{'word':16} no-CSS head text")
print("-" * 96)
for w, txt in rendered.items():
    if txt is None:
        continue
    hits = [why for pat, why in GLUE_PATTERNS if pat.search(txt)]
    mark = "  <== GLUED" if hits else ""
    print(f"{w:16} {txt[:70]:72}{mark}")
    if hits:
        fails.append((w, hits, txt))

print()
if fails:
    for w, why, txt in fails[:10]:
        print(f"FAIL {w!r}: {why}")
    sys.exit(1)
print("RESULT: PASS -- no head atom is glued to its neighbour without CSS")
