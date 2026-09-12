"""T8 gate: does div.ld-head emit its children in source DOM order?

For every sampled entry, every `.Head` block in the source (homographs and
sub-entries each have their own) is paired, in document order, with the matching
`ld-head` block we emit, and the child sequences are compared token by token.

Both sides are normalised to a shared token vocabulary. Source elements with no
visible text are skipped on both sides (the source has empty `lm5pp_POS` stubs,
and the renderer deliberately drops those).

Exit code is non-zero when any head mismatches.
"""
import sys
import collections
from bs4 import BeautifulSoup

sys.path.insert(0, r'C:\workspace\ldoce\converter')
import ldoce2yomitan as M

SIDE = r'C:\workspace\ldoce\extract\LDOCE5++ V 2-15.mdx.txt'
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 3000

DIRECT = {
    'PronCodes': 'ld-pron', 'PRON': 'ld-pron', 'AMEVARPRON': 'ld-pron-amevar',
    'LEVEL': 'ld-level', 'FREQ': 'ld-freq',
    'lm5pp_POS': 'ld-pos', 'GRAM': 'ld-gram',
}


def src_token(ch):
    cls = set(ch.get('class') or [])
    if cls & M.DROP_CLASSES:
        return None
    if 'HWD' in cls or 'HOMNUM' in cls:
        return 'HEAD'
    if 'HYPHENATION' in cls or ('tooltip' in cls and 'LEVEL' not in cls):
        # HYPHENATION is the hidden syllable-split duplicate; a tooltip without LEVEL
        # carries no payload. Both are dropped by the renderer.
        return None
    for tok, tok_cls in DIRECT.items():
        if tok in cls:
            return tok_cls
    if 'Inflections' in cls:
        return 'INFL'
    for tok in M.CHIP_PRIORITY:
        if tok in cls:
            return M.CHIP_MAP[tok]
    for tok, (map_cls, _f) in M.INLINE_MAP.items():
        if tok in cls:
            return map_cls
    return '?' + '|'.join(sorted(cls))


def our_tokens(head):
    out = []
    for ch in head.get('content') or []:
        if not isinstance(ch, dict):
            continue
        toks = ((ch.get('data') or {}).get('class') or '').split()
        if not toks:
            continue
        if 'ld-hwd-wrap' in toks:
            out.append('HEAD')
        elif 'ld-sep' in toks:
            continue
        elif 'ld-infl-form' in toks:
            out.append('INFL')
        elif any(t in toks for t in ('ld-infl-ann', 'ld-infl-region', 'ld-infl-lab',
                                     'ld-infl-pron')):
            # Annotations INSIDE an Inflections sequence ('or', '(same
            # pronunciation)', 'British English', and since audit A4 the
            # inflected form's own IPA). The renderer inlines the ld-infl
            # wrapper's children into ld-head, so these sit between two
            # ld-infl-form nodes; they belong to the INFL run and must not break
            # it, or squash() reports INFL / ann / INFL against the source's one
            # Inflections element (10 false positives before this).
            continue
        else:
            out.append(toks[0])
    return out


def squash(seq):
    merged = []
    for t in seq:
        if not merged or merged[-1] != t:
            merged.append(t)
    return merged


def collect_heads(node, acc):
    """All ld-head blocks in document order."""
    if isinstance(node, list):
        for x in node:
            collect_heads(x, acc)
    elif isinstance(node, dict):
        if (node.get('data') or {}).get('class') == 'ld-head':
            acc.append(node)
        for k, v in node.items():
            if k != 'data':
                collect_heads(v, acc)


ti = M.TermIndex()
recs = {}
n = 0
for key, content in M.iter_records(SIDE):
    k = M.strip_invisible(key).strip()
    if not k:
        continue
    kind, _ = M.classify_record(k, content)
    if kind == 'entry':
        ti.add(k)
        recs[k] = content
        n += 1
        if n >= LIMIT:
            break

renderer = M.LdoceRenderer(ti)
n_entries = 0
n_heads = 0
ok = 0
bad = []
count_bad = []
unknown = collections.Counter()

for k, content in recs.items():
    soup = BeautifulSoup(content, 'lxml')
    expect_all = []
    for h in soup.find_all('span', class_=lambda c: c and 'Head' in c.split()):
        # `<span class="etym"><span class="Head">...` is the etymology's own headword
        # (e.g. "aback"), not an entry head -- the renderer rightly does not emit it
        # into div.ld-head, so it must not be counted here either.
        if h.find_parent(class_='etym') is not None:
            continue
        toks = []
        for ch in h.children:
            if getattr(ch, 'name', None) is None:
                continue
            if not ch.get_text('', strip=True):
                continue                      # empty stub such as lm5pp_POS
            t = src_token(ch)
            if t is None:
                continue
            if t.startswith('?'):
                unknown[t] += 1
                continue
            toks.append(t)
        expect_all.append(squash(toks))
    if not expect_all:
        continue
    n_entries += 1

    nodes = renderer.render_record(k, content)
    got_all = []
    collect_heads(nodes, got_all)
    got_all = [squash(our_tokens(h)) for h in got_all]

    n_heads += len(expect_all)
    if len(expect_all) != len(got_all):
        if len(count_bad) < 8:
            count_bad.append((k, len(expect_all), len(got_all), expect_all, got_all))
        continue
    if all(e == g for e, g in zip(expect_all, got_all)):
        ok += 1
    elif len(bad) < 10:
        for e, g in zip(expect_all, got_all):
            if e != g:
                bad.append((k, e, g))
                break

print('词条采样 = %d（其中含 .Head 的 %d）' % (len(recs), n_entries))
print('Head 块总数 = %d' % n_heads)
print('顺序完全一致 = %d' % ok)
print('顺序不一致 = %d' % len(bad))
print('Head 块数量不符 = %d' % len(count_bad))
print()
for k, e, g in bad:
    print('MISMATCH %r' % k)
    print('   source :', e)
    print('   ours   :', g)
print()
for k, a, b, ea, ga in count_bad:
    print('COUNT %r source=%d ours=%d' % (k, a, b))
    print('   source:', ea)
    print('   ours  :', ga)
print()
if unknown:
    print('源里出现但未映射的 class:')
    for t, c in unknown.most_common(10):
        print('   %6d  %s' % (c, t))
sys.exit(0 if not bad and not count_bad else 1)
