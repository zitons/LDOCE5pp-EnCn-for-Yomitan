"""Fresh full-package checks plus residual contraction and frequency coverage.
All three package dates are explicit; no older report is overwritten.
"""
from collections import Counter,defaultdict
import gc,hashlib,json,re,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'converter'))
import ldoce2yomitan as C
import _apply_patch as patch
ZIP=ROOT/'yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip'
ORIGINAL=ROOT/'yomitan_full/LDOCE5pp_Yomitan_2026.09.11.zip'
PREV=ROOT/'yomitan_full/LDOCE5pp_Yomitan_2026.09.12.zip'
FREQ={'S1','S2','S3','W1','W2','W3'}
TAIL=re.compile(r"[A-Za-z]+['\u2019]$")
SUFFIX={'m','s','t','re','ve','ll','d'}

def flat(n):
    if isinstance(n,str):return n
    if isinstance(n,list):return ''.join(map(flat,n))
    return flat(n.get('content','')) if isinstance(n,dict) else ''

def walk(n):
    if isinstance(n,list):
        for x in n:yield from walk(x)
    elif isinstance(n,dict):
        yield n;yield from walk(n.get('content'))

def junctions(n,separated,parent='root'):
    if isinstance(n,dict):
        yield from junctions(n.get('content'),separated,n.get('data',{}).get('class',n.get('tag','root')))
    elif isinstance(n,list):
        for i,a in enumerate(n):
            j=i+(2 if separated else 1)
            if j>=len(n) or (separated and n[i+1]!=' '):continue
            b=n[j]
            lt,rt=flat(a),flat(b)
            m=TAIL.search(lt)
            if m and rt.lower() in SUFFIX:
                yield (parent,m[0],rt)
        for c in n:yield from junctions(c,separated,parent)

def dump(name,value):
    text=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    patch.P=str(OUT/name);patch.write_atomic(text)
    assert Path(patch.P).read_bytes()==text.encode('utf-8')

def main():
    stats=Counter();meta_expected=defaultdict(set);meta_actual=defaultdict(set)
    examples=[];words=set();samples=[];changed=[];sequence_errors=[];num_classes=Counter()
    sample_words={'apprentice','auxiliary verb','but','Berra, Yogi','need','act','access','7/7','criminal','MP4 player','vodcast','matter','the'}
    with zipfile.ZipFile(ZIP) as zn,zipfile.ZipFile(ORIGINAL) as zo,zipfile.ZipFile(PREV) as zp:
        css=zn.read('styles.css').decode('utf-8')
        stats['css_matches_source']=int(css==C.generate_css())
        names=zn.namelist();stats['duplicate_zip_members']=len(names)-len(set(names))
        for name in names:
            if re.fullmatch(r'term_meta_bank_\d+\.json',name):
                for r in json.loads(zn.read(name)):meta_actual[r[0]].add(r[2]['displayValue'])
        banks=sorted((n for n in names if re.fullmatch(r'term_bank_\d+\.json',n)),key=lambda n:int(re.search(r'\d+',n)[0]))
        for name in banks:
            current=json.loads(zn.read(name));old=json.loads(zo.read(name));prev=json.loads(zp.read(name))
            assert len(current)==len(old)==len(prev)
            for r,o,p in zip(current,old,prev):
                assert (r[0],r[1],r[6])==(o[0],o[1],o[6])==(p[0],p[1],p[6])
                if r[6]!=stats['rows']:sequence_errors.append([r[0],r[6],stats['rows']])
                stats['rows']+=1
                if r[4]<=0:stats['aliases']+=1;continue
                stats['entries']+=1
                meta_expected[r[0]].update(set(r[2].split())&FREQ)
                if r[0] in sample_words:samples.append({'word':r[0],'content':r[5][0]['content']})
                a=re.sub(r'\s+','',flat(r[5]));b=re.sub(r'\s+','',flat(p[5]))
                if a!=b:changed.append({'word':r[0],'sequence':r[6],'old_len':len(b),'new_len':len(a)})
                broken=Counter(junctions(o[5],False)) & Counter(junctions(r[5],True))
                for (parent,left,right),count in broken.items():
                    stats['split_contractions']+=count;words.add(r[0])
                    examples.append({'word':r[0],'parent':parent,'before':left+right,'after':left+' '+right,'count':count})
                for n in walk(r[5]):
                    cls=n.get('data',{}).get('class','')
                    if cls=='ld-snum':
                        stats['source_number_chips']+=1
                        if str(n.get('style',{}).get('fontSize'))=='0':stats['hidden_source_numbers']+=1
                    if n.get('tag') in {'ol','ul'}:
                        stats['lists']+=1
                        num_classes[cls]+=1
                        if n.get('style',{}).get('listStyleType')!='none':stats['lists_without_marker_suppression']+=1
            print(name,'rows',stats['rows'],'split_contractions',stats['split_contractions'],flush=True)
        missing=[];extra=[]
        for w,codes in meta_expected.items():
            if codes-meta_actual[w]:missing.append({'word':w,'definition_tags':sorted(codes),'frequency_rows':sorted(meta_actual[w]),'missing':sorted(codes-meta_actual[w])})
        for w,codes in meta_actual.items():
            if codes-meta_expected[w]:extra.append({'word':w,'extra':sorted(codes-meta_expected[w])})
    stats['words_with_split_contractions']=len(words)
    result={'package':str(ZIP),'package_sha256':hashlib.sha256(ZIP.read_bytes()).hexdigest(),
            'converter_sha256':hashlib.sha256((ROOT/'converter/ldoce2yomitan.py').read_bytes()).hexdigest(),
            'stats':dict(stats),'contraction_examples':examples,'frequency_missing':missing,'frequency_extra':extra,
            'nonwhitespace_text_changes':changed,'sequence_errors':sequence_errors,'list_classes':dict(num_classes)}
    dump('package_results.json',result);dump('sample_payload.json',samples)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
