"""Isolated counterfactual: bounded lemma entrances, never surface-form enumeration.

Does not change production packages, extraction databases, or generator rules.
"""
import argparse
import csv
import gzip
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from benchmark_phrase_versions import norm, sha, judge
from probe_fushidicts import Engine


OBJECT = r"(?:somebody|something|someone|sb|sth)(?:/(?:somebody|something|someone|sb|sth))*"
PARTICLES = set('away back down in off on out over round through together up aside apart along around under'.split())


def entrances(form):
    """Drop a terminal object slot or leading copula; keep all lexical words."""
    result = defaultdict(set)
    forms = {form}
    if form.startswith('be '):
        forms.add(form[3:])
        result[form[3:]].add('initial_be_lookup_head')
    for value in forms:
        shorter = re.sub(r'\s+' + OBJECT + r'$', '', value)
        if shorter != value:
            result[shorter].add('terminal_object_lookup_head')
    return result


def usable(key):
    return len(key.split()) >= 2 and not re.search(
        r'[/()\u2194]|\b(?:somebody|something|someone|sb|sth|etc|oneself)\b', key, re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--benchmark', required=True)
    ap.add_argument('--transforms', required=True)
    args = ap.parse_args()
    root = Path(args.benchmark)
    out = root / 'responsibility_audit'
    out.mkdir(exist_ok=True)
    frozen = json.loads((root/'manifest.json').read_text(encoding='utf8'))
    source = json.loads((root/'independent_source_definition_coverage/report.json').read_text(encoding='utf8'))
    package = Path(frozen['packages']['r5']['path'])
    for spec in [*frozen['packages'].values(), frozen['dll']]:
        assert sha(spec['path']) == spec['sha256'], spec
    for name, digest in frozen['transforms'].items():
        assert sha(Path(args.transforms)/name) == digest
    rows = []
    with zipfile.ZipFile(package) as z:
        for name in z.namelist():
            if re.fullmatch(r'term_bank_\d+\.json', name):
                rows.extend(json.loads(z.read(name)))
    existing = {norm(r[0]) for r in rows}
    evidence = defaultdict(lambda: defaultdict(list))

    def add(key, target, rule, base):
        key = ' '.join(key.split())
        if usable(key) and norm(key) not in existing:
            item = {'rule': rule, 'source': base}
            if item not in evidence[key][target]:
                evidence[key][target].append(item)

    # Only frozen r5 lemma spellings/retained source aliases; no r4 deletions
    # and no sample text are inputs to the proposal generation.
    for row in rows:
        targets = [row[0]] if row[2] in {'phrase', 'phrase-reference'} else (
            [g[0] for g in row[5]] if row[2] == 'non-lemma' else [])
        for key, rules in entrances(row[0]).items():
            for target in targets:
                for rule in rules:
                    add(key, target, rule, row[0])
    # Internal slots may move only with explicit source separability evidence.
    evidence_path = Path(frozen['packages']['r4']['path']).parent/'evidence.tsv'
    for row in csv.DictReader(evidence_path.open(encoding='utf-8-sig'), delimiter='\t'):
        if row['source'] != 'phrvbhwd':
            continue
        m = re.fullmatch(r'(\w+)\s+' + OBJECT + r'\s*\u2194\s*(\w+)', row['phrase_raw'])
        if m and m[2] in PARTICLES:
            add(m[1]+' '+m[2], row['phrase'], 'explicit_separable_phrasal_head', row['phrase_raw'])
    # Lowercase lookup variants are orthographic indexing, not pronoun expansion.
    for key, targets in list(evidence.items()):
        if key.lower() != key:
            for target, reasons in targets.items():
                for reason in reasons:
                    add(key.lower(), target, reason['rule'], reason['source'])
    additions = [[key, '', 'non-lemma', '', 0,
                  [[target, ['redirect']] for target in sorted(targets)], 0, '']
                 for key, targets in sorted(evidence.items())]
    trial = out/'r5_bounded_heads_EXPERIMENT_ONLY.zip'
    with zipfile.ZipFile(package) as zin, zipfile.ZipFile(trial, 'w', zipfile.ZIP_DEFLATED) as zout:
        last = max(int(re.search(r'\d+', n)[0]) for n in zin.namelist() if re.fullmatch(r'term_bank_\d+\.json', n))
        for name in zin.namelist():
            data = zin.read(name)
            if name == 'index.json':
                index = json.loads(data)
                index['title'] += ' RESPONSIBILITY EXPERIMENT ONLY'
                data = json.dumps(index, ensure_ascii=False).encode()
            zout.writestr(name, data)
        for i in range(0, len(additions), 10000):
            zout.writestr(f'term_bank_{last+1+i//10000}.json', json.dumps(additions[i:i+10000], ensure_ascii=False))
    (out/'entrance_evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf8')
    allowed_evidence = json.loads((root/'independent_source_definition_coverage/definition_coverage_evidence.json').read_text(encoding='utf8'))
    engine = Engine(frozen['dll']['path'], trial, out/'import_trial',
                    [Path(args.transforms)/n for n in ('en.json', 'en_irregular.json')])
    details = []
    totals = Counter()
    try:
        for i, case in enumerate(source['cases']):
            allowed = {norm(case['target'])}
            allowed.update(norm(k) for k in allowed_evidence.get(case['target'], {}).get('accepted_ids', []))
            found = None
            text = case['example']
            positions = sorted({0} | {m.start() for m in re.finditer(r'(?<!\w)[\w$\u00a3\u20ac]', text)})
            for offset in positions:
                actual = engine.lookup(text[offset:], 128)
                correct = [(j+1, r) for j, r in enumerate(actual) if norm(r['expression']) in allowed and len(r['matched'].split()) >= 2]
                if correct:
                    rank, row = correct[0]
                    found = dict(row, offset=offset, rank=rank)
                    break
            old4 = case['results']['r4']['128']
            old5 = case['results']['r5']['128']
            state = ('dictionary_rescued' if found else 'unresolved') if old4 and not old5 else (
                'baseline_retained' if found else 'baseline_lost') if old5 else (
                'new_hit_outside_r4' if found else 'both_originally_missed')
            totals[state] += 1
            detail = dict(case, trial=found, classification=state, sample_id=i)
            if old4 and not old5 and not found:
                # Keep the complete r5 result at the r4 match position for review.
                detail['trial_at_r4_offset'] = engine.lookup(text[old4['offset']:], 128)
            details.append(detail)
            if (i+1) % 500 == 0:
                print(json.dumps({'cases': i+1, 'counts': dict(totals)}), flush=True)
        controls = []
        with gzip.open(root/'cases.jsonl.gz', 'rt', encoding='utf8') as f:
            for line in f:
                case = json.loads(line)
                if case['group'] in {'controlled_positive', 'negative_control'}:
                    controls.append(dict(case, result=judge(engine.lookup(case['query'], 128), case)))
    finally:
        engine.close()
    report = {'experiment': 'r5 plus bounded lookup heads only; not a release or general accuracy proof',
              'rules': ['initial_be_lookup_head', 'terminal_object_lookup_head', 'explicit_separable_phrasal_head'],
              'additions': len(additions), 'alias_target_pairs': sum(len(t) for t in evidence.values()),
              'sample': len(details), 'counts': dict(totals),
              'hit': sum(x['trial'] is not None for x in details),
              'controls': {g: {'cases': sum(x['group']==g for x in controls),
                              'target_hit': sum(x['group']==g and x['result']['hit'] for x in controls)}
                           for g in ('controlled_positive', 'negative_control')},
              'hashes': {'trial': sha(trial), 'r5': sha(package), 'dll': sha(frozen['dll']['path']),
                         'source_report': sha(root/'independent_source_definition_coverage/report.json'),
                         'evidence_tsv': sha(evidence_path), 'script': sha(__file__)},
              'cases': details, 'control_details': controls}
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'cases', 'control_details'}}, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
