"""Check a bounded-head release against frozen inputs and original native queries."""
import argparse
import gzip
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from benchmark_phrase_versions import judge, norm, read_package, sha
from probe_fushidicts import Engine


def content_rows(package):
    result = {}
    with zipfile.ZipFile(package) as z:
        for name in z.namelist():
            if re.fullmatch(r'term_bank_\d+\.json', name):
                for row in json.loads(z.read(name)):
                    if row[2] != 'non-lemma':
                        result[row[0]] = row
    return result


def main():
    ap = argparse.ArgumentParser()
    for name in ('baseline', 'candidate', 'benchmark', 'dll', 'transforms', 'output'):
        ap.add_argument('--'+name, required=True)
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    b5, a5, _ = read_package(args.baseline)
    b6, a6, rules6 = read_package(args.candidate)
    old_content, new_content = content_rows(args.baseline), content_rows(args.candidate)
    assert old_content == new_content, 'Source entries or contexts changed'
    assert all(a6.get(k) == v for k, v in a5.items()), 'Retained alias targets changed'
    added = set(a6)-set(a5)
    assert len(added) == 4665, len(added)
    expected_rules = {'initial_be_lookup_head', 'terminal_object_lookup_head',
                      'explicit_separable_phrasal_head', 'source_lowercase_lookup'}
    assert all(rules6[k] <= expected_rules for k in added)
    cases = [(g, dict(query=k, span=k, targets=sorted(ts))) for g, mapping in (
        ('canonical', {k: {k} for k in b6}), ('retained_alias', a5),
        ('new_lookup_head', {k: a6[k] for k in sorted(added)})) for k, ts in mapping.items()]
    controls = []
    with gzip.open(Path(args.benchmark)/'cases.jsonl.gz', 'rt', encoding='utf8') as f:
        for line in f:
            case = json.loads(line)
            if case['group'] in {'controlled_positive', 'negative_control'}:
                controls.append(case)
    engine = Engine(args.dll, args.candidate, out/'import_candidate',
                    [Path(args.transforms)/n for n in ('en.json', 'en_irregular.json')])
    counts = Counter()
    misses = []
    try:
        for i, (group, case) in enumerate(cases):
            score = judge(engine.lookup(case['query'], max(128, len(case['query']))), case)
            counts[group+'_cases'] += 1
            counts[group+'_hit'] += score['hit']
            if not score['hit']:
                misses.append(dict(case, group=group, result=score))
            if (i+1) % 20000 == 0:
                print(json.dumps({'cases': i+1, 'misses': len(misses)}), flush=True)
        for case in controls:
            case['candidate_result'] = judge(engine.lookup(case['query'], 128), case)
    finally:
        engine.close()
    report = {'baseline_sha256': sha(args.baseline), 'candidate_sha256': sha(args.candidate),
              'dll_sha256': sha(args.dll), 'source_rows_identical': len(old_content),
              'retained_alias_target_sets_identical': len(a5), 'added_aliases': len(added),
              'scan': 'max(128, query length), full span and frozen canonical target',
              'native': dict(counts), 'misses': misses, 'controls': controls}
    (out/'release_checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    assert not misses, f'{len(misses)} literal-entry regression(s); see release_checks.json'
    print(json.dumps({k:v for k,v in report.items() if k not in {'controls','misses'}}, ensure_ascii=True))


if __name__ == '__main__':
    main()
