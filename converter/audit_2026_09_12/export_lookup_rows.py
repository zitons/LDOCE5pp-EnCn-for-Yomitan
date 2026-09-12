"""Export compact current-bank metadata for the official English transformer probe."""
import json, re, sys, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'converter'))
import _apply_patch as patch
rows=[]
with zipfile.ZipFile(ROOT/'yomitan_full/LDOCE5pp_Yomitan_2026.09.11.zip') as z:
    for name in z.namelist():
        if not re.fullmatch(r'term_bank_\d+\.json',name): continue
        for r in json.loads(z.read(name)):
            rows.append([r[0],r[3],None if r[4]>0 else [x[0] for x in r[5]],r[6]])
findings=json.loads((OUT/'source_findings.json').read_text(encoding='utf-8'))
pos_reference={x['word']:x['reference'][1] for x in findings['pos']}
patch.P=str(OUT/'lookup_rows.json')
patch.write_atomic(json.dumps({'rows':rows,'pos_reference':pos_reference},ensure_ascii=False,separators=(',',':')))
print('exported',len(rows),'current-bank metadata rows')
