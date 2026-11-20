"""Diagnostic packages only: localize dictionary routing vs engine matching.

Never edits the release package or production generation rules. Source-heading
core extraction below is an experiment, not an adopted grammar rule.
"""
import argparse
import csv
import json
import re
import sqlite3
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from benchmark_phrase_versions import norm, read_package, sha
from benchmark_phrase_source_examples import definitions
from phrase_lookup_heads import OBJECT, PARTICLES, usable
from probe_fushidicts import Engine


def main():
    ap = argparse.ArgumentParser()
    for arg in ('build', 'benchmark', 'dll', 'transforms'):
        ap.add_argument('--'+arg, required=True)
    ap.add_argument('--stage', action='append', choices=['source_heads_and_merge', 'also_allow_content_collision', 'also_source_variants', 'also_source_bodies', 'general_phrv_heads_and_bodies'])
    args = ap.parse_args()
    build, benchmark = Path(args.build), Path(args.benchmark)
    package = Path(json.loads((build/'build_report.json').read_text(encoding='utf8'))['package'])
    out = build/'diagnosis'
    out.mkdir(exist_ok=True)
    bodies, aliases, _ = read_package(package)
    original = json.loads((benchmark/'independent_source_definition_coverage/report.json').read_text(encoding='utf8'))
    allowed_evidence = json.loads((benchmark/'independent_source_definition_coverage/definition_coverage_evidence.json').read_text(encoding='utf8'))
    review = list(csv.DictReader((benchmark/'responsibility_audit/responsibility.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    remaining = [r for r in review if r['classification']!='dictionary_measured_rescue']
    proposals = defaultdict(set)
    general_proposals = defaultdict(set)
    sources = defaultdict(list)
    for row in csv.DictReader((build/'evidence.tsv').open(encoding='utf-8-sig'), delimiter='\t'):
        if row['source'] != 'phrvbhwd':
            continue
        raw = row['phrase_raw']
        general = ' '.join(re.sub(r"(?<![\w'\u2019])"+OBJECT+r"(?![\w'\u2019])", '', raw).replace('\u2194',' ').split()).lower()
        if usable(general) and norm(general)!=norm(row['phrase']):
            general_proposals[general].add(row['phrase'])
        m = re.fullmatch(r'(\w+)\s+' + OBJECT + r'\s*(?:\u2194\s*)?(\w+)(?:\s+' + OBJECT + r')?', raw)
        if m and m[2] in PARTICLES:
            key = (m[1]+' '+m[2]).lower()
            proposals[key].add(row['phrase'])
            sources[key].append({'raw': raw, 'target': row['phrase'], 'record_id': row['record_id'], 'xpath': row['xpath']})
    # Explicit source spellings, used solely to establish that normalization
    # would work. No general slash parser is adopted by this diagnostic.
    variants = {'tarred with the same brush': {'be/get tarred with the same brush'},
                'interested party': {'interested party/group'},
                'simplicity itself': {'be patience/kindness/simplicity etc itself'}}
    report = {'release_sha256': sha(package), 'source_rule_is_experimental': True,
              'heading_evidence': dict(sources), 'manual_source_variant_fixtures': {k:sorted(v) for k,v in variants.items()},
              'versions': {}}
    if (out/'diagnosis.json').exists():
        prior=json.loads((out/'diagnosis.json').read_text(encoding='utf8'))
        assert prior['release_sha256']==sha(package)
        report['versions']=prior['versions']
    repairs=defaultdict(list)
    db=sqlite3.connect('file:'+str(build/'extraction.sqlite')+'?mode=ro',uri=True)
    for key,body in db.execute("SELECT phrase,body FROM occurrences WHERE kind='phrvbhwd' AND phrase IN ('put out','cut up','lie down')"):
        if body: repairs[key].append(json.loads(body))
    db.close()
    for stage in (args.stage or ['source_heads_and_merge', 'also_allow_content_collision', 'also_source_variants', 'also_source_bodies', 'general_phrv_heads_and_bodies']):
        mapping = {k:set(v) for k,v in aliases.items()}
        for key, targets in (general_proposals if stage=='general_phrv_heads_and_bodies' else proposals).items():
            if key not in bodies or stage != 'source_heads_and_merge':
                mapping.setdefault(key, set()).update(targets)
        if stage in {'also_source_variants','also_source_bodies','general_phrv_heads_and_bodies'}:
            for key, targets in variants.items():
                mapping.setdefault(key, set()).update(targets)
        path = out/(stage+'_EXPERIMENT_ONLY.zip')
        modified = {k:sorted(v) for k,v in mapping.items() if v != aliases.get(k,set())}
        with zipfile.ZipFile(package) as zin, zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zout:
            last = max(int(re.search(r'\d+', n)[0]) for n in zin.namelist() if re.fullmatch(r'term_bank_\d+\.json', n))
            seq = 1000000
            for name in zin.namelist():
                data = zin.read(name)
                if re.fullmatch(r'term_bank_\d+\.json', name):
                    rows = json.loads(data)
                    for row in rows:
                        if row[2]=='non-lemma' and row[0] in modified:
                            row[5] = [[t,['redirect']] for t in modified[row[0]]]
                        elif stage in {'also_source_bodies','general_phrv_heads_and_bodies'} and row[2] in {'phrase','phrase-reference'}:
                            row[5].extend({'type':'structured-content','content':body} for body in repairs.get(row[0],[]))
                    data = json.dumps(rows, ensure_ascii=False).encode()
                elif name == 'index.json':
                    index = json.loads(data)
                    index['title'] += ' DIAGNOSIS '+stage
                    data = json.dumps(index).encode()
                zout.writestr(name, data)
            extra = []
            for key, targets in sorted(modified.items()):
                if key not in aliases:
                    extra.append([key,'','non-lemma','',-10,[[t,['redirect']] for t in targets],seq,''])
                    seq += 1
            zout.writestr(f'term_bank_{last+1}.json', json.dumps(extra, ensure_ascii=False))
        engine = Engine(args.dll, path, out/('import_'+stage),
                        [Path(args.transforms)/n for n in ('en.json','en_irregular.json')])
        results = []
        try:
            for decision in remaining:
                case = original['cases'][int(decision['sample_id'])]
                allowed = {norm(case['target'])}
                allowed.update(norm(t) for t in allowed_evidence.get(case['target'],{}).get('accepted_ids',[]))
                if stage in {'also_source_bodies','general_phrv_heads_and_bodies'}:
                    target_defs=set(definitions(bodies[case['target']][5]))
                    if target_defs and any(len(d.split())>=8 for d in target_defs):
                        for key,extra_bodies in repairs.items():
                            repaired=set(definitions(bodies[key][5]))
                            repaired.update(d for body in extra_bodies for d in definitions(body))
                            if target_defs<=repaired: allowed.add(norm(key))
                found = None
                text = case['example']
                for offset in sorted({0}|{m.start() for m in re.finditer(r'(?<!\w)[\w$\u00a3\u20ac]',text)}):
                    rows = engine.lookup(text[offset:],128)
                    good = [r for r in rows if norm(r['expression']) in allowed and len(r['matched'].split())>=2]
                    if good:
                        found = dict(good[0],offset=offset)
                        break
                results.append({'sample_id':decision['sample_id'],'prior_classification':decision['classification'],
                                'target':case['target'],'example':text,'found':found})
            probes = {q: engine.lookup(q,128) for q in ['put you out','put out','made good','make good',
                       'out of my depth','out of your depth','give me a shout','give somebody a shout',
                       'being to do something','red-handed']}
        finally:
            engine.close()
        summary = {'changed_alias_keys':len(modified), 'extra_rows':len(extra),
                   'recovered':sum(bool(r['found']) for r in results),
                   'recovered_by_prior_classification':dict(Counter(r['prior_classification'] for r in results if r['found'])),
                   'cases':results,'probes':probes,'package_sha256':sha(path)}
        report['versions'][stage] = summary
        print(json.dumps({'stage':stage,**{k:v for k,v in summary.items() if k not in {'cases','probes'}}}),flush=True)
    assert sha(package)==report['release_sha256']
    (out/'diagnosis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':
    main()
