"""Export reproducible triage; never turn residual benchmark misses into proven bugs."""
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from benchmark_phrase_versions import norm, sha


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--benchmark', required=True)
    args = ap.parse_args()
    root = Path(args.benchmark)
    out = root/'responsibility_audit'
    trial = json.loads((out/'report.json').read_text(encoding='utf8'))
    review_path = Path(__file__).with_name('phrase_responsibility_review.json')
    review = json.loads(review_path.read_text(encoding='utf8'))
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf8'))
    aliases = defaultdict(set)
    path = Path(manifest['packages']['r4']['path']).parent/'aliases.tsv'
    for row in csv.DictReader(path.open(encoding='utf-8-sig'), delimiter='\t'):
        aliases[norm(row['alias']), norm(row['target'])].update(row['rules'].split(','))
    counts = Counter()
    features = Counter()
    spans = Counter()
    rows = []
    for case in trial['cases']:
        old = case['results']['r4']['128']
        if not old or case['results']['r5']['128']:
            continue
        sample_id = str(case['sample_id'])
        if case['trial']:
            group = 'dictionary_measured_rescue'
            new = case['trial']
            a, b = norm(old['matched']), norm(new['matched'])
            spans['same_span' if old['offset'] == new['offset'] and a == b else
                  'shorter_same_start' if old['offset'] == new['offset'] and a.startswith(b+' ') else
                  'other_span'] += 1
        elif sample_id in review['dictionary_notation_candidates']:
            assert case['target'] == review['dictionary_notation_candidates'][sample_id]
            group = 'dictionary_notation_candidate'
        elif sample_id in review['scoring_or_sense_review']:
            assert case['target'] == review['scoring_or_sense_review'][sample_id]
            group = 'sense_or_scoring_review'
        else:
            group = 'engine_capability_candidate'
        rules = sorted(aliases[norm(old['matched']), norm(old['expression'])])
        feature = ''
        if group == 'engine_capability_candidate':
            feature = 'slot_or_argument_pattern' if re.search(
                r"\b(?:somebody|something|someone|your|yourself|sb|sth)\b", case['target'], re.I
            ) else 'fixed_phrase_inflection'
            features[feature] += 1
        counts[group] += 1
        rows.append({'sample_id': case['sample_id'], 'classification': group, 'feature': feature,
                     'target': case['target'], 'source_example': case['example'],
                     'r4_matched': old['matched'], 'r4_expression': old['expression'],
                     'r4_last_step_rules': ','.join(rules),
                     'trial_matched': case['trial']['matched'] if case['trial'] else '',
                     'trial_expression': case['trial']['expression'] if case['trial'] else '',
                     'trial_at_r4_offset': json.dumps(case.get('trial_at_r4_offset', []), ensure_ascii=False)})
    assert len(rows) == 497
    assert counts['dictionary_notation_candidate'] == len(review['dictionary_notation_candidates'])
    assert counts['sense_or_scoring_review'] == len(review['scoring_or_sense_review'])
    with (out/'responsibility.tsv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter='\t')
        w.writeheader()
        w.writerows(rows)
    result = {'denominator': '497 r4-only examples in fixed 2000-source-example sample; definition-coverage proxy, scan 128',
              'counts': dict(counts), 'engine_candidate_features': dict(features),
              'dictionary_rescue_spans_relative_to_r4': dict(spans),
              'trial_total': trial['hit'], 'trial_additions': trial['additions'],
              'manual_review': review, 'review_sha256': sha(review_path),
              'trial_report_sha256': sha(out/'report.json'), 'aliases_sha256': sha(path)}
    (out/'classification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k != 'manual_review'}, ensure_ascii=True))


if __name__ == '__main__':
    main()
