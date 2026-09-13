"""Run a full, validated CLI build in a NEW directory and retain UTF-8 evidence."""
import argparse
from datetime import date
import hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'converter'))
import _apply_patch as patch

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('mode',choices=('bilingual','mono'))
ap.add_argument('--output',type=Path)
args=ap.parse_args()
out=(args.output or ROOT/'yomitan_fixed'/args.mode).resolve()
if out.exists():raise SystemExit(f'Refusing to overwrite an existing verification directory: {out}')
out.mkdir(parents=True)
source=ROOT/'converter/ldoce2yomitan.py'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=sha(source);start=time.time()
cmd=[sys.executable,'-X','utf8','-u',str(source),'-i',str(ROOT/'extract/LDOCE5++ V 2-15.mdx.txt'),
     '-o',str(out),'-m',args.mode,'--revision',date.today().strftime('%Y.%m.%d')+'-followup-fix','--no-progress']
with (out/'build.log').open('w',encoding='utf-8',newline='\n') as log:
    with subprocess.Popen(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8') as proc:
        for line in proc.stdout:
            log.write(line);log.flush();print(line,end='',flush=True)
        code=proc.wait()
manifest={'command':cmd,'exit_code':code,'elapsed_seconds':round(time.time()-start,1),
          'converter_sha256':before,'source_unchanged_during_build':before==sha(source),
          'packages':[{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in out.glob('*.zip')]}
patch.P=str(out/'build_manifest.json');patch.write_atomic(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(manifest,ensure_ascii=False,indent=2),flush=True)
raise SystemExit(code or (0 if manifest['source_unchanged_during_build'] else 3))
