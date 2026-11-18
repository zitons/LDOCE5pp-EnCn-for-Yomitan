"""Compare source repairs and recheck the frozen 179 residual examples natively."""
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

from benchmark_phrase_source_examples import definitions
from benchmark_phrase_versions import norm, read_package, sha
from probe_fushidicts import Engine


def main():
    ap = argparse.ArgumentParser()
    for key in ('baseline', 'candidate', 'dll', 'transforms'):
        ap.add_argument('--'+key, required=True)
    args = ap.parse_args()
    old, old_aliases, _ = read_package(args.baseline)
    new, new_aliases, _ = read_package(args.candidate)
    base = Path(args.baseline).parent
    out = Path(args.candidate).parent/'validation'
    out.mkdir(exist_ok=True)
    changed = []
    for key in old:
        before, after = set(definitions(old[key][5])), set(definitions(new[key][5]))
        if before != after:
            changed.append(dict(phrase=key, before=len(before), after=len(after),
                                added=sorted(after-before), removed=sorted(before-after)))
    alias_changes = [dict(alias=k, old_targets=sorted(old_aliases.get(k, set())),
                          targets=sorted(v), added_targets=sorted(v-old_aliases.get(k, set())))
                     for k,v in new_aliases.items() if v != old_aliases.get(k, set())]
    (out/'source_body_changes.json').write_text(json.dumps(changed, ensure_ascii=False, indent=2), encoding='utf8')
    (out/'alias_changes.json').write_text(json.dumps(alias_changes, ensure_ascii=False, indent=2), encoding='utf8')
    cases = list(csv.DictReader((base/'diagnosis/corrected_remaining_179.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    candidate_defs = {key:set(definitions(row[5])) for key,row in new.items()}
    engine = Engine(args.dll, args.candidate, out/'import_candidate',
                    [Path(args.transforms)/n for n in ('en.json','en_irregular.json')])
    checked = []
    target_misses = []
    try:
        for change in alias_changes:
            key = change['alias']
            rows = engine.lookup(key, max(128, len(key)))
            actual = {norm(r['expression']) for r in rows if norm(r['matched']) == norm(key)}
            missing = {norm(t) for t in change['targets']} - actual
            if missing:
                target_misses.append(dict(alias=key, missing=sorted(missing), actual=rows))
        for case in cases:
            expected = set(definitions(old[case['target']][5]))
            strict_ids = {norm(case['target'])}
            sense_ids = set(strict_ids)
            if expected:
                for key, defs in candidate_defs.items():
                    if expected <= defs:
                        sense_ids.add(norm(key))
                        if any(len(d.split()) >= 8 for d in expected):
                            strict_ids.add(norm(key))
            text = case['sentence']
            strict = sense = None
            for pos in sorted({0}|{m.start() for m in re.finditer(r'(?<!\w)[\w$\u00a3\u20ac]', text)}):
                rows = engine.lookup(text[pos:],128)
                for row in rows:
                    if len(row['matched'].split()) < 2:
                        continue
                    evidence = dict(row, offset=pos)
                    if strict is None and norm(row['expression']) in strict_ids:
                        strict = evidence
                    if sense is None and norm(row['expression']) in sense_ids:
                        sense = evidence
                if strict:
                    break
            checked.append(dict(case, strict_found=strict, complete_source_sense_found=sense))
    finally:
        engine.close()
    summary = dict(baseline_sha256=sha(args.baseline), candidate_sha256=sha(args.candidate),
                   changed_definition_cards=len(changed),
                   source_definitions_added=sum(len(c['added']) for c in changed),
                   source_definitions_removed=sum(len(c['removed']) for c in changed),
                   new_aliases=len(set(new_aliases)-set(old_aliases)),
                   expanded_existing_aliases=sum(k in old_aliases and v != old_aliases[k] for k,v in new_aliases.items()),
                   added_target_pairs=sum(len(v-old_aliases.get(k,set())) for k,v in new_aliases.items()),
                   changed_aliases_all_targets_checked=len(alias_changes),
                   changed_aliases_missing_targets=target_misses,
                   residual_strict_hits=sum(bool(c['strict_found']) for c in checked),
                   diagnosed_dictionary_cases=len([c for c in checked if c['category']=='dictionary_can_address']),
                   diagnosed_dictionary_cases_repaired=sum(c['category']=='dictionary_can_address' and bool(c['complete_source_sense_found']) for c in checked),
                   unresolved_dictionary_cases=[c['sample_id'] for c in checked if c['category']=='dictionary_can_address' and not c['complete_source_sense_found']],
                   prior_categories=dict(Counter(c['category'] for c in checked)),
                   note='179 residual cases are frozen from r6. Strict scoring uses frozen target definitions and the >=8-word safeguard, evaluated against actual candidate bodies. Complete-source-sense evidence also permits shorter exact definitions; this supplementary evidence is not added to the independent benchmark scores.',
                   cases=checked)
    (out/'remaining_179_recheck.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2),encoding='utf8')
    assert not target_misses, 'A repaired alias does not return every source target; see remaining_179_recheck.json'
    print(json.dumps({k:v for k,v in summary.items() if k!='cases'},ensure_ascii=True))


if __name__ == '__main__':
    main()
