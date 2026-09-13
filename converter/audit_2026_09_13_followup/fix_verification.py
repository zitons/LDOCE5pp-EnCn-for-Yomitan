"""Verify all previously identified suffix cases and every non-glossary row field."""
from collections import defaultdict
import json,re,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'converter'))
import _apply_patch as patch
sys.path.insert(0,str(OUT))
from package_probe import flat
NEW=ROOT/'yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip'
OLD=ROOT/'yomitan_full/LDOCE5pp_Yomitan_2026.09.12.zip'
known=json.loads((ROOT/'converter/audit_2026_09_13/suffix_results.json').read_text(encoding='utf-8'))['examples']
by_word=defaultdict(list)
for case in known:by_word[case['word']].append(case)
meta_changes=[];fixed=[];failed=[];rows=0
with zipfile.ZipFile(NEW) as zn,zipfile.ZipFile(OLD) as zo:
    banks=sorted((n for n in zn.namelist() if re.fullmatch(r'term_bank_\d+\.json',n)),key=lambda n:int(re.search(r'\d+',n)[0]))
    for name in banks:
        nr=json.loads(zn.read(name));old=json.loads(zo.read(name));assert len(nr)==len(old)
        for a,b in zip(nr,old):
            rows+=1
            if a[:5]+a[6:]!=b[:5]+b[6:]:meta_changes.append([a[0],a[6]])
            if a[4]>0 and a[0] in by_word:
                text=flat(a[5])
                for case in by_word[a[0]]:
                    rec={'word':a[0],'before':case['before'],'after':case['after'],
                         'restored_text_present':case['before'] in text,
                         'bad_text_absent':case['after'] not in text}
                    (fixed if rec['restored_text_present'] and rec['bad_text_absent'] else failed).append(rec)
result={'rows_compared':rows,'non_glossary_field_changes':meta_changes,'known_suffix_cases_fixed':fixed,'known_suffix_cases_failed':failed}
patch.P=str(OUT/'fix_verification_results.json')
s=json.dumps(result,ensure_ascii=False,indent=2)+'\n';patch.write_atomic(s)
assert Path(patch.P).read_bytes()==s.encode('utf-8')
print(json.dumps({'rows_compared':rows,'metadata_changes':len(meta_changes),'known_suffix_cases_fixed':len(fixed),'known_suffix_cases_failed':failed},ensure_ascii=False,indent=2))
if meta_changes or failed:sys.exit(1)
