"""Controlled, read-only probes for every one of the frozen 149 matching cases.

Fixtures are diagnostic questions, never aliases or training data. Each surface
is verified to be a literal span in its own frozen source example. Compare the
actual sentence, that span, a verb-normalized span and an explicit source form.
"""
import argparse
import csv
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

from benchmark_phrase_source_examples import definitions
from benchmark_phrase_versions import norm, read_package, sha
from probe_fushidicts import Engine


def slot_probe(surface, lemma, source):
    """Keep the original verb token while using the fixture's source arguments.

    Only a verified one-token verb replacement is reversible this way. Complex
    contractions and passive frames require their own explicitly labeled group.
    """
    a,b,c = surface.split(),lemma.split(),source.split()
    if norm(surface)==norm(lemma): return source
    if a[1:]==b[1:] and b and c and norm(b[0])==norm(c[0]):
        return ' '.join([a[0],*c[1:]])
    return None


def classify(original, surface, lemma, slots, source, verb_changed, difference):
    if original: return 'resolved_by_dictionary_rules'
    if surface: return 'sentence_context_or_scan'
    if not source: return 'source_choice_or_probe_needs_review'
    if lemma: return 'verb_form_matching'
    if difference.startswith('passive'): return 'passive_argument_matching'
    if slots: return 'argument_or_possessive_matching'
    if slots is None: return 'negation_or_sentence_frame_matching'
    if verb_changed: return 'verb_and_argument_matching'
    return 'argument_or_possessive_matching'


def probe(engine, query, accepted, scan_words=False):
    positions = sorted({0}|{m.start() for m in re.finditer(r'(?<!\w)[\w$\u00a3\u20ac]', query)}) if scan_words else [0]
    found = None; actual = []
    for pos in positions:
        rows = engine.lookup(query[pos:],128)
        actual.append(dict(offset=pos, rows=rows))
        correct = [r for r in rows if norm(r['expression']) in accepted and len(r['matched'].split())>=2]
        if correct:
            found = dict(correct[0], offset=pos); break
    return dict(query=query, found=found, actual=actual)


def source_choice_experiment(package, path, cases):
    """Isolated fixture aliases test whether expanding a source choice suffices."""
    keys = set(); maximum = -1; last = 0
    with zipfile.ZipFile(package) as src, zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            data = src.read(name)
            if re.fullmatch(r'term_bank_\d+\.json',name):
                last=max(last,int(re.search(r'\d+',name)[0]))
                for row in json.loads(data):
                    keys.add(row[0]);maximum=max(maximum,row[6])
            elif name=='index.json':
                index=json.loads(data);index['title']+=' SOURCE CHOICE EXPERIMENT ONLY'
                data=json.dumps(index).encode()
            dst.writestr(name,data)
        rows=[]
        for case in cases:
            key=case['probes']['source']['query']
            assert key not in keys, ('A protected source key already exists', key)
            rows.append([key,'','non-lemma','',-10,[[case['target'],['redirect']]],maximum+len(rows)+1,''])
        dst.writestr(f'term_bank_{last+1}.json',json.dumps(rows).encode())


def main():
    ap = argparse.ArgumentParser()
    for key in ('baseline', 'candidate', 'dll', 'transforms', 'output'):
        ap.add_argument('--'+key, required=True)
    args = ap.parse_args()
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    path = Path(__file__).with_name('remaining_matching_probes.tsv')
    fixtures = list(csv.DictReader(path.open(encoding='utf8'), delimiter='\t'))
    frozen = json.loads((Path(args.baseline).parent/'validation/remaining_179_recheck.json').read_text(encoding='utf8'))
    cases = {c['sample_id']:c for c in frozen['cases'] if c['category']=='matching_candidate_not_fully_located'}
    assert len(fixtures) == len(cases) == 149
    assert {r['sample_id'] for r in fixtures} == set(cases)
    old, _, _ = read_package(args.baseline)
    new, _, _ = read_package(args.candidate)
    actual_defs = {key:set(definitions(row[5])) for key,row in new.items()}
    engine = Engine(args.dll, args.candidate, out/'import_candidate',
                    [Path(args.transforms)/n for n in ('en.json','en_irregular.json')])
    results = []; accepted_for = {}
    try:
        for fixture in fixtures:
            case = cases[fixture['sample_id']]
            assert norm(fixture['surface']) in norm(case['sentence']), fixture
            expected = set(definitions(old[case['target']][5]))
            accepted = {norm(case['target'])}
            if expected and any(len(d.split()) >= 8 for d in expected):
                accepted.update(norm(k) for k,v in actual_defs.items() if expected <= v)
            accepted_for[case['sample_id']] = accepted
            probes = {}
            for label, query in [('original',case['sentence']), ('surface',fixture['surface']),
                                 ('lemma',fixture['lemma_probe']), ('source',fixture['source_probe']),
                                 ('canonical',case['target'])]:
                probes[label] = probe(engine, query, accepted, label=='original')
            slot_query = slot_probe(fixture['surface'], fixture['lemma_probe'], fixture['source_probe'])
            probes['slots'] = probe(engine,slot_query,accepted) if slot_query else dict(query=None,found=None,actual=[])
            flags = {k:bool(v['found']) for k,v in probes.items()}
            category = classify(flags['original'], flags['surface'], flags['lemma'],
                                flags['slots'] if slot_query else None, flags['source'],
                                norm(fixture['surface'])!=norm(fixture['lemma_probe']), fixture['difference_after_lemma'])
            results.append(dict(sample_id=case['sample_id'], target=case['target'],
                                sentence=case['sentence'], category=category,
                                annotated_difference=fixture['difference_after_lemma'], probes=probes))
    finally:
        engine.close()
    missing = [r for r in results if not r['probes']['source']['found']]
    if missing:
        experiment = out/'source_choice_EXPERIMENT_ONLY.zip'
        source_choice_experiment(args.candidate, experiment, missing)
        engine = Engine(args.dll, experiment, out/'import_source_choice_experiment',
                        [Path(args.transforms)/n for n in ('en.json','en_irregular.json')])
        try:
            for row in missing:
                row['source_choice_experiment'] = {
                    label:probe(engine, row['probes'][label]['query'], accepted_for[row['sample_id']], label=='original')
                    for label in ('original','lemma','source')}
                result = row['source_choice_experiment']
                if result['source']['found'] and not result['original']['found']:
                    row['category'] = ('source_choice_and_passive_matching' if row['annotated_difference'].startswith('passive')
                                       else 'source_choice_and_matching')
                elif result['original']['found']:
                    row['category'] = 'source_choice_dictionary_gap'
        finally:
            engine.close()
    summary = dict(cases=len(results), counts=dict(Counter(r['category'] for r in results)),
                   candidate_sha256=sha(args.candidate), baseline_sha256=sha(args.baseline),
                   dll_sha256=sha(args.dll), fixture_sha256=sha(path),
                   source_probe_misses=[r['sample_id'] for r in results if not r['probes']['source']['found']],
                   note='Controlled probes locate the retrieval layer, not necessarily a single code defect. Source spelling probes and verb changes are explicit diagnostic fixtures, never production aliases. Expected IDs and full source-definition coverage use frozen r7 target definitions and the existing >=8-word safeguard.',
                   results=results)
    (out/'matching_layers.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    fields=['sample_id','target','sentence','category','annotated_difference','original_hit','surface_hit','lemma_hit','source_hit','canonical_hit','slots_hit']
    with (out/'matching_layers.tsv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,delimiter='\t');writer.writeheader()
        for row in results:
            writer.writerow({**{k:row[k] for k in fields[:5]},**{k+'_hit':bool(v['found']) for k,v in row['probes'].items()}})
    labels = {
        'resolved_by_dictionary_rules':'本次词典规则已修复',
        'verb_form_matching':'动词变了形就查不到',
        'argument_or_possessive_matching':'换代词、所有格或宾语后查不到',
        'verb_and_argument_matching':'动词变形与代词或宾语两层都卡住',
        'passive_argument_matching':'被动句省掉宾语后查不到',
        'source_choice_and_passive_matching':'词典选项未展开，且展开后仍不支持被动省宾语',
        'source_choice_and_matching':'词典选项及其他匹配两层都卡住',
        'source_choice_dictionary_gap':'仍有词典选项入口缺口',
        'sentence_context_or_scan':'独立短语可查，放进原句却查不到',
        'source_choice_or_probe_needs_review':'来源拼写仍需核对',
        'negation_or_sentence_frame_matching':'否定、缩写或整句框架变化后查不到',
    }
    with (out/'matching_layers_zh.tsv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f,delimiter='\t')
        writer.writerow(['样本编号','词典短语','原句','问题表现','只还原动词的查询','只按词典替换参数的查询','按词典形式的查询','原句查回','只还原动词后查回','只替换参数后查回','按词典形式查回'])
        for row in results:
            p=row['probes']
            writer.writerow([row['sample_id'],row['target'],row['sentence'],labels[row['category']],
                             p['lemma']['query'],p['slots']['query'],p['source']['query'],
                             *['是' if p[k]['found'] else '否' for k in ('original','lemma','slots','source')]])
    print(json.dumps({k:v for k,v in summary.items() if k!='results'},ensure_ascii=True))


if __name__ == '__main__': main()
