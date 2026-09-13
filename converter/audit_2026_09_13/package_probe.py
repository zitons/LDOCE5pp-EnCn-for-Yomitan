"""Read-only re-review of an explicit package; generated evidence stays local.

Run from the repository root:
  venv/Scripts/python.exe -X utf8 -u converter/audit_2026_09_13/package_probe.py
Pass --schema to validate EVERY bank with the local official Yomitan schema.
Does not rebuild or modify the converter or the published ZIP.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
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


def dump(name, data):
    text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    patch.P = str(OUT / name)
    patch.write_atomic(text)
    assert (OUT / name).read_bytes() == text.encode('utf-8')


def flat(n):
    if isinstance(n, str):
        return n
    if isinstance(n, list):
        return ''.join(map(flat, n))
    return flat(n.get('content', '')) if isinstance(n, dict) else ''


def walk(n):
    if isinstance(n, list):
        for c in n:
            yield from walk(c)
    elif isinstance(n, dict):
        yield n
        yield from walk(n.get('content'))


def own_numbers(n):
    # An inner list has its own counters, not those of the outer sense.
    if isinstance(n, list):
        for c in n:
            yield from own_numbers(c)
    elif isinstance(n, dict):
        if n.get('tag') in {'ol', 'ul', 'details'}:
            return
        if 'ld-snum' in (n.get('data', {}).get('class', '').split()):
            yield n
        else:
            yield from own_numbers(n.get('content'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('package', nargs='?', type=Path,
                    default=ROOT / 'yomitan_full/LDOCE5pp_Yomitan_2026.09.12.zip')
    ap.add_argument('--schema', action='store_true')
    ap.add_argument('--schema-banks', type=int, default=None,
                    help='limit official-schema validation to the first N banks; still scan all banks')
    args = ap.parse_args()
    validate = None
    if args.schema:
        import fastjsonschema
        schema = json.loads((ROOT / 'yomitan-ext/data/schemas/dictionary-term-bank-v3-schema.json').read_text(encoding='utf-8'))
        validate = fastjsonschema.compile(schema)
    stats, colors = Counter(), Counter()
    bad_number_words = set()
    examples, schema_errors, sequence_errors = [], [], []
    metadata, samples = defaultdict(list), []
    sample_words = {'a', 'run', 'bad', 'age', 'act', 'about', 'after', 'counter',
                    'down', 'last', 'less', 'max', 'people', 'get', 'back', 'one', 'and'}
    with zipfile.ZipFile(args.package) as z:
        names = z.namelist()
        stats['duplicate_zip_members'] = len(names) - len(set(names))
        css = z.read('styles.css').decode('utf-8')
        stats['css_matches_source'] = int(css == C.generate_css())
        banks = sorted((n for n in names if re.fullmatch(r'term_bank_\d+\.json', n)),
                       key=lambda n: int(re.search(r'\d+', n)[0]))
        for bank_index, bank in enumerate(banks, 1):
            rows = json.loads(z.read(bank))
            if validate is not None and (args.schema_banks is None or bank_index <= args.schema_banks):
                try:
                    validate(rows)
                    stats['schema_rows_passed'] += len(rows)
                except Exception as exc:
                    schema_errors.append({'bank': bank, 'error': str(exc)[:800]})
            for row in rows:
                if row[6] != stats['rows'] and len(sequence_errors) < 10:
                    sequence_errors.append([row[0], row[6], stats['rows']])
                stats['rows'] += 1
                if row[4] <= 0:
                    stats['aliases'] += 1
                    continue
                stats['entries'] += 1
                metadata[row[0]].append([row[2], row[3], row[6]])
                if row[0] in sample_words:
                    samples.append({'word': row[0], 'content': row[5][0]['content']})
                for n in walk(row[5]):
                    cls = n.get('data', {}).get('class', '')
                    style = n.get('style', {})
                    if style.get('color') in {'green', 'DodgerBlue'}:
                        colors[cls + ':' + style['color']] += 1
                    if cls != 'ld-senselist':
                        continue
                    stats['sense_lists'] += 1
                    items = [c for c in n.get('content', []) if isinstance(c, dict) and c.get('tag') == 'li']
                    stats['sense_list_items'] += len(items)
                    described = []
                    mismatch = False
                    for ordinal, item in enumerate(items, 1):
                        nums = list(own_numbers(item))
                        for num in nums:
                            text = flat(num).strip()
                            hidden = str(num.get('style', {}).get('fontSize')) == '0'
                            m = re.fullmatch(r'(\d+)[.)]?', text)
                            if m and hidden:
                                stats['hidden_numeric_chips'] += 1
                                if int(m[1]) != ordinal:
                                    stats['wrong_native_numbers'] += 1
                                    bad_number_words.add(row[0])
                                    mismatch = True
                        described.append({'native': ordinal,
                                          'source': [flat(x).strip() for x in nums],
                                          'hidden': [str(x.get('style', {}).get('fontSize')) == '0' for x in nums],
                                          'text': flat(item)[:120]})
                    if mismatch:
                        stats['lists_with_wrong_numbers'] += 1
                        if len(examples) < 24 or (row[0] in {'run', 'about', 'act'} and len(examples) < 35):
                            examples.append({'word': row[0], 'items': described})
            print(bank, 'rows_so_far=', stats['rows'], 'wrong_native_numbers=', stats['wrong_native_numbers'], flush=True)
    stats['words_with_wrong_numbers'] = len(bad_number_words)
    result = {'package': str(args.package), 'schema_enabled': args.schema,
              'schema_bank_limit': args.schema_banks,
              'package_sha256': hashlib.sha256(args.package.read_bytes()).hexdigest(),
              'converter_sha256': hashlib.sha256((ROOT / 'converter/ldoce2yomitan.py').read_bytes()).hexdigest(),
              'stats': dict(stats), 'inline_colors': dict(colors),
              'schema_errors': schema_errors, 'sequence_errors': sequence_errors,
              'number_examples': examples}
    dump('package_results.json', result)
    dump('entry_metadata.json', metadata)
    dump('sample_payload.json', samples)
    print(json.dumps({'stats': dict(stats), 'inline_colors': dict(colors),
                      'schema_errors': schema_errors, 'sequence_errors': sequence_errors,
                      'first_number_examples': examples[:2]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
