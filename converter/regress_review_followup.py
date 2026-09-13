"""Fast regression tests for F1/F2/F3; scratch builds never touch yomitan_full.
Run: venv/Scripts/python.exe -X utf8 converter/regress_review_followup.py
"""
import contextlib
import gc
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile
from bs4 import BeautifulSoup
import ldoce2yomitan as C
import _apply_patch as patch
ROOT=Path(__file__).resolve().parents[1]

def flat(n):
    if isinstance(n,str):return n
    if isinstance(n,list):return ''.join(map(flat,n))
    return flat(n.get('content','')) if isinstance(n,dict) else ''

def markup(word,body):
    return ('<div class="entry_content"><div class="ldoceEntry"><span class="Head">'
            f'<span class="HWD">{word}</span><span class="lm5pp_POS">noun</span>'
            '</span>'+body+'</div></div>')

def write(path,text):
    patch.P=str(path);patch.write_atomic(text)
    assert path.read_bytes()==text.encode('utf-8')

class TextRegressions(unittest.TestCase):
    def renderer(self,mode='mono'):
        index=C.TermIndex()
        for word in ('sample','re','t','known','model','kits'):index.add(word)
        return C.LdoceRenderer(index,mode=mode)
    def render(self,body,mode='mono'):
        return self.renderer(mode).render_record('sample',markup('sample',body))
    def link(self,text):return C.sc('a',text,href='?query=sample')

    def test_contractions_and_continuations(self):
        cases=[(['You’',self.link('re')],'You’re'),
               (['I didn’',self.link('t')],'I didn’t'),
               ([self.link('Don'),'’',self.link('t')],'Don’t'),
               ([self.link('Don’'),self.link('t')],'Don’t'),
               (["I'",C.sc('span','m',cls='ld-b')],"I'm"),
               ([self.link('terrorist'),'s'],'terrorists'),
               ([self.link('download'),'ed'],'downloaded'),
               ([self.link('SUM'),'1'],'SUM1')]
        for nodes,expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(flat(C.separate_inline_runs(nodes)),expected)

    def test_preserve_word_and_chip_separators(self):
        cases=[([self.link('coal'),' ',self.link('mines')],'coal mines'),
               (['coal ','mines'],'coal mines'),
               ([self.link('model'),self.link('kits')],'model kits'),
               ([C.sc('span','noun',cls='ld-pos'),C.sc('span','[countable]',cls='ld-gram')],'noun [countable]'),
               ([C.sc('span','informal',cls='ld-register'),C.sc('span','a)',cls='ld-snum')],'informal a)'),
               ([C.sc('span','/x/',cls='ld-pronblk'),C.sc('span','noun',cls='ld-pos')],'/x/ noun')]
        for nodes,expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(flat(C.separate_inline_runs(C.merge_adjacent_text(nodes))),expected)

    def test_all_title_translations_removed_only_in_mono(self):
        h=BeautifulSoup('<span class="heading"><span class="en_txt">GRAMMAR '
            '<span class="cn_txt">语法</span>: Verb patterns '
            '<span class="cn_txt">动词句型</span></span></span>','lxml').find('span')
        self.assertEqual(self.renderer()._panel_title(h,'GramBox'),('GRAMMAR : Verb patterns',None))
        self.assertEqual(self.renderer('bilingual')._panel_title(h,'GramBox'),
                         ('GRAMMAR : Verb patterns 动词句型','语法'))
        h=BeautifulSoup('<span class="heading">Usage <span class="cn_txt_ext">'
            '用法<span class="cn_txt">注</span></span></span>','lxml').find('span')
        self.assertEqual(self.renderer()._panel_title(h,'GramBox'),('Usage',None))

    def test_chinese_register_all_dispatch_paths(self):
        for tag in ('span','div'):
            el=BeautifulSoup(f'<{tag} class="REGISTERLAB LDOCE_switch_lang switch_siblings">'
                            f'【正式】</{tag}>','lxml').find(tag)
            cls=C.classes_of(el);r=self.renderer()
            for nodes in (r.render_element(el),r.render_inline_node(el),r.render_div(el,cls)):
                self.assertFalse(C.sc_has_text(nodes))
            self.assertIn('正式',flat(self.renderer('bilingual').render_element(el)))

    def test_language_switch_flags_are_not_language_labels(self):
        for cls in ('REGISTERLAB','DEF'):
            self.assertIn('formal English',flat(self.render(
                f'<span class="{cls} LDOCE_switch_lang switch_siblings">formal English</span>')))

    def test_not_notes_preserve_english_and_bilingual_text(self):
        for annotation in ('不用',' 不说 '):
            for wrapper in ('{}','<b>{}</b>'):
                text='Do this (NOT'+annotation+'that).'
                body=('<div class="EXAMPLE"><span class="english">'+wrapper.format(text)+
                      '<div class="cn_txt">译文</div></span></div>')
                mono=flat(self.render(body));bi=flat(self.render(body,'bilingual'))
                self.assertIn('Do this (NOT that).',mono)
                self.assertIsNone(C.CJK_RE.search(mono))
                self.assertIn(text,bi);self.assertIn('译文',bi)

    def test_unknown_cjk_is_left_for_validation(self):
        self.assertIn('字',flat(self.render('<div class="EXAMPLE">An unexpected 字.</div>')))

class PublicationRegressions(unittest.TestCase):
    def setUp(self):
        root=ROOT/'converter/audit_2026_09_13_followup/builds'
        root.mkdir(parents=True,exist_ok=True)
        self.work=Path(tempfile.mkdtemp(prefix='regression-',dir=root)).resolve()
        self.assertTrue(self.work.is_relative_to(root.resolve()))
        self.source=self.work/'records.mdx.txt';self.out=self.work/'out'
        self.good=[('audit-ok',markup('audit-ok','<span class="DEF">First.</span>')),
                   ('audit-broken',markup('audit-broken','<span class="DEF">Second.</span>'))]
        self.records(self.good)
    def records(self,records):
        write(self.source,''.join(k+'\n'+html+'\n</>\n' for k,html in records))
    def invoke(self,**kwargs):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return C.build(self.source,self.out,show_progress=False,**kwargs)
    def snapshot(self):
        return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.out.iterdir() if p.is_file()}
    def break_second_record(self):
        deep='<span>'*450+'definition'+'</span>'*450
        self.records([self.good[0],('audit-broken',markup('audit-broken',deep))])

    def test_renderer_error_after_bank_flush_is_never_published(self):
        with mock.patch.object(C,'TERM_BANK_BATCH',1):
            self.invoke(revision='good');before=self.snapshot();threshold=gc.get_threshold()
            self.break_second_record()
            for validate in (True,False):
                with self.subTest(validate=validate):
                    with self.assertRaises(C.BuildValidationError) as caught:
                        self.invoke(revision='must-not-publish',validate=validate)
                    self.assertTrue(any('render' in e.lower() for e in caught.exception.errors))
                    self.assertEqual(self.snapshot(),before)
                    self.assertEqual(gc.get_threshold(),threshold)

    def test_real_cli_rejects_render_failure_even_with_skip_validation(self):
        self.invoke(revision='good');before=self.snapshot();self.break_second_record()
        args=['-i',str(self.source),'-o',str(self.out),'--no-progress','--revision','bad']
        for extra in ([],['--skip-validation']):
            with contextlib.redirect_stdout(io.StringIO()) as log,contextlib.redirect_stderr(io.StringIO()):
                rc=C.main(args+extra)
            self.assertEqual(rc,2)
            self.assertNotIn('[OK] Dictionary package',log.getvalue())
            self.assertEqual(self.snapshot(),before)

    def test_duplicate_keys_are_not_misclassified_as_render_failures(self):
        self.records([('same',markup('same','<span class="DEF">One.</span>')),
                      ('same',markup('same','<span class="DEF">Two.</span>'))])
        p=self.invoke()
        with zipfile.ZipFile(p) as z:rows=json.loads(z.read('term_bank_1.json'))
        self.assertEqual(len(rows),2);self.assertEqual([r[6] for r in rows],[0,1])

    def test_failed_homograph_is_not_hidden_by_a_successful_same_key(self):
        self.records([('same',markup('same','<span class="DEF">One.</span>')),
                      ('same',markup('same','<span class="DEF">Two.</span>'))])
        self.invoke();before=self.snapshot()
        deep='<span>'*450+'definition'+'</span>'*450
        self.records([('same',markup('same','<span class="DEF">One.</span>')),
                      ('same',markup('same',deep))])
        with self.assertRaises(C.BuildValidationError):self.invoke()
        self.assertEqual(self.snapshot(),before)

    def test_all_render_failures_count_even_when_diagnostics_are_capped(self):
        self.invoke();before=self.snapshot()
        deep='<span>'*450+'definition'+'</span>'*450
        self.records([self.good[0]]+[(f'bad-{i}',markup(f'bad-{i}',deep)) for i in range(10)])
        with self.assertRaises(C.BuildValidationError) as caught:self.invoke()
        self.assertIn('10 source record(s)',caught.exception.errors[0])
        self.assertEqual(len(caught.exception.errors),9)  # summary + first 8 diagnostics
        self.assertEqual(self.snapshot(),before)

    def test_unknown_mono_cjk_is_still_rejected(self):
        package=Path(self.invoke(mode='mono'))
        digest=hashlib.sha256(package.read_bytes()).hexdigest()
        self.records([('sample',markup('sample','<span class="DEF">Unexpected 字.</span>'))])
        with self.assertRaises(C.BuildValidationError) as caught:self.invoke(mode='mono')
        self.assertTrue(any('CJK' in err for err in caught.exception.errors))
        self.assertEqual(hashlib.sha256(package.read_bytes()).hexdigest(),digest)

    def test_successful_build_may_skip_validation(self):
        self.assertTrue(Path(self.invoke(validate=False)).is_file())

if __name__=='__main__':unittest.main(verbosity=2)
