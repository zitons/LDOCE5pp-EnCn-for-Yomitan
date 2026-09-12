"""A3 follow-up: for EVERY entry the fix changes, compare against an lxml DOM
reference built the same way the audit's source_probe.py builds it.

Guards the 89 entries that changed but were not among the audit's 281 findings.
"""
import re
import sys
from pathlib import Path

ROOT = Path(r"C:\workspace\ldoce")
sys.path.insert(0, str(ROOT / "converter"))
import ldoce2yomitan as M  # noqa: E402
from lxml import html  # noqa: E402


def cls(e):
    return set((e.get("class") or "").split())


def ref_text(e, skip_portrait=True):
    parts = []
    if e.text:
        parts.append(e.text)
    for ch in e:
        if isinstance(ch.tag, str) and not (skip_portrait and "portrait" in cls(ch)):
            parts.append(ref_text(ch, skip_portrait))
        if ch.tail:
            parts.append(ch.tail)
    return "".join(parts)


OLD_POS = re.compile(
    r'<span[^>]*\bclass="[^"]*\blm5pp_POS\b[^"]*"[^>]*>(.*?)</span>', re.S)

changed = []
for i, (key, content) in enumerate(M.iter_records(ROOT / "extract/LDOCE5++ V 2-15.mdx.txt")):
    old = M.pos_tags_rules(OLD_POS.findall(content), M.FREQ_SCAN_RE.findall(content))
    new = M.pos_tags_rules(*M.extract_tags(content))
    if old == new:
        continue
    dom = html.fromstring(content)
    labels = [ref_text(el) for el in dom.iter("span") if "lm5pp_POS" in cls(el)]
    ref = M.pos_tags_rules(labels, M.FREQ_SCAN_RE.findall(content))
    changed.append((M.strip_invisible(key).strip(), i, old, new, ref))

bad_new = [c for c in changed if c[3] != c[4]]
bad_old = [c for c in changed if c[2] != c[4]]
print(f"entries where old != new        : {len(changed)}")
print(f"  of those, OLD != DOM reference: {len(bad_old)}")
print(f"  of those, NEW != DOM reference: {len(bad_new)}")
print()
for w, i, old, new, ref in bad_new[:15]:
    print(f"  MISMATCH {w!r}\n     old={old}\n     new={new}\n     ref={ref}")
print()
print("sample of fixed entries (NEW == reference):")
for w, i, old, new, ref in changed[:8]:
    print(f"  {w!r:22} old={old[0]!r}/{old[1]!r}  ->  new={new[0]!r}/{new[1]!r}")
