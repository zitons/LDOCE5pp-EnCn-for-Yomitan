"""Strict whole-package comparison: only the reviewed N2 spaces and N3 CSS may change."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'converter'))
import ldoce2yomitan as C

APOSTROPHE = chr(0x2019)
REPAIRS = {
    'come': ('relieve', 'd'),
    'come as a surprise/relief/blow etc (to somebody)': ('relieve', 'd'),
    'in vitro fertilization': ('fertilize', 'd'),
    'none': ('did', 'n' + APOSTROPHE + 't'),
    'not': ('did', 'n' + APOSTROPHE + 't'),
}
BASE_SHA = {
    'bilingual': '8544ed4c6677f7c8e1cdc17a3222dc69b40be3d3b0857feefecb2ccfe73d77e1',
    'mono': '73662eabaa3985eb9843026ca55a440838c12d286d6247fa7565cd93dcaa840e',
}
CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def flat(node):
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return ''.join(map(flat, node))
    return flat(node.get('content', '')) if isinstance(node, dict) else ''


def can_delete_space(items, index, pair):
    if index <= 0 or index + 1 >= len(items) or items[index] != ' ':
        return False
    match = re.search(r'[A-Za-z]+$', flat(items[index - 1]))
    return bool(match and (match[0], flat(items[index + 1])) == pair)


def compare_tree(old, new, pair, removed, path='glossary'):
    """Reject all structural/style/text edits except a reviewed standalone space."""
    if old == new:
        return
    if isinstance(old, dict) and isinstance(new, dict):
        assert old.keys() == new.keys(), (path, 'dictionary keys changed')
        for key in old:
            compare_tree(old[key], new[key], pair, removed, path + '.' + key)
        return
    if isinstance(old, list) and isinstance(new, list):
        i = j = 0
        while i < len(old) and j < len(new):
            if old[i] == new[j]:
                i += 1
                j += 1
            elif can_delete_space(old, i, pair):
                removed.append(path + f'[{i}]')
                i += 1
            else:
                compare_tree(old[i], new[j], pair, removed, path + f'[{i}]')
                i += 1
                j += 1
        assert i == len(old) and j == len(new), (path, 'unexpected list length change')
        return
    raise AssertionError((path, 'unexpected change', repr(old)[:150], repr(new)[:150]))


def normalized_css(css):
    return re.sub(r'\s+', ' ', re.sub(r'/\*.*?\*/', '', css, flags=re.S)).strip()


def self_test():
    anchor = lambda text: {'tag': 'a', 'content': text, 'href': '?query=probe'}
    old = [anchor('relieve'), ' ', anchor('d')]
    removed = []
    compare_tree(old, [old[0], old[2]], ('relieve', 'd'), removed)
    assert len(removed) == 1
    bad_cases = [
        ([anchor('model'), ' ', anchor('kits')], [anchor('model'), anchor('kits')], ('relieve', 'd')),
        (old, [old[0], anchor('days')], ('relieve', 'd')),
        ({'tag': 'span', 'content': 'text'}, {'tag': 'div', 'content': 'text'}, ('relieve', 'd')),
    ]
    for before, after, pair in bad_cases:
        try:
            compare_tree(before, after, pair, [])
        except AssertionError:
            continue
        raise AssertionError('Comparator accepted an unrelated change')
    assert APOSTROPHE != '?' and ord(APOSTROPHE) == 0x2019


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / 'yomitan_fixed/2026-09-14-n1-n3')
    parser.add_argument('--output', type=Path, default=HERE / 'results/fixes/full_comparison.json')
    args = parser.parse_args()
    assert args.output.resolve().is_relative_to((HERE / 'results').resolve())
    self_test()
    source_hash = digest(ROOT / 'converter/ldoce2yomitan.py')
    result = {'converter_sha256': source_hash, 'comparator_controls_passed': True, 'packages': []}
    for mode, suffix in [('bilingual', ''), ('mono', '_EN')]:
        manifest = json.loads((args.root / mode / 'build_manifest.json').read_text(encoding='utf-8'))
        assert manifest['exit_code'] == 0 and manifest['source_unchanged_during_build']
        assert manifest['converter_sha256'] == source_hash, 'Stale build manifest'
        assert len(manifest['packages']) == 1
        package = Path(manifest['packages'][0]['path'])
        assert digest(package) == manifest['packages'][0]['sha256']
        baseline = ROOT / f'yomitan_full/LDOCE5pp_Yomitan_2026.09.13{suffix}.zip'
        assert digest(baseline) == BASE_SHA[mode], 'Baseline changed'
        stats = Counter()
        changes = []
        with zipfile.ZipFile(baseline) as old_zip, zipfile.ZipFile(package) as new_zip:
            assert set(old_zip.namelist()) == set(new_zip.namelist())
            assert len(new_zip.namelist()) == len(set(new_zip.namelist()))
            old_index = json.loads(old_zip.read('index.json'))
            new_index = json.loads(new_zip.read('index.json'))
            old_revision, new_revision = old_index.pop('revision'), new_index.pop('revision')
            assert old_index == new_index
            old_css = old_zip.read('styles.css').decode('utf-8')
            new_css = new_zip.read('styles.css').decode('utf-8')
            marker = 'color:var(--text-color,#202124);'
            assert old_css.count(marker) == 1
            expected_css = old_css.replace(marker, 'color:var(--text-color,inherit);')
            assert normalized_css(new_css) == normalized_css(expected_css), 'Unexpected CSS edit'
            assert new_css == C.generate_css(), 'Package CSS does not match current source'
            for name in old_zip.namelist():
                if name not in ('index.json', 'styles.css') and not re.fullmatch(r'term_bank_\d+\.json', name):
                    assert old_zip.read(name) == new_zip.read(name), ('Auxiliary file changed', name)
                if mode == 'mono':
                    assert not CJK.search(new_zip.read(name).decode('utf-8')), ('CJK leak', name)
            banks = sorted((n for n in old_zip.namelist() if re.fullmatch(r'term_bank_\d+\.json', n)), key=lambda n:int(re.search(r'\d+', n)[0]))
            for name in banks:
                before = json.loads(old_zip.read(name))
                after = json.loads(new_zip.read(name))
                assert len(before) == len(after)
                stats['term_banks'] += 1
                for old, new in zip(before, after):
                    assert len(old) == len(new) == 8
                    assert all(old[i] == new[i] for i in (0, 1, 2, 3, 4, 6, 7)), ('Row fields changed', name, old[0])
                    assert new[6] == stats['rows']
                    stats['rows'] += 1
                    stats['content_rows' if old[4] > 0 else 'alias_rows'] += 1
                    if old[5] == new[5]:
                        continue
                    assert old[4] > 0 and old[0] in REPAIRS, ('Unexpected changed row', old[0], old[6])
                    pair = REPAIRS[old[0]]
                    removed = []
                    compare_tree(old[5], new[5], pair, removed)
                    before_text, after_text = flat(old[5]), flat(new[5])
                    broken, corrected = pair[0] + ' ' + pair[1], ''.join(pair)
                    expected_count = before_text.count(broken)
                    assert expected_count > 0 and len(removed) == expected_count
                    assert before_text.replace(broken, corrected) == after_text
                    assert broken not in after_text
                    stats['spaces_removed'] += len(removed)
                    changes.append({'word': old[0], 'sequence': old[6], 'spaces_removed': len(removed), 'paths': removed})
                print(mode, name, stats['rows'], flush=True)
            assert stats['rows'] == 245933 and stats['content_rows'] == 64659 and stats['alias_rows'] == 181274
            assert len(changes) == len(REPAIRS) and {c['word'] for c in changes} == REPAIRS.keys()
        result['packages'].append({'mode': mode, 'path': str(package), 'sha256': digest(package), 'bytes': package.stat().st_size,
                                   'baseline_sha256': BASE_SHA[mode], 'revisions': [old_revision, new_revision],
                                   'stats': dict(stats), 'changes': changes})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(mode, 'ONLY reviewed changes:', dict(stats), flush=True)
    assert digest(ROOT / 'converter/ldoce2yomitan.py') == source_hash
    print('Strict full-row and SC-tree comparison passed for both modes.', flush=True)


if __name__ == '__main__':
    main()