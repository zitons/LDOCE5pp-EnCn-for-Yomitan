import unittest
from benchmark_phrase_versions import judge, family


class BenchmarkScoringTests(unittest.TestCase):
    def test_full_input_wrong_target_does_not_pass(self):
        case={'targets':["take somebody's breath away"], 'span':'take my breath away'}
        wrong=[{'expression':'take away','matched':'take my breath away'}]
        self.assertFalse(judge(wrong,case)['hit'])
        self.assertTrue(judge(wrong,case)['wrong_full_only'])
        prefix=[{'expression':"take somebody's breath away",'matched':'take my breath'}]
        self.assertFalse(judge(prefix,case)['hit'])
        right=wrong+[{'expression':"take somebody's breath away",'matched':'take my breath away'}]
        score=judge(right,case)
        self.assertTrue(score['hit']);self.assertEqual(score['rank'],2)
        self.assertFalse(score['top1'])

    def test_context_uses_annotated_span_not_sentence_length(self):
        case={'targets':['hang by a thread'],'span':'Hanging by a thread'}
        score=judge([{'expression':'hang by a thread','matched':'Hanging by a thread'}],case)
        self.assertTrue(score['hit'])
        self.assertEqual(family({'finite_generic_pronoun','source_verb_past'}),'verb_inflection')


if __name__=='__main__':unittest.main()
