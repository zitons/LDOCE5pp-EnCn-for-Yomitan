"""Rerun current regressions with explicit packages and fresh logs.

Mostly non-browser. It also includes TWO browser-based steps, `regress_alignment.py`
(REVIEW D42/D43) for each mode, which need jsdom + headless Chrome AND a package that
actually CONTAINS the fix.

Two traps this harness must avoid, both raised in review:

  * the alignment steps must not use the `--bilingual/--mono` packages while those
    still default to a pre-fix build: the gate would then correctly FAIL against a
    known-broken baseline even though the current source is fine. They therefore
    have their own `--alignment-*` arguments, auto-discovered as the newest
    non-DEBUG package under yomitan_fixed/ whose styles.css carries the fix.
  * exit code 2 is NOT exclusive to missing prerequisites -- regress_head_separation,
    regress_render_contract, audit_nocss_final and audit_def_ex_geometry all use it
    too. Only the steps in SKIP_OK may be reclassified as skipped; for every other
    step any non-zero exit is a failure, whatever its value.
"""
import hashlib,json,re,subprocess,sys,time,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
import argparse

# A package is eligible for the alignment gate when its stylesheet carries the
# D42/D43 fix. Test the SUBSTANCE, not one specific rule: the original marker was
# the D42 descendant reset (`ld-colloexa *`), which D44 then deleted as unnecessary
# -- so a rule-literal marker silently rejected every post-D44 package and fell
# back to the previous one. These properties hold for both the D42 patch and the
# D44 rewrite: no negative text-indent anywhere, and the hanging classes use a
# positive margin-left.
FIX_MARK=re.compile(r'text-indent\s*:\s*-')
HANGING_MARK=re.compile(r'\[data-sc-class="ld-ex"\][^{]*\{[^}]*margin[^;}]*1\.6em')

def has_alignment_fix(pkg):
 try:
  css=zipfile.ZipFile(pkg).read('styles.css').decode('utf-8','replace')
 except Exception:
  return False
 if FIX_MARK.search(css):
  return False          # still on the fragile text-indent scheme
 return bool(HANGING_MARK.search(css))

def newest_fixed_package(mode):
 """Newest non-DEBUG package whose stylesheet carries the D42/D43 fix.

 Selecting by the fix itself -- rather than by directory name or mtime alone -- stays
 correct across rebuilds and renames: a pre-fix package is simply never eligible.
 The marker tests the substance (no negative text-indent + margin-left indents), so
 it keeps matching after the D44 rewrite replaced the original D42 band-aid rule.
 """
 for p in newest_first(mode):
  if has_alignment_fix(p):
   return p
 return None

def newest_first(mode):
 """Candidate packages under yomitan_fixed/, newest first, filtered by mode."""
 cands=[p for p in (ROOT/'yomitan_fixed').rglob('LDOCE5pp_Yomitan_*.zip') if '_DEBUG' not in p.name]
 if mode=='mono':
  cands=[p for p in cands if p.stem.endswith('_EN')]
 else:
  cands=[p for p in cands if not p.stem.endswith('_EN')]
 return sorted(cands,key=lambda q:q.stat().st_mtime,reverse=True)

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--output',type=Path,default=Path(__file__).resolve().parent/'results/regressions')
# The defaults are the CURRENT build under yomitan_fixed/, not the last released
# package: several steps compare a package against the current source (e.g.
# regress_content's "CSS matches current generate_css()"), so pointing them at a
# pre-fix build makes them fail even though nothing is wrong. yomitan_full/ is only
# a fallback for a checkout with no local build.
def _default(mode):
 got=newest_first(mode)
 return got[0] if got else ROOT/('yomitan_full/LDOCE5pp_Yomitan_2026.09.13'
                                 + ('_EN' if mode=='mono' else '')+'.zip')
ap.add_argument('--bilingual',type=Path,default=_default('bilingual'))
ap.add_argument('--mono',type=Path,default=_default('mono'))
ap.add_argument('--alignment-bilingual',type=Path,default=None,
                help='package WITH the D42/D43 fix (default: auto-discovered)')
ap.add_argument('--alignment-mono',type=Path,default=None,
                help='package WITH the D42/D43 fix (default: auto-discovered)')
args=ap.parse_args()
OUT=args.output.resolve()
if not OUT.is_relative_to((Path(__file__).resolve().parent/'results').resolve()):
 raise SystemExit('Logs must stay under this audit results/ directory')
OUT.mkdir(exist_ok=False)
bilingual=args.bilingual.resolve()
mono=args.mono.resolve()
align_bi=args.alignment_bilingual or newest_fixed_package('bilingual')
align_mo=args.alignment_mono or newest_fixed_package('mono')
align_bi=align_bi.resolve() if align_bi else None
align_mo=align_mo.resolve() if align_mo else None
print('alignment packages:',align_bi or '(none found)',align_mo or '(none found)',flush=True)
SKIP_CODE=2
# only these steps may turn exit 2 into "skipped"; every other non-zero exit is a failure
SKIP_OK={'bilingual_alignment','mono_alignment'}
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
 ('bilingual_alignment','regress_alignment.py',align_bi),
 ('mono_alignment','regress_alignment.py',align_mo),
 ('historical_content','audit_2026_09_12/regress_content.py',bilingual),
 ('headword_pollution','audit5_headword.py',bilingual),
]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
state={'packages':{str(p):sha(p) for p in (bilingual,mono)},
       'alignment_packages':{str(p):sha(p) for p in (align_bi,align_mo) if p},
       'checks':[]}
save=lambda:(OUT/'results.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for label,script,package in steps:
 if label in SKIP_OK and package is None:
  state['checks'].append({'name':label,'command':None,'exit_code':None,'skipped':True,
                          'reason':'no package containing the D42/D43 fix was found'})
  save(); print('SKIP',label,'-- pass --alignment-bilingual/--alignment-mono',flush=True)
  continue
 cmd=[sys.executable,'-X','utf8','-u',str(ROOT/'converter'/script)]
 if package:cmd.append(str(package))
 print('RUN',label,flush=True);start=time.monotonic()
 with (OUT/(label+'.log')).open('w',encoding='utf-8') as log:
  proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT)
 skipped=proc.returncode==SKIP_CODE and label in SKIP_OK
 state['checks'].append({'name':label,'command':cmd,'exit_code':proc.returncode,
                         'skipped':skipped,'seconds':round(time.monotonic()-start,1)})
 save()
 note='SKIPPED (harness prerequisites missing -- see log)' if skipped else ''
 print(label,proc.returncode,note,'seconds',state['checks'][-1]['seconds'],flush=True)
state['packages_unchanged']=all(sha(Path(p))==digest for p,digest in state['packages'].items())
state['alignment_packages_unchanged']=all(sha(Path(p))==digest
                                          for p,digest in state['alignment_packages'].items())
save()
skipped=[c['name'] for c in state['checks'] if c['skipped']]
failed=[c['name'] for c in state['checks'] if (c['exit_code'] or 0)!=0 and not c['skipped']]
if skipped:
 print('WARNING: these checks did not run:',', '.join(skipped),flush=True)
 print('         (the run is NOT a pass -- install the prerequisites or pass the package)',flush=True)
if failed:
 print('FAILED:',', '.join(failed),flush=True)
raise SystemExit(int(bool(failed) or bool(skipped) or not state['packages_unchanged']
                     or not state['alignment_packages_unchanged']))
