"""Carry forward reviewed triage, rechecking the released package's actual output."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from benchmark_phrase_versions import sha
from probe_fushidicts import Engine


def main():
    ap = argparse.ArgumentParser()
    for name in ('build', 'benchmark', 'dll', 'transforms'):
        ap.add_argument('--'+name, required=True)
    args = ap.parse_args()
    build = Path(args.build)
    benchmark = Path(args.benchmark)
    previous = json.loads((benchmark/'independent_source_definition_coverage/report.json').read_text(encoding='utf8'))
    current = json.loads((build/'validation/original_source/report.json').read_text(encoding='utf8'))
    assert previous['manifest']['sample_sha256'] == current['manifest']['sample_sha256']
    assert current['manifest']['packages']['r5'] == json.loads((build/'build_report.json').read_text(encoding='utf8'))['sha256']
    decisions = list(csv.DictReader((benchmark/'responsibility_audit/responsibility.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    engine = Engine(args.dll, json.loads((build/'build_report.json').read_text(encoding='utf8'))['package'],
                    build/'validation/import_candidate',
                    [Path(args.transforms)/n for n in ('en.json', 'en_irregular.json')])
    exported = []
    try:
        for item in decisions:
            if item['classification'] == 'dictionary_measured_rescue':
                continue
            i = int(item['sample_id'])
            case = current['cases'][i]
            old = previous['cases'][i]['results']['r4']['128']
            assert case['target'] == item['target']
            assert not case['results']['r5']['128'], item
            offset = old['offset']
            actual = engine.lookup(case['example'][offset:], 128)
            exported.append(dict(item, r6_query=case['example'][offset:],
                                 r6_actual=json.dumps(actual, ensure_ascii=False)))
    finally:
        engine.close()
    dest = build/'fushi_handover'
    dest.mkdir(exist_ok=True)
    for name, rows in [
        ('engine_candidates.tsv', [r for r in exported if r['classification']=='engine_capability_candidate']),
        ('dictionary_notation_candidates.tsv', [r for r in exported if r['classification']=='dictionary_notation_candidate']),
        ('sense_or_scoring_review.tsv', [r for r in exported if r['classification']=='sense_or_scoring_review'])]:
        with (dest/name).open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(exported[0]), delimiter='\t')
            w.writeheader()
            w.writerows(rows)
    report = {'candidate_sha256': current['manifest']['packages']['r5'],
              'dll_sha256': sha(args.dll), 'counts': dict(Counter(r['classification'] for r in exported)),
              'notice': '154 engine capability candidates, 3 dictionary notation candidates and 22 scoring/sense review cases; not 179 proven engine bugs. r6 outputs re-queried at original r4 match positions. No engine source changed.'}
    (dest/'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
