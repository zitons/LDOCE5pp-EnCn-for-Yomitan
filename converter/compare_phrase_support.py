"""Compare built phrase bodies and useful query keys; exclude topic navigation.

This is an audit only. LDOCE5++ is never an input to the LDOCE6 builder.
"""
import argparse
import csv
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import unquote


def norm(s): return ' '.join(s.casefold().split())
def multi(s): return bool(re.search(r'\s',s.strip()))
def topic(s, names):
    marker=s.find('-topic')
    if marker<0: return False
    end=marker+len('-topic')
    return s[:end] in names and (end==len(s) or s[end].isspace())
def redirect(r):
    return bool(r[5]) and all(isinstance(g,list) and len(g)==2 and isinstance(g[1],list)
                             and 'redirect' in g[1] for g in r[5])


def load(path, six=False):
    body=set(); aliases=set(); raw_all=set(); topics=set(); contexts=set(); references=set(); rows={}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if not re.fullmatch(r'term_bank_\d+\.json',n): continue
            for r in json.loads(z.read(n)):
                key=' '.join(r[0].split())
                rows[key]=r
                if multi(key): raw_all.add(key)
    # Synthetic topic prefixes are anchored to actual redirect targets.
    # A legitimate phrase containing "off-topic" is not a navigation key.
    topic_names=set() if six else {g[0] for r in rows.values() if redirect(r) for g in r[5]
                                   if g[0].endswith('-topic') and g[0] not in {'off-topic','on-topic'}}
    for key,r in rows.items():
        if six and r[2]=='source-context': contexts.add(key); continue
        if topic(key,topic_names): topics.add(key); continue
        if not multi(key): continue
        if six and r[2]=='phrase-reference': references.add(key); continue
        (aliases if redirect(r) else body).add(key)
    return dict(body=body,aliases=aliases,raw_all=raw_all,topics=topics,contexts=contexts,references=references,rows=rows)


def text(value):
    if isinstance(value,str): return value
    if isinstance(value,list): return ''.join(text(v) for v in value)
    if isinstance(value,dict): return text(value.get('content',''))
    return ''


def audit_links(data):
    errors=[]; nlinks=0
    def visit(v,key):
        nonlocal nlinks
        if isinstance(v,list):
            for item in v: visit(item,key)
        elif isinstance(v,dict):
            if v.get('tag')=='a':
                nlinks+=1
                target=unquote(v.get('href','').removeprefix('?query='))
                if target not in data['rows']: errors.append([key,'link',target])
            if 'content' in v: visit(v['content'],key)
    for key,r in data['rows'].items():
        if redirect(r):
            for target,_ in r[5]:
                if target not in data['rows'] or data['rows'][target][2] not in {'phrase','phrase-reference'}:
                    errors.append([key,'redirect',target])
                elif redirect(data['rows'][target]): errors.append([key,'redirect_chain',target])
        else:
            for g in r[5]:
                if isinstance(g,dict): visit(g.get('content'),key)
    return dict(links=nlinks,errors=errors)


def write(path,fields,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter='\t'); w.writerow(fields); w.writerows(rows)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ldoce6',required=True); ap.add_argument('--ldoce5',required=True)
    ap.add_argument('-o','--output',required=True)
    ap.add_argument('--previous',help='Previous LDOCE6 package whose useful query keys must all survive')
    args=ap.parse_args(); out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
    d6=load(args.ldoce6,True); d5=load(args.ldoce5)
    report={'normalization':'casefold and whitespace only; punctuation/parentheses retained for literal query support',
            'topic_policy':'Topic navigation keys identified by actual -topic redirect targets and their prefixes; legitimate off-topic/on-topic phrases retained. LDOCE6 source-context rows excluded from phrase counts.',
            'dictionaries':{},'cross_support':{},'validation':audit_links(d6)}
    for label,d in [('ldoce6',d6),('ldoce5',d5)]:
        report['dictionaries'][label]=dict(multiword_body_keys=len(d['body']),multiword_alias_keys=len(d['aliases']),
            multiword_reference_keys=len(d['references']),
            all_multiword_keys=len(d['raw_all']),excluded_topic_keys=len({k for k in d['topics'] if multi(k)}),
            normalized_body_keys=len({norm(k) for k in d['body']}),
            normalized_useful_query_keys=len({norm(k) for k in d['body']|d['aliases']|d['references']}))
    for label,source,target in [('ldoce6_bodies_in_ldoce5',d6,d5),('ldoce5_bodies_in_ldoce6',d5,d6)]:
        source_keys={norm(k) for k in source['body']}
        target_body={norm(k) for k in target['body']}; target_query=target_body|{norm(k) for k in target['aliases']|target['references']}
        report['cross_support'][label]=dict(total=len(source_keys),matched_body=len(source_keys&target_body),
            matched_body_or_alias=len(source_keys&target_query),unmatched=len(source_keys-target_query),
            percent=round(100*len(source_keys&target_query)/len(source_keys),2))
        write(out/(label+'.tsv'),['phrase','body_match','query_match'],
              ((p,int(norm(p) in target_body),int(norm(p) in target_query)) for p in sorted(source['body'])))
    allq={norm(k) for k in d6['body']|d6['aliases']|d6['references']}
    q5={norm(k) for k in d5['body']|d5['aliases']|d5['references']}
    report['query_overlap']=dict(shared=len(allq&q5),only6=len(allq-q5),only5=len(q5-allq))
    if args.previous:
        previous=load(args.previous,True)
        oldq={norm(k) for k in previous['body']|previous['aliases']|previous['references']}
        lost=sorted(oldq-allq)
        upgrade=dict(normalization='casefold and whitespace only; source contexts excluded',
                     previous_queries=len(oldq),current_queries=len(allq),
                     added_queries=len(allq-oldq),lost_queries=len(lost),
                     previous_only5=len(q5-oldq),current_only5=len(q5-allq),
                     newly_covered_5_queries=len((q5-oldq)&allq),
                     current_only6=len(allq-q5),current_shared=len(allq&q5),
                     scope='Query support only; not a linguistic correctness proof for every alias.')
        (out.parent/'upgrade_report.json').write_text(json.dumps(upgrade,ensure_ascii=False,indent=2),encoding='utf8')
        (out.parent/'added_multiword_queries.txt').write_text(''.join(k+'\n' for k in sorted(allq-oldq)),encoding='utf8')
        assert not lost, {'lost_previous_queries':lost}
    # Literal queries useful to an end user, verified against package rows.
    probes=['hang by a thread','hanging by a thread','abandon yourself to something','abandon yourself to sth',
            'answer criticism','answer charges',"hot on somebody's heels","on sb's heels",'camping equipment']
    report['probes']={p:{label: norm(p) in {norm(k) for k in d['body']|d['aliases']|d['references']}
                         for label,d in [('ldoce6',d6),('ldoce5',d5)]} for p in probes}
    hang=d6['rows'].get('hang by a thread')
    assert hang and not redirect(hang),'Missing independent hang by a thread entry'
    payload=text([g.get('content') for g in hang[5] if isinstance(g,dict)])
    assert 'very dangerous situation' in payload and 'his life hanging by a thread' in payload
    assert not report['validation']['errors'],report['validation']['errors'][:10]
    (out/'support_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
