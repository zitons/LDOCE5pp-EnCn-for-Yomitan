"""Text-conservation gate: how much source text never reaches the output?

For every sampled entry, the visible text of the source record is tokenised and
compared (as a multiset) against the text carried by the rendered structured
content. Only *words* are compared -- the source has no markup vocabulary in its
text nodes, and the SC side counts only `content` strings, never `tag`/`lang`
values (otherwise the SC element names themselves show up as "extra" and the
totals look inflated).

Deliberate omissions are modelled on the source side so they do not masquerade
as loss:
  * DROP_CLASSES subtrees (UI chrome, audio buttons, image links, .suppressed --
    the original stylesheet has `.suppressed { display: none; }`)
  * HYPHENATION (hidden syllable-split duplicate of HWD)
  * tooltip without LEVEL (carries no payload)
  * <style>/<script> bodies (the source embeds per-entry CSS/JS)
  * class="landscape" (the alternative rendering that _pick_landscape discards)

Anything still missing is real loss. Note the known exception: the `See picture`
cross-reference (class `imagerelated`) IS displayed by the original and IS
dropped by us -- see REVIEW.md D8.
"""
import re
import sys
import collections
from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, r'C:/workspace/ldoce/converter')
import ldoce2yomitan as M

SIDE = r'C:/workspace/ldoce/extract/LDOCE5++ V 2-15.mdx.txt'
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 800

TOK = re.compile(r'[A-Za-z]+|[\u4e00-\u9fff]|\d+')
DROP = set(M.DROP_CLASSES)
EXTRA_HIDDEN = {'HYPHENATION', 'landscape'}


def is_hidden(cls):
    return bool(cls & DROP) or bool(cls & EXTRA_HIDDEN) or ('tooltip' in cls and 'LEVEL' not in cls)


def src_tokens(node, acc):
    for ch in getattr(node, 'children', []):
        if isinstance(ch, NavigableString):
            p = ch.parent
            if p is not None and p.name in ('style', 'script'):
                continue
            acc.extend(TOK.findall(str(ch).lower()))
        elif isinstance(ch, Tag):
            if ch.name in ('style', 'script'):
                continue
            if is_hidden(set(ch.get('class') or [])):
                continue
            src_tokens(ch, acc)
    return acc


def sc_tokens(node, acc):
    """Only visible text: `content` strings. Never `tag`/`lang`/`title` values."""
    if isinstance(node, str):
        acc.update(TOK.findall(node.lower()))
    elif isinstance(node, list):
        for x in node:
            sc_tokens(x, acc)
    elif isinstance(node, dict):
        c = node.get('content')
        if c is not None:
            sc_tokens(c, acc)
    return acc


ti = M.TermIndex()
recs = {}
for key, content in M.iter_records(SIDE):
    k = M.strip_invisible(key).strip()
    if not k:
        continue
    kind, _ = M.classify_record(k, content)
    if kind == 'entry':
        ti.add(k)
        recs[k] = content
        if len(recs) >= LIMIT:
            break

renderer = M.LdoceRenderer(ti)
missing_total = collections.Counter()
offender_tokens = 0
offenders = []
src_n = got_n = 0
for k, content in recs.items():
    soup = BeautifulSoup(content, 'lxml')
    st = collections.Counter(src_tokens(soup, []))
    ot = collections.Counter()
    sc_tokens(renderer.render_record(k, content) or [], ot)
    src_n += sum(st.values())
    got_n += sum(ot.values())
    miss = st - ot
    if miss:
        missing_total.update(miss)
        offender_tokens += sum(miss.values())
        offenders.append((sum(miss.values()), k, miss))

print('样本词条 = %d' % len(recs))
print('源侧词元 = %d   输出侧词元 = %d' % (src_n, got_n))
print('未到达输出的词元 = %d  (%.3f%% of source)' % (offender_tokens, offender_tokens * 100.0 / max(src_n, 1)))
print('有缺失的词条 = %d (%.1f%%)' % (len(offenders), len(offenders) * 100.0 / max(len(recs), 1)))
print()
print('缺失词元 TOP 20:')
for w, c in missing_total.most_common(20):
    print('   %7d  %r' % (c, w))
print()
offenders.sort(reverse=True)
print('缺失最多的词条 TOP 6:')
for n, k, miss in offenders[:6]:
    print('   %-24r 缺失 %d: %s' % (k, n, [w for w, _ in miss.most_common(8)]))
print()
print('判读：`i/t/u/c/adj/adv/phr/v` 是 landscape 语法码（我们取其中一种渲染）；')
print('      `see/picture/见图` 类若出现在 top 里即是 D8（已知、待修）。')
