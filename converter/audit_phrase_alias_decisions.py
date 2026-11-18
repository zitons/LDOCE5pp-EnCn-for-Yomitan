"""Inventory kept heads, provably redundant old keys, and unresolved old expansion.

Redundancy is measured against frozen r5 full-span target results, not guessed
from a spelling. Natural-language validity and rank equivalence are not implied.
"""
import argparse
import csv
import gzip
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from benchmark_phrase_versions import family, norm, read_package, sha


def write(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter='\t')
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    for arg in ('r4', 'r5', 'r6', 'benchmark', 'output'):
        ap.add_argument('--'+arg, required=True)
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    _, a4, rules4 = read_package(args.r4)
    _, a5, _ = read_package(args.r5)
    _, a6, rules6 = read_package(args.r6)
    benchmark = Path(args.benchmark)
    manifest = json.loads((benchmark/'manifest.json').read_text(encoding='utf8'))
    assert sha(args.r4) == manifest['packages']['r4']['sha256']
    assert sha(args.r5) == manifest['packages']['r5']['sha256']
    assert sha(benchmark/'cases.jsonl.gz') == manifest['cases_sha256']
    removed_cases = {}
    negative = set()
    with gzip.open(benchmark/'cases.jsonl.gz', 'rt', encoding='utf8') as f:
        for line in f:
            case = json.loads(line)
            if case['group'] == 'removed_alias':
                removed_cases[case['id']] = case
            if case['group'] == 'negative_control':
                negative.add(norm(case['query']))
    redundant = set()
    partial = set()
    with gzip.open(benchmark/'results.jsonl.gz', 'rt', encoding='utf8') as f:
        for line in f:
            if '"scan": "128"' not in line:
                continue
            row = json.loads(line)
            case = removed_cases.get(row['id'])
            if not case:
                continue
            covered = {norm(t) for t in row['r5']['correct_targets']}
            expected = {norm(t) for t in case['targets']}
            if expected <= covered:
                redundant.add(case['query'])
            elif covered:
                partial.add(case['query'])
    counts = Counter()
    families = defaultdict(Counter)
    nonrestored = []
    for key in sorted(set(a4)-set(a6)):
        category = ('negative_control_bad' if norm(key) in negative else
                    'engine_redundant_all_targets' if key in redundant else
                    'partial_target_coverage_review' if key in partial else
                    'unresolved_not_restored')
        counts[category] += 1
        fam = family(rules4[key])
        families[category][fam] += 1
        nonrestored.append({'alias': key, 'targets': json.dumps(sorted(a4[key]), ensure_ascii=False),
                            'classification': category, 'rule_family': fam,
                            'rules': ','.join(sorted(rules4[key]))})
    fields = ['alias', 'targets', 'classification', 'rule_family', 'rules']
    write(out/'not_restored_aliases.tsv', nonrestored, fields)
    write(out/'redundant_aliases.tsv', [r for r in nonrestored if r['classification']=='engine_redundant_all_targets'], fields)
    write(out/'known_bad_aliases.tsv', [r for r in nonrestored if r['classification']=='negative_control_bad'], fields)
    kept = [{'alias': k, 'targets': json.dumps(sorted(a6[k]), ensure_ascii=False),
             'rules': ','.join(sorted(rules6[k]))} for k in sorted(set(a6)-set(a5))]
    write(out/'restored_lookup_heads.tsv', kept, ['alias', 'targets', 'rules'])
    # These keys can help manual pattern searches. Do not pretend their
    # existence improves ordinary prose matching, and do not delete them blind.
    pattern = [{'alias': k, 'targets': json.dumps(sorted(ts), ensure_ascii=False),
                'rules': ','.join(sorted(rules6[k]))} for k, ts in sorted(a6.items())
               if re.search(r'[/()\u2194]|\b(?:somebody|something|someone|sb|sth|etc|oneself)\b', k, re.I)]
    write(out/'manual_notation_aliases.tsv', pattern, ['alias', 'targets', 'rules'])
    result = {'r4_aliases': len(a4), 'r5_aliases': len(a5), 'r6_aliases': len(a6),
              'new_bounded_heads': len(kept), 'not_restored': len(nonrestored),
              'classification': dict(counts), 'by_family': {k: dict(v) for k,v in families.items()},
              'manual_notation_aliases': len(pattern),
              'interpretation': 'Only engine_redundant_all_targets is measured no-need-to-restore at scan128. Not a proof of grammatical validity or equal rank. Unresolved old expansions are not all useless or all engine bugs. Manual notation aliases retained for typed pattern searches.',
              'packages_sha256': {v: sha(getattr(args,v)) for v in ('r4','r5','r6')}}
    (out/'alias_decisions.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
