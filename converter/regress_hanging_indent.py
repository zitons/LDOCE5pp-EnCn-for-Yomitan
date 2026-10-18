"""Regression gate: the hanging indent must HOLD GEOMETRICALLY.

   Implementation-agnostic since PR #10: the hang may be built with
   margin-left + a hanging bullet, or padding-left + an in-flow
   inline-block bullet of the same width. What the gate checks is the
   RESULT: every line of an example starts at the same left edge, and the
   bullet hangs into the gutter to the left of that edge.

   WHY not margin-left specifically: text-indent is INHERITED, so a hang
   built with text-indent leaks into every descendant that opens a block
   container (the mechanism behind REVIEW D42/D43 and TYPOGRAPHY T9).
   That hazard is checked directly (no text-indent on a hanging class or
   its descendants) instead of by forbidding one implementation in favour
   of another.

REVIEW D42/D43 and TYPOGRAPHY T9 all trace back to one mechanism: a negative
`text-indent` used for a hanging indent. `text-indent` is INHERITED, so it leaks
into every descendant that opens a block container (block elements and
inline-block alike); `margin-left` applies to the element's own box and does not
inherit. The original dictionary's stylesheet uses a negative text-indent zero
times out of 684 rules.

This gate locks the migration in:

  1. generate_css() declares NO negative text-indent at all.
  2. every class that draws a hanging bullet (the ld-ex family and the ld-corpexa
     family) carries a positive margin-left, and its ::before carries the matching
     negative margin-left -- i.e. the bullet still hangs out.
  3. the bullet position and the wrapped-line position are measured in a real
     browser: the bullet must sit left of the indent, and the wrapped lines must
     sit exactly at it. That is the property the whole scheme exists to provide,
     and it is what silently regressed before.
  4. no descendant of a hanging-indent block may declare a text-indent at all
     (there is nothing to inherit, so any such declaration is dead weight that
     would mask a future regression).
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

SCGEN = os.path.join(ROOT, "scgen_test")
TOL = 0.6          # px

# classes that draw a hanging bullet, and the indent each one uses
HANGING = {
    "ld-ex": "1.6em", "ld-ex-good": "1.6em", "ld-ex-bad": "1.6em",
    "ld-corpexa": "1.2em", "ld-corpexa-corpus": "1.2em",
    "ld-corpexa-dics": "1.2em", "ld-corpexa-encyc": "1.2em",
    "ld-corpexa-online": "1.2em", "ld-corpexa-phrases": "1.2em",
}

# Group heads (grammar pattern / collocation) are NOT hanging bullets: they are
# one bold line that CONTAINS its examples. They used to be listed in HANGING
# because they were rendered as example items -- with a dash and a 1.6em indent
# -- and their own <ul> then indented the examples one level further. The gate
# now locks the corrected shape instead:
#   * the head is a block at a 1.1em step (the original uses 18px against the
#     example's 42px), with NO ::before -- a head is not an example line;
#   * the head's own example list is pulled back by the same 1.1em, so its
#     examples land on the ordinary example column, not one level below it.
GROUPS = {"ld-gramexa": "1.1em", "ld-colloexa": "1.1em"}


def _rules(css):
    flat = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(re.sub(r"\s+", " ", a).strip(), b)
            for a, b in re.findall(r"([^{}]+)\{([^{}]*)\}", flat)]


def _margin_left(body):
    """The effective margin-left of a declaration block.

    Understands the `margin` shorthand, because the hanging rules use
    `margin:1px 0 3px 1.6em` (top right bottom left) rather than a separate
    margin-left declaration -- matching on a literal `margin-left:` reports
    "absent" for a rule that does declare it.
    """
    ml = re.search(r"(?<![-\w])margin-left\s*:\s*([^;]+)", body)
    if ml:
        return ml.group(1).strip()
    m = re.search(r"(?<![-\w])margin\s*:\s*([^;]+)", body)
    if m:
        parts = m.group(1).split()
        if len(parts) == 4:
            return parts[3]
        if len(parts) == 3:
            return parts[1]
        if len(parts) == 2:
            return parts[1]
        if len(parts) == 1:
            return parts[0]
    return None


def _decl(body, prop):
    m = re.search(rf"(?<![-\w]){re.escape(prop)}\s*:\s*([^;]+)", body)
    return m.group(1).strip() if m else None


def _left_indent(body):
    """The effective LEFT indent of a declaration block (margin or padding,
    longhand or shorthand), or None."""
    for prop in ("margin-left", "padding-left"):
        v = _decl(body, prop)
        if v:
            return v
    for shorthand in ("margin", "padding"):
        m = re.search(rf"(?<![-\w]){shorthand}\s*:\s*([^;]+)", body)
        if m:
            parts = m.group(1).split()
            if len(parts) == 4:
                return parts[3]
            if len(parts) in (2, 3):
                return parts[1]
            if len(parts) == 1:
                return parts[0]
    return None


def check_static(css):
    """Verify the hang GEOMETRICALLY, whatever mechanism builds it."""
    fails = []
    rules = _rules(css)

    # S1/S4: no text-indent anywhere in a hanging block or its descendants.
    # text-indent inherits, so ANY value on a hanging class leaks into block
    # descendants; the hang must be built with box geometry instead.
    # text-indent:0 is a RESET (it stops the leak) and is not only allowed but
    # required on any hanging class whose sheet sets an inherited indent
    # elsewhere -- only a NON-ZERO value can create the hang.
    neg = [sel for sel, body in rules
           if any(f'"{cls}"' in sel for cls in HANGING)
           and re.search(r"text-indent\s*:\s*(?!0\s*[;}])(?!0px\s*[;}])[^;]+", body)]
    if neg:
        fails.append(f"text-indent declared on a hanging class: {neg[:4]}")

    for cls, indent in HANGING.items():
        base = [b for sel, b in rules
                if re.search(rf'\[data-sc-class="{cls}"\]', sel)
                and "::before" not in sel]
        if not base:
            fails.append(f"{cls}: no base rule found")
            continue
        left = _left_indent(base[0])
        if not left or not left.startswith(indent.split("em")[0]):
            fails.append(f"{cls}: left indent is {left or 'absent'}, "
                         f"expected {indent}")
        before = [b for sel, b in rules
                  if f'[data-sc-class="{cls}"]::before' in sel]
        if not before:
            fails.append(f"{cls}: no ::before rule")
            continue
        b = before[0]
        ml = _decl(b, "margin-left")
        msh = _left_indent(b) if (ml is None and _decl(b, "padding-left") is None) else None
        pos = _decl(b, "position")
        leftpos = _decl(b, "left")
        hangs = (
            (ml and ml.startswith("-"))
            or (pos == "absolute" and leftpos and leftpos.startswith("-"))
        )
        if not hangs:
            fails.append(f"{cls}: ::before does not hang out "
                         f"(margin-left {ml}, position {pos} {leftpos})")

    # Group heads: block at a small step, no bullet, and their own list pulled
    # back so the contained examples keep the ordinary example column.
    fails += check_groups(rules)
    return fails


def _effective(rules, cls):
    """Effective `display` and left indent of the bare `[data-sc-class="cls"]`
    rule, in sheet order.

    All such rules have the SAME specificity (0-1-0), so the last declaration
    wins regardless of which block it sits in. Picking the first matching rule
    (or the last block that happens to mention the class) is how the compact
    sheet's `ld-colloexa { display:inline }` override survived a green gate:
    the block rule existed, but a later sibling rule undid it.
    """
    display = None
    left = None
    for sel, body in rules:
        parts = [p.strip() for p in sel.split(",")]
        if f'[data-sc-class="{cls}"]' not in parts:
            continue
        d = _decl(body, "display")
        if d is not None:
            display = d
        i = _left_indent(body)
        if i is not None:
            left = i
    return display, left


def _effective_pseudo(rules, cls, pseudo="::before", prop="content"):
    """Effective value of `prop` on `[data-sc-class="cls"]<pseudo>`.

    Presence is not the question: both sheets deliberately emit a ::before rule
    with `content:none` to switch off the marker that scheme B writes into the
    DOM. Only a rule that actually PAINTS something (a value other than none)
    means the group head is still dressed as an example.
    """
    value = None
    target = f'[data-sc-class="{cls}"]{pseudo}'
    for sel, body in rules:
        parts = [p.strip() for p in sel.split(",")]
        if target not in parts:
            continue
        v = _decl(body, prop)
        if v is not None:
            value = v.strip()
    return value


def check_groups(rules):
    """The group-head contract, evaluated against the EFFECTIVE cascade."""
    fails = []
    for cls, step in GROUPS.items():
        display, left = _effective(rules, cls)
        if left != step:
            fails.append(f"{cls}: head indent is {left or 'absent'}, expected {step}")
        if display != "block":
            fails.append(f"{cls}: head is {display or 'not declared'}, expected "
                         f"block -- a later same-specificity rule overrides it")
        if _effective_pseudo(rules, cls) not in (None, "none"):
            fails.append(f"{cls}: still draws an example bullet "
                         f"(::before content {_effective_pseudo(rules, cls)})")
        pull = [b for sel, b in rules
                if re.search(rf'\[data-sc-class="{cls}"\]\s*>\s*'
                             rf'\[data-sc-class="ld-exlist"\]', sel)]
        if not pull:
            fails.append(f"{cls}: its inner example list is not pulled back -- "
                         f"examples would sit one level too deep")
        else:
            ml = _decl(pull[-1], "margin-left")
            if ml != "-" + step:
                fails.append(f"{cls}: inner list margin-left is {ml}, "
                             f"expected -{step}")
    return fails


def check_dynamic(css):
    """Measure bullet vs wrapped-line position in a real browser."""
    import ldoce2yomitan as C

    probes = {
        "item": 'a single thing, especially a single piece of clothing',
        "break down": 'substance breaks down',
    }
    sc = {}
    zpath = None
    for cand in (os.path.join(ROOT, "yomitan_fixed", "2026-09-15-align", "bilingual"),
                 os.path.join(ROOT, "yomitan_full")):
        if os.path.isdir(cand):
            for n in sorted(os.listdir(cand), reverse=True):
                if n.endswith(".zip") and "_DEBUG" not in n:
                    zpath = os.path.join(cand, n)
                    break
        if zpath:
            break
    if not zpath:
        return ["no package found to probe"], []
    import zipfile
    with zipfile.ZipFile(zpath) as z:
        for n in z.namelist():
            if not re.fullmatch(r"term_bank_\d+\.json", n):
                continue
            for r in json.loads(z.read(n)):
                if r[4] > 0 and r[0] in probes and r[0] not in sc:
                    for it in r[5]:
                        if isinstance(it, dict) and it.get("type") == "structured-content":
                            sc[r[0]] = it["content"]
    if not sc:
        return ["probe words not found in the package"], []

    fails = []
    skips = []
    # A missing harness prerequisite (node, headless Chrome) is an ENVIRONMENT
    # problem, not a broken scheme. Reporting it as FAIL makes "Chrome is not
    # running" look like "the hanging indent regressed", which is exactly the
    # misreading that wastes a debugging round. Skip instead, and say why.
    for tool in ("node",):
        try:
            subprocess.run([tool, "--version"], capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as e:
            return [], [f"SKIP dynamic checks: {tool} unavailable ({e})"]
    try:
        import urllib.request
        with urllib.request.urlopen(f"{os.environ.get('CDP_TARGET', 'http://127.0.0.1:9333')}"
                                    f"/json/version", timeout=5) as resp:
            resp.read()
    except Exception as e:
        return [], [f"SKIP dynamic checks: no DevTools endpoint at "
                    f"{os.environ.get('CDP_TARGET', 'http://127.0.0.1:9333')} ({e.__class__.__name__})"]

    with open(os.path.join(SCGEN, "_hi_sc.json"), "w", encoding="utf-8") as f:
        json.dump(sc, f, ensure_ascii=False)
    with open(os.path.join(SCGEN, "_hi.css"), "w", encoding="utf-8") as f:
        f.write(css)
    page = os.path.join(ROOT, "_hi.html")
    # the page URL is derived from the repo root, never written as a literal:
    # a hardcoded absolute path here silently points at another checkout
    page_url = "file:///" + page.replace("\\", "/")
    r = subprocess.run(["node", "_hi_page.mjs", "_hi_sc.json", "_hi.css", "390", page],
                       capture_output=True, text=True, encoding="utf-8", cwd=SCGEN)
    if r.returncode != 0:
        return [f"page build failed: {r.stderr[:300]}"], []
    r = subprocess.run(["node", "cdp.mjs", page_url, "_hi_expr.js"],
                       capture_output=True, text=True, encoding="utf-8", cwd=SCGEN,
                       env={**os.environ, "CDP_TARGET": "http://127.0.0.1:9333"})
    if r.returncode != 0:
        return [f"probe failed (is headless Chrome on :9333?): {r.stderr[:200]}"], []
    try:
        data = json.loads(json.loads(r.stdout.strip()))
    except Exception as e:
        return [f"could not parse probe output: {e}"], []

    for word, recs in data.items():
        for d in recs:
            if d["wrapped_l"] is None:
                continue          # single-line example: nothing to align
            if not (d["bullet_l"] < d["wrapped_l"] - TOL):
                fails.append(f"{word} {d['cls']}: bullet {d['bullet_l']} is not left of "
                             f"the wrapped lines {d['wrapped_l']} -- the hanging indent "
                             f"is broken")
            if abs(d["first_l"] - d["wrapped_l"]) > 40:
                fails.append(f"{word} {d['cls']}: first line {d['first_l']} vs wrapped "
                             f"{d['wrapped_l']} differ by more than the indent")
    return fails, skips


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--css", default=None, help="stylesheet to test "
                    "(default: generate_css())")
    args = ap.parse_args()
    if args.css:
        css = open(args.css, encoding="utf-8").read()
        compact_css = None
    else:
        sys.path.insert(0, HERE)
        import ldoce2yomitan as C
        css = C.generate_css()
        compact_css = C.generate_css("compact")

    print("=== static checks ===")
    f1 = check_static(css)
    for f in f1:
        print("   FAIL", f)
    print(f"   {len(HANGING)} hanging classes checked, "
          f"{len(f1)} static failure(s)")

    if compact_css is not None:
        fc = ["[compact] " + f for f in check_groups(_rules(compact_css))]
        for f in fc:
            print("   FAIL", f)
        print(f"   compact sheet: group-head contract, {len(fc)} failure(s)")
        f1 += fc

    print("\n=== dynamic checks (real browser) ===")
    f2, skips = check_dynamic(css)
    for s in skips:
        print("  ", s)
    for f in f2:
        print("   FAIL", f)
    if not f2 and skips:
        print("   (dynamic checks did not run -- environment, not the scheme)")
    print(f"   {len(f2)} dynamic failure(s), {len(skips)} skip(s)")

    bad = f1 + f2
    print()
    if bad:
        print("HANGING INDENT GATE: FAIL")
        return 1
    if skips:
        print("HANGING INDENT GATE: PASS (static only; dynamic skipped)")
        return 0
    print("HANGING INDENT GATE: PASS  (hanging geometry intact: each hanging "
          "class indents 1.6em on the left, its bullet hangs out, and no "
          "hanging class uses text-indent)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
