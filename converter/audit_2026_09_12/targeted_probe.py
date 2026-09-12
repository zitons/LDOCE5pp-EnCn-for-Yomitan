"""Confirm source-probe findings against current ZIP; reproduce fail-open builds.
All builds and mutations are isolated under this audit directory.

HISTORICAL EVIDENCE -- DO NOT READ AS A PASS/FAIL GATE.
This script measures the PRE-FIX package and its closing assertions (see the
bottom of the file) assert that the defects are still present, so it is EXPECTED
to fail once the converter is fixed. The negative regression tests that replaced
those assertions live in `regress_gates.py` (A1 publish gate, A6 sequence check)
and `regress_content.py` (A2/A3/A4/A5 on a rebuilt package).
"""
import collections
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'converter'))
import ldoce2yomitan as M
import _apply_patch as patch
from bs4 import BeautifulSoup


def write(name,text):
    patch.P=str(OUT/name)
    patch.write_atomic(text)


def dump(name,obj):
    write(name,json.dumps(obj,ensure_ascii=False,indent=2))


def text(n):
    if isinstance(n,str): return n
    if isinstance(n,list): return ''.join(map(text,n))
    if isinstance(n,dict): return text(n.get('content',''))
    return ''


def walk(n):
    if isinstance(n,list):
        for c in n: yield from walk(c)
    elif isinstance(n,dict):
        yield n
        yield from walk(n.get('content',[]))


src=json.loads((OUT/'source_findings.json').read_text(encoding='utf-8'))
mono_words={r['word'] for r in src['mono_heading_candidates']}
pron_words={r['word'] for r in src['inflection_pronunciation']}
pos_words={r['word'] for r in src['pos']}
selected=mono_words|pron_words|pos_words
package={}
ti=M.TermIndex()
with zipfile.ZipFile(ROOT/'yomitan_full/LDOCE5pp_Yomitan_2026.09.11.zip') as z:
    banks=sorted((n for n in z.namelist() if re.fullmatch(r'term_bank_\d+\.json',n)),
                 key=lambda n:int(re.search(r'\d+',n).group()))
    for name in banks:
        for row in json.loads(z.read(name)):
            if row[4]>0:
                ti.add(row[0])
                if row[0] in selected:
                    package.setdefault(row[0],[]).append(row)
            else:
                ti.add_alias_word(row[0])

result={}
confirmed_pos=[]
for p in src['pos']:
    hits=package.get(p['word'],[])
    if not any([r[2],r[3]]==p['actual'] for r in hits):
        raise AssertionError(('POS source/ZIP mismatch',p['word']))
    confirmed_pos.append({'word':p['word'],'actual':p['actual'],'reference':p['reference'],
                          'missing_tags':sorted(set(p['reference'][0].split())-set(p['actual'][0].split())),
                          'missing_rules':sorted(set(p['reference'][1].split())-set(p['actual'][1].split()))})
result['pos_confirmed_package_rows']=len(confirmed_pos)
result['pos_missing_rule_words']=sum(bool(x['missing_rules']) for x in confirmed_pos)
result['pos_missing_tag_words']=sum(bool(x['missing_tags']) for x in confirmed_pos)
result['pos_examples']=confirmed_pos[:25]

mono=M.LdoceRenderer(ti,mode='mono')
mono_findings=[]
pron_findings=[]
head_pair_failures=[]
occurrence=collections.Counter()
for key,content in M.iter_records(ROOT/'extract/LDOCE5++ V 2-15.mdx.txt'):
    key=M.strip_invisible(key).strip()
    if key not in selected or M.classify_record(key,content)[0]!='entry': continue
    which=occurrence[key]; occurrence[key]+=1
    row=package[key][which]
    if key in mono_words:
        nodes=mono.render_record(key,content)
        blob=json.dumps(nodes,ensure_ascii=False)
        hits=list(M.CJK_RE.finditer(blob))
        if hits:
            m=hits[0]
            mono_findings.append({'word':key,'sequence':row[6],'CJK_chars':len(hits),
                                  'example':blob[max(0,m.start()-70):m.start()+150]})
    if key not in pron_words: continue
    soup=BeautifulSoup(content,M.HTML_PARSER)
    root=soup.find('div',class_='entry_content') or soup.find('span',class_='lm5ppbody') or soup
    source_heads=[h for h in root.find_all('span',class_='Head') if h.find_parent(class_='etym') is None]
    output_heads=[n for n in walk(row[5]) if (n.get('data') or {}).get('class')=='ld-head']
    if len(source_heads)!=len(output_heads):
        head_pair_failures.append([key,len(source_heads),len(output_heads)])
        continue
    for h,out in zip(source_heads,output_heads):
        for infl in h.find_all('span',class_='Inflections'):
            for pron in infl.find_all('span',class_='PronCodes',recursive=False):
                ipa=[M.sc_text(p.get_text('',strip=True)).strip() for p in pron.find_all('span',class_='PRON')]
                missing=[p for p in ipa if p and p not in text(out)]
                if missing:
                    pron_findings.append({'word':key,'sequence':row[6],
                                          'source_inflections':M.collapse_ws(infl.get_text(' ',strip=True)),
                                          'package_head':text(out),'missing':missing})
result['mono_heading_candidate_words_tested']=len(mono_words)
result['mono_CJK_records_confirmed']=len(mono_findings)
result['mono_CJK_words_confirmed']=len({x['word'] for x in mono_findings})
result['package_inflection_ipa_missing_spans']=len(pron_findings)
result['package_inflection_ipa_missing_words']=len({x['word'] for x in pron_findings})
result['source_package_head_pair_failures']=head_pair_failures
result['mono_examples']=mono_findings[:8]
result['pron_examples']=pron_findings[:8]
dump('targeted_content_findings.json',{'POS':confirmed_pos,'mono':mono_findings,'inflection_IPA':pron_findings})
print('confirmed content',json.dumps({k:v for k,v in result.items() if not k.endswith('_examples')},ensure_ascii=False,indent=2),flush=True)

# Real source fixture, real CLI, first a passing build, then an invalid build
# into the same *audit-only* output directory. Production artifacts untouched.
fixtures=json.loads((OUT/'fixtures.json').read_text(encoding='utf-8'))
build_dir=OUT/'isolated_mono_build'
build_dir.mkdir(exist_ok=True)
for word in ('be','age'):
    write(word+'_fixture.mdx.txt',word+'\n'+fixtures[word][0]+'\n</>\n')
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
    proc=subprocess.run([sys.executable,str(ROOT/'converter/ldoce2yomitan.py'),
                         '-i',str(OUT/(word+'_fixture.mdx.txt')),'-o',str(build_dir),
                         '-m','mono','--no-progress','--revision','audit-2026.09.12'],
                         capture_output=True,text=True,encoding='utf-8',env=env,cwd=ROOT)
    log=proc.stdout+proc.stderr
    write('build_'+word+'.log',log)
    zips=list(build_dir.glob('*.zip'))
    assert len(zips)==1,(word,zips)
    artifact=zips[0]
    has_cjk=False
    with zipfile.ZipFile(artifact) as z:
        for name in z.namelist():
            if re.fullmatch(r'term_bank_\d+\.json',name) and M.CJK_RE.search(z.read(name).decode('utf-8')):
                has_cjk=True
    result['build_'+word]={'returncode':proc.returncode,'validation_failed':'[FAIL] Validation errors:' in log,
                         'prints_final_OK':'[OK] Dictionary package:' in log,'zip':str(artifact),
                         'zip_sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),'zip_has_CJK':has_cjk}
result['invalid_build_replaced_valid_zip']=(result['build_be']['zip']==result['build_age']['zip'] and
        result['build_be']['zip_sha256']!=result['build_age']['zip_sha256'] and
        not result['build_be']['validation_failed'] and result['build_age']['validation_failed'])

# Mutation test: the project's gapless-and-unique sequence promise is stronger
# than format-3's integer schema. Check both duplicates and a missing zero.
mutation=OUT/'duplicate_sequence.zip'
idx={'title':'audit fixture','format':3,'revision':'audit','sequenced':True,
     'sourceLanguage':'en','targetLanguage':'zh'}
rows=[[k,'','','',10,[{'type':'structured-content','content':{'tag':'div','content':k}}],0,''] for k in ('one','two')]
with zipfile.ZipFile(mutation,'w') as z:
    z.writestr('index.json',json.dumps(idx))
    z.writestr('tag_bank_1.json','[]')
    z.writestr('styles.css','')
    z.writestr('term_bank_1.json',json.dumps(rows))
errors,stats=M.validate_package(str(mutation),M.TermIndex(),'audit','bilingual')
result['duplicate_sequence_mutation']={'errors':errors,'stats':dict(stats),'input_sequences':[0,0]}
dump('targeted_results.json',result)
print('build and mutation results',json.dumps({k:v for k,v in result.items() if k.startswith('build_') or k.endswith('mutation') or k=='invalid_build_replaced_valid_zip'},ensure_ascii=False,indent=2))
assert result['build_be']['returncode']==0 and not result['build_be']['validation_failed']
assert result['build_age']['returncode']==0 and result['build_age']['validation_failed']
assert result['invalid_build_replaced_valid_zip']
