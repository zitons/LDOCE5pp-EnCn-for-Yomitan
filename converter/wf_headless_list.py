"""List every word whose entry has a headerless div.wordfams (T10 set)."""
import os
import io
import re

SIDE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "extract", "LDOCE5++ V 2-15.mdx.txt")
pat = re.compile(r'<div class="wordfams">(.{0,100})', re.S)
key = None
buf = []
words = []

with io.open(SIDE, encoding="utf-8", newline="") as fh:
    for line in fh:
        line = line.rstrip("\r\n")
        if line == "</>":
            if key:
                c = "\n".join(buf)
                for m in pat.finditer(c):
                    if not m.group(1).lstrip().startswith('<span class="LDOCE5pp_sensefold'):
                        words.append(key)
                        break
            key = None
            buf = []
        elif key is None and not buf:
            key = line
        else:
            buf.append(line)

print(len(words), "words")
print(",".join(words))
