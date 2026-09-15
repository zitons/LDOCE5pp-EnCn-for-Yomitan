"""Rerun current non-browser regressions with explicit packages and fresh logs."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
import argparse
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--output',type=Path,default=Path(__file__).resolve().parent/'results/regressions')
ap.add_argument('--bilingual',type=Path,default=ROOT/'yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip')
ap.add_argument('--mono',type=Path,default=ROOT/'yomitan_full/LDOCE5pp_Yomitan_2026.09.13_EN.zip')
args=ap.parse_args()
OUT=args.output.resolve()
if not OUT.is_relative_to((Path(__file__).resolve().parent/'results').resolve()):
 raise SystemExit('Logs must stay under this audit results/ directory')
OUT.mkdir(exist_ok=False)
bilingual=args.bilingual.resolve()
mono=args.mono.resolve()
steps=[
 ('followup_fast','regress_review_followup.py',None),
 ('publication_and_sequence','audit_2026_09_12/regress_gates.py',None),
 ('bilingual_lists','regress_list_validity.py',bilingual),
 ('mono_lists','regress_list_validity.py',mono),
 ('bilingual_head_separation','regress_head_separation.py',bilingual),
 ('mono_head_separation','regress_head_separation.py',mono),
 ('inline_css','regress_inline_vs_css.py',bilingual),
 ('css_fallback','regress_css_fallback.py',None),
 ('markers','regress_scheme_b.py',bilingual),
 ('historical_content','audit_2026_09_12/regress_content.py',bilingual),
 ('headword_pollution','audit5_headword.py',bilingual),
]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
state={'packages':{str(p):sha(p) for p in (bilingual,mono)},'checks':[]}
for label,script,package in steps:
 cmd=[sys.executable,'-X','utf8','-u',str(ROOT/'converter'/script)]
 if package:cmd.append(str(package))
 print('RUN',label,flush=True);start=time.monotonic()
 with (OUT/(label+'.log')).open('w',encoding='utf-8') as log:
  proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT)
 state['checks'].append({'name':label,'command':cmd,'exit_code':proc.returncode,'seconds':round(time.monotonic()-start,1)})
 (OUT/'results.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(label,proc.returncode,'seconds',state['checks'][-1]['seconds'],flush=True)
state['packages_unchanged']=all(sha(Path(p))==digest for p,digest in state['packages'].items())
(OUT/'results.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
raise SystemExit(int(any(c['exit_code']!=0 for c in state['checks']) or not state['packages_unchanged']))