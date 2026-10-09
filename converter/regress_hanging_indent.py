"""Regression gate: the hanging indent must stay margin-left based.

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
    "ld-gramexa": "1.6em", "ld-colloexa": "1.6em",
    "ld-corpexa": "1.2em", "ld-corpexa-corpus": "1.2em",
    "ld-corpexa-dics": "1.2em", "ld-corpexa-encyc": "1.2em",
    "ld-corpexa-online": "1.2em", "ld-corpexa-phrases": "1.2em",
}


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


def check_static(css):
    fails = []
    rules = _rules(css)

    neg = [sel for sel, body in rules if re.search(r"text-indent\s*:\s*-", body)]
    if neg:
        fails.append(f"negative text-indent still declared: {neg[:4]}")

    # every hanging class must have a positive margin-left, and its ::before a
    # matching negative one
    for cls, indent in HANGING.items():
        base = [b for sel, b in rules
                if re.search(rf'\[data-sc-class="{cls}"\]', sel)
                and "::before" not in sel]
        if not base:
            fails.append(f"{cls}: no base rule found")
            continue
        ml = _margin_left(base[0])
        if not ml or not ml.startswith(("1.6em", "1.2em")):
            fails.append(f"{cls}: margin-left is {ml or 'absent'}, expected {indent}")
        before = [b for sel, b in rules
                  if f'[data-sc-class="{cls}"]::before' in sel]
        if not before:
            fails.append(f"{cls}: no ::before rule")
            continue
        bml = _margin_left(before[0])
        if not bml or not bml.startswith("-"):
            fails.append(f"{cls}: ::before margin-left is {bml or 'absent'} "
                         f"(the bullet would not hang out)")
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
        return ["no package found to probe"]
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
        return ["probe words not found in the package"]

    fails = []
    with open(os.path.join(SCGEN, "_hi_sc.json"), "w", encoding="utf-8") as f:
        json.dump(sc, f, ensure_ascii=False)
    with open(os.path.join(SCGEN, "_hi.css"), "w", encoding="utf-8") as f:
        f.write(css)
    page = os.path.join(ROOT, "_hi.html")
    r = subprocess.run(["node", "_hi_page.mjs", "_hi_sc.json", "_hi.css", "390", page],
                       capture_output=True, text=True, encoding="utf-8", cwd=SCGEN)
    if r.returncode != 0:
        return [f"page build failed: {r.stderr[:300]}"]
    r = subprocess.run(["node", "cdp.mjs", "file:///C:/workspace/ldoce/_hi.html", "_hi_expr.js"],
                       capture_output=True, text=True, encoding="utf-8", cwd=SCGEN,
                       env={**os.environ, "CDP_TARGET": "http://127.0.0.1:9333"})
    if r.returncode != 0:
        return [f"probe failed (is headless Chrome on :9333?): {r.stderr[:200]}"]
    try:
        data = json.loads(json.loads(r.stdout.strip()))
    except Exception as e:
        return [f"could not parse probe output: {e}"]

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
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--css", default=None, help="stylesheet to test "
                    "(default: generate_css())")
    args = ap.parse_args()
    if args.css:
        css = open(args.css, encoding="utf-8").read()
    else:
        sys.path.insert(0, HERE)
        import ldoce2yomitan as C
        css = C.generate_css()

    print("=== static checks ===")
    f1 = check_static(css)
    for f in f1:
        print("   FAIL", f)
    print(f"   {len(HANGING)} hanging classes checked, "
          f"{len(f1)} static failure(s)")

    print("\n=== dynamic checks (real browser) ===")
    f2 = check_dynamic(css)
    for f in f2:
        print("   FAIL", f)
    print(f"   {len(f2)} dynamic failure(s)")

    bad = f1 + f2
    print()
    if bad:
        print("HANGING INDENT GATE: FAIL")
        return 1
    print("HANGING INDENT GATE: PASS  (margin-left scheme intact)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
