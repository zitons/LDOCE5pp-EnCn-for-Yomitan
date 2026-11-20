"""Export source-sense evidence and corrected residual triage, without releases."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from benchmark_phrase_source_examples import definitions
from benchmark_phrase_versions import read_package, sha
from validate_phrase_release import content_rows
from probe_fushidicts import Engine


def main():
    ap=argparse.ArgumentParser()
    for name in ('build','dll','transforms'):
        ap.add_argument('--'+name,required=True)
    args=ap.parse_args()
    build=Path(args.build);out=build/'diagnosis'
    package=Path(json.loads((build/'build_report.json').read_text(encoding='utf8'))['package'])
    bodies,_,_=read_package(package)
    manual_path=Path(__file__).with_name('remaining_sense_review.json')
    manual=json.loads(manual_path.read_text(encoding='utf8'))
    decisions={key:(category,note) for category,items in manual.items() if isinstance(items,dict) for key,note in items.items()}
    source_rows=list(csv.DictReader((build/'fushi_handover/sense_or_scoring_review.tsv').open(encoding='utf-8-sig'),delimiter='\t'))
    assert len(decisions)==len(source_rows)==22
    evidence=[]
    for row in source_rows:
        key=row['sample_id'];category,note=decisions[key]
        actual=json.loads(row['r6_actual'])
        evidence.append({'sample_id':key,'category':category,'note':note,'target':row['target'],
                         'sentence':row['source_example'],'expected_definitions':list(definitions(bodies[row['target']][5])),
                         'r6_returned_phrase_definitions':{r['expression']:list(definitions(bodies[r['expression']][5])) for r in actual if r['expression'] in bodies}})
    (out/'sense_review_evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8')
    diagnosis=json.loads((out/'diagnosis.json').read_text(encoding='utf8'))
    stage=diagnosis['versions']['general_phrv_heads_and_bodies']
    rows=[]
    for item in stage['cases']:
        key=item['sample_id']
        category=('already_usable_or_scoring' if key in manual['already_correct_in_r6'] or key in manual['scoring_only'] else
                  'dictionary_can_address' if item['found'] or key in manual['dictionary_can_address'] else
                  'matching_candidate_not_fully_located')
        rows.append({'sample_id':key,'category':category,'target':item['target'],'sentence':item['example'],
                     'prior_classification':item['prior_classification'],'diagnostic_match':json.dumps(item['found'],ensure_ascii=False),
                     'manual_note':decisions.get(key,('',''))[1]})
    counts=Counter(r['category'] for r in rows)
    assert len(rows)==179
    assert counts==Counter(dictionary_can_address=23,already_usable_or_scoring=7,matching_candidate_not_fully_located=149)
    with (out/'corrected_remaining_179.tsv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t');w.writeheader();w.writerows(rows)
    # Recheck representative normalized inputs, including actual returned senses.
    probes={}
    for label,path,import_dir in [('r6',package,build/'validation/import_candidate'),
                                  ('diagnostic',out/'general_phrv_heads_and_bodies_EXPERIMENT_ONLY.zip',out/'import_general_phrv_heads_and_bodies')]:
        data=content_rows(path)
        engine=Engine(args.dll,path,import_dir,[Path(args.transforms)/n for n in ('en.json','en_irregular.json')])
        try:
            probes[label]={}
            for query in ['knocked him back several thousand dollars','put you out','red-handed','made good','make good','out of my depth','out of your depth','give me a shout','give somebody a shout']:
                found=engine.lookup(query,128)
                for row in found:
                    record=data.get(row['expression'])
                    row['phrase_definitions']=list(definitions(record[5])) if record and record[2] in {'phrase','phrase-reference'} else []
                probes[label][query]=found
        finally:engine.close()
    (out/'native_probe_evidence.json').write_text(json.dumps(probes,ensure_ascii=False,indent=2),encoding='utf8')
    result={'remaining179':dict(counts),'reviewed22':dict(Counter(x['category'] for x in evidence)),
            'source_sense_shadowing':3,'release_unchanged':sha(package)==diagnosis['release_sha256'],
            'manual_review_sha256':sha(manual_path),
            'notice':'23 dictionary-side feasibility cases include 3 manual source-variant fixtures, not completed general parsing rules. 149 cases are still matching candidates, not 149 proven engine bugs. No production release modified.'}
    assert result['release_unchanged']
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':main()
