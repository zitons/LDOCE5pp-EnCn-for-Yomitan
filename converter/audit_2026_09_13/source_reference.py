"""Independent full-corpus DOM reference for A3, paired by occurrence, not key union."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys
import zipfile
from lxml import html

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'converter'))
import ldoce2yomitan as C
import _apply_patch as patch

ZIP=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'yomitan_full/LDOCE5pp_Yomitan_2026.09.12.zip'
metadata=defaultdict(list)
with zipfile.ZipFile(ZIP) as z:
    for name in z.namelist():
        if re.fullmatch(r'term_bank_\d+\.json',name):
            for row in json.loads(z.read(name)):
                if row[4]>0:metadata[row[0]].append([row[2],row[3],row[6]])
print('loaded metadata:',sum(map(len,metadata.values())),flush=True)
old=json.loads((ROOT/'converter/audit_2026_09_12/source_findings.json').read_text(encoding='utf-8'))['pos']
old_bad={f['word']:f for f in old if not any(r[:2]==f['reference'] for r in metadata.get(f['word'],[]))}
pos_xpath=html.etree.XPath("//span[contains(concat(' ', normalize-space(@class), ' '), ' lm5pp_POS ')]")
portrait_xpath=html.etree.XPath(".//span[contains(concat(' ', normalize-space(@class), ' '), ' portrait ')]")
freq_xpath=html.etree.XPath("//span[contains(concat(' ', normalize-space(@class), ' '), ' FREQ ')]")
occurrence=Counter();checked=0;bad=[];stale=[];parse_errors=[];wide=[]
for key,content in C.iter_records(ROOT/'extract/LDOCE5++ V 2-15.mdx.txt'):
    key=C.strip_invisible(key).strip()
    if key not in metadata or C.classify_record(key,content)[0]!='entry':continue
    which=occurrence[key];occurrence[key]+=1
    if which>=len(metadata[key]):
        bad.append({'word':key,'error':'missing entry occurrence'});continue
    got=metadata[key][which]
    try:tree=html.fromstring(content)
    except Exception as exc:
        parse_errors.append({'word':key,'error':str(exc)});continue
    tags=[];rules=[]
    for n in pos_xpath(tree):
        for p in portrait_xpath(n):
            if p.getparent() is not None:p.drop_tree()
        text=re.sub(r'\s+',' ',' '.join(n.itertext())).strip().lower().strip(' .;')
        for part in [text]+re.split('[,;]',text):
            part=part.strip(' .()')
            tag=C.POS_TAG_MAP.get(part)
            rule=C.POS_RULE_MAP.get(part)
            if tag and tag not in tags:tags.append(tag)
            if rule and rule not in rules:rules.append(rule)
    for n in freq_xpath(tree):
        match=re.match(r'([SW][123])(?![0-9])', ''.join(n.itertext()).strip())
        if match and match[1] not in tags:tags.append(match[1])
    reference=[' '.join(tags),' '.join(rules)]
    if set(tags)!=set(got[0].split()) or set(rules)!=set(got[1].split()):
        bad.append({'word':key,'occurrence':which,'reference':reference,'got':got[:2]})
    if key in old_bad:
        stale.append({'word':key,'old_reference':old_bad[key]['reference'],
                      'fresh_reference':reference,'got':got[:2]})
    if len(tags)>C.TAG_LIMIT:wide.append([key,len(tags)])
    checked+=1
    if checked%10000==0:print('checked=',checked,'mismatches=',len(bad),flush=True)
result={'package':str(ZIP),'entries_checked':checked,'mismatches':bad,
        'parse_errors':parse_errors,'old_gate_mismatches':stale,'wide_rows':wide}
patch.P=str(OUT/'source_reference_results.json');patch.write_atomic(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
if bad or parse_errors:sys.exit(1)
