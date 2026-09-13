"""Regression gate: the no-CSS inline fallbacks must not override the stylesheet.

Every style the renderer attaches inline (SEMANTIC_INLINE_STYLES, BLOCK_BOTTOM_MARGIN,
UA_MARKER_OFF) is a *fallback* for hosts that load no stylesheet. An inline declaration
beats an author rule in the cascade, so a fallback whose value differs from the class
rule silently rewrites the styled rendering.

That already shipped once: `color:green` / `color:DodgerBlue` fallbacks for ld-pos /
ld-defcn / ... beat the theme-adaptive palette, dropping dark-theme Chinese definitions
from ~6.5:1 to 3.245:1 contrast while the stylesheet was loaded (audit R3). The same
class of bug put margin-bottom:1px on 133k ld-def nodes that the rule says is 0.

The invariant enforced here: for every inline property, the matching class rule in
generate_css() either

    (a) declares the SAME value (so the fallback is a no-op when CSS is present), or
    (b) marks that property !important (so the stylesheet wins regardless).

It also measures the static scheme-A neutrals, which are theme-blind by construction:
each must clear 3:1 against BOTH a white and a dark host background.
"""
import re
import sys

sys.path.insert(0, r"C:\workspace\ldoce\converter")
import ldoce2yomitan as C  # noqa: E402

css = C.generate_css()
css_nc = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
# the adaptive palette lives inside @supports and only redefines --ld-* variables,
# so masking it keeps rule parsing unambiguous (same trick as regress_css_fallback)
masked = re.sub(r"@supports[^{]*\{(?:[^{}]|\{[^{}]*\})*\}", "\n", css_nc, flags=re.S)

SIMPLE = re.compile(r'^\[data-sc-class~?="([^"]+)"\]$')

# ---- class -> merged declarations (a class may appear in several rules) ----
decls = {}
for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", masked):
    for part in sel.split(","):
        m = SIMPLE.match(part.strip())
        if not m:
            continue
        bucket = decls.setdefault(m.group(1), {})
        for d in body.split(";"):
            if ":" not in d:
                continue
            prop, val = d.split(":", 1)
            prop = prop.strip().lower()
            val = val.replace("!important", "").strip()
            imp = "!important" in d
            if prop and val:
                bucket[prop] = (val, imp) if not imp else (val, True)

WEIGHT = {"bold": "700", "normal": "400", "bolder": "800", "lighter": "300"}
PROP_NAME = re.compile(r"[A-Z]")


def kebab(name):
    return PROP_NAME.sub(lambda m: "-" + m.group(0).lower(), name)


def norm(prop, value):
    v = value.replace("!important", "").strip().lower()
    if prop == "font-weight":
        return WEIGHT.get(v, v)
    if prop in ("color", "background-color"):
        return v.replace(" ", "")
    return re.sub(r"\s+", " ", v)


def margin_bottom(shorthand):
    """margin-bottom implied by an `margin:` shorthand."""
    parts = shorthand.split()
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0]
    return parts[2]          # 3- or 4-value form


def rule_value(cls, prop):
    """(value, important) for `prop` on `cls`, expanding the margin shorthand."""
    d = decls.get(cls)
    if not d:
        return None, False
    if prop in d:
        return d[prop]
    if prop.startswith("margin-") and "margin" in d:
        short, imp = d["margin"]
        if prop == "margin-bottom":
            mb = margin_bottom(short)
            if mb:
                return mb, imp
    return None, False


fails = []
checked = 0

print("== inline fallbacks vs class rules ==")
inline_items = []
for cls, styles in sorted(C.SEMANTIC_INLINE_STYLES.items()):
    for prop, val in styles.items():
        inline_items.append((cls, prop, val))
for cls, val in sorted(C.BLOCK_BOTTOM_MARGIN.items()):
    inline_items.append((cls, "marginBottom", val))

for cls, prop, inline_val in inline_items:
    css_prop = kebab(prop)
    got = rule_value(cls, css_prop)
    if got == (None, False):
        # also accept the shorthand having been written on the same rule list
        fails.append(f"{cls}.{css_prop}: inline {inline_val!r} but the class rule "
                     f"declares nothing")
        continue
    css_val, imp = got
    checked += 1
    same = norm(css_prop, css_val) == norm(css_prop, str(inline_val))
    if not (same or imp):
        fails.append(f"{cls}.{css_prop}: inline {inline_val!r} vs rule {css_val!r} "
                     f"-- differs and the rule is not !important")
    else:
        mode = "equal" if same else "!important"
        print(f"  OK  {cls:22} {css_prop:12} inline={str(inline_val):12} rule={css_val:22} [{mode}]")

print(f"  ({checked} inline declarations checked)")

# ---- list-markers: the inline listStyleType must be a legal SC property ----
print()
print("== UA marker suppression ==")
for prop, val in C.UA_MARKER_OFF.items():
    legal = prop in C.SC_STYLE_ALLOWED
    print(f"  {'OK ' if legal else 'BAD'} {prop}={val!r} legal-in-SC={legal}")
    if not legal:
        fails.append(f"UA_MARKER_OFF uses {prop}, not in SC_STYLE_ALLOWED "
                     f"(the generator would drop it silently)")

# ---- scheme-A neutrals: contrast on both a white and a dark host -----------
print()
print("== static neutral fallbacks (theme-blind) ==")


def srgb_lum(rgb):
    def ch(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(fg, bg):
    l1, l2 = srgb_lum(fg), srgb_lum(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def parse_colour(text):
    """(rgb, alpha) from #rrggbb or rgb()/rgba()."""
    t = text.strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{6})", t)
    if m:
        h = m.group(1)
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)], 1.0
    m = re.fullmatch(r"rgba?\(([^)]*)\)", t)
    if m:
        nums = [n.strip() for n in m.group(1).replace("/", " ").replace(",", " ").split()]
        vals = []
        for n in nums[:3]:
            vals.append(round(float(n[:-1]) * 255 / 100) if n.endswith("%") else round(float(n)))
        a = 1.0
        if len(nums) > 3:
            a = float(nums[3][:-1]) / 100 if nums[3].endswith("%") else float(nums[3])
        return vals, a
    return None, None


def composited(fg, a, bg):
    return [fg[i] * a + bg[i] * (1 - a) for i in range(3)]


HOSTS = [("light #ffffff", [255, 255, 255], [32, 33, 36]),
         ("dark  #1e1e1e", [30, 30, 30], [232, 232, 232])]
static_neutrals = {}
for name, val in re.findall(r"(--ld-[\w-]+)\s*:\s*([^;]+);", masked):
    if name in ("--ld-text2", "--ld-dim", "--ld-faint"):
        static_neutrals[name] = val.strip()

if len(static_neutrals) < 3:
    fails.append(f"static neutrals not found in the unprotected block: {static_neutrals}")
else:
    MIN = 3.0
    for name in ("--ld-text2", "--ld-dim", "--ld-faint"):
        raw = static_neutrals[name]
        rgb, a = parse_colour(raw)
        if rgb is None:
            # a value that inherits the host text colour cannot fail contrast by
            # construction -- check it against the two representative host themes
            if "currentColor" in raw or "--text-color" in raw:
                line = []
                for label, bg, fg in HOSTS:
                    c = contrast(fg, bg)
                    line.append(f"{label} {c:.2f}:1 {'OK' if c >= MIN else 'FAIL'}")
                    if c < MIN:
                        fails.append(f"{name} inherits {label}: {c:.2f}:1 < {MIN}")
                print(f"  OK   {name:12} {raw:34} " + "   ".join(line))
            else:
                fails.append(f"{name}: cannot parse {raw!r}")
            continue
        line = []
        for label, bg, _fg in HOSTS:
            c = contrast(composited(rgb, a, bg), bg)
            line.append(f"{label} {c:.2f}:1 {'OK' if c >= MIN else 'FAIL'}")
            if c < MIN:
                fails.append(f"{name}={raw} on {label}: {c:.2f}:1 < {MIN}")
        verdict = "OK " if all("FAIL" not in x for x in line) else "BAD"
        print(f"  {verdict}  {name:12} {raw:34} " + "   ".join(line))

print()
if fails:
    print(f"RESULT: FAIL ({len(fails)})")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("RESULT: PASS -- inline fallbacks are no-ops under CSS and clear 3:1 unaided")
