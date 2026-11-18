import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from lxml import html
from build_ldoce6_phrases import (alias_variants, assemble, extract, sc, scope_for, example_attests,
    plain, lexical_slash_slots, omit_terminal_object, suppress_repeated_heading,explicit_parenthesized_choices)
from phrase_alias_rules import enhanced_variants, full_alternatives, grouped_slashes, optional_forms
from supplement_phrase_sources import supplement_sources


class PhraseBuildTests(unittest.TestCase):
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
        for key in ['pen up','pen in','pen up somebody','pen somebody in','pen in sth']:
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
            self.assertEqual(rows['self explanatory'][5],[['self-explanatory',['redirect']]])
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
        self.assertEqual(resolve('be/go/keep on at somebody'),
            {'be on at somebody','go on at somebody','keep on at somebody'})

    def test_enhanced_lookup_preserves_lexical_words_and_uses_source_marker(self):
        self.assertEqual(optional_forms('eye(s)'),{'eye','eyes'})
        aliases,_=enhanced_variants('bring somebody down',['bring somebody ↔ down'],{}, {},[],lambda s:[],example_attests)
        self.assertIn('bring down somebody',aliases)
        self.assertIn('bring down sb',aliases)
        self.assertIn('bring down',aliases)
        aliases,_=enhanced_variants('be at your wits’ end!',['be at your wits’ end!'],{}, {},[],lambda s:[],example_attests)
        self.assertIn("at your wits' end",aliases)
        self.assertNotIn("at wits' end",aliases)
        aliases,_=enhanced_variants('hang by a thread',['hang by a thread'],{}, {},[],lambda s:[],example_attests)
        self.assertNotIn('hanging by a thread',aliases)
        aliases,_=enhanced_variants('Dylan, Bob',['Dylan, Bob'],{}, {},[],lambda s:[],example_attests)
        self.assertIn('Bob Dylan',aliases)

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

    def test_source_pos_choices_and_limited_placeholder_omission(self):
        lexicon={'criticism':{'noun'},'charge':{'noun','verb'},'accusation':{'noun'},
                 'have':{'verb'},'know':{'verb'},'boy':{'noun'},'clever':{'adjective'}}
        self.assertTrue(lexical_slash_slots('answer criticism/charges/accusations etc',lexicon))
        self.assertTrue(lexical_slash_slots('have/know all the answers',lexicon))
        self.assertFalse(lexical_slash_slots("there's a good boy/clever dog etc",lexicon))
        self.assertTrue(explicit_parenthesized_choices("(hard/hot/close) on somebody's heels"))
        self.assertFalse(explicit_parenthesized_choices('(have a look/take a look)'))
        self.assertEqual(omit_terminal_object('abandon yourself to something'),'abandon yourself to')
        self.assertEqual(omit_terminal_object('be hard on sb'),'be hard on')
        self.assertIsNone(omit_terminal_object('take something'))
        self.assertIsNone(omit_terminal_object('give somebody something'))
        self.assertFalse(lexical_slash_slots('hang up your hat/football boots',{'hat':{'noun'},'football':{'noun'},'boots':{'noun'}}))
        self.assertFalse(lexical_slash_slots('hang up your hat/football boots',{'hat':{'noun'},'football':{'noun'},'boot':{'noun'}}))
        self.assertFalse(lexical_slash_slots('your heart/thoughts go out',{'heart':{'noun'},'thought':{'noun'},'go':{'verb'}}))
        self.assertFalse(lexical_slash_slots('bring charges/a lawsuit',{'charge':{'noun'},'a':{'noun','determiner'}}))

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
