"""Compare old joined link/emphasis suffixes to new inserted spaces, row by row.
Counts only junctions actually present in BOTH published packages.
"""
from collections import Counter
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'converter'))
import ldoce2yomitan as C
import _apply_patch as patch
NEW=ROOT/'yomitan_full/LDOCE5pp_Yomitan_2026.09.12.zip'
OLD=ROOT/'yomitan_full/LDOCE5pp_Yomitan_2026.09.11.zip'
ALLOWED={'ld-colloin','ld-nodew','ld-b','ld-it','ld-em','ld-strong','ld-en'}
SUFFIX=re.compile(r'^(?:s|es|ed|ing|ly|er|est)\b')


def pairs(n,new,parent='root'):
    if isinstance(n,dict):
        yield from pairs(n.get('content'),new,n.get('data',{}).get('class',n.get('tag','root')))
    elif isinstance(n,list):
        for i,a in enumerate(n):
            j=i+(2 if new else 1)
            if j>=len(n) or (new and n[i+1]!=' '):continue
            b=n[j]
            if not isinstance(a,dict) or not isinstance(b,str):continue
            cls=a.get('data',{}).get('class','')
            if a.get('tag')!='a' and cls not in ALLOWED:continue
            if not SUFFIX.match(b):continue
            at=C._plain_text(a)
            if not re.search('[A-Za-z]$',at):continue
            sig=(parent,a.get('tag'),cls,at[-80:],b[:100])
            yield sig
        for c in n:yield from pairs(c,new,parent)


count=0;words=set();examples=[];categories=Counter();row_count=0
with zipfile.ZipFile(OLD) as zo,zipfile.ZipFile(NEW) as zn:
    banks=sorted((n for n in zn.namelist() if re.fullmatch(r'term_bank_\d+\.json',n)),key=lambda n:int(re.search(r'\d+',n)[0]))
    for name in banks:
        old=json.loads(zo.read(name));new=json.loads(zn.read(name))
        assert len(old)==len(new),(name,len(old),len(new))
        for ro,rn in zip(old,new):
            assert (ro[0],ro[1],ro[6])==(rn[0],rn[1],rn[6])
            if rn[4]<=0:continue
            row_count+=1
            shared=Counter(pairs(ro[5],False)) & Counter(pairs(rn[5],True))
            for sig,n in shared.items():
                count+=n;words.add(rn[0]);categories[sig[0]+' | '+(sig[2] or sig[1])]+=n
                if len(examples)<25 or rn[0]=='criminal':
                    examples.append({'word':rn[0],'count':n,'parent':sig[0],
                                     'before':sig[-2]+sig[-1],
                                     'after':sig[-2]+' '+sig[-1]})
        print(name,'damaged_suffix_junctions=',count,flush=True)
result={'entry_rows_compared':row_count,'changed_suffix_junctions':count,
        'distinct_words':len(words),'categories':dict(categories),'examples':examples}
patch.P=str(OUT/'suffix_results.json');patch.write_atomic(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
