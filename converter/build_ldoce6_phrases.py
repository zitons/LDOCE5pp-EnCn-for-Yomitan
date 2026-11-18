"""Build an independently sourced LDOCE6 phrase dictionary for Yomitan.

Extracted phrase bodies and supporting source contexts are separate row types.
Alias decisions use only LDOCE6 text; no other dictionary is read by this build.
Ambiguous slash/parenthesis expansion is recorded rather than guessed.
"""
import argparse
import csv
import hashlib
import itertools
import json
import re
import sqlite3
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote, unquote

from lxml import html
from phrase_alias_rules import enhanced_variants, full_alternatives, orthographic_forms
from supplement_phrase_sources import supplement_sources
from phrase_pronoun_aliases import apply_pronouns
from apply_phrase_inflections import apply_inflections

PRIMARY = {'phrasetext', 'lexunit', 'phrvbhwd', 'phrv'}
EXTRACTION_VERSION = 2
INTERNAL = re.compile(r'^(faq-|guideword$|word-set-|boxes of )', re.I)
CLASS = "contains(concat(' ',normalize-space(@class),' '),$c)"
SELECT = html.etree.XPath('//*[' + ' or '.join(
    "contains(concat(' ',normalize-space(@class),' '),' " + c + " ')" for c in sorted(PRIMARY)) + ']')
BLOCK = {'sense','subsense','phrvbentry','phrase','example','entry','entryhead',
         'colloexa','gramexa','tail','runon','collocate','content'}
DROP = {'at-link','buttons','popup-button','arrow','entrymenu','pope_menu',
        'verbtable','collobox','thesbox','thescollobox','chwd'}
STYLE_CLASSES = ('entryhead','sense','subsense','sensenum','lexunit','phrasetext',
                 'phrvbhwd','example','nodeword','def','defbold','gloss','pos','gram',
                 'registerlab','geo','collo','propform','colloinexa','signpost','hwd',
                 'homnum','proncodes','pron','freq','level','ac','gram','inflections')


def clean(text):
    return re.sub(r'\s+', ' ', text).strip()


def classes(node):
    return set(node.get('class','').split())


def find(node, cls):
    return node.xpath('.//*[' + CLASS + ']', c=' '+cls+' ')


def element(tag, content, cls=None, **attributes):
    out={'tag':tag,'content':content,**attributes}
    if cls and tag!='a':
        out['data']={'class':'l6p-'+cls}
    return out


def sc(node):
    """Convert a source subtree, preserving text, nesting and emphasis.

    Media are intentionally omitted; no source JS/CSS/onclick reaches output.
    Query links are resolved against the finished package before export.
    """
    if not isinstance(node.tag,str): return ''
    tag=node.tag.lower()
    cls=classes(node)
    if tag in {'script','style','head','link','meta','img','audio','source'} or cls & DROP:
        return ''
    if 'hyphenation' in cls:
        parent=node.getparent()
        if parent is not None and 'entryhead' in classes(parent) and find(parent,'hwd'):
            return ''  # Source CSS supplies syllable dots; this is not a second headword.
    kids=[]
    if node.text: kids.append(re.sub(r'\s+',' ',node.text))
    for child in node:
        value=sc(child)
        if value: kids.append(value)
        if child.tail: kids.append(re.sub(r'\s+',' ',child.tail))
    if tag=='br': return {'tag':'br'}
    if not kids: return ''
    if 'entryhead' in cls:
        visible=[v for v in kids if plain(v).strip()]
        kids=list(itertools.chain.from_iterable(([v,' '] for v in visible)))
        if kids: kids.pop()
    if tag in {'html','body'}: return kids
    style_cls=next((c for c in STYLE_CLASSES if c in cls),None)
    if 'homnum' in cls:
        return element('span',kids,'homnum',style={'verticalAlign':'super','fontSize':'0.75em'})
    if tag=='a':
        href=node.get('href','')
        if href.startswith('entry://'):
            target=unquote(href[8:].split('#',1)[0])
            if target: return element('a',kids,'link',href='?query='+quote(target,safe=''))
        return kids
    if tag in {'ul','ol','li','table','tbody','thead','tfoot','tr','td','th','details','summary'}:
        return element(tag,kids,style_cls)
    if tag in {'b','strong','i','em'}:
        return element('span',kids,'bold' if tag in {'b','strong'} else 'italic')
    return element('div' if tag in {'div','p'} or cls & BLOCK else 'span',kids,style_cls)


def texts(scope, cls):
    return list(dict.fromkeys(clean(n.text_content()) for n in find(scope,cls)
                             if clean(n.text_content())))


def metrics(scope):
    defs=texts(scope,'def')
    if not defs: defs=texts(scope,'defbold')
    examples=texts(scope,'example')
    examples += [clean(n.text_content()) for n in scope.xpath(
        './/ul[contains(concat(" ",normalize-space(@class)," ")," exas ")]/li')]
    return defs,list(dict.fromkeys(examples))


def scope_for(node, kind):
    ancestors=list(node.iterancestors())
    if any(classes(p)&{'menuitem','entrymenu'} for p in ancestors): return None
    wanted={'phrase'} if kind=='phrasetext' else {'sense','subsense','phrvbentry'}
    for p in ancestors:
        if classes(p)&wanted: return p
    return None


def iter_records(path, cache=False):
    if cache:
        with Path(path).open(encoding='utf-8') as f:
            for line in f: yield json.loads(line)
    else:
        from mdict_utils.reader import MDX
        for k,v in MDX(str(path)).items(): yield k.decode('utf-8'),v.decode('utf-8')


def dump(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'))


def extract(path, db_path, cache=False, limit=None):
    if db_path.exists(): db_path.unlink()
    db=sqlite3.connect(db_path)
    db.executescript('''
      CREATE TABLE sources(record_id INTEGER PRIMARY KEY, headword TEXT, body TEXT, defs TEXT, examples TEXT);
      CREATE TABLE occurrences(phrase TEXT, record_id INTEGER, parent TEXT, kind TEXT,
        xpath TEXT, sense TEXT, body TEXT, defs TEXT, examples TEXT);
      CREATE TABLE lexical_pos(word TEXT, pos TEXT, PRIMARY KEY(word,pos));
      CREATE TABLE metadata(name TEXT PRIMARY KEY, value TEXT);
    ''')
    db.execute('INSERT INTO metadata VALUES(?,?)',('extraction_version',str(EXTRACTION_VERSION)))
    counts=Counter()
    with db:
        for rid,(key,source) in enumerate(iter_records(path,cache),1):
            if limit and rid>limit: break
            counts['records']+=1
            key=clean(key)
            if INTERNAL.match(key):
                counts['internal_records_excluded']+=1
                continue
            root=html.fromstring(source)
            nodes=SELECT(root)
            scope_cache={}
            for n in nodes:
                kind=next(c for c in sorted(PRIMARY) if c in classes(n))
                phrase=clean(n.text_content())
                if not phrase: raise ValueError(f'Empty {kind} at {key}')
                scope=scope_for(n,kind)
                body=''
                defs,examples=[],[]
                sense=''
                if scope is not None:
                    if scope not in scope_cache:
                        ds,es=metrics(scope)
                        scope_cache[scope]=(dump(sc(scope)),ds,es)
                    body,defs,examples=scope_cache[scope]
                    for p in [scope,*scope.iterancestors()]:
                        if classes(p)&{'sense','subsense'}:
                            nums=[c for c in p if 'sensenum' in classes(c)]
                            sense=clean(nums[0].text_content()) if nums else ''
                            break
                db.execute('INSERT INTO occurrences VALUES(?,?,?,?,?,?,?,?,?)',
                    (phrase,rid,key,kind,n.getroottree().getpath(n),sense,body,dump(defs),dump(examples)))
                counts[kind]+=1
            # Only original lexical content is used for source-context rows.
            # Popup material was extracted above and is never mixed into a sense.
            for pop in root.xpath('//*[@class="at-link"]'):
                pop.getparent().remove(pop)
            for head in find(root,'entryhead'):
                hwds=find(head,'hwd')
                if not hwds: continue
                word=clean(hwds[0].text_content()).casefold()
                if ' ' in word: continue
                labels=[p for p in head if 'pos' in classes(p)]
                for label in labels:
                    for pos in re.findall(r'\b(?:noun|verb|adjective|adverb|preposition|pronoun|conjunction|determiner|exclamation|modal)\b',label.text_content()):
                        db.execute('INSERT OR IGNORE INTO lexical_pos VALUES(?,?)',(word,pos))
            main_body=dump(sc(root))
            ds,es=metrics(root)
            db.execute('INSERT INTO sources VALUES(?,?,?,?,?)',(rid,key,main_body,dump(ds),dump(es)))
            if re.search(r'\s',key):
                db.execute('INSERT INTO occurrences VALUES(?,?,?,?,?,?,?,?,?)',
                    (key,rid,key,'key','/', '',main_body,dump(ds),dump(es)))
                counts['key']+=1
            if rid%5000==0:
                print(f'extracted {rid:,} records',flush=True)
    db.executescript('CREATE INDEX phrase_idx ON occurrences(phrase); CREATE INDEX source_key_idx ON sources(headword);')
    db.close()
    return dict(counts)


PLACEHOLDERS = {'somebody':'sb','something':'sth',"somebody's":"sb's","something's":"sth's"}


def alias_variants(phrase, max_variants=64):
    """Conservative local alternatives, never arbitrary multiword slash scope.

    This function proposes candidates. Assembly validates lexical choices
    against LDOCE6 parts of speech or source examples. Object omission has a
    separate, deliberately limited rule for established lexical entries.
    """
    result={phrase: {'original'}}
    review=[]
    optional=re.findall(r'\(([^()]*)\)',phrase)
    forms={phrase}
    if '(' in phrase or ')' in phrase:
        # Compact optional groups only; explanatory/long brackets need review.
        if re.sub(r'\([^()]*\)','',phrase).count('(') or any(
                len(x.split())>2 or re.search(r'\b(?:especially|usually|also|or)\b',x) for x in optional):
            review.append('ambiguous_parentheses')
        elif optional:
            forms={''}
            parts=re.split(r'(\([^()]*\))',phrase)
            for part in parts:
                choices=[part]
                if part.startswith('(') and part.endswith(')'):
                    choices=['',part[1:-1]]
                forms={a+b for a in forms for b in choices}
                if len(forms)>max_variants:
                    review.append('variant_limit'); forms={phrase}; break
            forms={clean(p) for p in forms}|{phrase}
    expanded=set(forms)
    for form in sorted(forms):
        tokens=form.split()
        if any('/' in a and '/' in b for a,b in zip(tokens,tokens[1:])):
            review.append('multiword_slash_boundary'); continue
        choices=[]
        ambiguous=False
        for token in tokens:
            if '/' not in token:
                choices.append([token]); continue
            alts=token.split('/')
            # Equal syntactic slots are safe for sb/sth and short middle slots.
            # Multiword alternatives such as "have a look/take a look" remain
            # unresolved; the repeated-word boundary is a strong warning.
            prefix=' '.join(tokens[:len(choices)])
            suffix=' '.join(tokens[len(choices)+1:])
            if (any(not a or re.search(r'[\d$£€%()]',a) for a in alts)
                    or any(' ' + a + ' ' in ' ' + prefix + ' ' for a in alts)
                    or any(' ' + a + ' ' in ' ' + suffix + ' ' for a in alts)
                    or bool(set(prefix.split()) & set(suffix.split()))
                    or 'or' in prefix.split()
                    or (len(tokens)==1 and not all(a in PLACEHOLDERS for a in alts))):
                ambiguous=True; break
            choices.append(alts)
        if ambiguous:
            review.append('ambiguous_slash'); continue
        if len(list(itertools.islice(itertools.product(*choices),max_variants+1)))>max_variants:
            review.append('variant_limit'); continue
        expanded.update(' '.join(items) for items in itertools.product(*choices))
    for form in expanded:
        if form and form!=phrase:
            result.setdefault(form,set()).add('source_notation')
        # Keep both fully-spelled and fully-abbreviated placeholder forms.
        shortened=re.sub(r"\bsome(?:body|thing)(?:'s)?\b",lambda m:PLACEHOLDERS.get(m[0],m[0]),form)
        if shortened!=form:
            result.setdefault(shortened,set()).add('placeholder_abbreviation')
    # "etc" denotes an open slot. Remove the marker only after all slashes
    # have been resolved; never infer new vocabulary for that open slot.
    for form,reasons in list(result.items()):
        if '/' not in form and re.search(r'\betc\b',form):
            closed=clean(re.sub(r'\betc\.?\s*','',form))
            if closed: result.setdefault(closed,set()).add('omit_etc_marker')
        if '↔' in form:
            result.setdefault(clean(form.replace('↔',' ')),set()).add('omit_separability_marker')
    result.pop(phrase,None)
    return result,sorted(set(review))


def plain(value):
    if isinstance(value,str): return value
    if isinstance(value,list): return ''.join(plain(v) for v in value)
    if isinstance(value,dict): return plain(value.get('content',''))
    return ''


def query_targets(value):
    if isinstance(value,list):
        return set().union(*(query_targets(v) for v in value)) if value else set()
    if isinstance(value,dict):
        result=query_targets(value.get('content',[]))
        if value.get('tag')=='a': result.add(unquote(value.get('href','').removeprefix('?query=')))
        return result
    return set()


def link_reference_text(value, target):
    if isinstance(value,str):
        return element('a',value,href='?query='+quote(target,safe='')) if clean(value).casefold()==target.casefold() else value
    if isinstance(value,list): return [link_reference_text(v,target) for v in value]
    if isinstance(value,dict) and value.get('tag')!='a':
        value=dict(value)
        if 'content' in value: value['content']=link_reference_text(value['content'],target)
    return value


def safe_slash_slots(phrase):
    groups=[set(t.strip('(),.!?').casefold().split('/')) for t in phrase.split() if '/' in t]
    families=[{'somebody','something',"somebody's","something's"},
              {'him','her','me','us','them','you'}, {'his','her','my','our','their','your','its'},
              {'i','he','she','it','we','they','you'}, {'a','an','the'},
              {'in','on','at','by','from','with','for','to','into','onto','of','upon'},
              {'can','could','will','would','shall','should','may','might','must'}]
    return bool(groups) and all(any(g<=f for f in families) for g in groups)


def lexical_slash_slots(phrase, lexicon, preferred=None):
    """Accept local choices with compatible parts of speech in LDOCE6 itself.

    This does not infer multiword slash boundaries. Regular noun plurals are
    reduced only for POS lookup, never exported as extra inflected query keys.
    """
    groups=[t.strip('(),.!?').split('/') for t in phrase.split() if '/' in t]
    tokens=phrase.split()
    articles={'a','an','the'}
    if any(set(w.casefold() for w in g)&articles and not set(w.casefold() for w in g)<=articles for g in groups):
        return False
    def tags(word):
        word=word.casefold()
        result={preferred[word]} if preferred is not None and word in preferred else set(lexicon.get(word,set()))
        if word.endswith('s') and not word.endswith('ss'):
            roots={word[:-1]}
            if word.endswith('es'): roots.add(word[:-2])
            if word.endswith('ies'): roots.add(word[:-3]+'y')
            for root in roots:
                if 'noun' in lexicon.get(root,set()) and (preferred is None or preferred.get(root)=='noun'):
                    result.add('noun')
        return result
    # Agreement and multiword boundaries cannot be inferred from POS alone.
    for i,left in enumerate(tokens):
        if '/' not in left: continue
        alts=left.strip('(),.!?').casefold().split('/')
        if not all('noun' in tags(w) for w in alts): continue
        following=tokens[i+1].strip('(),.!?').casefold() if i+1<len(tokens) else ''
        if 'noun' in tags(following): return False  # hat/football boots
        plurals={w.endswith('s') and ('noun' in lexicon.get(w[:-1],set()) or
                 w.endswith('ies') and 'noun' in lexicon.get(w[:-3]+'y',set())) for w in alts}
        if len(plurals)>1 and (i and tokens[i-1].casefold() in {'a','an'} or
                              'verb' in tags(following)):
            return False  # your heart/thoughts go ... needs agreement, not concatenation
    return bool(groups) and all(bool(set.intersection(*(tags(w) for w in group))) for group in groups)


def explicit_parenthesized_choices(phrase):
    found=False
    for group in re.findall(r'\(([^()]*)\)',phrase):
        if '/' in group and not re.search(r'\s|\d',group) and all(group.split('/')):
            phrase=phrase.replace('('+group+')','')
            found=True
    return found and '/' not in phrase


def omit_terminal_object(phrase):
    if re.search(r'[/()↔]',phrase): return None
    match=re.search(r'\s+(?:somebody|something|sb|sth)$',phrase)
    if not match: return None
    base=clean(phrase[:match.start()]); words=base.split()
    preps={'to','of','for','with','from','in','on','at','into','onto','against','about',
           'over','under','through','around','round','upon','between','among','without','beyond'}
    fixed=[w for w in words if w not in {'somebody','something','sb','sth'}]
    return base if len(words)>=3 and len(fixed)>=2 and words[-1] in preps else None


def initial_forms(word):
    variants={word,word+'s',word+'es',word+'ed',word+'ing'}
    if word.endswith('e'): variants.update({word+'d',word[:-1]+'ing'})
    if word.endswith('y'): variants.update({word[:-1]+'ies',word[:-1]+'ied'})
    if len(word)>2 and word[-1] not in 'aeiouwxy' and word[-2] in 'aeiou':
        variants.update({word+word[-1]+'ed',word+word[-1]+'ing'})
    irregular={'be':{'am','is','are','was','were','been','being'},'have':{'has','had','having'},
        'do':{'does','did','done','doing'},'go':{'goes','went','gone','going'},
        'get':{'gets','got','gotten','getting'},'give':{'gives','gave','given','giving'},
        'take':{'takes','took','taken','taking'},'make':{'makes','made','making'},
        'hang':{'hangs','hung','hanged','hanging'},'keep':{'keeps','kept','keeping'},
        'come':{'comes','came','coming'},'hold':{'holds','held','holding'},
        'stand':{'stands','stood','standing'},'lose':{'loses','lost','losing'},
        'find':{'finds','found','finding'},'leave':{'leaves','left','leaving'},
        'bring':{'brings','brought','bringing'},'put':{'puts','putting'},
        'run':{'runs','ran','running'},'say':{'says','said','saying'},
        'see':{'sees','saw','seen','seeing'},'know':{'knows','knew','known','knowing'}}
    return variants|irregular.get(word,set())


def example_attests(alias, examples):
    """Literal source-example evidence for uncertain lexical slash expansion.

    Flexible person/object placeholders and possessives are notation, not new
    vocabulary. Only regular initial-verb endings are tolerated here; absence
    of evidence sends a candidate to review rather than approving a guess.
    """
    alias=clean(alias.replace('↔',' ').replace('(', '').replace(')', ''))
    alias=re.sub(r'\betc\.?','',alias).strip(' .!?')
    words=alias.split()
    if not words: return False
    pattern=[]
    for i,w in enumerate(words):
        folded=w.casefold()
        if folded in {'somebody','something','sb','sth'}:
            pattern.append(r"[\w'-]+(?:\s+[\w'-]+){0,4}")
        elif folded in {"somebody's","sb's","one's",'your'}:
            pattern.append(r"(?:your|his|her|its|their|our|my|[\w'-]+'s)")
        elif i==0 and folded.isalpha() and len(folded)>2:
            variants=initial_forms(folded)
            pattern.append('(?:'+'|'.join(re.escape(v) for v in sorted(variants))+')')
        else: pattern.append(re.escape(folded))
    expression=re.compile(r'(?<!\w)'+r'\s+'.join(pattern)+r'(?!\w)',re.I)
    return any(expression.search(e) for e in examples)


def rewrite_links(value, available):
    if isinstance(value,list): return [rewrite_links(x,available) for x in value]
    if not isinstance(value,dict): return value
    value=dict(value)
    if value.get('tag')=='a':
        value.pop('data',None)
        target=unquote(value.get('href','').removeprefix('?query='))
        if target not in available:
            return rewrite_links(value.get('content',''),available)
    if 'content' in value: value['content']=rewrite_links(value['content'],available)
    return value


def suppress_repeated_heading(value, phrase):
    if isinstance(value,list):
        return [new for v in value if (new:=suppress_repeated_heading(v,phrase))!='']
    if not isinstance(value,dict): return value
    labels={'l6p-hwd','l6p-lexunit','l6p-phrasetext','l6p-phrvbhwd'}
    if value.get('data',{}).get('class') in labels and clean(plain(value).replace('↔',' '))==phrase:
        return ''
    value=dict(value)
    if 'content' in value: value['content']=suppress_repeated_heading(value['content'],phrase)
    if value.get('data',{}).get('class')=='l6p-entryhead' and not plain(value).strip(): return ''
    return value


CSS='''
[data-sc-class="l6p-root"] {line-height:1.45;color:var(--text-color,inherit);overflow-wrap:anywhere}
[data-sc-class="l6p-title"] {font-size:1.15em;font-weight:bold;margin-bottom:.5em}
[data-sc-class="l6p-sense"],[data-sc-class="l6p-subsense"] {margin:.4em 0}
[data-sc-class="l6p-example"] {display:block;font-style:italic;margin:.35em 0 .35em .8em}
[data-sc-class="l6p-sensenum"] {font-weight:bold;margin-right:.4em}
[data-sc-class="l6p-nodeword"],[data-sc-class="l6p-lexunit"],
[data-sc-class="l6p-phrasetext"],[data-sc-class="l6p-phrvbhwd"],
[data-sc-class="l6p-hwd"],[data-sc-class="l6p-bold"] {font-weight:bold}
[data-sc-class="l6p-pos"],[data-sc-class="l6p-registerlab"],[data-sc-class="l6p-geo"],
[data-sc-class="l6p-italic"] {font-style:italic;margin-right:.3em}
[data-sc-class="l6p-origin"] {font-size:.85em;margin:.5em 0;opacity:.8}
[data-sc-class="l6p-context"] {margin-top:.6em}
[data-sc-class="l6p-entryhead"] {display:block;font-size:1.05em;margin:.5em 0;font-weight:normal;line-height:1.65}
[data-sc-class="l6p-proncodes"] {white-space:normal;font-weight:normal;overflow-wrap:anywhere}
[data-sc-class="l6p-freq"],[data-sc-class="l6p-ac"] {font-size:.8em;border:1px solid currentColor;border-radius:3px;padding:0 .25em}
[data-sc-class="l6p-level"] {font-size:.9em;letter-spacing:.02em}
[data-sc-class="l6p-gram"] {font-size:.9em;font-weight:normal}
'''


def write_tsv(path, fields, rows):
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter='\t'); w.writerow(fields); w.writerows(rows)


def assemble(db_path, out, revision):
    db=sqlite3.connect(db_path)
    db.row_factory=sqlite3.Row
    version=db.execute('SELECT value FROM metadata WHERE name=?',('extraction_version',)).fetchone()
    if not version or int(version[0])!=EXTRACTION_VERSION: raise ValueError('Extraction version changed; rebuild without --reuse-extraction')
    lexicon=defaultdict(set)
    preferred={}
    for word,pos in db.execute('SELECT word,pos FROM lexical_pos ORDER BY rowid'):
        lexicon[word].add(pos); preferred.setdefault(word,pos)
    raw_phrases=[r[0] for r in db.execute('SELECT DISTINCT phrase FROM occurrences ORDER BY phrase')]
    identities=defaultdict(list)
    for p in raw_phrases: identities[clean(p.replace('↔',' '))].append(p)
    phrases=sorted(identities)
    phrase_set=set(phrases)
    raw_to_canonical={raw:p for p,raws in identities.items() for raw in raws}
    source_keys={r[0] for r in db.execute('SELECT DISTINCT headword FROM sources')}
    reference_names=phrase_set|source_keys
    folded_names=defaultdict(set)
    for name in reference_names: folded_names[name.casefold()].add(name)
    def plain_reference(body):
        value=plain(body)
        if '→' not in value: return None
        tail=clean(value.rsplit('→',1)[1])
        if tail in reference_names: return tail
        folded=folded_names.get(tail.casefold(),set())
        return next(iter(folded)) if len(folded)==1 else None
    canonical={}
    evidence=[]
    required_sources=set()
    counts=Counter()
    for phrase in phrases:
        occurrences=[]
        for raw in identities[phrase]:
            occurrences.extend(db.execute('SELECT * FROM occurrences WHERE phrase=?',(raw,)))
        rich=[]
        for r in occurrences:
            defs=json.loads(r['defs']); examples=json.loads(r['examples'])
            evidence.append((phrase,r['phrase'],r['parent'],r['kind'],r['record_id'],r['xpath'],r['sense'],len(defs),len(examples)))
            if r['body'] and (defs or examples): rich.append((r,defs,examples))
        # A dedicated source entry contains the complete phrase's own senses.
        dedicated=[x for x in rich if x[0]['kind'] in {'key','compound-key'}]
        candidates=dedicated or sorted(rich,key=lambda x:(-bool(x[1]),-len(x[1]),-len(x[2])))
        selected=[]; seen_defs=set(); seen_examples=set()
        for r,defs,examples in candidates:
            if set(defs)<=seen_defs and set(examples)<=seen_examples: continue
            selected.append((r,defs,examples))
            seen_defs.update(defs); seen_examples.update(examples)
        parents=sorted({raw_to_canonical.get(r['parent'],r['parent']) for r in occurrences})
        required_sources.update(parents)
        children=[element('div',phrase,'title')]
        for r,defs,examples in selected:
            children.append(json.loads(r['body']))
        status='definitions' if seen_defs else 'examples' if selected else 'reference_only'
        if not selected:
            references=[r for r in occurrences if r['body'] and
                        (query_targets(json.loads(r['body']))-{phrase} or plain_reference(json.loads(r['body'])))]
            if references:
                r=next((r for r in references if r['kind']=='key'),references[0])
                body=json.loads(r['body'])
                textual_target=plain_reference(body)
                if textual_target and textual_target!=phrase:
                    body=link_reference_text(body,textual_target)
                children.append(body)
                for target in query_targets(body)-{phrase}:
                    if target in phrase_set:
                        status='cross_reference'
                    elif target in source_keys:
                        required_sources.add(target)
                        status='cross_reference'
            else:
                children.append(element('div','See the source entry for this expression.','reference-only'))
                # Preserve a source stub rather than create a self-link loop.
                own=db.execute('SELECT body FROM sources WHERE headword=?',(phrase,)).fetchone()
                if own: children.append(json.loads(own[0]))
            counts[status]+=1
        else:
            counts['with_definitions' if seen_defs else 'examples_only']+=1
        origin=list(itertools.chain.from_iterable(
            ([element('a',p,'link',href='?query='+quote(p,safe='')),'; '] for p in parents if p!=phrase)))
        children.append(element('div',['Source: ',*origin] if origin else 'LDOCE6','origin'))
        canonical[phrase]=dict(content=element('div',children,'root'),parents=parents,
                               definitions=len(seen_defs),examples=len(seen_examples),
                               status=status,example_texts=seen_examples,kinds={r['kind'] for r in occurrences})
    contexts={}
    context_queue=sorted(required_sources-phrase_set)
    queued=set(context_queue)
    for parent in context_queue:
        rows=list(db.execute('SELECT * FROM sources WHERE headword=? ORDER BY record_id',(parent,)))
        if not rows: raise ValueError(f'Missing source context: {parent}')
        children=[] if any('"class":"l6p-entryhead"' in r['body'] for r in rows) else [element('div',parent,'title')]
        for r in rows:
            body=json.loads(r['body'])
            children.append(body)
            if not json.loads(r['defs']):
                for target in sorted(query_targets(body)-phrase_set-queued):
                    if db.execute('SELECT 1 FROM sources WHERE headword=?',(target,)).fetchone():
                        queued.add(target); context_queue.append(target)
        contexts[parent]=element('div',children,'root')
    aliases=defaultdict(lambda:defaultdict(set))
    review=[]
    collisions=[]
    for phrase in phrases:
        variants,reasons=alias_variants(phrase)
        accepted={phrase}
        pos_compatible=lexical_slash_slots(phrase,lexicon,preferred) if '/' in phrase else False
        explicit_choices=explicit_parenthesized_choices(phrase)
        for raw in identities[phrase]:
            if raw!=phrase: variants.setdefault(raw,set()).add('source_separability_notation')
        review.extend((phrase,r) for r in reasons)
        for alias,rules in variants.items():
            if '/' in phrase and '/' not in alias and not safe_slash_slots(phrase) and not pos_compatible and not explicit_choices:
                if not example_attests(alias,canonical[phrase]['example_texts']):
                    review.append((phrase,'unattested_slash_candidate: '+alias)); continue
                rules.add('source_example_attested')
            elif '/' in phrase and '/' not in alias and pos_compatible:
                rules.add('source_pos_compatible')
            elif '/' in phrase and '/' not in alias and explicit_choices:
                rules.add('source_parenthesized_choices')
            if alias in phrase_set or alias in contexts:
                collisions.append((alias,phrase,'existing_content_wins')); continue
            aliases[alias][phrase].update(rules)
            accepted.add(alias)
        if canonical[phrase]['definitions'] and canonical[phrase]['kinds'] & {'key','lexunit'}:
            # Only explicit lexical entries get this limited prefix lookup.
            # Never strip objects from a generic bare phrasal-verb pattern.
            for form in accepted:
                base=omit_terminal_object(form)
                if base and base not in phrase_set and base not in contexts:
                    aliases[base][phrase].add('terminal_object_placeholder_omitted')
        def simple(form):
            proposed,_=alias_variants(form)
            safe=safe_slash_slots(form) or lexical_slash_slots(form,lexicon,preferred) or explicit_parenthesized_choices(form)
            return {a for a in proposed if '/' not in a and
                    ('/' not in form or safe or example_attests(a,canonical[phrase]['example_texts']))}
        for side in full_alternatives(phrase):
            # A side with its own brackets or choices contributes its plain readings.
            for alias in ({side} if not re.search(r'[/()]',side) else set())|simple(side):
                if alias in phrase_set or alias in contexts:
                    collisions.append((alias,phrase,'existing_content_wins'));continue
                aliases[alias][phrase].add('source_full_alternatives')
        enhanced,notes=enhanced_variants(phrase,identities[phrase],lexicon,preferred,
            canonical[phrase]['example_texts'],simple,example_attests)
        review.extend((phrase,n) for n in notes)
        for alias,rules in enhanced.items():
            if alias in phrase_set or alias in contexts:
                collisions.append((alias,phrase,'existing_content_wins'));continue
            aliases[alias][phrase].update(rules)
    # Explicit lexical variants/plurals are source facts, never inferred forms.
    supplemental=Counter()
    has_forms=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_query_forms'").fetchone()
    if has_forms:
        for alias,target,rule in db.execute('SELECT alias,target,rule FROM source_query_forms ORDER BY alias,target,rule'):
            target=raw_to_canonical.get(target,target)
            if target not in phrase_set:continue
            candidates={alias}|orthographic_forms(alias)
            for value in candidates:
                if value in phrase_set or value in contexts:continue
                aliases[value][target].add(rule);supplemental[rule]+=1
    pronoun_stats=apply_pronouns(phrase_set,aliases,contexts)
    inflection_stats=apply_inflections(db,phrase_set,aliases,preferred)
    # A source context must not be shadowed by a query alias.
    for key in set(aliases)&set(contexts):del aliases[key]
    # fushidicts uses case-sensitive index keys and lowercased query variants.
    # Lowercase keys let inflected lowercase input reach capitalized lemmas.
    for alias,targets in list(aliases.items()):
        lower=alias.lower()
        if lower!=alias and lower not in phrase_set and lower not in contexts:
            for target in targets:aliases[lower][target].add('source_lowercase_lookup')
    for phrase in phrases:
        lower=phrase.lower()
        if lower!=phrase and lower not in phrase_set and lower not in contexts:
            aliases[lower][phrase].add('source_lowercase_lookup')
    available=phrase_set|set(contexts)|set(aliases)
    rows=[]
    for phrase in phrases:
        tag='phrase-reference' if canonical[phrase]['status'] in {'cross_reference','reference_only'} else 'phrase'
        rows.append([phrase,'',tag,'',10,[{'type':'structured-content','content':
            rewrite_links(suppress_repeated_heading(canonical[phrase]['content'],phrase),available)}],len(rows),''])
    for parent,content in contexts.items():
        rows.append([parent,'','source-context','',-5,[{'type':'structured-content','content':
            rewrite_links(content,available)}],len(rows),''])
    for alias,targets in sorted(aliases.items()):
        rows.append([alias,'','non-lemma','',-10,[[p,['redirect']] for p in sorted(targets)],len(rows),''])
    title='LDOCE6 English Phrases'
    index={'title':title,'format':3,'revision':revision,'sequenced':True,
           'sourceLanguage':'en','targetLanguage':'en','description':
           'Source-attested LDOCE6 phrases with local definitions/examples, source contexts and structure-aware query aliases.'}
    package=out/f'LDOCE6_Phrases_{revision}.zip'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr('index.json',dump(index)); z.writestr('styles.css',CSS)
        z.writestr('tag_bank_1.json',dump([
            ['phrase','partOfSpeech',0,'Source-attested phrase',0],
            ['phrase-reference','misc',-2,'Source cross-reference; no local definition',0],
            ['source-context','misc',-5,'Original source entry context',0],
            ['non-lemma','misc',-5,'Phrase query variant',0]]))
        for start in range(0,len(rows),10000):
            z.writestr(f'term_bank_{start//10000+1}.json',dump(rows[start:start+10000]))
    write_tsv(out/'phrases.tsv',['phrase','status','definitions','examples','parents_json'],
        ((p,c['status'],c['definitions'],c['examples'],dump(c['parents'])) for p,c in canonical.items()))
    write_tsv(out/'aliases.tsv',['alias','target','rules'],
        ((a,p,','.join(sorted(rules))) for a,ts in sorted(aliases.items()) for p,rules in sorted(ts.items())))
    write_tsv(out/'evidence.tsv',['phrase','phrase_raw','parent','source','record_id','xpath','sense','definitions','examples'],evidence)
    write_tsv(out/'review.tsv',['phrase','reason'],review)
    write_tsv(out/'alias_collisions.tsv',['alias','target','reason'],collisions)
    report=dict(counts=counts,source_distinct_expressions=len(raw_phrases),notation_duplicates_merged=len(raw_phrases)-len(canonical),
        phrase_entries=len(canonical),multiword_phrase_entries=sum(bool(re.search(r'\s',p)) for p in canonical),
        source_context_entries=len(contexts),alias_entries=len(aliases),alias_target_pairs=sum(len(v) for v in aliases.values()),
        ambiguous_alias_entries=sum(len(v)>1 for v in aliases.values()),review_items=len(review),
        rows=len(rows),package=str(package.resolve()),bytes=package.stat().st_size,
        sha256=hashlib.sha256(package.read_bytes()).hexdigest(),
        alias_rules=dict(Counter(rule for targets in aliases.values() for rules in targets.values() for rule in rules)),
        automatic_inflection_aliases=True,
        inflection_generation=dict(inflection_stats),
        finite_pronoun_generation=dict(pronoun_stats),
        supplemental_source_forms=dict(supplemental),
        policy='Only LDOCE6 source data; no LDOCE5++ input to extraction or alias generation. Source choice groups, separability, spelling, explicit pronoun slots (including the generic possessive your) and POS-constrained inflections become direct canonical aliases. Dictionary notation is never inflected; arbitrary names and numeric ranges are not enumerated.')
    (out/'build_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    db.close()
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    return report


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('-i','--input',required=True)
    ap.add_argument('--cache',action='store_true')
    ap.add_argument('-o','--output',required=True)
    ap.add_argument('--revision',default='2026.11.18')
    ap.add_argument('--reuse-extraction',action='store_true')
    ap.add_argument('--limit',type=int)
    ap.add_argument('--supplement-sources',action='store_true',help='Add source compound keys and explicitly declared query forms')
    args=ap.parse_args()
    out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
    db=out/'extraction.sqlite'
    if not args.reuse_extraction:
        report=extract(args.input,db,args.cache,args.limit)
        (out/'extraction_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    if args.supplement_sources:
        supplemental=supplement_sources(args.input,db,args.cache)
        (out/'supplemental_source_report.json').write_text(json.dumps(supplemental,ensure_ascii=False,indent=2),encoding='utf8')
    assemble(db,out,args.revision)


if __name__=='__main__': main()
