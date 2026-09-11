"""Why does bs4 see ~27k elements with class wordfams while the exact-attribute
regex saw 4,041? And does the new guard ever skip a LEGITIMATE panel?

For every record: parse with lxml, walk all elements with 'wordfams' in their
class list, classify by (a) inside lm5pp_popup?, (b) has direct-child sensefold?,
(c) is it the exact class="wordfams" form?
"""
import io
import re
from collections import Counter

from bs4 import BeautifulSoup

SIDE = r"C:\workspace\ldoce\extract\LDOCE5++ V 2-15.mdx.txt"

tot = 0
in_popup = 0
headless = 0
classes = Counter()
headless_in_content = []
key = None
buf = []


def scan(k, c):
    global tot, in_popup, headless
    soup = BeautifulSoup(c, "lxml")
    for el in soup.find_all(True):
        cl = el.get("class") or []
        if "wordfams" not in cl:
            continue
        tot += 1
        classes[el.get("class", None) and " ".join(el["class"])] += 1
        is_popup = el.find_parent(class_="lm5pp_popup") is not None
        if is_popup:
            in_popup += 1
        framed = el.find("span", class_="LDOCE5pp_sensefold", recursive=False) is not None
        if not framed:
            headless += 1
            if not is_popup and len(headless_in_content) < 20:
                headless_in_content.append((k, " ".join(el["class"])))


with io.open(SIDE, encoding="utf-8", newline="") as fh:
    for line in fh:
        line = line.rstrip("\r\n")
        if line == "</>":
            if key and "wordfams" in buf_join:
                pass
            if key:
                scan(key, "\n".join(buf))
            key = None
            buf = []
        elif key is None and not buf:
            key = line
        else:
            buf.append(line)
        buf_join = ""

print(f"elements with class wordfams: {tot}")
print(f"  inside lm5pp_popup        : {in_popup}")
print(f"  headerless (guard skips)  : {headless}")
print(f"  headerless NOT in popup   : {headless - sum(1 for k, c in headless_in_content)} "
      f"(list below is capped at 20)")
print("\ndistinct class strings (top 10):")
for cls, n in classes.most_common(10):
    print(f"   {n:>7}  {cls!r}")
print("\nheaderless examples outside popup:")
for k, cls in headless_in_content:
    print(f"   {k!r}  class={cls!r}")
