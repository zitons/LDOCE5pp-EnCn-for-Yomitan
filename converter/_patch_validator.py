"""Validator hardening: enforce the single-token discipline automatically.

Yomitan writes data:{class} into ONE attribute value, so "[data-sc-class=X]"
only matches when the emitted value is exactly X. A compound value such as
"ld-panel ld-panel-online" therefore silently loses every exact-match rule, and
the old check could not see it: collect_sc_classes() split the value and the
token was "defined" somewhere in the CSS even though no selector could ever
match that element.

New rule:
  * a token emitted as the WHOLE value  -> may be covered by ="X" or ~="X"
  * a token emitted inside a multi-token value -> MUST be covered by ~="X"
This is what already made "ld-sense-cross ld-sense-n" correct, and it now
catches the compound-class mistake at build time.
"""
import sys

sys.path.insert(0, r"C:\workspace\ldoce\converter")
from _apply_patch import apply  # noqa: E402

OLD_COLLECT = '''def collect_sc_classes(value, found):
    if isinstance(value, list):
        for item in value:
            collect_sc_classes(item, found)
    elif isinstance(value, dict):
        cls = (value.get("data") or {}).get("class")
        if cls:
            found.update(cls.split())
        for key, item in value.items():
            if key != "data":
                collect_sc_classes(item, found)
'''

NEW_COLLECT = '''def collect_sc_classes(value, found, compound=None):
    """Collect emitted class tokens, split by how they were emitted.

    `found`      -- tokens emitted as the entire class value (="X" or ~="X")
    `compound`   -- tokens emitted inside a multi-token value (only ~="X" matches)

    Yomitan sets data.class as a single attribute value, so a compound value can
    only be reached by an attribute-substring selector. Keeping the two sets
    apart is what makes the CSS check able to catch "ld-panel ld-panel-online".
    """
    if compound is None:
        compound = set()
    if isinstance(value, list):
        for item in value:
            collect_sc_classes(item, found, compound)
    elif isinstance(value, dict):
        cls = (value.get("data") or {}).get("class")
        if cls:
            parts = cls.split()
            if len(parts) > 1:
                compound.update(parts)
            else:
                found.update(parts)
        for key, item in value.items():
            if key != "data":
                collect_sc_classes(item, found, compound)
'''

OLD_CSS = '''        css = zf.read("styles.css").decode("utf-8") if "styles.css" in names else ""
        defined = set()
        for m in re.findall(r'\\[data-sc-class="([^"]+)"\\]', css):
            defined.update(m.split())
        for m in re.findall(r'\\[data-sc-class~="([^"]+)"\\]', css):
            defined.update(m.split())
        missing = used_classes - defined
        if missing:
            errors.append("CSS missing selectors for: " + ", ".join(sorted(missing)))
'''

NEW_CSS = '''        css = zf.read("styles.css").decode("utf-8") if "styles.css" in names else ""
        defined_exact = set()
        for m in re.findall(r'\\[data-sc-class="([^"]+)"\\]', css):
            defined_exact.update(m.split())
        defined_substr = set()
        for m in re.findall(r'\\[data-sc-class~="([^"]+)"\\]', css):
            defined_substr.update(m.split())
        defined = defined_exact | defined_substr
        missing = used_classes - defined
        if missing:
            errors.append("CSS missing selectors for: " + ", ".join(sorted(missing)))
        # A compound class value is only reachable via an attribute-substring
        # selector. Exact-match rules look correct in the stylesheet yet can never
        # apply to those elements, so require ~= for every compound token.
        loose = used_compound - defined_substr
        if loose:
            errors.append(
                "CSS: compound class values need [data-sc-class~=\\"...\\"] selectors for: "
                + ", ".join(sorted(loose)))
'''

if __name__ == "__main__":
    apply("validator compound-class check", [
        (OLD_COLLECT, NEW_COLLECT, 1),
        (OLD_CSS, NEW_CSS, 1),
        ('    used_classes = set()\n',
         '    used_classes = set()\n    used_compound = set()\n', 1),
        ('                        collect_sc_classes(item["content"], used_classes)\n',
         '                        collect_sc_classes(item["content"], used_classes, used_compound)\n', 1),
    ])
    print("VALIDATOR HARDENED")
