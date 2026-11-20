import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from lxml import html
from build_ldoce6_phrases import (alias_variants, assemble, extract, sc, scope_for, example_attests,
    plain, suppress_repeated_heading,explicit_parenthesized_choices, declared_plural_forms)
from phrase_alias_rules import enhanced_variants, full_alternatives, grouped_slashes, optional_forms
from supplement_phrase_sources import supplement_sources


class PhraseBuildTests(unittest.TestCase):
    def test_source_examples_validate_choices_without_generating_inflections(self):
        self.assertTrue(example_attests('be tarred with the same brush',
                        ["I'm tarred with the same brush as William."]))
        self.assertTrue(example_attests('be simplicity itself', ['Loading it is simplicity itself.']))
        self.assertFalse(example_attests('be kindness itself', ['Loading it is simplicity itself.']))
        self.assertFalse(example_attests('get tarred with the same brush',
                         ["I'm tarred with the same brush as William."]))
        self.assertFalse(example_attests('be a', ['It is a problem.']))
        self.assertTrue(example_attests('go to show something',
                        ['It goes to show how people judge appearances.'], initial_verb=True))
        self.assertFalse(example_attests('in style', ['ins style']))
        self.assertFalse(example_attests('interested party', ['All interested parties are invited.']))
        self.assertTrue(example_attests('interested party', ['All interested parties are invited.'],
                        {'party': {'parties'}}))
        self.assertFalse(example_attests('interested group', ['All interested groups are invited.'],
                         {'party': {'parties'}}))

    def test_source_choice_evidence_builds_basic_forms_only(self):
        records = [
            ['party', '<span class="entryhead"><span class="hwd">party</span><span class="pos">noun</span><span class="inflections">(plural parties)</span></span><span class="def">a group</span>'],
            ['interested', '<span class="sense"><span class="lexunit">interested party/group</span><span class="def">someone affected by the result</span><span class="example">All interested parties are invited.</span></span>'],
            ['tar', '<span class="sense"><span class="lexunit">be/get tarred with the same brush</span><span class="def">considered to have the same faults</span><span class="example">She was tarred with the same brush.</span></span>'],
            ['itself', '<span class="sense"><span class="lexunit">be patience/kindness/simplicity etc itself</span><span class="def">be very patient, kind or simple</span><span class="example">Loading it is simplicity itself.</span></span>'],
            ['go', '<span class="entryhead"><span class="hwd">go</span><span class="pos">verb</span></span><span class="sense"><span class="lexunit">go to show/prove/indicate etc something</span><span class="def">help to prove something</span><span class="example">It goes to show how people judge appearances.</span></span>'],
            ['show', '<span class="entryhead"><span class="hwd">show</span><span class="pos">verb</span></span><span class="def">demonstrate</span>'],
            ['prove', '<span class="entryhead"><span class="hwd">prove</span><span class="pos">verb</span></span><span class="def">demonstrate truth</span>'],
            ['indicate', '<span class="entryhead"><span class="hwd">indicate</span><span class="pos">verb</span></span><span class="def">show</span>'],
            ['swing', '<span class="phrvbentry"><span class="phrvbhwd">swing around/round</span><span class="def">turn something around</span><span class="example">He swung the boat around.</span></span>'],
        ]
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); src = root/'input.jsonl'; db = root/'source.sqlite'
            src.write_text(''.join(json.dumps(x)+'\n' for x in records), encoding='utf8')
            extract(src, db, cache=True); supplement_sources(src, db, cache=True)
            report = assemble(db, root, 'test')
            with zipfile.ZipFile(report['package']) as z:
                rows = {r[0]: r for n in z.namelist() if n.startswith('term_bank_')
                        for r in json.loads(z.read(n))}
            for key in ['interested party', 'tarred with the same brush', 'simplicity itself',
                        'go to show', 'swing around', 'swing round']:
                self.assertIn(key, rows)
            for key in ['interested parties', 'is simplicity itself', 'was tarred with the same brush',
                        'interested group', 'kindness itself', 'get tarred with the same brush',
                        'prove something', 'prove sth']:
                self.assertNotIn(key, rows)

    def test_declared_plural_evidence_stays_with_its_own_noun_head(self):
        def span(cls, text): return {'data': {'class': 'l6p-'+cls}, 'content': text}
        body = span('entryhead', [span('hwd', 'party'), span('pos', 'noun'),
                                  span('inflections', '(plural parties)')])
        self.assertEqual(declared_plural_forms(body, 'party'), {'parties'})
        self.assertEqual(declared_plural_forms(body, 'group'), set())
        body['content'][1] = span('pos', 'verb')
        self.assertEqual(declared_plural_forms(body, 'party'), set())

    def test_same_spelling_senses_and_existing_lookup_targets_are_preserved(self):
        records = [
            ['put out', '<span class="entryhead"><span class="hwd">put out</span><span class="pos">adjective</span></span><span class="def">upset or offended</span>'],
            ['put', '<span class="phrvbentry"><span class="phrvbhwd">put out</span><span class="def">cause extra work for someone</span></span>'
             '<span class="phrvbentry"><span class="phrvbhwd">put somebody away</span><span class="def">send someone to prison</span></span>'
             '<span class="phrvbentry"><span class="phrvbhwd">put something away</span><span class="def">store something</span></span>'],
            ['drag', '<span class="phrvbentry"><span class="phrvbhwd">drag something out of somebody</span><span class="def">force someone to tell you something</span></span>'],
        ]
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); src = root/'input.jsonl'; db = root/'source.sqlite'
            src.write_text(''.join(json.dumps(x)+'\n' for x in records), encoding='utf8')
            extract(src, db, cache=True); supplement_sources(src, db, cache=True)
            report = assemble(db, root, 'test')
            with zipfile.ZipFile(report['package']) as z:
                rows = {r[0]: r for n in z.namelist() if n.startswith('term_bank_')
                        for r in json.loads(z.read(n))}
            body = plain(rows['put out'][5])
            self.assertIn('upset or offended', body)
            self.assertIn('cause extra work for someone', body)
            self.assertEqual({x[0] for x in rows['put away'][5]},
                             {'put somebody away', 'put something away'})
            self.assertEqual(rows['drag out of'][5],
                             [['drag something out of somebody', ['redirect']]])

    def test_no_guessed_inflections_pronouns_or_unmarked_omissions(self):
        records = [
            ['give', '<span class="entryhead"><span class="hwd">give</span><span class="pos">verb</span><span class="pasttense">gave</span></span><span class="sense"><span class="lexunit">give somebody a hand</span><span class="def">help someone</span></span>'],
            ['be', '<span class="sense"><span class="lexunit">be to do something</span><span class="def">an arrangement</span></span>'],
            ['endear', '<span class="sense"><span class="lexunit">endear somebody to somebody</span><span class="def">make someone liked</span></span>'],
            ['re-form', '<span class="entryhead"><span class="hwd">re-form</span><span class="pos">verb</span></span><span class="def">form again</span>'],
            ['Diana, Princess of Wales', '<span class="entryhead"><span class="hwd">Diana, Princess of Wales</span><span class="lexvar">Princess Di, Princess Diana, Lady Di</span><span class="lexvar">Lady Diana</span></span><span class="def">a princess</span>'],
        ]
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); src=root/'input.jsonl'; db=root/'extraction.sqlite'
            src.write_text(''.join(json.dumps(x)+'\n' for x in records),encoding='utf8')
            extract(src,db,cache=True); supplemental=supplement_sources(src,db,cache=True)
            report=assemble(db,root,'test')
            with zipfile.ZipFile(report['package']) as z:
                rows={r[0]:r for n in z.namelist() if n.startswith('term_bank_') for r in json.loads(z.read(n))}
            for key in ['give him a hand','gave somebody a hand','give a hand','being to do something',
                        'to do something','endear to','re form','Princess Di, Princess Diana, Lady Di']:
                self.assertNotIn(key,rows,key)
            for key in ['give somebody a hand','give sb a hand','be to do something','re-form','Lady Diana']:
                self.assertIn(key,rows,key)
            self.assertFalse(report['automatic_inflection_aliases'])
            self.assertEqual(supplemental['counts']['ambiguous_declared_form_skipped'],1)

    def test_complete_slash_alternatives_preserve_phrase_boundaries(self):
        self.assertEqual(full_alternatives('make up your mind/make your mind up'),
                         {'make up your mind', 'make your mind up'})
        self.assertEqual(full_alternatives('keep something quiet/keep quiet (about something)'),
                         {'keep something quiet', 'keep quiet (about something)'})
        self.assertEqual(full_alternatives('stand firm/stand fast etc'), {'stand firm', 'stand fast'})
        self.assertEqual(full_alternatives('a shot across the bows/a warning shot (across the bows)'),
                         {'a shot across the bows', 'a warning shot (across the bows)'})
        for phrase in ('be mad about/for/on somebody', 'be supposed to do/be something',
                       'answer criticism/charges/accusations etc'):
            self.assertFalse(full_alternatives(phrase), phrase)

    def test_source_separable_slots_do_not_need_all_surface_objects(self):
        aliases,_=enhanced_variants('pen somebody/something up/in',
            ['pen somebody/something ↔ up/in'],{}, {},[],lambda s:[],example_attests)
        for key in ['pen up somebody','pen somebody in','pen in sth']:
            self.assertIn(key,aliases)
        self.assertNotIn('pen him in',aliases)  # Runtime supplies actual objects.

    def test_compounds_case_and_declared_plural_have_source_evidence(self):
        records=[['self-explanatory','<span class="entryhead"><span class="hwd">self-explanatory</span><span class="orthvar">self‧explanatory</span><span class="buttons"><span class="at-link"><span class="lexvar">unrelated vocabulary</span></span></span></span><span class="def">easy to understand</span>'],
            ['A level','<span class="entryhead"><span class="hwd">A level</span></span><span class="def">an examination</span>'],
            ['court martial','<span class="entryhead"><span class="hwd">court martial</span><span class="inflections"><span class="pluralform"><span class="italic">plural </span>courts martial</span></span></span><span class="def">a military court</span>']]
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);src=root/'input.jsonl';db=root/'source.sqlite'
            src.write_text(''.join(json.dumps(x)+'\n' for x in records),encoding='utf8')
            extract(src,db,cache=True);supplement_sources(src,db,cache=True)
            report=assemble(db,root,'test')
            with zipfile.ZipFile(report['package']) as z:
                rows={r[0]:r for n in z.namelist() if n.startswith('term_bank_') for r in json.loads(z.read(n))}
            self.assertNotIn('self explanatory',rows)
            self.assertEqual(rows['a level'][5],[['A level',['redirect']]])
            self.assertEqual(rows['courts martial'][5],[['court martial',['redirect']]])
            self.assertNotIn('a levels',rows)
            self.assertNotIn('explained',rows)
            self.assertNotIn('unrelated vocabulary',rows)
            self.assertIn('selfexplanatory',rows)
            self.assertNotIn('self‧explanatory',rows)

    def test_group_boundaries_and_etc_are_words(self):
        lexicon={w:{p} for w,p in [('hat','noun'),('football','noun'),('boots','noun'),('briefcase','noun'),
            ('appetite','noun'),('thirst','noun'),('sweat','noun'),('run','verb'),('stretch','verb'),
            ('walk','verb'),('hate','verb'),('look','noun'),('take','verb'),('have','verb'),('camping','noun'),
            ('gear','noun'),('equipment','noun'),('fire','noun'),('police','noun'),('station','noun')]}
        lexicon.update({w:{'verb'} for w in ['rise','come','return','like','know','understand','get','go','keep']})
        lexicon['sweat']={'noun','verb'};lexicon['like']={'verb','preposition'}
        preferred={w:next(iter(ps)) for w,ps in lexicon.items()}
        preferred['sweat']='verb';preferred['like']='preposition'
        resolve=lambda s:grouped_slashes(s,lexicon,preferred)
        self.assertEqual(resolve('hang up your hat/football boots/briefcase etc'),
            {'hang up your hat','hang up your football boots','hang up your briefcase'})
        self.assertEqual(resolve('work up an appetite/a thirst/a sweat'),
            {'work up an appetite','work up a thirst','work up a sweat'})
        self.assertEqual(resolve("be sick of/can't stand/hate the sight of somebody/something"),
            {p+' the sight of '+o for p in ['be sick of',"can't stand",'hate'] for o in ['somebody','something']})
        self.assertEqual(resolve('run/stretch/walk etc the length of something'),
            {v+' the length of something' for v in ['run','stretch','walk']})
        self.assertEqual(resolve('have a look/take a look'),{'have a look','take a look'})
        self.assertFalse(resolve('camping gear/equipment'))
        self.assertFalse(resolve('fire/police station'))
        self.assertFalse(resolve('a shot across the bows/a warning shot'))
        self.assertFalse(resolve('a wide variation/difference/gap etc'))
        self.assertEqual(resolve('rise/come back/return from the dead'),
            {'rise from the dead','come back from the dead','return from the dead'})
        self.assertEqual(resolve('get to like/know/understand somebody'),
            {'get to like somebody','get to know somebody','get to understand somebody'})
        lexicon.update({w:{'verb'} for w in ['show','prove','indicate']})
        self.assertEqual(resolve('go to show/prove/indicate etc something'),
            {'go to show something','go to prove something','go to indicate something'})
        self.assertEqual(resolve('be/go/keep on at somebody'),
            {'be on at somebody','go on at somebody','keep on at somebody'})

    def test_enhanced_lookup_preserves_lexical_words_and_uses_source_marker(self):
        self.assertEqual(optional_forms('eye(s)'),{'eye','eyes'})
        aliases,_=enhanced_variants('bring somebody down',['bring somebody ↔ down'],{}, {},[],lambda s:[],example_attests)
        self.assertIn('bring down somebody',aliases)
        self.assertIn('bring down sb',aliases)
        self.assertNotIn('bring down',aliases)
        aliases,_=enhanced_variants('be at your wits’ end!',['be at your wits’ end!'],{}, {},[],lambda s:[],example_attests)
        self.assertIn("be at your wits' end",aliases)
        self.assertNotIn("at wits' end",aliases)
        aliases,_=enhanced_variants('hang by a thread',['hang by a thread'],{}, {},[],lambda s:[],example_attests)
        self.assertNotIn('hanging by a thread',aliases)
        aliases,_=enhanced_variants('Dylan, Bob',['Dylan, Bob'],{}, {},[],lambda s:[],example_attests)
        self.assertNotIn('Bob Dylan',aliases)
        aliases,_=enhanced_variants('Daily Mirror, The',['Daily Mirror, The'],{}, {},[],lambda s:[],example_attests)
        self.assertIn('The Daily Mirror',aliases)

    def test_headword_not_duplicated_and_metadata_has_real_separators(self):
        source=html.fromstring('''<span class="entryhead"><span class="hwd">abandon</span><span
          class="hyphenation frequent">a<span class="hs0"></span>ban<span class="hs0"></span>don</span><span
          class="homnum frequent">1</span><span class="proncodes">/<span class="pron">əˈbændən</span>/</span><span
          class="level tooltip">●●○</span><span class="freq">W3</span><span class="ac">AWL</span><span
          class="pos">verb</span><span class="gram">[transitive]</span></span>''')
        body=sc(source)
        self.assertEqual(plain(body),'abandon 1 /əˈbændən/ ●●○ W3 AWL verb [transitive]')
        self.assertEqual(plain(body).count('abandon'),1)
        homnum=next(x for x in body['content'] if isinstance(x,dict) and x.get('data',{}).get('class')=='l6p-homnum')
        self.assertEqual(homnum['style']['verticalAlign'],'super')
        self.assertNotIn('abandon',plain(suppress_repeated_heading(body,'abandon')))

    def test_explicit_choices_and_required_constituents(self):
        self.assertTrue(explicit_parenthesized_choices("(hard/hot/close) on somebody's heels"))
        self.assertFalse(explicit_parenthesized_choices('(have a look/take a look)'))
        for phrase,bad in [('endear somebody to somebody','endear to'),
                           ("a word in somebody's ear",'a word in ear'),
                           ('be hard on somebody','hard on somebody')]:
            aliases,_=enhanced_variants(phrase,[phrase],{}, {},[],lambda s:[],example_attests)
            self.assertNotIn(bad,aliases)

    def test_hang_uses_its_own_sense_and_preserves_subsenses(self):
        source=html.fromstring('''<div><span class="sense"><span class="sensenum">8</span>
          <span class="def">a neighbouring, unrelated definition</span></span>
          <span class="sense newline"><span class="sensenum">9</span>
          <span class="lexunit newline">hang by a thread</span>
          <span class="def">in danger of ending</span><span class="example">His life is
          <span class="nodeword">hanging by a thread</span>.</span></span></div>''')
        node=source.xpath('//*[@class="lexunit newline"]')[0]
        payload=json.dumps(sc(scope_for(node,'lexunit')))
        self.assertIn('in danger of ending',payload)
        self.assertNotIn('unrelated',payload)
        self.assertIn('hanging by a thread',payload)

    def test_alias_scope_and_placeholders(self):
        self.assertEqual(alias_variants('hang by a thread')[0],{})
        aliases,_=alias_variants('answer criticism/charges/accusations etc')
        self.assertIn('answer charges',aliases)
        aliases,_=alias_variants("(hard/hot/close) on somebody's heels")
        self.assertIn("hot on somebody's heels",aliases)
        self.assertIn("on sb's heels",aliases)
        aliases,review=alias_variants('have a look/take a look')
        self.assertNotIn('have a take a look',aliases)
        self.assertIn('ambiguous_slash',review)
        for phrase,bad in [('work up an appetite/a thirst/a sweat','work up an appetite thirst sweat'),
                           ('hang up your hat/football boots/briefcase etc','hang up your hat boots etc')]:
            aliases,review=alias_variants(phrase)
            self.assertNotIn(bad,aliases)
            self.assertIn('multiword_slash_boundary',review)
        self.assertFalse(example_attests("there's a good boy dog",["There's a good boy!", "There's a clever dog!"]))
        aliases,review=alias_variants('$100/50 a clip')
        self.assertNotIn('$50 a clip',aliases)
        self.assertIn('ambiguous_slash',review)

    def test_duplicate_records_contexts_and_reference_only_are_explicit(self):
        records=[['hang','''<div><span class="sense"><span class="lexunit">hang by a thread</span>
          <span class="def">in great danger</span><span class="example">His life is hanging by a thread.</span>
          </span><span class="phrase"><span class="phrasetext">an unresolved phrase</span></span></div>'''],
          ['a shared phrase','<span class="entry"><span class="sense"><span class="def">first meaning</span></span></span>'],
          ['a shared phrase','<span class="entry"><span class="sense"><span class="def">second meaning</span></span></span>'],
          ['camping','<span class="sense"><span class="lexunit newline">camping gear/equipment</span><span class="example">camping equipment</span></span>'],
          ['act','<div><span class="menuitem"><span class="phrv">act something out</span></span><span class="phrvbentry"><span class="phrvbhwd">act something ↔ out</span><span class="sense"><span class="def">perform it</span></span></span></div>'],
          ['A named group','<span class="sense"><span class="lexunit">A named group</span><span class="relatedwd"><span class="neutral"> → </span>ABC</span></span>'],
          ['ABC','<span class="sense"><span class="def">an organization</span></span>']]
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); src=root/'input.jsonl'
            src.write_text(''.join(json.dumps(x)+'\n' for x in records),encoding='utf-8')
            extract(src,root/'source.sqlite',cache=True)
            report=assemble(root/'source.sqlite',root,'test')
            with zipfile.ZipFile(report['package']) as z:
                rows=[r for n in z.namelist() if n.startswith('term_bank_') for r in json.loads(z.read(n))]
            bodies={r[0]:r for r in rows if r[2] in {'phrase','phrase-reference'}}
            self.assertEqual(len(bodies),6)
            self.assertIn('perform it',json.dumps(bodies['act something out']))
            self.assertNotIn('act something ↔ out',bodies)
            self.assertEqual(report['notation_duplicates_merged'],1)
            self.assertEqual(report['counts']['cross_reference'],1)
            self.assertIn('first meaning',json.dumps(bodies['a shared phrase']))
            self.assertIn('second meaning',json.dumps(bodies['a shared phrase']))
            self.assertEqual(report['counts']['reference_only'],1)
            self.assertIn('hang',{r[0] for r in rows if r[2]=='source-context'})
            self.assertEqual(len({r[0] for r in rows}),len(rows))


if __name__=='__main__': unittest.main()
