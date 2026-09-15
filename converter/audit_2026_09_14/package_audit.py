"""Independent exhaustive package invariants and byte-for-byte rebuild comparison."""
from collections import Counter,defaultdict
import hashlib,json,re,sys,time,zipfile
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent/'results'
import argparse
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--build-root',type=Path,default=OUT/'build')
args=ap.parse_args()
FREQ={'S1':1000,'S2':2000,'S3':3000,'W1':1000,'W2':2000,'W3':3000}
CJK=re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]')
INVISIBLE=re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\u00ad\u200b-\u200d\u2060-\u2064\ufeff]')

def banks(z):return sorted((n for n in z.namelist() if re.fullmatch(r'term_bank_\d+\.json',n)),key=lambda n:int(re.search(r'\d+',n)[0]))
def sha(data):return hashlib.sha256(data).hexdigest()
def nodes(tree,parents=()):
    if isinstance(tree,list):
        for x in tree:yield from nodes(x,parents)
    elif isinstance(tree,dict):
        yield tree,parents
        yield from nodes(tree.get('content'),parents+(tree.get('tag'),))

def audit(mode,package,rebuild):
    start=time.monotonic();stats=Counter();errors=[];entry_counts=Counter();aliases={};all_terms=set();rule_union=defaultdict(set);expected_freq=defaultdict(set);actual_freq=defaultdict(set);link_targets=Counter();classes=set();compound=set()
    def error(kind,data):
        stats['errors_'+kind]+=1
        if len(errors)<50:errors.append({'kind':kind,'data':data})
    compared=[]
    with zipfile.ZipFile(package) as z,zipfile.ZipFile(rebuild) as fresh:
        if len(set(z.namelist()))!=len(z.namelist()):error('duplicate_members',None)
        if set(z.namelist())!=set(fresh.namelist()):error('rebuild_member_names',None)
        for name in z.namelist():
            a,b=z.read(name),fresh.read(name)
            if name=='index.json':
                ia,ib=json.loads(a),json.loads(b);ia.pop('revision',None);ib.pop('revision',None)
                if ia!=ib:error('rebuild_index',{'old':ia,'new':ib})
            elif a!=b:
                error('rebuild_bytes',{'file':name,'old_sha256':sha(a),'new_sha256':sha(b)})
            compared.append({'file':name,'identical':a==b,'old_sha256':sha(a),'new_sha256':sha(b)})
        tag_names={row[0] for row in json.loads(z.read('tag_bank_1.json'))}
        css=z.read('styles.css').decode('utf-8')
        css_exact=set(re.findall(r'\[data-sc-class="([^"]+)"\]',css));css_words=set(re.findall(r'\[data-sc-class~="([^"]+)"\]',css))
        for name in z.namelist():
            raw=z.read(name).decode('utf-8')
            if mode=='mono' and CJK.search(raw):error('mono_cjk',name)
            if INVISIBLE.search(raw):error('invisible_or_control',name)
            if re.fullmatch(r'term_meta_bank_\d+\.json',name):
                for term,kind,meta in json.loads(raw):
                    stats['frequency_rows']+=1
                    if kind!='freq' or meta['value']!=FREQ.get(meta['displayValue']):error('frequency_value',term)
                    actual_freq[term].add(meta['displayValue'])
        for name in banks(z):
            stats['term_banks']+=1
            for r in json.loads(z.read(name)):
                if r[6]!=stats['rows']:error('sequence',[r[0],r[6],stats['rows']])
                stats['rows']+=1;all_terms.add(r[0])
                if not set((r[2]+' '+r[7]).split())<=tag_names:error('undeclared_tag',r[0])
                if r[4]>0:
                    stats['content_rows']+=1;entry_counts[r[0]]+=1
                    rule_union[r[0]].update(r[3].split());expected_freq[r[0]].update(set(r[2].split())&FREQ.keys())
                    for item in r[5]:
                        for n,parents in nodes(item):
                            tag=n.get('tag');cl=set(n.get('data',{}).get('class','').split());classes.update(cl)
                            if len(cl)>1:compound.update(cl)
                            if tag=='a':
                                stats['query_links']+=1
                                if 'a' in parents:error('nested_anchor',[r[0],r[6]])
                                u=urlsplit(n['href']);q=parse_qs(u.query)
                                if u.scheme or u.netloc or q.get('wildcards')!=['off'] or len(q.get('query',[]))!=1:error('link_encoding',[r[0],n['href']])
                                else:link_targets[q['query'][0]]+=1
                            elif tag in ('ol','ul'):
                                stats['lists']+=1
                                for child in n.get('content',[]):
                                    if isinstance(child,str) and not child.strip():continue
                                    if not isinstance(child,dict) or child.get('tag')!='li':error('invalid_list_child',[r[0],tag])
                            elif tag=='li':
                                stats['list_items']+=1
                                if not parents or parents[-1] not in ('ol','ul'):error('orphan_li',[r[0],parents[-2:]])
                            if 'ld-snum' in cl:
                                stats['number_chips']+=1
                                if n.get('style',{}).get('fontSize') in (0,'0','0px'):error('hidden_number',r[0])
                else:
                    stats['alias_rows']+=1
                    if r[0] in aliases:error('duplicate_alias',r[0])
                    aliases[r[0]]=(set(r[3].split()),[i[0] for i in r[5]])
            print(mode,name,stats['rows'],flush=True)
        for term,(rules,targets) in aliases.items():
            if term in entry_counts:error('alias_shadows_content',term)
            if any(t not in entry_counts for t in targets):error('alias_missing_content_target',term)
            expected=set().union(*(rule_union[t] for t in targets))
            if rules!=expected:error('alias_rules_union',{'term':term,'actual':sorted(rules),'expected':sorted(expected)})
            stats['redirect_items']+=len(targets)
        for term,count in link_targets.items():
            if term not in all_terms:error('dangling_query',[term,count])
        for term in set(expected_freq)|set(actual_freq):
            if expected_freq[term]!=actual_freq[term]:error('frequency_coverage',term)
        if not classes <= css_exact|css_words:error('missing_css',sorted(classes-css_exact-css_words))
        if not compound <= css_words:error('compound_css',sorted(compound-css_words))
    stats['unique_content_terms']=len(entry_counts);stats['duplicate_content_terms']=sum(n>1 for n in entry_counts.values());stats['unique_query_targets']=len(link_targets)
    return {'mode':mode,'package':str(package),'package_sha256':sha(package.read_bytes()),'rebuild':str(rebuild),'rebuild_sha256':sha(rebuild.read_bytes()),'stats':dict(stats),'errors':errors,'comparison':compared,'seconds':round(time.monotonic()-start,1)}
results=[]
for mode,suffix in [('bilingual',''),('mono','_EN')]:
    package=ROOT/f'yomitan_full/LDOCE5pp_Yomitan_2026.09.13{suffix}.zip'
    manifest=json.loads((args.build_root/mode/'build_manifest.json').read_text(encoding='utf-8'))
    assert manifest['exit_code']==0 and manifest['source_unchanged_during_build']
    assert manifest['converter_sha256']==sha((ROOT/'converter/ldoce2yomitan.py').read_bytes()), 'Refusing stale build manifest'
    rebuild=Path(manifest['packages'][0]['path'])
    results.append(audit(mode,package,rebuild))
    (OUT/'package_audit.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'mode':mode,'stats':results[-1]['stats'],'errors':results[-1]['errors']},ensure_ascii=False),flush=True)
raise SystemExit(int(any(r['errors'] for r in results)))