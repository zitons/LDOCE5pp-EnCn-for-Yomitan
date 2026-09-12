"""Regression gate for scheme A (portable CSS fallbacks).

Asserts against generate_css() output, statically:
  1. every custom property that a var() consumer relies on has a static default
     declared OUTSIDE any @supports block
  2. the adaptive color-mix() palette lives INSIDE an @supports test for
     color-mix (so a non-supporting engine never parses it)
  3. every property whose value uses color-mix() outside @supports carries a
     preceding static declaration
  4. no declaration consumed via var(--ld-*) can end up undefined

Rationale (measured, see converter/_cssfallback_probe*.html + CDP):
  * `color: X; color: var(--undefined)` -> X is DISCARDED (parent colour wins)
  * var(--defined-but-invalid, fallback) -> fallback IGNORED
  * static default outside @supports + fancy value inside -> static wins
"""
import re
import sys

sys.path.insert(0, r"C:\workspace\ldoce\converter")
import ldoce2yomitan as C  # noqa: E402

css = C.generate_css()
fails = []

# Strip comments FIRST. The stylesheet documents the @supports strategy in
# comments that literally contain the text "@supports", and a scanner that sees
# those would treat a comment as the start of a block and swallow the real rules.
css_nc = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

# mask every @supports block so we can reason about the unprotected part
SUPPORTS_RE = re.compile(r"@supports[^{]*\{(?:[^{}]|\{[^{}]*\})*\}", re.S)
masked = SUPPORTS_RE.sub("\n/*SUPPORTS*/\n", css_nc)

def rules(text):
    return [(re.sub(r"\s+", " ", s).strip(), b)
            for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", text)]

# ---- 1. custom properties have static defaults outside @supports -----------
defined_outside = set()
for sel, body in rules(masked):
    for name in re.findall(r"(--ld-[\w-]+)\s*:", body):
        defined_outside.add(name)
consumed = set(re.findall(r"var\((--ld-[\w-]+)", css))
missing_default = sorted(consumed - defined_outside)
print(f"custom properties consumed        : {len(consumed)}")
print(f"defined outside @supports         : {len(defined_outside)}")
if missing_default:
    fails.append(f"no static default outside @supports: {missing_default}")
else:
    print("  OK  every consumed --ld-* has a static default")

# the static defaults must not themselves be color-mix()
bad_defaults = []
for sel, body in rules(masked):
    for name, val in re.findall(r"(--ld-[\w-]+)\s*:\s*([^;]+)", body):
        if "color-mix(" in val:
            bad_defaults.append((name, val.strip()[:60]))
if bad_defaults:
    fails.append(f"static defaults still use color-mix: {bad_defaults[:4]}")
else:
    print("  OK  no static default uses color-mix()")

# ---- 2. the adaptive palette is inside @supports ---------------------------
supports_blocks = SUPPORTS_RE.findall(css_nc)
has_cm_supports = any("color-mix(" in b for b in supports_blocks)
if not has_cm_supports:
    fails.append("no @supports (color: color-mix(...)) block found")
else:
    print(f"  OK  @supports color-mix block present ({len(supports_blocks)} block(s))")

# ---- 3. unprotected color-mix declarations have a static predecessor ------
unprotected = []
for sel, body in rules(masked):
    decls = [d.strip() for d in body.split(";") if d.strip()]
    for i, d in enumerate(decls):
        if "color-mix(" not in d or ":" not in d:
            continue
        prop = d.split(":", 1)[0].strip()
        prev = [p for p in decls[:i]
                if ":" in p and p.split(":", 1)[0].strip() == prop
                and "color-mix(" not in p]
        if not prev:
            unprotected.append((sel[:60], d[:70]))
if unprotected:
    fails.append(f"{len(unprotected)} color-mix decls lack a static predecessor: "
                 f"{unprotected[:3]}")
else:
    print("  OK  every unprotected color-mix declaration has a static predecessor")

# ---- 4. sanity: text still distinguishable in the static palette -----------
pairs = re.findall(r"(--ld-[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;", masked)
vals = {}
for name, v in pairs:
    vals.setdefault(name, v)
distinct = len(set(vals.values()))
print(f"  static colour defaults found      : {len(vals)} ({distinct} distinct)")
if distinct < 8:
    fails.append(f"too few distinct static colours: {distinct}")

print()
if fails:
    for f in fails:
        print("FAIL:", f)
    sys.exit(1)
print("RESULT: PASS -- scheme A fallbacks are complete and correctly layered")
