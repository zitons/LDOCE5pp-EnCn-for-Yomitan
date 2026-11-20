"""Check a bounded-head release against frozen inputs and original native queries."""
import argparse
import gzip
import json
import re
import sqlite3
import zipfile
from collections import Counter
from pathlib import Path
from benchmark_phrase_versions import judge, norm, read_package, sha
from probe_fushidicts import Engine
from benchmark_phrase_source_examples import definitions
from benchmark_phrase_versions import examples


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
    ap.add_argument('--source-body-repair', action='store_true',
                    help='Allow additive source senses and alias targets; verify source completeness instead')
    ap.add_argument('--source-choice-repair', action='store_true',
                    help='Allow source-example-validated choice keys, with identical source bodies')
    ap.add_argument('--removed-targets', help='Explicit reviewed ledger of incorrect target pairs to remove')
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    b5, a5, _ = read_package(args.baseline)
    b6, a6, rules6 = read_package(args.candidate)
    old_content, new_content = content_rows(args.baseline), content_rows(args.candidate)
    corrections = json.loads(Path(args.removed_targets).read_text(encoding='utf8')) if args.removed_targets else []
    allowed_removed = {(r['alias'],r['target']) for r in corrections}
    actual_removed = {(key,target) for key,targets in a5.items() for target in targets-a6.get(key,set())}
    assert actual_removed == allowed_removed, ('Unreviewed target loss or unapplied correction',actual_removed,allowed_removed)
    if args.source_choice_repair:
        assert old_content == new_content, 'Source-choice repair must not change source content'
    if args.source_body_repair:
        assert old_content.keys() == new_content.keys(), 'Source inventory changed'
        for key, old in old_content.items():
            new = new_content[key]
            if old[2] == 'source-context':
                assert old[5] == new[5], ('Source context changed', key)
            assert set(definitions(old[5])) <= set(definitions(new[5])), ('Lost definitions', key)
            assert set(examples(old[5])) <= set(examples(new[5])), ('Lost examples', key)
        assert set(a5) <= set(a6), 'Retained alias key lost'
        db = sqlite3.connect('file:'+str(Path(args.candidate).parent/'extraction.sqlite')+'?mode=ro', uri=True)
        source_checks = 0
        actual_definitions = {key: set(definitions(row[5])) for key,row in b6.items()}
        for raw, body in db.execute('SELECT phrase, body FROM occurrences WHERE body IS NOT NULL'):
            key = ' '.join(raw.replace('\u2194', ' ').split())
            # Extraction metadata can include excluded thesaurus sections.
            # Compare the actual source body that this build is meant to retain.
            expected = set(definitions(json.loads(body))) if body else set()
            assert expected <= actual_definitions[key], ('Missing source definitions', key, expected-actual_definitions[key])
            source_checks += 1
        db.close()
    else:
        assert old_content == new_content, 'Source entries or contexts changed'
        assert all(a6.get(k) == v for k, v in a5.items()), 'Retained alias targets changed'
    added = set(a6)-set(a5)
    if not args.source_body_repair:
        assert len(added) == 4665, len(added)
    expected_rules = {'initial_be_lookup_head', 'terminal_object_lookup_head',
                      'explicit_separable_phrasal_head', 'source_lowercase_lookup',
                      'source_phrasal_argument_lookup_head'}
    if args.source_choice_repair:
        expected_rules.update({'source_notation', 'source_example_attested',
                               'source_validated_local_choices', 'omit_etc_marker',
                               'placeholder_abbreviation', 'source_phrasal_particle_choices'})
    assert all(rules6[k] <= expected_rules for k in added)
    assert all(target in b6 for targets in a6.values() for target in targets), 'Alias chain or missing target'
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
              'dll_sha256': sha(args.dll), 'source_rows_checked': len(old_content),
              'source_body_repair': args.source_body_repair,
              'source_occurrences_checked': source_checks if args.source_body_repair else None,
              'retained_aliases_checked': len(a5), 'added_aliases': len(added),
              'expanded_aliases': sum(a6[k] != v for k,v in a5.items()),
              'reviewed_removed_target_pairs': corrections,
              'scan': 'max(128, query length), full span and frozen canonical target',
              'native': dict(counts), 'misses': misses, 'controls': controls}
    (out/'release_checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    assert not misses, f'{len(misses)} literal-entry regression(s); see release_checks.json'
    print(json.dumps({k:v for k,v in report.items() if k not in {'controls','misses'}}, ensure_ascii=True))


if __name__ == '__main__':
    main()
