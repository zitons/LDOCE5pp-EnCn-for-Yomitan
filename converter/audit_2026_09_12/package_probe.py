"""Audit the pinned shipped archive, all metadata/aliases and stratified rerenders.
No production files are modified. Evidence is written atomically beside this file.
"""
import collections
import hashlib
import json
import random
import re
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'converter'))
import ldoce2yomitan as M
import _apply_patch as patch

ZIP = ROOT / 'yomitan_full/LDOCE5pp_Yomitan_2026.09.11.zip'
SIDE = ROOT / 'extract/LDOCE5++ V 2-15.mdx.txt'


def dump(name, obj):
    patch.P = str(OUT / name)
    patch.write_atomic(json.dumps(obj, ensure_ascii=False, indent=2))


def walk(n):
    if isinstance(n, list):
        for c in n:
            yield from walk(c)
    elif isinstance(n, dict):
        yield n
        if n.get('type') == 'structured-content' or 'tag' in n:
            yield from walk(n.get('content', []))


def resolve_targets(word, target_map, entries, fold, norm):
    result, seen = [], set()
    pending = list(target_map.get(word, []))
    while pending:
        t = pending.pop()
        if t in seen:
            continue
        seen.add(t)
        hit = t
        if hit not in entries:
            hit = fold.get(t.casefold()) or norm.get(M.norm_target(t)) or t
        if hit in entries:
            if hit not in result:
                result.append(hit)
        elif t in target_map:
            pending.extend(target_map[t])
    return result


start = time.time()
result = {'archive': str(ZIP), 'archive_sha256': hashlib.sha256(ZIP.read_bytes()).hexdigest(),
          'converter_sha256':hashlib.sha256((ROOT/'converter/ldoce2yomitan.py').read_bytes()).hexdigest()}
entry_specs = []
alias_rows = {}
entry_counts = collections.Counter()
entry_rule_union = collections.defaultdict(set)
seqs = []
expected_frequency = set()
sizes = []
with zipfile.ZipFile(ZIP) as z:
    banks = sorted((n for n in z.namelist() if re.fullmatch(r'term_bank_\d+\.json', n)),
                   key=lambda n: int(re.search(r'\d+', n).group()))
    result['zip_duplicate_names'] = len(z.namelist()) - len(set(z.namelist()))
    result['zip_crc_failure'] = z.testzip()
    idx = json.loads(z.read('index.json'))
    result['index'] = idx
    result['css_matches_current_code'] = z.read('styles.css').decode('utf-8') == M.generate_css()
    result['tag_bank_matches_current_code'] = json.loads(z.read('tag_bank_1.json')) == M.build_tag_bank(True)
    for name in banks:
        for row in json.loads(z.read(name)):
            seqs.append(row[6])
            if row[4] > 0:
                entry_specs.append([row[0], row[2], row[3], row[6]])
                entry_counts[row[0]] += 1
                entry_rule_union[row[0]].update(row[3].split())
                expected_frequency.update((row[0], code, M.FREQ_VALUE[code])
                                          for code in row[2].split() if code in M.FREQ_VALUE)
                sizes.append((len(json.dumps(row[5],ensure_ascii=False)), row[6]))
            else:
                alias_rows[row[0]] = row
    frequencies = []
    for name in z.namelist():
        if re.fullmatch(r'term_meta_bank_\d+\.json', name):
            frequencies.extend(json.loads(z.read(name)))
    actual_frequency = {(x[0],x[2]['displayValue'],x[2]['value']) for x in frequencies}
    result.update(rows=len(seqs), entries=len(entry_specs), aliases=len(alias_rows),
                  duplicate_entry_expressions=sum(c>1 for c in entry_counts.values()),
                  sequence_exact=sorted(seqs)==list(range(len(seqs))),
                  frequency_rows=len(frequencies), frequency_missing=sorted(expected_frequency-actual_frequency),
                  frequency_extra=sorted(actual_frequency-expected_frequency))
    incomplete_alias_rules=[]
    for word,row in alias_rows.items():
        union=set()
        for target,_ in row[5]:
            union.update(entry_rule_union[target])
        if union != set(row[3].split()):
            incomplete_alias_rules.append([word,row[3],sorted(union),row[5]])
    result['alias_rules_not_union_of_target_rows']=incomplete_alias_rules
    sample=set(random.Random(20260912).sample([s[3] for s in entry_specs],512))
    named={'A','the','andante','Algeria','4-F','bad','be','age','backpedal','run','love','heart',
           'close','improve','child','children','good','well','read','foot','woman','mouse'}
    sample.update(s[3] for s in entry_specs if s[0] in named or entry_counts[s[0]]>1)
    sizes.sort()
    sample.update(s[1] for s in sizes[:15]+sizes[-15:])
    shipped={}
    for name in banks:
        for row in json.loads(z.read(name)):
            if row[6] in sample:
                shipped[row[6]]=row
    payload=[{'word':f'{row[0]} [seq={seq}]','content':row[5][0]['content']}
             for seq,row in sorted(shipped.items())]
    dump('generator_payload.json',payload)
    print('archive',json.dumps({k:result[k] for k in ('rows','entries','aliases','sequence_exact','frequency_rows')},ensure_ascii=False),flush=True)
    print('selected exact row identities',len(sample),'including all duplicate-expression rows',flush=True)

# Recreate index in source order; compare *every* entry's cheap metadata.
ti=M.TermIndex()
target_map={}
contents={}
entry_ordinal=0
key_rules={}
metadata_mismatches=[]
for key,content in M.iter_records(SIDE):
    key=M.strip_invisible(key).strip()
    kind,target=M.classify_record(key,content)
    if kind=='entry':
        ti.add(key)
        tags,rules=M.pos_tags_rules(*M.extract_tags(content))
        key_rules[key]=rules
        expected=entry_specs[entry_ordinal]
        if expected[:3] != [key,tags,rules] or expected[3]!=entry_ordinal:
            metadata_mismatches.append([entry_ordinal,[key,tags,rules],expected])
        if entry_ordinal in sample:
            contents[entry_ordinal]=(key,content)
        entry_ordinal+=1
    elif kind=='redirect' and target and target!=key:
        target_map.setdefault(key,[]).append(target)
result['source_entry_metadata_comparisons']=entry_ordinal
result['source_entry_metadata_mismatches']=metadata_mismatches
fold={k.casefold():k for k in ti.exact}
norm={M.norm_target(k):k for k in ti.exact}
expected_alias={}
for word in target_map:
    if word in ti.exact:
        continue
    targets=resolve_targets(word,target_map,ti.exact,fold,norm)
    if targets:
        ti.add_alias_word(word)
        rules=' '.join(dict.fromkeys(t for target in targets for t in key_rules[target].split()))
        expected_alias[word]=(rules,[[target,['redirect']] for target in targets])
result['source_alias_missing_from_package']=sorted(set(expected_alias)-set(alias_rows))
result['package_alias_missing_from_source_plan']=sorted(set(alias_rows)-set(expected_alias))
alias_mismatches=[]
for word,(rules,gloss) in expected_alias.items():
    got=alias_rows.get(word)
    if got and (got[3]!=rules or got[5]!=gloss):
        alias_mismatches.append({'word':word,'package':[got[3],got[5]],'replayed':[rules,gloss]})
result['alias_replay_mismatches']=alias_mismatches
print('source metadata mismatches',len(metadata_mismatches),'alias replay mismatches',len(alias_mismatches),flush=True)

renderer=M.LdoceRenderer(ti)
rerender_mismatches=[]
for i,(seq,(key,content)) in enumerate(sorted(contents.items())):
    nodes=renderer.render_record(key,content)
    tags,rules=M.pos_tags_rules(*M.extract_tags(content))
    row=[key,'',tags,rules,M.ENTRY_SCORE,[{'type':'structured-content','content':M.sc('div',nodes,cls='ld')}],seq,'']
    actual=M.sanitize_strings(row)
    if actual != shipped[seq]:
        rerender_mismatches.append({'word':key,'sequence':seq})
    if (i+1)%250==0:
        print('rerendered',i+1,flush=True)
result['rerendered_rows']=len(contents)
result['rerender_mismatches']=rerender_mismatches
errors,stats=M.validate_package(str(ZIP),ti,idx['revision'],'bilingual',full_rows=True)
result['builtin_validation_errors']=errors
result['builtin_validation_stats']=dict(stats)
result['elapsed_seconds']=round(time.time()-start,2)
dump('package_results.json',result)
print(json.dumps({k: (len(v) if k == 'alias_rules_not_union_of_target_rows' else v) for k,v in result.items()},ensure_ascii=False,indent=2))
"""Nonzero status is reserved for failures of this pinned-package consistency test.
Semantic source defects are recorded by source_probe.py, independently of this gate.
"""
assert not errors and result['sequence_exact'] and not metadata_mismatches and not rerender_mismatches
assert not result['source_alias_missing_from_package'] and not result['package_alias_missing_from_source_plan']
