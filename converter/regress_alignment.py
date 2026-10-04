"""Regression gate: horizontal alignment of labels and glosses.

Locks in the fixes from REVIEW D42/D43 so this class of defect cannot come back
silently. Renders real rows from a built package in Hoshi's real context (its
popup.css, the real wrapper, the real NESTED scoping of our stylesheet) and
asserts:

  A. every ACTIV chip inside a numbered sense starts at the same left edge as the
     `ld-def` that sense introduces.  Before D43 the chip followed the in-flow hung
     sense number while the definition started at the content column: 4.1px off on
     the reported case, up to 24px elsewhere.
  B. every `ld-defcn` inside a hanging-indent carrier computes `text-indent: 0`.
     Before D42 it inherited the carrier's negative value and its first line was
     pulled ~23px left.
  C. the ACTIV chip carries no `text-transform` and no `letter-spacing`, matching
     the original stylesheet.

Nothing is hard-coded:
  * repository root comes from this file's location (override --root)
  * the jsdom generator dir is <root>/scgen_test (override --scgen / SCGEN_DIR)
  * Hoshi's popup.css is OPTIONAL -- if absent the gate says so and still runs,
    because these invariants are about OUR stylesheet; point --popup-css at a copy
    for a fully faithful render.
  * the hanging-indent carriers are parsed OUT of the stylesheet under test, so a
    carrier added to the CSS is covered here automatically -- and the gate also
    asserts that EVERY carrier introducing a negative text-indent appears in the
    reset rule, i.e. that the CSS itself is complete.

Usage:
    python converter/regress_alignment.py <package.zip> [--sample N] [--width W]
Exit code 0 only if every check passes.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile

TOL = 0.6           # px; sub-pixel rounding is not a defect

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CDP_TARGET = os.environ.get("CDP_TARGET", "http://127.0.0.1:9333")


def check_harness(scgen):
    """Report what is missing before rendering anything.

    This gate needs a real browser: Yomitan's own structured-content generator runs
    under jsdom (to build the DOM), and the measurements come from headless Chrome
    over the DevTools protocol. Those are genuine external prerequisites, so say so
    precisely instead of letting node die with a bare ECONNREFUSED halfway through.

    Returns a list of (problem, remedy) pairs; empty means everything is present.
    """
    problems = []
    if shutil.which("node") is None:
        problems.append(("node not found on PATH", "install Node.js (v20+)"))
    for rel, remedy in (
        ("js/display/structured-content-generator.js",
         "scgen_test is incomplete -- it is tracked in git, so `git checkout` it"),
        ("node_modules/jsdom", "run: npm ci --prefix scgen_test"),
        ("cdp.mjs", "scgen_test/cdp.mjs is tracked in git -- `git checkout` it"),
    ):
        if not os.path.exists(os.path.join(scgen, rel)):
            problems.append((f"missing {rel} in {scgen}", remedy))
    if not problems:
        try:
            urllib.request.urlopen(f"{CDP_TARGET}/json/version", timeout=5).read()
        except Exception as e:
            problems.append((
                f"no DevTools endpoint at {CDP_TARGET} ({type(e).__name__})",
                "start a headless Chrome, e.g.\n"
                "      chrome --headless=new --disable-gpu --no-sandbox \\\n"
                "             --remote-debugging-port=9333 --user-data-dir=<tmp> about:blank\n"
                "      (or point CDP_TARGET at one that is already running)"))
    return problems


# --------------------------------------------------------------------------- css
def _rules(css):
    flat = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(re.sub(r"\s+", " ", a).strip(), b)
            for a, b in re.findall(r"([^{}]+)\{([^{}]*)\}", flat)]


def carriers_reset_in_css(css):
    """Carrier classes reset through a `carrier * { text-indent:0 }` rule."""
    out = set()
    for sel, body in _rules(css):
        if not re.search(r"text-indent\s*:\s*0", body):
            continue
        for part in sel.split(","):
            m = re.match(r'\s*\[data-sc-class="([^"]+)"\]\s*\*\s*$', part.strip())
            if m:
                out.add(m.group(1))
    return out


def carriers_with_negative_indent(css):
    """Carrier classes that set a negative text-indent -- the ones that must be reset."""
    out = set()
    for sel, body in _rules(css):
        if re.search(r"text-indent\s*:\s*-", body):
            out |= set(re.findall(r'data-sc-class="([^"]+)"', sel))
    return out


# ------------------------------------------------------------------- sampling
def _row_id(row, bank, idx):
    """A row identity, not just an expression.

    The dictionary has duplicate expression rows (the same headword appearing more
    than once), so an expression is not a row identity: appending it twice would
    inflate the working set while extract() kept only the first row, making the
    sample smaller than requested and possibly validating a different homograph
    than the one that triggered the match. `sequence` (field 7) is unique
    dictionary-wide; fall back to bank:index when it is absent.
    """
    return (row[0], row[6] if len(row) > 6 else f"{bank}:{idx}")


def pick_rows(zip_path, sample):
    want_act, want_cn, seen_act, seen_cn = [], [], set(), set()
    z = zipfile.ZipFile(zip_path)
    banks = sorted(n for n in z.namelist() if re.fullmatch(r"term_bank_\d+\.json", n))
    step = max(1, len(banks) // 12)
    for b in banks[::step]:
        for idx, r in enumerate(json.loads(z.read(b))):
            if r[4] <= 0:
                continue
            rid = _row_id(r, b, idx)
            body = json.dumps(r[5], ensure_ascii=False)
            if "ld-snum" in body and "ld-act" in body and rid not in seen_act \
                    and len(want_act) < sample:
                seen_act.add(rid)
                want_act.append(rid)
            if "ld-colloexa" in body and "ld-defcn" in body and rid not in seen_cn \
                    and len(want_cn) < sample:
                seen_cn.add(rid)
                want_cn.append(rid)
        if len(want_act) >= sample and len(want_cn) >= sample:
            break
    return want_act, want_cn


def extract(zip_path, row_ids):
    wanted = set(row_ids)
    out = {}
    z = zipfile.ZipFile(zip_path)
    for n in z.namelist():
        if not re.fullmatch(r"term_bank_\d+\.json", n):
            continue
        for idx, r in enumerate(json.loads(z.read(n))):
            if r[4] <= 0:
                continue
            rid = _row_id(r, n, idx)
            if rid in wanted and rid not in out:
                for it in r[5]:
                    if isinstance(it, dict) and it.get("type") == "structured-content":
                        out[rid] = it["content"]
    return out


# ---------------------------------------------------------------------- render
PAGE_MJS = r"""
import fs from 'node:fs';
import {JSDOM} from 'jsdom';
const cases = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const dictCss = fs.readFileSync(process.argv[3], 'utf8');
const width = parseInt(process.argv[4], 10);
const popupHref = process.argv[6];
const genMod = await import('./js/display/structured-content-generator.js');
let body = '';
for (const c of cases) {
    const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>');
    const win = dom.window;
    globalThis.location = win.location;
    class F { prepareLink(n,h){n.setAttribute('href',h);} prepareScripts(){} prepareHTML(){} loadMedia(){} openMediaInTab(){} }
    const gen = new genMod.StructuredContentGenerator(new F(), win.document, win);
    const el = gen.createStructuredContent(c.sc, c.dict);
    el.setAttribute('data-dictionary', c.dict);
    // one unique data-dictionary per case: sharing a scope would let one case's
    // stylesheet apply to every other case and silently invalidate the comparison
    body += '<div class="yomitan-glossary"><details class="glossary-group" open>'
         +  '<summary class="dict-label"><span class="dict-name">' + c.dict + '</span></summary>'
         +  '<div data-dictionary="' + c.dict + '" data-case="' + c.id.replace(/"/g, '') + '">'
         +  '<style>[data-dictionary="' + c.dict + '"] {\n' + dictCss
         +  '\ncolor: var(--text-color) !important;\n}</style>'
         +  '<div class="glossary-content">' + el.outerHTML + '</div>'
         +  '</div></details></div>';
}
const link = popupHref ? '<link rel="stylesheet" href="' + popupHref + '">' : '';
fs.writeFileSync(process.argv[5],
  '<!doctype html><html><head><meta charset="utf-8">' + link
+ '<style>html,body{margin:0;background:#1e1e1e;color:#e8e8e8;font-family:system-ui,sans-serif}'
+ `[data-case]{width:${width}px}` + '</style></head><body>' + body + '</body></html>');
console.log('page ok');
"""

EXPR_JS = r"""
(() => {
  const CARRIERS = __CARRIERS__;
  // An empty selector list would make closest('') throw a SyntaxError, which
  // cdp.mjs reports by falling back to a result OBJECT -- and iterating that
  // yields its key strings, so the gate died with "str has no attribute get"
  // instead of reporting the real verdict. That case is exactly a package whose
  // stylesheet has no reset rule at all, i.e. the one this gate must fail.
  const carrierSel = CARRIERS.length
      ? CARRIERS.map(c => '[data-sc-class="' + c + '"]').join(',') : null;
  const out = [];
  for (const holder of document.querySelectorAll('[data-case]')) {
    const id = holder.dataset.case;
    const L = (e) => Math.round(e.getBoundingClientRect().left*100)/100;
    const cls = (e) => e.getAttribute('data-sc-class') || '';
    const painted = (e) => { try { return e.checkVisibility({checkOpacity:true, checkVisibilityCSS:true, contentVisibilityAuto:true}); } catch(_) { return true; } };
    const rec = {id, first: [], gutter: [], indent: [], style: null};

    // A. Nothing except the sense number may start LEFT of the sense's own content
    //    column. That is the exact signature of the hung in-flow number: its
    //    negative margin drags the whole first line left, so the content on that
    //    line begins before the column (measured 42.42 vs 46.5 on the broken
    //    package).
    //    Two earlier formulations were tried and discarded:
    //      * "the first classed child must equal the column" -- a sense whose first
    //        node carries no data-sc-class (a plain wrapper/text) pushed the first
    //        CLASSED child right, giving 54-170px false positives on the FIXED
    //        package;
    //      * "every ld-act chip must equal the ld-def column" -- several labels
    //        flow inline side by side, so the 2nd/3rd on a line are legitimately
    //        offset (59-233px false positives).
    //    A chip pushed RIGHT is ordinary inline flow; only leftward intrusion is
    //    the defect, and this formulation cannot confuse the two.
    for (const sense of holder.querySelectorAll(
             '[data-sc-class~="ld-sense"], [data-sc-class~="ld-sense-cross"], '
           + '[data-sc-class~="ld-sense-merge"], [data-sc-class~="ld-subsense"], '
           + '[data-sc-class="ld-runon"]')) {
      if (!sense.querySelector(':scope > [data-sc-class="ld-snum"]')) continue;
      const cs = getComputedStyle(sense);
      const sr = sense.getBoundingClientRect();
      const column = Math.round((sr.left + parseFloat(cs.paddingLeft)
                                 + parseFloat(cs.borderLeftWidth)) * 100) / 100;
      for (const k of sense.children) {
        if (!k.hasAttribute || !k.hasAttribute('data-sc-class')) continue;
        if (cls(k) === 'ld-snum' || !painted(k)) continue;
        const l = k.getBoundingClientRect().left;
        if (l < column - 0.6) {
          rec.gutter.push({
            column, left: Math.round(l*100)/100,
            delta: Math.round((l - column)*100)/100,
            is_act: cls(k).split(/\s+/).includes('ld-act'),
            cls: cls(k),
            text: (k.textContent||'').trim().slice(0,24)
          });
        }
      }
    }

    // B. every ld-defcn under ANY carrier the stylesheet resets (parsed from the CSS)
    for (const defcn of holder.querySelectorAll('[data-sc-class="ld-defcn"]')) {
      if (!painted(defcn)) continue;
      if (carrierSel && !defcn.closest(carrierSel)) continue;
      rec.indent.push({textIndent: getComputedStyle(defcn).textIndent,
                       text: (defcn.textContent||'').trim().slice(0,20)});
    }

    // C. chip must not be uppercased or letter-spaced any more
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
"""


def build_page(rows, css, scgen, width, popup_css, out_html):
    cases = [{"id": f"{e}||{s}", "dict": f"LDOCE5pp #{i+1}", "sc": sc}
             for i, ((e, s), sc) in enumerate(rows.items())]
    with open(os.path.join(scgen, "_ra_cases.json"), "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False)
    with open(os.path.join(scgen, "_ra.css"), "w", encoding="utf-8") as f:
        f.write(css)
    with open(os.path.join(scgen, "_ra_page.mjs"), "w", encoding="utf-8") as f:
        f.write(PAGE_MJS)
    href = "file:///" + os.path.abspath(popup_css).replace("\\", "/") if popup_css else ""
    r = subprocess.run(["node", "_ra_page.mjs", "_ra_cases.json", "_ra.css", str(width),
                        out_html, href],
                       capture_output=True, text=True, encoding="utf-8", cwd=scgen)
    if r.returncode != 0:
        print("page build failed:", r.stderr[:800])
        return False
    return True


def _parse_cdp(out):
    """cdp.mjs may hand back the expression's value directly or JSON-encode it once
    more (it depends on how the harness serialises the result). Accept either --
    assuming the double-encoded shape crashed the gate with a TypeError instead of
    reporting a verdict."""
    v = json.loads(out.strip())
    if isinstance(v, str):
        v = json.loads(v)
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zip")
    ap.add_argument("--sample", type=int, default=25)
    ap.add_argument("--width", type=int, default=390)
    ap.add_argument("--root", default=None, help="repository root (default: derived from this file)")
    ap.add_argument("--scgen", default=None,
                    help="jsdom generator dir (default <root>/scgen_test, env SCGEN_DIR)")
    ap.add_argument("--popup-css", default=None,
                    help="Hoshi's popup.css (default <root>/_hoshi/popup.css, env "
                         "HOSHI_POPUP_CSS); optional")
    ap.add_argument("--css", choices=("package", "generator"), default="package",
                    help="stylesheet to test: the one IN the package (default, what "
                         "actually ships) or the current generator output")
    args = ap.parse_args()

    root = os.path.abspath(args.root or ROOT)
    scgen = os.path.abspath(args.scgen or os.environ.get("SCGEN_DIR")
                            or os.path.join(root, "scgen_test"))
    popup = args.popup_css or os.environ.get("HOSHI_POPUP_CSS") \
        or os.path.join(root, "_hoshi", "popup.css")
    if not os.path.isdir(scgen):
        raise SystemExit(f"jsdom generator dir not found: {scgen}\n  pass --scgen or set SCGEN_DIR")
    missing = check_harness(scgen)
    if missing:
        print("HARNESS: cannot run this gate -- prerequisites are missing.\n")
        for what, remedy in missing:
            print(f"  * {what}")
            print(f"      -> {remedy}")
        print("\nThis gate needs a real browser because Yomitan's structured-content")
        print("generator produces the DOM (under jsdom) and the measurements come from")
        print("headless Chrome over the DevTools protocol. Nothing was checked.")
        return 2
    popup_used = popup if os.path.isfile(popup) else None

    print(f"package    : {os.path.basename(args.zip)}")
    print(f"root       : {root}")
    print(f"scgen      : {scgen}")
    print(f"hoshi popup: {popup_used or '(absent - rendering WITHOUT it; these invariants '
          'concern OUR stylesheet, pass --popup-css for full fidelity)'}")

    if args.css == "package":
        css = zipfile.ZipFile(args.zip).read("styles.css").decode("utf-8")
        src = "the package's own styles.css"
    else:
        sys.path.insert(0, os.path.join(root, "converter"))
        import ldoce2yomitan as C
        css = C.generate_css()
        src = "generate_css() (current source)"
    print(f"stylesheet : {src} ({len(css):,} chars)")

    reset = carriers_reset_in_css(css)
    neg = carriers_with_negative_indent(css)
    uncovered = sorted(neg - reset)
    print(f"\ncarriers with a negative text-indent ({len(neg)}): {sorted(neg)}")
    print(f"carriers reset through `carrier *`   ({len(reset)}): {sorted(reset)}")
    if uncovered:
        print(f"  [FAIL] not reset, so their block descendants inherit the indent: {uncovered}")
    else:
        print("  [OK] every carrier is covered by the descendant reset")

    act_rows, cn_rows = pick_rows(args.zip, args.sample)
    ids = act_rows + [r for r in cn_rows if r not in act_rows]
    print(f"\nsample     : {len(act_rows)} row(s) with ld-snum+ld-act, "
          f"{len(cn_rows)} with ld-colloexa+ld-defcn -> {len(ids)} unique row id(s)")
    if not ids:
        print("nothing to check")
        return 1
    rows = extract(args.zip, set(ids))
    print(f"extracted  : {len(rows)} row(s), keyed by (expression, sequence)")
    if len(rows) < len(ids):
        print(f"  [!] {len(ids) - len(rows)} sampled row id(s) did not round-trip")

    out_html = os.path.join(root, "_ra.html")
    if not build_page(rows, css, scgen, args.width, popup_used, out_html):
        return 2
    # Which carriers to test in the DOM: the ones the stylesheet resets, or -- when
    # it resets none (the very case this gate must fail) -- the ones that introduce
    # a negative indent, so check B still inspects the right nodes.
    check_carriers = reset or neg
    with open(os.path.join(scgen, "_ra_expr.js"), "w", encoding="utf-8") as f:
        f.write(EXPR_JS.replace("__CARRIERS__",
                                json.dumps(sorted(check_carriers), ensure_ascii=False)))
    r = subprocess.run(["node", "cdp.mjs", "file:///" + out_html.replace("\\", "/"), "_ra_expr.js"],
                       capture_output=True, text=True, encoding="utf-8", cwd=scgen,
                       env={**os.environ, "CDP_TARGET": CDP_TARGET})
    if r.returncode != 0:
        print("render failed:", r.stderr[:800])
        return 2

    recs = _parse_cdp(r.stdout)
    firsts = [c for rec in recs for c in rec.get("first", [])]
    gutters = [c for rec in recs for c in rec.get("gutter", [])]
    indents = [i for rec in recs for i in rec.get("indent", [])]
    styles = [rec["style"] for rec in recs if rec.get("style")]
    bad_gutter = list(gutters)
    bad_gutter_act = [c for c in gutters if c.get("is_act")]
    bad_indent = [i for i in indents if i["textIndent"] != "0px"]
    bad_style = [s for s in styles
                 if s["textTransform"] != "none" or s["letterSpacing"] not in ("normal", "0px")]

    print(f"\nA. nothing but the number may start LEFT of the sense content column")
    print(f"   {len(gutters)} child node(s) intrude ({len(bad_gutter_act)} of them ld-act chips)")
    for c in bad_gutter[:10]:
        flag = "ld-act" if c.get("is_act") else c.get("cls")
        print(f"     {flag:12} left={c['left']} column={c['column']} "
              f"delta={c['delta']}px  {c['text']!r}")
    print(f"\nB. ld-defcn under any reset carrier: computed text-indent must be 0")
    print(f"   {len(indents)} node(s) checked, {len(bad_indent)} still inheriting")
    for i in bad_indent[:8]:
        print(f"     text-indent={i['textIndent']}  {i['text']!r}")
    print(f"\nC. ld-act chip: no uppercase, no letter-spacing")
    print(f"   {len(styles)} chip(s) checked, {len(bad_style)} wrong")
    for s in bad_style[:4]:
        print(f"     text-transform={s['textTransform']} letter-spacing={s['letterSpacing']}")
    if styles:
        print(f"   sample: display={styles[0]['display']} font-size={styles[0]['fontSize']} "
              f"text-transform={styles[0]['textTransform']} "
              f"letter-spacing={styles[0]['letterSpacing']}")

    problems = []
    if uncovered:
        problems.append(f"{len(uncovered)} carrier(s) not reset in the CSS")
    if not indents:
        problems.append("sample too small to be meaningful -- widen it")
    if bad_gutter:
        problems.append(f"{len(bad_gutter)} node(s) start left of the sense content column "
                        f"({len(bad_gutter_act)} ld-act)")
    if bad_indent:
        problems.append(f"{len(bad_indent)} ld-defcn still inheriting an indent")
    if bad_style:
        problems.append(f"{len(bad_style)} chip(s) still uppercase/letter-spaced")
    print()
    if problems:
        for p in problems:
            print("  -", p)
        print("ALIGNMENT GATE: FAIL")
        return 1
    print("ALIGNMENT GATE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
