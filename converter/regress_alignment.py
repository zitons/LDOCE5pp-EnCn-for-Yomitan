"""Regression gate: horizontal alignment of labels and glosses.

Locks in the two fixes from REVIEW D42/D43 so this class of defect cannot come
back silently. Renders real entries from a built package in Hoshi's real context
(its popup.css + the real wrapper + the real nested scoping of our stylesheet) and
asserts, for every sampled entry:

  A. every `ld-act` (ACTIV) chip starts at the same left edge as the `ld-def` of
     the sense it labels.  Before D43 this was off by 4.1px (and up to 24px on
     `break`), because the chip followed the in-flow hung sense number while the
     definition started at the content column.
  B. every `ld-defcn` inside an `ld-colloexa` starts at the same left edge as the
     English gloss / collocation line it translates.  Before D42 this was off by
     23.3px, because `text-indent` is inherited and a BLOCK descendant applies it
     to its own first line (T9 had only covered inline-block descendants).
  C. the ACTIV chip carries no `text-transform` and no `letter-spacing`, matching
     the original stylesheet.

Usage:
    python converter/regress_alignment.py <package.zip> [--sample N] [--width W]
Exit code 0 only if every sampled pair is aligned within TOL.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import zipfile

sys.path.insert(0, r"C:\workspace\ldoce\converter")
import ldoce2yomitan as C  # noqa: E402

SCGEN = r"C:\workspace\ldoce\scgen_test"
TOL = 0.6           # px; sub-pixel rounding is not a defect


def pick_entries(zip_path, sample):
    """Entries that exercise both shapes, spread across banks."""
    want_act, want_cn = [], []
    z = zipfile.ZipFile(zip_path)
    banks = sorted(n for n in z.namelist() if re.fullmatch(r"term_bank_\d+\.json", n))
    step = max(1, len(banks) // 12)
    for b in banks[::step]:
        for r in json.loads(z.read(b)):
            if r[4] <= 0:
                continue
            body = json.dumps(r[5], ensure_ascii=False)
            # A needs a NUMBERED sense that also carries a label chip; B needs a
            # Chinese gloss inside a hanging-indent carrier.
            if "ld-snum" in body and "ld-act" in body and len(want_act) < sample:
                want_act.append(r[0])
            if "ld-colloexa" in body and "ld-defcn" in body and len(want_cn) < sample:
                want_cn.append(r[0])
        if len(want_act) >= sample and len(want_cn) >= sample:
            break
    return want_act, want_cn


def extract(zip_path, words):
    sc = {}
    z = zipfile.ZipFile(zip_path)
    for n in z.namelist():
        if not re.fullmatch(r"term_bank_\d+\.json", n):
            continue
        for r in json.loads(z.read(n)):
            if r[4] > 0 and r[0] in words and r[0] not in sc:
                for it in r[5]:
                    if isinstance(it, dict) and it.get("type") == "structured-content":
                        sc[r[0]] = it["content"]
    return sc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zip")
    ap.add_argument("--sample", type=int, default=25)
    ap.add_argument("--width", type=int, default=390)
    ap.add_argument("--css", choices=("package", "generator"), default="package",
                    help="which stylesheet to test: the one IN the package (default, "
                         "tests what actually ships) or the current generator output")
    args = ap.parse_args()

    act_words, cn_words = pick_entries(args.zip, args.sample)
    words = act_words + [w for w in cn_words if w not in act_words]
    print(f"package: {os.path.basename(args.zip)}")
    print(f"sample : {len(act_words)} entries with ld-act, "
          f"{len(cn_words)} with ld-colloexa+ld-defcn -> {len(words)} unique")
    if not words:
        print("nothing to check (no matching entries)"); return 0

    sc = extract(args.zip, set(words))
    if args.css == "package":
        css = zipfile.ZipFile(args.zip).read("styles.css").decode("utf-8")
        src = "the package's own styles.css"
    else:
        css = C.generate_css()
        src = "generate_css() (current source)"
    print(f"stylesheet: {src} ({len(css):,} chars)")
    open(os.path.join(SCGEN, "_ra_sc.json"), "w", encoding="utf-8").write(
        json.dumps(sc, ensure_ascii=False))
    open(os.path.join(SCGEN, "_ra.css"), "w", encoding="utf-8").write(css)

    open(os.path.join(SCGEN, "_ra_page.mjs"), "w", encoding="utf-8").write("""
import fs from 'node:fs';
import {JSDOM} from 'jsdom';
const scByWord = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const dictCss = fs.readFileSync(process.argv[3], 'utf8');
const width = parseInt(process.argv[4], 10);
const genMod = await import('./js/display/structured-content-generator.js');
const NAME = 'LDOCE5pp (LM5pp)';
let body = '';
for (const [w, s] of Object.entries(scByWord)) {
    const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>');
    const win = dom.window;
    globalThis.location = win.location;
    class F { prepareLink(n,h){n.setAttribute('href',h);} prepareScripts(){} prepareHTML(){} loadMedia(){} openMediaInTab(){} }
    const gen = new genMod.StructuredContentGenerator(new F(), win.document, win);
    const el = gen.createStructuredContent(s, NAME);
    el.setAttribute('data-dictionary', NAME);
    body += '<div class="yomitan-glossary"><details class="glossary-group" open>'
         +  '<summary class="dict-label"><span class="dict-name">' + NAME + '</span></summary>'
         +  '<div data-dictionary="' + NAME + '" data-word="' + w + '">'
         +  '<style>[data-dictionary="' + NAME + '"] {\\n' + dictCss
         +  '\\ncolor: var(--text-color) !important;\\n}</style>'
         +  '<div class="glossary-content">' + el.outerHTML + '</div>'
         +  '</div></details></div>';
}
fs.writeFileSync(process.argv[5],
  '<!doctype html><html><head><meta charset="utf-8">'
+ '<link rel="stylesheet" href="file:///C:/workspace/ldoce/_hoshi/popup.css">'
+ '<style>html,body{margin:0;background:#1e1e1e;color:#e8e8e8;font-family:system-ui,sans-serif}'
+ `[data-word]{width:${width}px}` + '</style></head><body>' + body + '</body></html>');
console.log('page ok');
""")

    open(os.path.join(SCGEN, "_ra_expr.js"), "w", encoding="utf-8").write(r"""
(() => {
  const out = [];
  for (const holder of document.querySelectorAll('[data-word]')) {
    const word = holder.dataset.word;
    const L = (e) => Math.round(e.getBoundingClientRect().left*100)/100;
    const painted = (e) => { try { return e.checkVisibility({checkOpacity:true, checkVisibilityCSS:true, contentVisibilityAuto:true}); } catch(_) { return true; } };
    const rec = {word, col: [], indent: [], style: null};

    // A. the content column must not be disturbed by the sense number.
    //    For a sense carrying ld-snum, the first painted content child must start
    //    exactly at that sense's own content column (left + padding-left + border).
    //    While the number was an in-flow inline-block with a negative margin, the
    //    first content started at the number's right edge instead (measured 70.9
    //    vs a 75.0 column), which is the D43 defect.
    for (const sense of holder.querySelectorAll(
             '[data-sc-class~="ld-sense"], [data-sc-class~="ld-sense-cross"], '
           + '[data-sc-class~="ld-sense-merge"], [data-sc-class~="ld-subsense"], '
           + '[data-sc-class="ld-runon"]')) {
      const snum = sense.querySelector(':scope > [data-sc-class="ld-snum"]');
      if (!snum) continue;
      const cs = getComputedStyle(sense);
      const r = sense.getBoundingClientRect();
      const column = Math.round((r.left + parseFloat(cs.paddingLeft)
                                 + parseFloat(cs.borderLeftWidth)) * 100) / 100;
      // first painted child element carrying a dictionary class, not inside a
      // nested sense (those have their own column)
      let first = null;
      for (const child of sense.children) {
        if (!child.hasAttribute || !child.hasAttribute('data-sc-class')) continue;
        if (child.getAttribute('data-sc-class') === 'ld-snum') continue;
        if (!painted(child)) continue;
        if (child.querySelector('[data-sc-class~="ld-sense"], [data-sc-class~="ld-subsense"]')) continue;
        first = child; break;
      }
      if (!first) continue;
      rec.col.push({
        word, column, first: L(first), delta: Math.round((L(first) - column)*100)/100,
        snum_left: L(snum), snum_position: getComputedStyle(snum).position,
        cls: first.getAttribute('data-sc-class')
      });
    }

    // B. inherited text-indent must be dead for every descendant of a carrier.
    //    Computing it directly avoids the "compare against which sibling?"
    //    question, and is exactly the D42 fix.
    for (const defcn of holder.querySelectorAll('[data-sc-class="ld-defcn"]')) {
      if (!painted(defcn)) continue;
      const box = defcn.closest('[data-sc-class="ld-colloexa"], [data-sc-class="ld-corpexa"], '
                              + '[data-sc-class="ld-ex"], [data-sc-class="ld-gramexa"]');
      if (!box) continue;
      rec.indent.push({
        word, textIndent: getComputedStyle(defcn).textIndent,
        text: (defcn.textContent||'').trim().slice(0,20)
      });
    }

    // C. chip must not be uppercased or letter-spaced any more (original has neither)
    const anyChip = [...holder.querySelectorAll('[data-sc-class~="ld-act"]')].find(painted);
    if (anyChip) {
      const cs = getComputedStyle(anyChip);
      rec.style = {textTransform: cs.textTransform, letterSpacing: cs.letterSpacing,
                   display: cs.display, fontSize: cs.fontSize};
    }
    out.push(rec);
  }
  return JSON.stringify(out, null, 1);
})()
""")

    page = r"C:\workspace\ldoce\_ra.html"
    r = subprocess.run(["node", "_ra_page.mjs", "_ra_sc.json", "_ra.css", str(args.width), page],
                       capture_output=True, text=True, encoding="utf-8", cwd=SCGEN)
    if r.returncode != 0:
        print("build failed:", r.stderr[:800]); return 2
    r = subprocess.run(["node", "cdp.mjs", "file:///C:/workspace/ldoce/_ra.html", "_ra_expr.js"],
                       capture_output=True, text=True, encoding="utf-8", cwd=SCGEN)
    if r.returncode != 0:
        print("cdp failed:", r.stderr[:800]); return 2

    rows = json.loads(json.loads(r.stdout.strip()))
    cols = [c for row in rows for c in row.get("col", [])]
    indents = [i for row in rows for i in row.get("indent", [])]
    styles = [row["style"] for row in rows if row.get("style")]

    bad_col = [c for c in cols if abs(c["delta"]) > TOL]
    bad_indent = [i for i in indents if i["textIndent"] != "0px"]
    bad_style = [s for s in styles
                 if s["textTransform"] != "none" or s["letterSpacing"] not in ("normal", "0px")]

    print(f"\nA. numbered sense: first content child at its own content column")
    print(f"   {len(cols)} sense(s) checked, {len(bad_col)} not on the column")
    for c in bad_col[:10]:
        print(f"     {c['word']:18} column={c['column']} first<{c['cls']}>={c['first']} "
              f"delta={c['delta']}px  (snum left={c['snum_left']} {c['snum_position']})")
    if cols:
        good = cols[0]
        print(f"   sample ok: {good['word']} column={good['column']} first={good['first']} "
              f"delta={good['delta']}px snum={good['snum_position']}")

    print(f"\nB. ld-defcn inside a hanging-indent carrier: computed text-indent must be 0")
    print(f"   {len(indents)} node(s) checked, {len(bad_indent)} still inheriting an indent")
    for i in bad_indent[:8]:
        print(f"     {i['word']:18} text-indent={i['textIndent']}  {i['text']!r}")

    print(f"\nC. ld-act chip carries no uppercase / no letter-spacing")
    print(f"   {len(styles)} chip(s) checked, {len(bad_style)} wrong")
    for s in bad_style[:4]:
        print(f"     text-transform={s['textTransform']} letter-spacing={s['letterSpacing']}")
    if styles:
        print(f"   sample: display={styles[0]['display']} font-size={styles[0]['fontSize']} "
              f"text-transform={styles[0]['textTransform']} letter-spacing={styles[0]['letterSpacing']}")

    ok = bool(cols) and bool(indents) and not (bad_col or bad_indent or bad_style)
    if not cols or not indents:
        print("\n[!] sample too small to be meaningful -- widen it")
        ok = False
    print("\n" + ("ALIGNMENT GATE: PASS" if ok else "ALIGNMENT GATE: FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
