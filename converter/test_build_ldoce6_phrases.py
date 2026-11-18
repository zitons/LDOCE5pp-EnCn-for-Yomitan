import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from lxml import html
from build_ldoce6_phrases import (alias_variants, assemble, extract, sc, scope_for, example_attests,
    plain, lexical_slash_slots, omit_terminal_object, suppress_repeated_heading,explicit_parenthesized_choices)


class PhraseBuildTests(unittest.TestCase):
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
