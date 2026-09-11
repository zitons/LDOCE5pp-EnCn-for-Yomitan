"""Locate the boxes whose lm5ppBoxHead carries a sense-gloss heading
('– Meaning 1: ...') and show their classes + what the renderer does with them."""
import re
import sys

from bs4 import BeautifulSoup

sys.path.insert(0, r"C:/workspace/ldoce/converter")
import ldoce2yomitan as M  # noqa: E402

SIDE = r"C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt"
WORD = sys.argv[1] if len(sys.argv) > 1 else "act"

content = None
for key, c in M.iter_records(SIDE):
    if M.strip_invisible(key).strip() == WORD:
        content = c
        break

soup = BeautifulSoup(content, "lxml")
print(f"=== {WORD}: every lm5ppBoxHead, with its enclosing box class ===")
for h in soup.find_all(class_="lm5ppBoxHead"):
    txt = re.sub(r"\s+", " ", h.get_text(" ", strip=True)).strip()
    box = h.find_parent(class_="lm5ppBox")
    boxcls = " ".join(box.get("class") or []) if box is not None else "?"
    marker = "  <<< SENSE-GLOSS HEADING" if re.match(r"^\s*[-–—]", txt) else ""
    print(f"  box={boxcls[:52]:>54}  heading={txt[:70]!r}{marker}")

print()
print("=== what _panel_title returns for those headings ===")
for h in soup.find_all(class_="lm5ppBoxHead"):
    txt = re.sub(r"\s+", " ", h.get_text(" ", strip=True)).strip()
    if not re.match(r"^\s*[-–—]", txt):
        continue
    box = h.find_parent(class_="lm5ppBox")
    boxcls = [c for c in (box.get("class") or []) if c not in ("lm5ppBox", "BoxHide")]
    token = M.PANEL_CLASSES & set(box.get("class") or [])
    # emulate the renderer's introspection of the panel token
    print(f"  heading={txt[:60]!r}")
    print(f"    box extra classes={boxcls} PANEL_CLASSES hit={sorted(token)}")
    for t in sorted(token):
        print(f"    _panel_title(heading, {t!r}) -> {M.LdoceRenderer._panel_title(None, txt, t)}")
    if not token:
        print(f"    NO PANEL_CLASSES hit -> render_div dispatches elsewhere")
        print(f"    full box class={box.get('class')}")
