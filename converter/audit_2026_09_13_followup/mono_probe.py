"""Render EVERY source content record in mono mode; do not build/publish a ZIP.
The current package supplies a complete lookup index, not test-word-only links.
"""
from collections import Counter
import gc,hashlib,json,re,sys,time,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'converter'))
import ldoce2yomitan as C
import _apply_patch as patch
ZIP=ROOT/'yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip'
SOURCE=ROOT/'extract/LDOCE5++ V 2-15.mdx.txt'

def text_hits(node,path='root'):
    if isinstance(node,str):
        m=C.CJK_RE.search(node)
        if m:yield {'path':path,'text':node[max(0,m.start()-70):m.start()+180]}
    elif isinstance(node,list):
        for i,x in enumerate(node):yield from text_hits(x,path+f'[{i}]')
    elif isinstance(node,dict):
        path+='.'+node.get('data',{}).get('class',node.get('tag','object'))
        for k,v in node.items():yield from text_hits(v,path+'.'+k)


def main():
    started=time.time();gc.set_threshold(50000,100,100)
    index=C.TermIndex();entry_keys=set();aliases=[]
    with zipfile.ZipFile(ZIP) as z:
        for bank in sorted((n for n in z.namelist() if re.fullmatch(r'term_bank_\d+\.json',n)),key=lambda n:int(re.search(r'\d+',n)[0])):
            for row in json.loads(z.read(bank)):
                if row[4]>0:index.add(row[0]);entry_keys.add(row[0])
                else:aliases.append(row[0])
    for key in aliases:index.add_alias_word(key)
    renderer=C.LdoceRenderer(index,mode='mono')
    stats=Counter();leaks=[];errors=[]
    print('index ready',len(entry_keys),'entries',len(aliases),'aliases',flush=True)
    for key,content in C.iter_records(SOURCE):
        key=C.strip_invisible(key).strip()
        if C.classify_record(key,content)[0]!='entry':continue
        stats['entries']+=1
        try:
            nodes=renderer.render_record(key,content)
        except Exception as exc:
            stats['render_errors']+=1
            errors.append({'word':key,'exception':repr(exc)})
            continue
        if not nodes or not C.sc_has_text(nodes):stats['empty']+=1
        hits=list(text_hits(nodes))
        if hits:
            stats['entries_with_cjk']+=1
            stats['cjk_string_nodes']+=len(hits)
            leaks.append({'word':key,'hits':hits[:8]})
            if len(leaks)<=8:print('CJK',key,repr(hits[0]),flush=True)
        if stats['entries']%5000==0:
            print('rendered',stats['entries'],'leaks',stats['entries_with_cjk'],'elapsed',round(time.time()-started,1),flush=True)
    result={'package':str(ZIP),'converter_sha256':hashlib.sha256((ROOT/'converter/ldoce2yomitan.py').read_bytes()).hexdigest(),
            'stats':dict(stats),'leaks':leaks,'errors':errors,'elapsed_seconds':round(time.time()-started,1)}
    patch.P=str(OUT/'mono_render_results.json')
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n';patch.write_atomic(text)
    assert Path(patch.P).read_bytes()==text.encode('utf-8')
    print(json.dumps({'stats':dict(stats),'first_leaks':leaks[:5],'errors':errors[:8],'elapsed_seconds':result['elapsed_seconds']},ensure_ascii=False,indent=2))
    return int(bool(leaks or errors))

if __name__=='__main__':sys.exit(main())
