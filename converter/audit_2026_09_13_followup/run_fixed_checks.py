"""Wait for both full builds, then run and checkpoint non-browser package gates."""
import argparse,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'converter'))
import _apply_patch as patch
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--root',type=Path,default=ROOT/'yomitan_fixed/verified')
args=ap.parse_args();out=args.root.resolve()
files={m:out/m/'build_manifest.json' for m in ('bilingual','mono')}
last={};deadline=time.monotonic()+2700
while not all(p.exists() for p in files.values()):
    if time.monotonic()>deadline:raise SystemExit('Timed out waiting for full build manifests; no success assumed.')
    for m,p in files.items():
        log=out/m/'build.log'
        if log.exists():
            tail=log.read_text(encoding='utf-8',errors='replace').splitlines()[-1:]
            if tail and last.get(m)!=tail[0]:print(m,tail[0],flush=True);last[m]=tail[0]
    time.sleep(15)
manifests={m:json.loads(p.read_text(encoding='utf-8')) for m,p in files.items()}
paths={}
for m,info in manifests.items():
    if info['exit_code']!=0 or not info['source_unchanged_during_build']:
        raise SystemExit(f'{m} build failed; see {out/m/"build.log"}')
    assert len(info['packages'])==1
    paths[m]=info['packages'][0]['path']
steps=[
 ('all_row_comparison',[str(HERE/'verify_fixed.py'),'--root',str(out)]),
 ('bilingual_structure',[str(ROOT/'converter/audit4_structure.py'),paths['bilingual']]),
 ('mono_structure',[str(ROOT/'converter/audit4_structure.py'),paths['mono']]),
 ('bilingual_reproduce',[str(ROOT/'converter/audit3_reproduce.py'),paths['bilingual']]),
 ('bilingual_headword',[str(ROOT/'converter/audit5_headword.py'),paths['bilingual']]),
 ('bilingual_lists',[str(ROOT/'converter/regress_list_validity.py'),paths['bilingual']]),
 ('mono_lists',[str(ROOT/'converter/regress_list_validity.py'),paths['mono']]),
 ('bilingual_head_separation',[str(ROOT/'converter/regress_head_separation.py'),paths['bilingual']]),
 ('previous_content_regressions',[str(ROOT/'converter/audit_2026_09_12/regress_content.py'),paths['bilingual']]),
]
checkpoint=out/'post_checks.json'
fingerprint={m:{k:v[k] for k in ('path','sha256')} for m,v in ((m,manifests[m]['packages'][0]) for m in manifests)}
state={'packages':fingerprint,'checks':[]}
if checkpoint.exists():
    previous=json.loads(checkpoint.read_text(encoding='utf-8'))
    if previous.get('packages')==fingerprint:state=previous
for label,arguments in steps:
    prior=next((r for r in state['checks'] if r['name']==label),None)
    if prior and prior['exit_code']==0:print('already passed',label,flush=True);continue
    command=[sys.executable,'-X','utf8','-u']+arguments
    log=out/(label+'.log');started=time.time();print('RUN',label,flush=True)
    with log.open('w',encoding='utf-8',newline='\n') as handle:
        result=subprocess.run(command,cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT)
    rec={'name':label,'exit_code':result.returncode,'elapsed_seconds':round(time.time()-started,1),'log':str(log)}
    state['checks']=[r for r in state['checks'] if r['name']!=label]+[rec]
    patch.P=str(checkpoint);patch.write_atomic(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(rec),flush=True)
    if result.returncode:
        print(log.read_text(encoding='utf-8')[-10000:],flush=True)
        raise SystemExit(result.returncode)
print('All non-browser post-build gates completed.',flush=True)
