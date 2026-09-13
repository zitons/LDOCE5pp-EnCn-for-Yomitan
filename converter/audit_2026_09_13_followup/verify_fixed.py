"""Compare fixed full builds to the recorded pre-fix package, including whitespace.
Run after build_fixed.py has completed BOTH bilingual and mono builds.
"""
from collections import Counter,defaultdict
import hashlib,json,re,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'converter'))
import _apply_patch as patch
BASE=ROOT/'yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip'
FIXED=ROOT/'yomitan_fixed'
CJK=re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')
TAIL=re.compile(r'^(?:[dstm]|ll|re|ve)(?:\b|$)',re.I)


def flat(n):
    if isinstance(n,str):return n
    if isinstance(n,list):return ''.join(map(flat,n))
    return flat(n.get('content','')) if isinstance(n,dict) else ''


def walk(n):
    if isinstance(n,list):
        for v in n:yield from walk(v)
    elif isinstance(n,dict):
        yield n;yield from walk(n.get('content'))


def dump(name,obj):
    text=json.dumps(obj,ensure_ascii=False,indent=2)+'\n'
    patch.P=str(FIXED/name);patch.write_atomic(text)
    assert Path(patch.P).read_bytes()==text.encode('utf-8')


def only_apostrophe_space_removals(before,after):
    i=j=removed=0
    while i<len(before) and j<len(after):
        if before[i]==after[j]:i+=1;j+=1;continue
        if not before[i].isspace():return False,removed
        start=i
        while i<len(before) and before[i].isspace():i+=1
        if start==0 or before[start-1] not in ("'", chr(0x2019)) or not TAIL.match(before[i:]):return False,removed
        removed+=1
    return i==len(before) and j==len(after),removed


def main():
    global FIXED
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=FIXED,
                        help='directory containing bilingual/ and mono/ full builds')
    FIXED=parser.parse_args().root.resolve()
    # ASCII code points make the character check independent of shell encoding.
    for apostrophe in ("'", chr(0x2019)):
        assert only_apostrophe_space_removals(
            'You'+apostrophe+' re fired!', 'You'+apostrophe+'re fired!') == (True, 1)
    assert not only_apostrophe_space_removals('model kits', 'modelkits')[0]
    assert not only_apostrophe_space_removals('word? s', 'word?s')[0]
    current_sha=hashlib.sha256((ROOT/'converter/ldoce2yomitan.py').read_bytes()).hexdigest()
    manifests={m:json.loads((FIXED/m/'build_manifest.json').read_text(encoding='utf-8')) for m in ('bilingual','mono')}
    paths={}
    for mode,m in manifests.items():
        assert m['exit_code']==0 and m['source_unchanged_during_build'] and m['converter_sha256']==current_sha
        assert len(m['packages'])==1
        paths[mode]=Path(m['packages'][0]['path'])
    known=json.loads((OUT/'package_results.json').read_text(encoding='utf-8'))['contraction_examples']
    prior=json.loads((ROOT/'converter/audit_2026_09_13/suffix_results.json').read_text(encoding='utf-8'))['examples']
    wanted=defaultdict(list)
    for case in known+prior:wanted[case['word']].append(case)
    stats=Counter();failures=[];changes=[];payload=[];numbered_lists=Counter()
    def fail(message):
        stats['failures']+=1
        if len(failures)<30:failures.append(message)
    with zipfile.ZipFile(BASE) as old,zipfile.ZipFile(paths['bilingual']) as bi,zipfile.ZipFile(paths['mono']) as mono:
        for mode,z in [('bilingual',bi),('mono',mono)]:
            names=z.namelist()
            if len(names)!=len(set(names)):fail(mode+': duplicate members')
            index=json.loads(z.read('index.json'))
            if index['targetLanguage']!=('en' if mode=='mono' else 'zh'):fail(mode+': wrong target language')
            if z.read('styles.css')!=old.read('styles.css'):fail(mode+': stylesheet changed unexpectedly')
            if mode=='mono':
                for name in names:
                    if name.endswith('.json') and not re.fullmatch(r'term_bank_\d+\.json',name):
                        if CJK.search(z.read(name).decode('utf-8')):fail('CJK in mono '+name)
        banks=sorted((n for n in old.namelist() if re.fullmatch(r'term_bank_\d+\.json',n)),key=lambda n:int(re.search(r'\d+',n)[0]))
        for bank in banks:
            br=json.loads(bi.read(bank));orows=json.loads(old.read(bank))
            mono_text=mono.read(bank).decode('utf-8');mr=json.loads(mono_text)
            if CJK.search(mono_text):fail('CJK in mono '+bank)
            if not len(br)==len(orows)==len(mr):fail('bank length differs: '+bank);continue
            for original,bilingual,english in zip(orows,br,mr):
                row_number=stats['rows'];stats['rows']+=1
                for mode,row in [('bilingual',bilingual),('mono',english)]:
                    if row[:5]+row[6:]!=original[:5]+original[6:]:fail(mode+' metadata changed: '+str(row[0]))
                    if row[6]!=row_number:fail(mode+' sequence differs: '+str(row[0]))
                if original[4]<=0:
                    stats['aliases']+=1
                    for mode,row in [('bilingual',bilingual),('mono',english)]:
                        a={(i[0],tuple(i[1])) for i in original[5]}
                        b={(i[0],tuple(i[1])) for i in row[5]}
                        if a!=b:fail(mode+' alias targets changed: '+str(row[0]))
                    continue
                stats['entries']+=1
                old_text=flat(original[5]);new_text=flat(bilingual[5])
                if re.sub(r'\s+','',old_text)!=re.sub(r'\s+','',new_text):fail('bilingual content changed: '+str(original[0]))
                if old_text!=new_text:
                    ok,n=only_apostrophe_space_removals(old_text,new_text)
                    if not ok:fail('unexpected whitespace change: '+str(original[0]))
                    stats['changed_content_rows']+=1;stats['removed_apostrophe_spaces']+=n
                    if len(changes)<12:changes.append({'word':original[0],'spaces_removed':n,'allowed':ok})
                for case in wanted.get(original[0],[]):
                    if case['before'] not in new_text or case['after'] in new_text:
                        fail('known word seam not restored: '+str(original[0])+' '+case['before'])
                    else:stats['known_cases_restored']+=1
                if original[0] in {'act','access','apprentice','auxiliary verb','but','need','7/7','criminal'}:
                    payload.append({'word':bilingual[0],'content':bilingual[5][0]['content']})
                for mode,row in [('bilingual',bilingual),('mono',english)]:
                    for node in walk(row[5]):
                        cls=node.get('data',{}).get('class','')
                        if cls=='ld-snum' and str(node.get('style',{}).get('fontSize'))=='0':fail(mode+' hidden number: '+row[0])
                        if cls in {'ld-senselist','ld-exlist','ld-corpulist'}:
                            numbered_lists[mode]+=1
                            if node.get('style',{}).get('listStyleType')!='none':fail(mode+' native counter enabled: '+row[0])
            print(bank,'rows=',stats['rows'],'removed_spaces=',stats['removed_apostrophe_spaces'],'failures=',stats['failures'],flush=True)
    if stats['known_cases_restored']!=len(known)+len(prior):fail('not all historical cases were exercised')
    if stats['rows']!=245933 or stats['entries']!=64659 or stats['aliases']!=181274:fail('unexpected canonical corpus counts')
    result={'converter_sha256':current_sha,'baseline':str(BASE),'paths':{k:str(v) for k,v in paths.items()},
            'stats':dict(stats),'numbered_lists':dict(numbered_lists),'failures':failures,'sample_changes':changes}
    dump('verification.json',result);dump('sample_payload.json',payload)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return int(bool(stats['failures']))

if __name__=='__main__':sys.exit(main())
