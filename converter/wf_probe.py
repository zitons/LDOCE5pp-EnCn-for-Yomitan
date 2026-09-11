"""Print the raw structure of every div.wordfams block of given words."""
import io
import re
import sys

SIDE = r"C:\workspace\ldoce\extract\LDOCE5++ V 2-15.mdx.txt"
words = set(sys.argv[1:]) or {"close"}
pat = re.compile(r'<div class="wordfams">', re.I)

key = None
buf = []
with io.open(SIDE, encoding="utf-8", newline="") as fh:
    for line in fh:
        line = line.rstrip("\r\n")
        if line == "</>":
            if key in words:
                c = "\n".join(buf)
                for i, m in enumerate(pat.finditer(c), 1):
                    start = m.start()
                    # find matching close by depth counting
                    depth = 0
                    j = start
                    while j < len(c):
                        if c.startswith("<div", j):
                            depth += 1
                        elif c.startswith("</div>", j):
                            depth -= 1
                            if depth == 0:
                                j += 6
                                break
                        j += 1
                    block = c[start:j + 1]
                    print("=" * 78)
                    print(f"WORD {key!r}  wordfams #{i}  len={len(block)}")
                    print("HEAD200:", block[:200].replace("\n", " "))
                    print("TAIL120:", block[-120:].replace("\n", " "))
                    # top-level child tags only
                    inner = block[len('<div class="wordfams">'):-6]
                    kids = []
                    d = 0
                    k = 0
                    while k < len(inner):
                        if inner.startswith("<div", k) or inner.startswith("<span", k):
                            if d == 0:
                                kids.append(inner[k:k + 90].split(">")[0] + ">")
                            d += 1
                        elif inner.startswith("</div>", k) or inner.startswith("</span>", k):
                            d -= 1
                        k += 1
                    print("TOP-LEVEL CHILDREN:")
                    for kid in kids[:6]:
                        print("   ", kid)
            key = None
            buf = []
        elif key is None and not buf:
            key = line
        else:
            buf.append(line)
