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
# Alignment-fix eligibility, PR #10 review round.  Two hard lessons are built
# into this checker:
#
# 1. STRIP COMMENTS BEFORE MATCHING.  The stylesheet now carries a
#    documentation block ("three other forms were measured and rejected: ...
#    text-indent:-1.6em ..."), and a raw-substring match reads that prose as a
#    live declaration -- FIX_MARK matched the comment and rejected every correct
#    package on disk, which silently SKIPped both alignment gates while the
#    suite stayed green.
# 2. JUDGE BY SELECTOR + PROPERTY, not by substring.  The hang may be built
#    with margin-left (D44) or padding-left + an in-flow fixed-width bullet
#    (PR #10); both are geometrically equivalent.  What must hold is: the five
#    hanging classes resolve a left indent of the expected size, their ::before
#    hangs out to the left, and NO hanging class uses text-indent (it inherits,
#    which is the mechanism behind D42/D43).
_HANGING_CLASSES=['ld-ex','ld-ex-good','ld-ex-bad','ld-gramexa','ld-colloexa']
_HANGING_INDENT={'ld-ex':'1.6em','ld-ex-good':'1.6em','ld-ex-bad':'1.6em',
                 'ld-gramexa':'1.6em','ld-colloexa':'1.6em'}

def _css_rules(css):
 flat=re.sub(r'/\*.*?\*/','',css,flags=re.S)
 return [(re.sub(r'\s+',' ',a).strip(),b)
         for a,b in re.findall(r'([^{}]+)\{([^{}]*)\}',flat)]

def _left_indent(body):
 for prop in ('margin-left','padding-left'):
  m=re.search(rf'(?<![-\w]){prop}\s*:\s*([^;]+)',body)
  if m: return m.group(1).strip()
 for shorthand in ('margin','padding'):
  m=re.search(rf'(?<![-\w]){shorthand}\s*:\s*([^;]+)',body)
  if m:
   parts=m.group(1).split()
   if len(parts)==4: return parts[3]
   if len(parts) in (2,3): return parts[1]
   if len(parts)==1: return parts[0]
 return None

def has_alignment_fix(pkg):
 try:
  css=zipfile.ZipFile(pkg).read('styles.css').decode('utf-8','replace')
 except Exception:
  return False
 rules=_css_rules(css)
 for cls in _HANGING_CLASSES:
  base=[b for sel,b in rules
        if re.search(rf'\[data-sc-class="{cls}"\]',sel) and '::before' not in sel]
  if not base:
   return False
  left=_left_indent(base[0])
  if not left or not left.startswith(_HANGING_INDENT[cls].split('em')[0]):
   return False
  before=[b for sel,b in rules if f'[data-sc-class="{cls}"]::before' in sel]
  if not before:
   return False
  b=before[0]
  ml=re.search(r'(?<![-\w])margin-left\s*:\s*([^;]+)',b)
  pos=re.search(r'(?<![-\w])position\s*:\s*([^;]+)',b)
  leftpos=re.search(r'(?<![-\w])left\s*:\s*([^;]+)',b)
  hangs=((ml and ml.group(1).strip().startswith('-'))
         or (pos and pos.group(1).strip()=='absolute'
             and leftpos and leftpos.group(1).strip().startswith('-')))
  if not hangs:
   return False
  ti=re.search(r'(?<![-\w])text-indent\s*:\s*([^;]+)',b)
  if ti and ti.group(1).strip() not in ('0','0px'):
   return False
 return True

def newest_fixed_package(mode):
 """Newest non-DEBUG package whose stylesheet carries the alignment fix.

 Selecting by the fix itself -- rather than by directory name or mtime alone -- stays
 correct across rebuilds and renames: a pre-fix package is simply never eligible.
 The marker judges the GEOMETRY (left indent + hanging bullet, no text-indent on
 a hanging class), so it matches both the D44 margin-left scheme and the PR #10
 padding/bullet scheme.
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
# A FIXED output name means the second run of the day either clobbers the first
# run's evidence or refuses to start (mkdir(exist_ok=False)) -- the PR #10 round
# produced exactly that: the standard line's results.json was overwritten by a
# compact re-run and could not be told apart afterwards.  Timestamp every run.
if args.output == Path(__file__).resolve().parent/'results/regressions':
 args.output=args.output.parent/f"regressions_{time.strftime('%Y%m%d_%H%M%S')}"
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
# A missing alignment package is NOT a silent skip: has_alignment_fix() is the
# gate that decides whether the two most important checks run at all, and the
# PR #10 round proved it can reject every package on disk while the suite stays
# green.  Say so loudly and fail, unless the caller passed packages explicitly
# (then a wrong --alignment-* argument is the caller's responsibility and the
# run proceeds).
if args.alignment_bilingual is None and align_bi is None:
 print('FAIL: no package on disk carries the alignment fix -- both alignment '
       'gates would be skipped. Rebuild, or pass --alignment-bilingual/--alignment-mono.',
       flush=True)
 raise SystemExit(1)
SKIP_CODE=2
# exit 2 means "prerequisite missing" and only these steps may turn it into a skip
SKIP_OK={'bilingual_alignment','mono_alignment','hanging_indent'}
# ...but only the alignment steps genuinely need a package on the command line.
# regress_hanging_indent.py tests the stylesheet and takes no package, so lumping
# it in here made line 122 skip it before it ever ran.
NEEDS_PKG={'bilingual_alignment','mono_alignment'}
steps=[
 ('followup_fast','regress_review_followup.py',None),
 ('publication_and_sequence','audit_2026_09_12/regress_gates.py',None),
 ('bilingual_lists','regress_list_validity.py',bilingual),
 ('mono_lists','regress_list_validity.py',mono),
 # Hierarchy: a node can be valid on its own and still sit one level too deep.
 # No earlier gate looked at "is this item at the right level", so 47,611
 # wrapper <li>, 23,930 subsenses inside an <ol> and 22,279 nested example
 # lists all passed 14/14. See regress_hierarchy.py.
 ('bilingual_hierarchy','regress_hierarchy.py',bilingual),
 ('mono_hierarchy','regress_hierarchy.py',mono),
 ('bilingual_head_separation','regress_head_separation.py',bilingual),
 ('mono_head_separation','regress_head_separation.py',mono),
 ('inline_css','regress_inline_vs_css.py',bilingual),
 ('css_fallback','regress_css_fallback.py',None),
 ('markers','regress_scheme_b.py',bilingual),
 ('bilingual_alignment','regress_alignment.py',align_bi),
 ('mono_alignment','regress_alignment.py',align_mo),
 # D44: the hanging-indent gate. Static + dynamic, needs Chrome, so a missing
 # browser must degrade to SKIP, not FAIL -- the same contract as the
 # alignment steps above (SKIP_OK).
 ('hanging_indent','regress_hanging_indent.py',None),
 ('historical_content','audit_2026_09_12/regress_content.py',bilingual),
 ('headword_pollution','audit5_headword.py',bilingual),
]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
state={'packages':{str(p):sha(p) for p in (bilingual,mono)},
       'alignment_packages':{str(p):sha(p) for p in (align_bi,align_mo) if p},
       'checks':[]}
save=lambda:(OUT/'results.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for label,script,package in steps:
 if label in NEEDS_PKG and package is None:
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
