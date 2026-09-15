"""Real CLI failure-path probes. All overwrites occur ONLY in new audit fixtures."""
import hashlib, json, subprocess, sys, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
import argparse
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'results/publication')
args = ap.parse_args()
OUT = args.output.resolve()
if not OUT.is_relative_to((Path(__file__).resolve().parent / 'results').resolve()):
    raise SystemExit('Publication fixtures must stay under this audit results/ directory')
if OUT.exists(): raise SystemExit('Refusing to overwrite existing fixture directory')
OUT.mkdir(parents=True)

def record(key, body):
    return key + '\n<div class="entry_content">' + body + '</div>\n</>\n'

def run(src, out, extra=()):
    cmd = [sys.executable,'-X','utf8',str(ROOT/'converter/ldoce2yomitan.py'),'-i',str(src),'-o',str(out),'--no-progress',*extra]
    proc = subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',cwd=ROOT)
    return {'command':cmd,'exit_code':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr}

def package_state(out):
    files = list(out.glob('*.zip')); assert len(files)==1, files
    p=files[0]
    with zipfile.ZipFile(p) as z:
        rows=[r for name in z.namelist() if name.startswith('term_bank_') for r in json.loads(z.read(name))]
    return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'expressions':[r[0] for r in rows if r[4]>0],'rows':len(rows)}

results=[]
for kind in ('empty_record','empty_same_key_record','limit_overwrite'):
    case=OUT/kind;case.mkdir();out=case/'out';src=case/'source.txt'
    second_key='kept' if kind=='empty_same_key_record' else 'lost'
    good=record('kept','<span class="DEF">Retained definition.</span>')+record(second_key,'<span class="DEF">Second definition.</span>')
    src.write_text(good,encoding='utf-8')
    baseline=run(src,out);assert baseline['exit_code']==0,baseline
    before=package_state(out)
    if kind.startswith('empty'):
        src.write_text(record('kept','<span class="DEF">Retained definition.</span>')+record(second_key,''),encoding='utf-8')
        attempt=run(src,out)
    else:
        attempt=run(src,out,('--limit','1'))
    after=package_state(out)
    rec={'case':kind,'before':before,'attempt':attempt,'after':after,'previous_package_preserved':before['sha256']==after['sha256']}
    results.append(rec)
    print(kind,'rc=',attempt['exit_code'],'before=',before['rows'],'after=',after['rows'],'preserved=',rec['previous_package_preserved'],flush=True)
(OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')