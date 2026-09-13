"""Reproduce mono failure and test failure-publication safety in fresh directories."""
import hashlib,json,re,subprocess,sys,time,zipfile
from pathlib import Path
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'converter'))
import ldoce2yomitan as C
import _apply_patch as patch

def write(path,text):
    patch.P=str(path);patch.write_atomic(text)
    assert path.read_bytes()==text.encode('utf-8')

def cli(source,dest,mode):
    args=[sys.executable,'-X','utf8','-u',str(ROOT/'converter/ldoce2yomitan.py'),'-i',str(source),'-o',str(dest),'-m',mode,'--no-progress','--revision','followup-audit']
    r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=120)
    return {'args':args,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}

def records_text(records):return ''.join(k+'\n'+c+'\n</>\n' for k,c in records)

def synthetic(word,text):
    return '<div class="entry_content"><div class="ldoceEntry"><span class="Head"><span class="HWD">'+word+'</span><span class="lm5pp_POS">noun</span></span><span class="Sense"><span class="DEF">'+text+'</span></span></div></div>'

def zip_words(path):
    with zipfile.ZipFile(path) as z:
        return [r[0] for n in z.namelist() if re.fullmatch(r'term_bank_\d+\.json',n) for r in json.loads(z.read(n)) if r[4]>0]

def main():
    dest=OUT/'builds'/time.strftime('%Y%m%d-%H%M%S');dest.mkdir(parents=True,exist_ok=False)
    wanted={'approximate','for','hardly','need'};records=[];excerpts=[]
    for key,content in C.iter_records(ROOT/'extract/LDOCE5++ V 2-15.mdx.txt'):
        if key not in wanted or C.classify_record(key,content)[0]!='entry':continue
        records.append((key,content))
        soup=BeautifulSoup(content,'lxml')
        if key=='approximate':
            for node in soup.find_all('span',class_='REGISTERLAB'):
                if C.CJK_RE.search(node.get_text()):excerpts.append({'word':key,'source_html':str(node)[:600]})
        elif key in {'for','hardly'}:
            for node in soup.find_all(class_='EXAMPLE'):
                if re.search(r'NOT\s*[\u3400-\u9fff]',node.get_text()):excerpts.append({'word':key,'source_html':str(node)[:700]})
        else:
            for node in soup.find_all('span',class_='heading'):
                if 'Verb patterns' in node.get_text():excerpts.append({'word':key,'source_html':str(node)[:800]})
    assert {k for k,c in records}==wanted
    fixture=dest/'mono_records.mdx.txt';write(fixture,records_text(records))
    mono=cli(fixture,dest/'mono','mono')
    print('MONO exit=',mono['exit_code'],flush=True)
    print(mono['stdout'][-1700:]+mono['stderr'],flush=True)
    write(dest/'mono.log',mono['stdout']+mono['stderr'])
    fixture2=dest/'render_records.mdx.txt'
    good_records=[('audit-ok',synthetic('audit-ok','a valid definition')),('audit-broken',synthetic('audit-broken','another valid definition'))]
    write(fixture2,records_text(good_records));good=cli(fixture2,dest/'render','bilingual')
    assert good['exit_code']==0,good
    zips=list((dest/'render').glob('*.zip'));assert len(zips)==1
    package=zips[0];good_sha=hashlib.sha256(package.read_bytes()).hexdigest();good_words=zip_words(package)
    deep='<span>'*450+'deep definition'+'</span>'*450
    write(fixture2,records_text([good_records[0],('audit-broken',synthetic('audit-broken',deep))]))
    bad=cli(fixture2,dest/'render','bilingual')
    bad_sha=hashlib.sha256(package.read_bytes()).hexdigest();bad_words=zip_words(package)
    print('DEEP RENDER exit=',bad['exit_code'],'before=',good_words,'after=',bad_words,'same_zip=',good_sha==bad_sha,flush=True)
    print(bad['stdout'][-1700:]+bad['stderr'],flush=True)
    write(dest/'render_bad.log',bad['stdout']+bad['stderr'])
    result={'directory':str(dest),'source_records':len(records),'source_excerpts':excerpts,'mono':mono,
            'render_failure':{'good_exit_code':good['exit_code'],'good_words':good_words,'good_sha256':good_sha,'after_words':bad_words,'after_sha256':bad_sha,**bad}}
    write(OUT/'build_results.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'source_excerpts':excerpts},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
