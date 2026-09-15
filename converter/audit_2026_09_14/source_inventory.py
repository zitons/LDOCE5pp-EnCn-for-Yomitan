"""Independent lxml/source probes, not a comparison against an earlier converter.
Candidates are NOT automatically findings; retain source and package context.
"""
from collections import Counter
import hashlib, json, re, sys, time, zipfile
from pathlib import Path
from lxml import html, etree
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'results'
SOURCE = ROOT / 'extract/LDOCE5++ V 2-15.mdx.txt'
import argparse
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('package', nargs='?', type=Path, default=ROOT / 'yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip')
ap.add_argument('--output', type=Path, default=OUT / 'source_inventory.json')
args = ap.parse_args()
PACKAGE = args.package.resolve()
RESULT = args.output.resolve()
if not RESULT.is_relative_to(OUT.resolve()):
    raise SystemExit('Inventory results must stay under this audit results/ directory')

def records(path):
    key = None; lines = []
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            line = line.rstrip('\r\n')
            if line == '</>':
                if key is not None: yield key, '\n'.join(lines)
                key = None; lines = []
            elif key is None: key = line
            else: lines.append(line)
        if key is not None: yield key, '\n'.join(lines)

def flat(x):
    if isinstance(x, str): return x
    if isinstance(x, list): return ''.join(map(flat, x))
    if isinstance(x, dict): return flat(x.get('content', ''))
    return ''

def cls(e): return set((e.get('class') or '').split()) if isinstance(e.tag, str) else set()
def text(e): return ''.join(e.itertext())
def compact(t): return re.sub(r'\s+', ' ', t).strip()
def snippet(e): return etree.tostring(e, encoding='unicode', method='html')[:1800]

started = time.monotonic(); lexicon = set(); packaged = {}; metadata = {}; occurrences = Counter()
with zipfile.ZipFile(PACKAGE) as z:
    for name in sorted((n for n in z.namelist() if re.fullmatch(r'term_bank_\d+\.json', n)), key=lambda n:int(re.search(r'\d+', n)[0])):
        for row in json.loads(z.read(name)):
            if re.fullmatch('[A-Za-z]{3,30}', row[0]): lexicon.add(row[0].lower())
            if row[4] > 0:
                packaged[(row[0], occurrences[row[0]])] = flat(row[5])
                metadata[(row[0], occurrences[row[0]])] = (row[2], row[3])
                occurrences[row[0]] += 1
print('Loaded', len(packaged), 'content rows;', len(lexicon), 'lexical words', flush=True)
counts = Counter(); candidates = []; structural = []; metadata_errors = []; occurrences.clear(); duplicates = set()
prose = {'DEF', 'english', 'EXAMPLE', 'exa', 'GOODEXA', 'BADEXA', 'GramExa', 'ColloExa'}
exclude = {'Head', 'Inflections', 'wordfams', 'cn_txt', 'cn_txt_ext', 'portrait', 'GRAM', 'REGISTERLAB', 'GEO', 'lm5pp_POS', 'title', 'heading', 'PronCodes'}
plain = {'NonDV', 'defRef', 'DEFBOLD', 'COLLOINEXA', 'neutral', 'GOODBOLD', 'HINTBOLD', 'STRONG', 'italic'}

def check_seam(left, right, node, kind, key, occurrence, current):
    a = re.search(r'[A-Za-z]+$', left); b = re.match(r'[A-Za-z]+', right)
    if not a or not b: return
    a, b = a[0], b[0]; word = a + b
    lexical = word.lower() in lexicon
    affix = (b.lower() in {'s','es','d','ed','ing','n','er','est'} and len(a) >= 3) or a.lower() in {'un','dis','mis','re','pre','non','de'}
    if not (lexical or affix) or len(a) + len(b) < 4: return
    pair = re.compile(r'(?<![A-Za-z])' + re.escape(a) + r'\s+' + re.escape(b) + r'(?![A-Za-z])')
    hit = pair.search(current)
    if not hit: return
    identity = (key, occurrence, a, b, kind, snippet(node))
    if identity in duplicates: return
    duplicates.add(identity)
    counts['seam_candidates'] += 1
    candidates.append({'key': key, 'occurrence': occurrence, 'kind': kind, 'joined': word,
                       'split': a + ' ' + b, 'in_lexicon': lexical, 'source_html': snippet(node),
                       'package_context': current[max(0,hit.start()-100):hit.end()+100]})


# Independent mapping from the output format contract; no converter helper calls.
POS = {'noun':'noun','verb':'verb','adjective':'adj','adverb':'adv','pronoun':'pron',
       'preposition':'prep','conjunction':'conj','exclamation':'excl','determiner':'det',
       'number':'num','modal verb':'modal','auxiliary verb':'aux','linking verb':'linking-v',
       'phrasal verb':'phrasal-v','prefix':'prefix','suffix':'suffix','combining form':'combining-form',
       'abbreviation':'abbr','symbol':'symb','idiom':'idiom','definite article':'def-article',
       'indefinite article':'indef-article','ordinal number':'ordinal-num','infinitive marker':'inf-marker',
       'infin marker':'inf-marker','short form':'short-form'}
RULE = {'noun':'n','n':'n','verb':'v','v':'v','adjective':'adj','adj':'adj','adverb':'adv','adv':'adv',
        'modal verb':'v','auxiliary verb':'v','phrasal verb':'v','linking verb':'v'}
def label_text(e):
    parts=[e.text or '']
    for child in e:
        if isinstance(child.tag,str) and 'portrait' not in cls(child): parts.append(label_text(child))
        parts.append(child.tail or '')
    return ''.join(parts)
def expected_metadata(doc):
    tags=[]; rules=[]; freq=[]
    for e in doc.iter('span'):
        c=cls(e)
        if 'lm5pp_POS' in c:
            label=compact(label_text(e)).lower().strip(' .;')
            for part in [label]+re.split('[,;]',label):
                part=part.strip(' .()')
                if part in POS and POS[part] not in tags: tags.append(POS[part])
                if part in RULE and RULE[part] not in rules: rules.append(RULE[part])
        if 'FREQ' in c:
            hit=re.match(r'^([SW][123])(?![0-9])',text(e).lstrip())
            if hit and hit[1] not in freq: freq.append(hit[1])
    return (' '.join(tags+freq),' '.join(rules))
assert expected_metadata(html.fromstring('<span class="lm5pp_POS">noun, <span class="landscape">adjective</span><span class="portrait">adj</span></span>')) == ('noun adj','n adj')

for key, content in records(SOURCE):
    counts['source_records'] += 1
    key = re.sub('[\u00ad\u200b-\u200d\u2060-\u2064\ufeff]', '', key).strip()
    if re.match(r'^(ACTIV:|ldoce\d+jpg)', key, re.I):
        counts['resource_records'] += 1; continue
    if content.lstrip().startswith('@@@LINK='):
        counts['redirect_records'] += 1; continue
    if not ('entry_content' in content[:8000] or 'ldoceEntry' in content[:8000]): continue
    occurrence = occurrences[key]; occurrences[key] += 1; counts['entries'] += 1
    current = packaged.get((key, occurrence), '')
    if not current: counts['missing_packaged_record'] += 1
    doc = html.fromstring(content)
    expected=expected_metadata(doc)
    if expected != metadata.get((key,occurrence)):
        metadata_errors.append({'key':key,'occurrence':occurrence,'expected':expected,'actual':metadata.get((key,occurrence))})
    roots = []; asset_nodes = []
    for e in doc.iter():
        if not isinstance(e.tag, str): continue
        c = cls(e)
        if 'entry_content' in c: roots.append(e)
        if 'asset' in c: asset_nodes.append(e)
        if e.tag in ('td', 'th') and ('rowspan' in e.attrib or 'colspan' in e.attrib):
            counts['table_spans'] += 1; structural.append({'kind':'table-span','key':key,'html':snippet(e)})
        if 'DEF' in c:
            cn = [n for n in e.iterdescendants() if 'cn_txt' in cls(n)]
            top = [n for n in cn if not any(p in cn for p in n.iterancestors() if p is not e)]
            if len(top) > 1:
                # English text outside the Chinese subtrees prevents the first-only branch.
                parts = []
                for n in e.iter():
                    if n in cn or any(p in cn for p in n.iterancestors()): continue
                    if n.text: parts.append(n.text)
                    for child in n:
                        if child.tail: parts.append(child.tail)
                if not compact(''.join(parts)):
                    counts['multi_chinese_only_def'] += 1
                    structural.append({'kind':'multi-chinese-only-def','key':key,'html':snippet(e)})
        if c & {'GEO', 'GRAM', 'lm5pp_POS'}:
            for child in e:
                descendants = list(child.iterdescendants())
                if any('portrait' in cls(n) for n in descendants) and any('landscape' in cls(n) for n in descendants):
                    counts['nested_portrait_label'] += 1
                    structural.append({'kind':'nested-portrait-label','key':key,'html':snippet(e)})
        if not (e.tag in ('a', 'b', 'i', 'em', 'strong') or c & plain): continue
        parent = e.getparent()
        if parent is None: continue
        ancestry = [e, *e.iterancestors()]
        if any(cls(n) & exclude for n in ancestry) or not any(cls(n) & prose for n in ancestry): continue
        body = text(e)
        previous = e.getprevious(); left = (previous.tail or '') if previous is not None else (parent.text or '')
        if left and body: check_seam(left, body, parent, 'text-element', key, occurrence, current)
        if e.tail and body: check_seam(body, e.tail, parent, 'element-text', key, occurrence, current)
        following = e.getnext()
        if following is not None and not (e.tail or '') and not (cls(following) & exclude):
            check_seam(body, text(following), parent, 'element-element', key, occurrence, current)
    if len(roots) > 1:
        counts['multiple_entry_content'] += 1; structural.append({'kind':'multiple-entry-content','key':key,'count':len(roots)})
    for asset in asset_nodes:
        sibling = asset.getnext(); groups = []
        while sibling is not None:
            if 'assetlink' in cls(sibling): groups.append(sibling)
            elif compact(text(sibling)): break
            sibling = sibling.getnext()
        has = [any('exaGroup' in cls(n) for n in g) for g in groups]
        if any(has) and not all(has):
            counts['mixed_assetlink_groups'] += 1
            structural.append({'kind':'mixed-assetlink-groups','key':key,'html':[snippet(g) for g in groups]})
    if counts['entries'] % 5000 == 0: print(dict(counts), 'seconds', round(time.monotonic()-started,1), flush=True)
result = {'source': str(SOURCE), 'source_bytes': SOURCE.stat().st_size, 'package': str(PACKAGE),
          'package_sha256': hashlib.sha256(PACKAGE.read_bytes()).hexdigest(), 'counts': dict(counts),
          'seam_candidates': candidates, 'structural_candidates': structural, 'metadata_errors':metadata_errors,
          'seconds': round(time.monotonic()-started, 1)}
OUT.mkdir(exist_ok=True)
RESULT.parent.mkdir(parents=True, exist_ok=True)
RESULT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'counts':dict(counts),'seconds':result['seconds'],'metadata_errors':len(metadata_errors)},ensure_ascii=False),flush=True)
assert counts['entries'] == len(packaged) and not counts['missing_packaged_record'] and not metadata_errors