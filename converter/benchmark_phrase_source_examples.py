"""Independent source-example sampling, scanning word starts; no alias-based selection."""
import argparse
import csv
import json
import random
import re
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from benchmark_phrase_versions import plain, examples, norm, sha
from probe_fushidicts import Engine


def definitions(node):
    if isinstance(node,list):
        for x in node: yield from definitions(x)
    elif isinstance(node,dict):
        if node.get('data',{}).get('class')=='l6p-def': yield norm(plain(node)).strip(' .')
        else: yield from definitions(node.get('content',[]))


def main():
    ap=argparse.ArgumentParser()
    for arg in ('r4','r5','dll','transforms','output'):ap.add_argument('--'+arg,required=True)
    ap.add_argument('--sample',type=int,default=2000)
    ap.add_argument('--seed',type=int,default=20261118)
    ap.add_argument('--exclude-sample',help='Frozen sample JSON to exclude for a disjoint holdout')
    ap.add_argument('--allow-source-definition-coverage',action='store_true')
    args=ap.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    pool=[];seen=set();defsets={}
    with zipfile.ZipFile(args.r4) as z:
        for name in z.namelist():
            if not re.fullmatch(r'term_bank_\d+\.json',name):continue
            for row in json.loads(z.read(name)):
                if row[2] not in {'phrase','phrase-reference'}:continue
                defsets[row[0]]=set(definitions(row[5]))
                for text in examples(row[5]):
                    if (row[0],text) not in seen:
                        pool.append({'target':row[0],'example':text});seen.add((row[0],text))
    allowed={key:{norm(key)} for key in defsets}
    evidence={}
    if args.allow_source_definition_coverage:
        inverse=defaultdict(set)
        for key,defs in defsets.items():
            for definition in defs: inverse[definition].add(key)
        for key,defs in defsets.items():
            if not defs or not any(len(d.split())>=8 for d in defs): continue
            containing=set.intersection(*(inverse[d] for d in defs))
            allowed[key].update(norm(k) for k in containing)
            if len(containing)>1: evidence[key]={'accepted_ids':sorted(containing),'required_complete_definition_set':sorted(defs)}
        (out/'definition_coverage_evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8')
    excluded=set()
    if args.exclude_sample:
        excluded={(c['target'],c['example']) for c in json.loads(Path(args.exclude_sample).read_text(encoding='utf8'))}
    eligible=[c for c in pool if (c['target'],c['example']) not in excluded]
    sample=random.Random(args.seed).sample(sorted(eligible,key=lambda c:(c['target'],c['example'])),min(args.sample,len(eligible)))
    (out/'sample.json').write_text(json.dumps(sample,ensure_ascii=False,indent=2),encoding='utf8')
    manifest={'population':len(pool),'eligible_population':len(eligible),'excluded_examples':len(pool)-len(eligible),
              'excluded_sample_sha256':sha(args.exclude_sample) if args.exclude_sample else None,
              'sample':len(sample),'seed':args.seed,
              'selection':'Uniform sample of deduplicated (source canonical ID, source example), independent of alias matching.',
              'criterion':'At any word start, retrieve the canonical ID or explicitly enabled source-definition-covered phrase ID, with >=2 matched words. No gold exact span annotation.',
              'definition_coverage_enabled':args.allow_source_definition_coverage,
              'definition_policy':'Same canonical ID, or another phrase entry containing every identical target definition, with at least one definition >=8 words. Source-context entries excluded. This is a conservative source-text proxy, not manual semantic annotation.',
              'packages':{v:sha(getattr(args,v)) for v in ('r4','r5')},'dll_sha256':sha(args.dll),'sample_sha256':sha(out/'sample.json')}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    engines={v:Engine(args.dll,getattr(args,v),out/('import_'+v),[Path(args.transforms)/n for n in ('en.json','en_irregular.json')]) for v in ('r4','r5')}
    totals=defaultdict(Counter);paired=Counter();details=[];started=time.perf_counter();calls=Counter()
    try:
        for i,case in enumerate(sample):
            text=case['example'];positions=sorted({0}|{m.start() for m in re.finditer(r'(?<!\w)[\w$\u00a3\u20ac]',text)})
            results={}
            for scan in (16,128):
                for v in (('r4','r5') if i%2==0 else ('r5','r4')):
                    found=None
                    for start in positions:
                        rows=engines[v].lookup(text[start:],scan);calls[v]+=1
                        correct=[(j+1,r) for j,r in enumerate(rows) if norm(r['expression']) in allowed[case['target']] and len(r['matched'].split())>=2]
                        if correct:
                            rank,row=correct[0];found={'offset':start,'rank':rank,'matched':row['matched'],'expression':row['expression'],'match_kind':'canonical_id' if norm(row['expression'])==norm(case['target']) else 'source_definition_coverage'};break
                    results[v,str(scan)]=found
                    totals[v,str(scan)]['cases']+=1;totals[v,str(scan)]['hit']+=bool(found)
                    totals[v,str(scan)]['top1']+=bool(found and found['rank']==1)
                h4,h5=bool(results['r4',str(scan)]),bool(results['r5',str(scan)])
                state='both_hit' if h4 and h5 else 'r4_only' if h4 else 'r5_only' if h5 else 'neither'
                paired[str(scan),state]+=1
            details.append(dict(case,results={v:{s:results[v,s] for s in ('16','128')} for v in ('r4','r5')}))
            if (i+1)%100==0:print(json.dumps({'cases':i+1,'total':len(sample),'native_calls':dict(calls),'seconds':round(time.perf_counter()-started,1)}),flush=True)
        report={'manifest':manifest,'results':[dict(version=v,scan=s,**c) for (v,s),c in sorted(totals.items())],
                'paired':[dict(scan=s,state=state,count=n) for (s,state),n in sorted(paired.items())],
                'native_calls':dict(calls),'elapsed_seconds':round(time.perf_counter()-started,2),
                'limitations':['Retrieval somewhere in its own source example is a proxy; no manually labeled phrase boundaries.',
                               'Examples may contain one-word realizations, paraphrases or explanations, so misses are not all engine bugs.',
                               'This is a paired fixed random sample, not an exhaustive test of all natural inputs.'],
                'cases':details}
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps({k:v for k,v in report.items() if k not in {'cases','manifest'}},ensure_ascii=False),flush=True)
    finally:
        for e in engines.values():e.close()


if __name__=='__main__':main()
