"""Add LDOCE6 compound keys and explicitly declared lexical/plural forms.

This supplements the original core extraction without changing its inventory.
No regular inflections are synthesized and no LDOCE5++ data are read.
"""
import json
import re
import sqlite3
from collections import Counter
from lxml import html


def clean(s):return ' '.join(s.translate(str.maketrans('','','ˌˈ·‧')).split())


POS_LABELS=r'\b(?:noun|verb|adjective|adverb|preposition|pronoun|conjunction|determiner|exclamation|modal)\b'


def compound_key(key):
    return ' ' not in key and bool(re.search(r'[A-Za-z][\-‐‑–][A-Za-z]',key)) and not key.startswith('-')


def supplement_sources(path,db_path,cache=False):
    db=sqlite3.connect(db_path);db.row_factory=sqlite3.Row
    counts=Counter();examples=[]
    db.executescript('''CREATE TABLE IF NOT EXISTS source_query_forms(
      alias TEXT,target TEXT,rule TEXT,record_id INTEGER,xpath TEXT,
      PRIMARY KEY(alias,target,rule,record_id));
      CREATE TABLE IF NOT EXISTS source_word_forms(word TEXT,form TEXT,kind TEXT,record_id INTEGER,xpath TEXT,
        PRIMARY KEY(word,form,kind,record_id));
      CREATE TABLE IF NOT EXISTS source_head_grammar(word TEXT,pos TEXT,gram TEXT,syllables INTEGER,record_id INTEGER,
        PRIMARY KEY(word,pos,gram,record_id));
      CREATE TABLE IF NOT EXISTS source_entry_pos(record_id INTEGER,div TEXT,pos TEXT,
        PRIMARY KEY(record_id,div,pos));
      DELETE FROM source_entry_pos;
      DELETE FROM source_query_forms;
      DELETE FROM source_word_forms;
      DELETE FROM source_head_grammar;
      DELETE FROM occurrences WHERE kind='compound-key';''')
    for row in db.execute('SELECT * FROM sources ORDER BY record_id'):
        key=row['headword']
        if compound_key(key):
            db.execute('INSERT INTO occurrences VALUES(?,?,?,?,?,?,?,?,?)',
                (key,row['record_id'],key,'compound-key','/', '',row['body'],row['defs'],row['examples']))
            counts['compound_source_records']+=1
    eligible={r[0] for r in db.execute("SELECT DISTINCT phrase FROM occurrences WHERE kind IN ('key','compound-key')")}
    verbs={r[0] for r in db.execute("SELECT word FROM lexical_pos WHERE pos='verb'")}
    nouns={r[0] for r in db.execute("SELECT word FROM lexical_pos WHERE pos='noun'")}
    if cache:
        def records():
            with open(path,encoding='utf8') as f:
                for line in f:yield json.loads(line)
    else:
        from mdict_utils.reader import MDX
        def records():
            for k,v in MDX(str(path)).items():yield k.decode('utf8'),v.decode('utf8')
    # A sense-level phrase inherits the word class of the homograph it sits in.
    sense_records={r[0] for r in db.execute("SELECT DISTINCT record_id FROM occurrences WHERE kind='lexunit'")}
    for rid,(key,source) in enumerate(records(),1):
        key=' '.join(key.split())
        if (rid not in sense_records and key not in eligible and key.lower() not in verbs
                and not (key.lower() in nouns and 'pluralform' in source)):continue
        root=html.fromstring(source)
        # Popup thesaurus entries can sit under the outer entryhead in the
        # source DOM. Their variants describe other words, not this headword.
        for popup in root.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," at-link ")]'):
            popup.drop_tree()
        for head in root.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," entryhead ")]'):
            hwds=head.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," hwd ")]')
            if not hwds or clean(hwds[0].text_content())!=clean(key):continue
            pos=' '.join(clean(n.text_content()) for n in head if 'pos' in n.get('class','').split())
            homograph=re.fullmatch(r'(/html/body/div(?:\[\d+\])?)/span/span\[1\]',head.getroottree().getpath(head))
            if homograph:
                for label in re.findall(POS_LABELS,pos):
                    db.execute('INSERT OR IGNORE INTO source_entry_pos VALUES(?,?,?)',(rid,homograph[1],label))
                    counts['source_entry_pos']+=1
            gram=' '.join(clean(n.text_content()) for n in head if 'gram' in n.get('class','').split())
            hyps=head.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," hyphenation ")]')
            syllables=1+len(hyps[0].xpath('.//*[starts-with(@class,"hs")]')) if hyps else None
            for label in re.findall(POS_LABELS,pos):
                db.execute('INSERT OR IGNORE INTO source_head_grammar VALUES(?,?,?,?,?)',(key,label,gram,syllables,rid))
            for cls,kind in [('ptandpp','past'),('ptandpp','participle'),('pasttense','past'),('pastpart','participle'),('prespart','ing'),('t3perssing','third'),('pluralform','plural')]:
                for node in head.xpath('.//*[contains(concat(" ",normalize-space(@class)," "),$cls)]',cls=' '+cls+' '):
                    nearest=next((p for p in node.iterancestors() if 'entryhead' in p.get('class','').split()),None)
                    if nearest is not head:continue
                    copy=html.fromstring(html.tostring(node,encoding='unicode'))
                    for label in list(copy.iterdescendants()):
                        if set(label.get('class','').split()) & {'infllab','italic','proncodes','geo','pron','neutral'}:
                            if label.getparent() is not None:label.drop_tree()
                    value=clean(copy.text_content()).strip(' ,;')
                    for form in re.split(r'\s*(?:,|/|\bor\b)\s*',value):
                        form=clean(form)
                        if not form or form==key or not re.fullmatch(r"[A-Za-z][A-Za-z '\-’]*",form):continue
                        db.execute('INSERT OR IGNORE INTO source_word_forms VALUES(?,?,?,?,?)',
                            (key,form,kind,rid,node.getroottree().getpath(node)))
                        counts['source_word_form_'+kind]+=1
            if key not in eligible:continue
            for cls,rule in [('lexvar','source_declared_lexical_variant'),('orthvar','source_declared_spelling_variant'),('pluralform','source_declared_plural')]:
                for node in head.xpath('.//*[contains(concat(" ",normalize-space(@class)," "),$cls)]',cls=' '+cls+' '):
                    nearest=next((p for p in node.iterancestors() if 'entryhead' in p.get('class','').split()),None)
                    if nearest is not head:continue
                    copy=html.fromstring(html.tostring(node,encoding='unicode'))
                    if cls=='pluralform':
                        for label in copy.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," infllab ") or contains(concat(" ",normalize-space(@class)," ")," italic ") or contains(concat(" ",normalize-space(@class)," ")," neutral ")]'):
                            label.drop_tree()
                    value=clean(copy.text_content()).strip(' ,;')
                    values=[value]
                    if ', ' in value and ',' not in key and not value[0].isupper():values=value.split(', ')
                    for alias in values:
                        alias=clean(alias)
                        if not alias or alias==key or alias.startswith('-') or len(alias)>160:continue
                        if re.search(r'\b(?:plural|past tense|participle|usually|especially)\b',alias):continue
                        db.execute('INSERT OR IGNORE INTO source_query_forms VALUES(?,?,?,?,?)',
                            (alias,key,rule,rid,node.getroottree().getpath(node)))
                        counts[rule]+=1
                        if len(examples)<25:examples.append([alias,key,rule])
        if rid%5000==0:print(f'supplemented through source record {rid:,}',flush=True)
    db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('supplemental_sources_version','2'))
    db.commit();db.close()
    return {'counts':dict(counts),'examples':examples,'policy':'Source compound headwords and explicit entry-head variants/plurals only; no automatic inflections.'}
