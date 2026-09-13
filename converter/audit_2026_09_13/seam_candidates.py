"""Find newly inserted ASCII-word seams in the pre-change shipped package.
This is a candidate finder, NOT a defect count. Confirm hits against source HTML.
"""
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'converter'))
import ldoce2yomitan as C
import _apply_patch as patch

ZIP = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'yomitan_full/LDOCE5pp_Yomitan_2026.09.11.zip'
counts = Counter()
examples = defaultdict(list)


def label(n):
    return n.get('data', {}).get('class') or n.get('tag', '?') if isinstance(n, dict) else 'text'


def scan(n, word, parent='root'):
    if isinstance(n, dict):
        scan(n.get('content'), word, label(n))
    elif isinstance(n, list):
        for a, b in zip(n, n[1:]):
            if not C._is_inline(a) or not C._is_inline(b) or not C._seam_needs_space(a, b):
                continue
            at, bt = C._plain_text(a), C._plain_text(b)
            if not re.search(r"[A-Za-z][A-Za-z'\u2019-]*$", at) or not re.match('[A-Za-z]', bt):
                continue
            kind = parent + ' | ' + label(a) + ' -> ' + label(b)
            counts[kind] += 1
            if len(examples[kind]) < 4:
                examples[kind].append({'word': word, 'left': at[-70:], 'right': bt[:90]})
        for c in n:
            scan(c, word, parent)


with zipfile.ZipFile(ZIP) as z:
    for name in z.namelist():
        if not re.fullmatch(r'term_bank_\d+\.json', name):
            continue
        for row in json.loads(z.read(name)):
            if row[4] > 0:
                scan(row[5], row[0])
        print(name, 'candidates=', sum(counts.values()), flush=True)
result = {'baseline_package': str(ZIP), 'counts': dict(counts), 'examples': dict(examples)}
patch.P = str(OUT / 'seam_candidates.json')
patch.write_atomic(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
for kind, count in counts.most_common():
    if kind.startswith(('ld-head |', 'ld-infl |', 'ld-wf-group |')):
        continue
    print(kind, count, json.dumps(examples[kind][:2], ensure_ascii=False))
