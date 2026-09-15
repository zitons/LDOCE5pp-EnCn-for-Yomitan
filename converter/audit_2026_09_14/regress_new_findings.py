"""Regression coverage for the 2026-09-14 fixes (N1/N2); red on the audited baseline.
Self-contained source fixtures, no corpus dependency, no production ZIP writes.
Retains temporary publication fixtures under this audit's ignored results/.
"""
import contextlib
import gc
import json
import hashlib
import io
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'converter'))
import ldoce2yomitan as C


def plain(node):
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return ''.join(map(plain, node))
    if isinstance(node, dict):
        if 'ld-mark' in node.get('data', {}).get('class', '').split():
            return ''
        return plain(node.get('content', ''))
    return ''


def render(html, mode='bilingual'):
    index = C.TermIndex()
    for word in ('relieve', 'fertilize', 'd', 're', 'download'):
        index.add(word)
    renderer = C.LdoceRenderer(index, mode=mode)
    result = renderer.render_record('probe', '<div class="entry_content">' + html + '</div>')
    return re.sub(r'\s+', ' ', plain(result)).strip()


class NewReviewRegressions(unittest.TestCase):
    def test_linked_suffix_is_not_split(self):
        for mode in ('bilingual', 'mono'):
            for stem in ('relieve', 'fertilize'):
                with self.subTest(mode=mode, stem=stem):
                    html = ('<span class="DEF"><span class="NonDV">'
                            f'<a class="defRef" href="entry://{stem}">{stem}</a>'
                            '</span><a class="defRef" href="entry://d">d</a></span>')
                    self.assertEqual(render(html, mode), stem + 'd')

    def test_negative_contraction_is_not_split(self):
        for mode in ('bilingual', 'mono'):
            with self.subTest(mode=mode):
                html = ('<div class="EXAMPLE"><span class="english">I did'
                        '<span class="COLLOINEXA">n\u2019t</span> know anybody.'
                        '</span></div>')
                self.assertEqual(render(html, mode), 'I didn\u2019t know anybody.')

    def test_existing_seam_controls_remain_valid(self):
        self.assertEqual(render('You\u2019<a href="entry://re">re</a>'), 'You\u2019re')
        self.assertEqual(render('<a href="entry://download">download</a>ed'), 'downloaded')
        self.assertEqual(render('<span class="GRAM">[countable]</span>'
                                '<span class="lm5pp_POS">noun</span>'), '[countable] noun')
        self.assertEqual(render('model <span class="NonDV">kits</span>'), 'model kits')

    def test_word_fragment_shapes_and_spelling_controls(self):
        def tag(text):
            return C.sc('a', text, href='?query=probe')
        for stem in ('relieve', 'fertilize', 'agree', 'argue', 'glue'):
            for left, right in ((stem, tag('d')), (tag(stem), tag('d')), (tag(stem), 'd')):
                with self.subTest(stem=stem, left=type(left).__name__, right=type(right).__name__):
                    self.assertEqual(plain(C.separate_inline_runs([left, right])), stem + 'd')
        for head, tail in (('did', "n't"), ('did', 'n\u2019t'), ('DID', "N'T"),
                           ('do', "n't"), ('is', "n't"), ('ca', "n't"), ('wo', "n't")):
            for left, right in ((head, tag(tail)), (tag(head), tag(tail)), (tag(head), tail)):
                with self.subTest(head=head, tail=tail):
                    self.assertEqual(plain(C.separate_inline_runs([left, right])), head + tail)

    def test_word_spaces_and_labels_are_not_collapsed(self):
        def tag(text):
            return C.sc('a', text, href='?query=probe')
        cases = [
            ([tag('model'), tag('kits')], 'model kits'),
            ([tag('games'), tag('console')], 'games console'),
            ([tag('coal'), tag('mines')], 'coal mines'),
            ([tag('three'), tag('days')], 'three days'),
            ([tag('grade'), ' ', tag('d')], 'grade d'),
            (['grade ', tag('d')], 'grade d'),
            ([tag('grade'), tag(' d')], 'grade d'),
            ([tag('vitamin'), tag('D')], 'vitamin D'),
            ([tag('10'), tag('d')], '10 d'),
            ([C.sc('span', 'adjective', cls='ld-pos'), tag('d')], 'adjective d'),
            ([tag('grade'), C.sc('span', 'd', cls='ld-gram')], 'grade d'),
            ([C.sc('span', 'did', cls='ld-gram'), tag("n't")], "did n't"),
            (['did ', tag("n't")], "did n't"),
            (['do', tag("n'thing")], "do n'thing"),
        ]
        for nodes, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(plain(C.separate_inline_runs(nodes)), expected)

    def assert_empty_record_rejected(self, duplicate, validate):
        parent = Path(__file__).resolve().parent / 'results'
        parent.mkdir(exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix='empty-gate-', dir=parent))
        # No recursive deletion: evidence is intentionally retained in this new directory.
        self.assertTrue(work.resolve().is_relative_to(parent.resolve()))
        source = work / 'source.txt'
        out = work / 'out'
        def record(key, text):
            return f'{key}\n<div class="entry_content">{text}</div>\n</>\n'
        second = 'kept' if duplicate else 'lost'
        source.write_text(record('kept', 'First definition.') + record(second, 'Second definition.'), encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            package = Path(C.build(str(source), str(out), revision='audit-negative', show_progress=False))
        before = hashlib.sha256(package.read_bytes()).hexdigest()
        source.write_text(record('kept', 'First definition.') + record(second, ''), encoding='utf-8')
        rejected = False
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            try:
                C.build(str(source), str(out), revision='audit-negative', show_progress=False, validate=validate)
            except C.BuildValidationError:
                rejected = True
        preserved = before == hashlib.sha256(package.read_bytes()).hexdigest()
        (work / 'attempt.log').write_text(log.getvalue(), encoding='utf-8')
        self.assertTrue(rejected and preserved,
                        f'Empty source record silently lost: rejected={rejected}, old_zip_preserved={preserved}, fixture={work}')

    def test_empty_record_prevents_publication(self):
        for validate in (True, False):
            with self.subTest(validate=validate):
                self.assert_empty_record_rejected(duplicate=False, validate=validate)

    def test_empty_same_key_record_prevents_publication(self):
        for validate in (True, False):
            with self.subTest(validate=validate):
                self.assert_empty_record_rejected(duplicate=True, validate=validate)


class EmptyPublicationRegressions(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parent / 'results/fixes'
        parent.mkdir(parents=True, exist_ok=True)
        self.work = Path(tempfile.mkdtemp(prefix='publication-', dir=parent)).resolve()
        self.assertTrue(self.work.is_relative_to(parent.resolve()))
        self.source = self.work / 'source.txt'
        self.out = self.work / 'out'
        self.good = [('kept', 'First definition.'), ('lost', 'Second definition.')]
        self.write_records(self.good)

    def write_records(self, records):
        self.source.write_text(''.join(
            f'{key}\n<div class="entry_content">{body}</div>\n</>\n'
            for key, body in records), encoding='utf-8')

    def invoke(self, **kwargs):
        self.log = io.StringIO()
        with contextlib.redirect_stdout(self.log), contextlib.redirect_stderr(self.log):
            return C.build(str(self.source), str(self.out), show_progress=False, **kwargs)

    def snapshot(self):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.out.iterdir() if p.is_file()}

    def reject(self, **kwargs):
        before = self.snapshot()
        thresholds = gc.get_threshold()
        with self.assertRaises(C.BuildValidationError) as caught:
            self.invoke(**kwargs)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(gc.get_threshold(), thresholds)
        self.assertFalse(list(self.out.glob('*.part')))
        self.assertNotIn('[OK] Dictionary package', self.log.getvalue())
        return caught.exception.errors

    def test_empty_record_after_flushed_bank_keeps_old_package(self):
        with mock.patch.object(C, 'TERM_BANK_BATCH', 1):
            self.invoke(revision='good')
            self.write_records([self.good[0], ('lost', '')])
            for validate in (True, False):
                with self.subTest(validate=validate):
                    errors = self.reject(revision='bad', validate=validate)
                    self.assertIn('1 source record(s) rendered empty content', errors[0])

    def test_empty_diagnostics_are_capped_but_all_records_count(self):
        self.invoke()
        self.write_records([self.good[0]] + [(f'empty-{i}', '') for i in range(10)])
        errors = self.reject()
        self.assertIn('10 source record(s) rendered empty content', errors[0])
        self.assertEqual(len(errors), 9)

    def test_mixed_empty_and_exception_failures_are_both_reported(self):
        self.invoke()
        deep = '<span>' * 450 + 'definition' + '</span>' * 450
        self.write_records([self.good[0], ('empty', ''), ('broken', deep)])
        errors = self.reject()
        self.assertTrue(any('1 source record(s) failed rendering' in e for e in errors))
        self.assertTrue(any('1 source record(s) rendered empty content' in e for e in errors))

    def test_mono_translation_only_entry_cannot_be_silently_dropped(self):
        self.invoke(mode='mono')
        self.write_records([self.good[0], ('lost', '<span class="cn_txt">\u4e2d\u6587</span>')])
        errors = self.reject(mode='mono')
        self.assertIn('rendered empty content', errors[0])

    def test_main_returns_two_for_empty_records_in_both_modes(self):
        for mode in ('bilingual', 'mono'):
            self.write_records(self.good)
            self.invoke(mode=mode)
            before = self.snapshot()
            self.write_records([self.good[0], ('lost', '')])
            args = ['-i', str(self.source), '-o', str(self.out), '-m', mode, '--no-progress']
            for extra in ([], ['--skip-validation']):
                with self.subTest(mode=mode, extra=extra):
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        code = C.main(args + extra)
                    self.assertEqual(code, 2)
                    self.assertEqual(self.snapshot(), before)

    def test_whitespace_comments_and_empty_wrappers_are_counted(self):
        self.invoke()
        empty = ['', ' \n\t ', '<!-- comment only -->', '<span> </span>']
        self.write_records([self.good[0]] + [(f'empty-{i}', html) for i, html in enumerate(empty)])
        errors = self.reject()
        self.assertIn('4 source record(s) rendered empty content', errors[0])

    def test_unselected_empty_record_does_not_poison_debug_build(self):
        self.write_records([self.good[0], ('lost', '')])
        package = self.invoke(test_words='kept')
        with zipfile.ZipFile(package) as archive:
            rows = json.loads(archive.read('term_bank_1.json'))
        self.assertEqual([row[0] for row in rows], ['kept'])


if __name__ == '__main__':
    unittest.main(verbosity=2)