"""Frozen-package, paired native retrieval benchmark; never changes dictionary builds."""
import argparse
import csv
import gzip
import hashlib
import json
import random
import re
import statistics
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from probe_fushidicts import Engine
from audit_fushidicts_gaps import CASES


def norm(s):
    return ' '.join(s.casefold().split())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read_package(path):
    bodies = {}
    aliases = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not re.fullmatch(r'term_bank_\d+\.json', name):
                continue
            for row in json.loads(z.read(name)):
                if row[2] in {'phrase', 'phrase-reference'}:
                    bodies[row[0]] = row
                elif row[2] == 'non-lemma':
                    aliases[row[0]] = {g[0] for g in row[5]}
    rules = defaultdict(set)
    for row in csv.DictReader((Path(path).parent/'aliases.tsv').open(encoding='utf-8-sig'), delimiter='\t'):
        rules[row['alias']].update(row['rules'].split(','))
    folded = defaultdict(set)
    for key, rs in rules.items():
        folded[norm(key)].update(rs)
    for key in rules:
        rules[key].update(folded[norm(key)])
    return bodies, aliases, rules


def family(rules):
    if any('verb_' in r for r in rules): return 'verb_inflection'
    if any('noun_' in r for r in rules): return 'noun_inflection'
    if 'finite_generic_pronoun' in rules: return 'pronoun_substitution'
    if rules & {'lookup_omit_generic_object','lookup_omit_initial_be','terminal_object_placeholder_omitted'}: return 'constituent_omission'
    if 'source_comma_order' in rules: return 'comma_order'
    if 'source_pos_compatible' in rules: return 'pos_slash'
    if 'grouped_multiword_alternatives' in rules: return 'grouped_slash'
    if rules & {'source_declared_lexical_variant','source_declared_spelling_variant','source_declared_plural'}: return 'declared_variant'
    if 'source_orthographic_variant' in rules: return 'orthography'
    return 'other'


def plain(node):
    if isinstance(node, str): return node
    if isinstance(node, list): return ''.join(plain(x) for x in node)
    if isinstance(node, dict): return plain(node.get('content', ''))
    return ''


def examples(node):
    if isinstance(node, list):
        for x in node: yield from examples(x)
    elif isinstance(node, dict):
        if node.get('data', {}).get('class') == 'l6p-example':
            yield ' '.join(plain(node).split())
        else:
            yield from examples(node.get('content', []))


def make_cases(bodies, aliases4, aliases5, rules, out):
    cases = []
    def add(group, query, targets, span=None, category='', positive=True, **extra):
        cases.append(dict(id=len(cases),group=group,category=category,query=query,
                          span=span or query,targets=sorted(targets),positive=positive,**extra))
    for key in sorted(bodies):
        add('canonical', key, {key}, category='notation' if re.search(r'[/()\u2194]|\b(?:somebody|something|etc)\b',key) else 'plain')
    for key in sorted(aliases4.keys() | aliases5.keys()):
        retained = key in aliases4 and key in aliases5
        targets = aliases4.get(key,set()) | aliases5.get(key,set())
        add('retained_alias' if retained else 'removed_alias' if key in aliases4 else 'added_alias',
            key,targets,category=family(rules.get(key,set())))
    by_target = defaultdict(set)
    for key, targets in aliases4.items():
        for target in targets: by_target[target].add(key)
    for key, targets in aliases5.items():
        for target in targets: by_target[target].add(key)
    seen = set(); total_examples = matched_examples = 0
    with (out/'unmatched_source_examples.jsonl').open('w',encoding='utf8') as unmatched:
        for target,row in sorted(bodies.items()):
            candidates = by_target[target] | {target}
            candidates = [k for k in candidates if len(k.split())>=2 and not re.search(r'[/()\u2194]|\b(?:somebody|something|someone|sb|sth|etc|oneself)\b', k, re.I)]
            candidates.sort(key=lambda s:(-len(s),s))
            pattern = re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(k).replace(r'\ ',r'\s+') for k in candidates)+r')(?!\w)',re.I) if candidates else None
            for example in examples(row[5]):
                if (target,example) in seen: continue
                seen.add((target,example)); total_examples += 1
                match = pattern.search(example) if pattern else None
                if not match:
                    unmatched.write(json.dumps({'target':target,'example':example},ensure_ascii=False)+'\n')
                    continue
                matched_examples += 1
                span=match[0]
                add('source_span',span,{target},category='source_attested',source_example=example)
                add('source_context',example[match.start():],{target},span=span,category='source_attested',source_example=example)
    invalid_targets=[]
    for category,query,target in CASES:
        if target not in bodies:
            invalid_targets.append(dict(query=query,target=target,reason='canonical_target_absent'))
        else:
            add('controlled_positive',query,{target},category=category)
    extra = [
        ('heldout_name','give Alex a hand','give (somebody) a hand'),
        ('heldout_name','gave Dr Zhang a hand','give (somebody) a hand'),
        ('heldout_possessive',"pull Alex's leg","pull somebody's leg"),
        ('heldout_possessive',"broke Alex's heart","break somebody's heart"),
        ('heldout_object','give the new student a hand','give (somebody) a hand'),
        ('heldout_object','picked the new student up','pick up'),
    ]
    for category,query,target in extra:
        if target in bodies: add('controlled_positive',query,{target},category=category)
    negatives = [
        ('how can me do something','how can/could somebody do something?'),
        ('how can her do it?','how can/could somebody do something?'),
        ('being to do something','be to do something'),
        ('endear to','endear somebody to somebody'),
        ('a word in ear',"(have/drop) a word in somebody's ear"),
        ('gived him a hand','give (somebody) a hand'),
        ('give Alex a hat','give (somebody) a hand'),
        ('give him a headache','give (somebody) a hand'),
        ('take Mary away',"take somebody's breath away"),
        ('put her bag down','put your foot down'),
    ]
    for query,target in negatives:
        if target in bodies: add('negative_control',query,{target},category='wrong_target_or_invalid_construction',positive=False)
    return cases,dict(total_unique_source_examples=total_examples,selected_examples=matched_examples,
                      unmatched_examples=total_examples-matched_examples,invalid_control_targets=invalid_targets)


def judge(rows,case):
    expected={norm(t) for t in case['targets']}; span=norm(case['span'])
    full=[(i+1,r) for i,r in enumerate(rows) if norm(r['matched'])==span]
    correct=[(i,r) for i,r in full if norm(r['expression']) in expected]
    return dict(hit=bool(correct),top1=bool(correct and correct[0][0]==1),
                rank=correct[0][0] if correct else None,
                wrong_full_only=bool(full and not correct),
                any_full=bool(full),prefix_only=bool(rows and not full),
                correct_targets=sorted({r['expression'] for _,r in correct}),
                actual=[{'expression':r['expression'],'matched':r['matched']} for r in rows[:8]])


def percentile(values,p):
    return sorted(values)[min(len(values)-1,int((len(values)-1)*p))] if values else None


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for arg in ('r4','r5','dll','transforms','output'): ap.add_argument('--'+arg,required=True)
    ap.add_argument('--limit',type=int,help='Smoke only; final runs omit this')
    args=ap.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    b4,a4,rules=read_package(args.r4);b5,a5,_=read_package(args.r5)
    assert set(b4)==set(b5),'Canonical inventory changed'
    cases,selection=make_cases(b4,a4,a5,rules,out)
    if args.limit:
        strata=defaultdict(list)
        for c in cases: strata[c['group']].append(c)
        chosen=[];rng=random.Random(20261118)
        for rows in strata.values(): chosen.extend(rng.sample(rows,min(len(rows),max(1,args.limit//len(strata)))))
        cases=sorted(chosen,key=lambda c:c['id'])
    with gzip.open(out/'cases.jsonl.gz','wt',encoding='utf8') as f:
        for c in cases:f.write(json.dumps(c,ensure_ascii=False)+'\n')
    manifest=dict(packages={'r4':{'path':args.r4,'sha256':sha(args.r4)},'r5':{'path':args.r5,'sha256':sha(args.r5)}},
                  dll={'path':args.dll,'sha256':sha(args.dll)},
                  transforms={n:sha(Path(args.transforms)/n) for n in ['en.json','en_irregular.json']},
                  aliases_tsv_sha256={v:sha(Path(getattr(args,v)).parent/'aliases.tsv') for v in ('r4','r5')},
                  cases_sha256=sha(out/'cases.jsonl.gz'),selection=selection,
                  counts=dict(Counter(c['group'] for c in cases)),
                  scans={'16':'Fixed window 16','128':'Fixed window 128','full':'max(128, query codepoint length); removes scan truncation'},
                  expected_targets='Frozen package canonical IDs, never inferred from tested engine output',
                  retrieval_limits={'max_results':32,'max_terms':32},smoke=bool(args.limit))
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'phase':'prepared','counts':manifest['counts'],'selection':selection}),flush=True)
    transforms=[Path(args.transforms)/n for n in ('en.json','en_irregular.json')]
    engines={v:Engine(args.dll,getattr(args,v),out/('import_'+v),transforms) for v in ['r4','r5']}
    totals=defaultdict(Counter);diff_counts=Counter();differences=defaultdict(list)
    latency={v:[] for v in engines};cache={v:{} for v in engines};calls=Counter();started=time.perf_counter()
    try:
        with gzip.open(out/'results.jsonl.gz','wt',encoding='utf8') as raw, (out/'regressions.tsv').open('w',encoding='utf-8-sig',newline='') as regressions:
            writer=csv.writer(regressions,delimiter='\t');writer.writerow(['group','category','scan','input','expected_targets','r4_hit','r5_hit','r4_rank','r5_rank','r5_actual'])
            for index,case in enumerate(cases):
                for label,scan in [('16',16),('128',128),('full',max(128,len(case['query'])))]:
                    scores={}
                    # Alternating order avoids a systematic first-engine timing bias.
                    order=['r4','r5'] if index%2==0 else ['r5','r4']
                    for v in order:
                        key=(case['query'],scan)
                        if key not in cache[v]:
                            t=time.perf_counter_ns();rows=engines[v].lookup(case['query'],scan)
                            elapsed=(time.perf_counter_ns()-t)/1e6
                            latency[v].append(elapsed);calls[v]+=1;cache[v][key]=rows
                        scores[v]=judge(cache[v][key],case)
                        counter=totals[(case['group'],case['category'],label,v)]
                        counter['cases']+=1
                        for field in ['hit','top1','wrong_full_only','any_full','prefix_only']:counter[field]+=scores[v][field]
                    h4,h5=scores['r4']['hit'],scores['r5']['hit']
                    state='both_hit' if h4 and h5 else 'r4_only' if h4 else 'r5_only' if h5 else 'neither'
                    diff_counts[(case['group'],label,state)]+=1
                    if state in {'r4_only','r5_only'}:
                        writer.writerow([case['group'],case['category'],label,case['query'],' | '.join(case['targets']),int(h4),int(h5),scores['r4']['rank'],scores['r5']['rank'],json.dumps(scores['r5']['actual'],ensure_ascii=False)])
                        if len(differences[(case['group'],label,state)])<20:
                            differences[(case['group'],label,state)].append({'query':case['query'],'targets':case['targets'],'r4':scores['r4'],'r5':scores['r5']})
                    raw.write(json.dumps({'id':case['id'],'scan':label,'r4':scores['r4'],'r5':scores['r5']},ensure_ascii=False)+'\n')
                if (index+1)%5000==0:
                    print(json.dumps({'phase':'running','cases':index+1,'total':len(cases),'native_calls':dict(calls),'seconds':round(time.perf_counter()-started,1)}),flush=True)
                # Bound memoization: nearby scans/groups still share repeated calls.
                if (index+1)%10000==0:
                    cache={v:{} for v in engines}
        records=[]
        for (group,category,scan,v),counts in sorted(totals.items()):
            records.append(dict(group=group,category=category,scan=scan,version=v,**counts))
        report=dict(manifest=manifest,results=records,
                    paired=[dict(group=g,scan=s,state=state,count=n) for (g,s,state),n in sorted(diff_counts.items())],
                    differences=[dict(group=g,scan=s,state=state,samples=rows) for (g,s,state),rows in sorted(differences.items())],
                    latency={v:dict(native_calls=calls[v],mean_ms=statistics.mean(latency[v]),p50_ms=percentile(latency[v],.5),p95_ms=percentile(latency[v],.95),p99_ms=percentile(latency[v],.99)) for v in engines},
                    elapsed_seconds=round(time.perf_counter()-started,2),
                    limitations=['Alias replay tests dictionary-index retrieval, not grammatical correctness of every r4 key.',
                                 'Real-example spans are selected using the union of frozen indexes; selection is documented and is not an unbiased natural-language corpus.',
                                 'Unmatched examples are separately recorded and excluded from span hit-rate denominators.',
                                 'Negative controls are curated cases, not a corpus-wide false-positive-rate estimate.',
                                 'Native popup API with isolated phrase dictionary only; not Flutter UI or installed dictionary combinations.',
                                 'Latency includes Python FFI/JSON overhead and memoization is excluded from native-call timing.'])
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps({'phase':'complete','elapsed_seconds':report['elapsed_seconds'],'latency':report['latency']}),flush=True)
    finally:
        for e in engines.values():e.close()


if __name__=='__main__':main()
