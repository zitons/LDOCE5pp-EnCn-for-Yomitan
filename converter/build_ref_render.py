import io, re, sys, os
sys.path.insert(0, r'C:\workspace\ldoce\converter')
from ldoce2yomitan import iter_records, strip_invisible

SIDE = r'C:\workspace\ldoce\extract\LDOCE5++ V 2-15.mdx.txt'
CSS = io.open(r'C:\workspace\ldoce\mdd_assets\LM5style.css', encoding='utf-8', errors='replace').read()

WANT = ['18-wheeler', 'abandon', 'improve', 'seeing', 'second class', 'the']
recs = {}
for key, content in iter_records(SIDE):
    k = strip_invisible(key).strip()
    if k in WANT and k not in recs:
        recs[k] = content
    if len(recs) == len(WANT):
        break

print('取到:', list(recs))

# 看看根容器叫什么
for k, c in list(recs.items())[:2]:
    m = re.search(r'<div class="([^"]*)"[^>]*>\s*<span class="([^"]*)"', c)
    print(f'  {k}: 首个 div/span class = {m.groups() if m else None}')
    for probe in ('ldoceEntry', 'entry_content', 'lm5ppbody', 'freq'):
        print(f'     含 {probe}: {probe in c}')

def clean(c):
    c = re.sub(r'<link[^>]*>', '', c)
    c = re.sub(r'<script.*?</script>', '', c, flags=re.S)
    return c

blocks = []
for k in WANT:
    if k not in recs:
        continue
    blocks.append(f'<hr><h2 style="font:14px monospace;color:#888">{k}</h2>\n' + clean(recs[k]))

html = '<!doctype html><html><head><meta charset="utf-8"><style>\n' \
    + CSS + '\n' \
    + 'body{background:#fff;margin:0;padding:12px;max-width:760px;}\n' \
    + '</style></head><body>\n' + '\n'.join(blocks) + '\n</body></html>'

out = r'C:\workspace\ldoce\_original_render.html'
io.open(out, 'w', encoding='utf-8').write(html)
print('written', out, len(html), 'bytes')
