import unittest
from phrase_pronoun_aliases import pronoun_variants


class PronounTests(unittest.TestCase):
    def test_objects_and_possessives(self):
        self.assertIn('give him a hand', pronoun_variants('give somebody a hand'))
        self.assertIn('take her breath away', pronoun_variants("take somebody's breath away"))
        self.assertIn('put it down', pronoun_variants('put something down'))
        self.assertIn('keep it to myself', pronoun_variants('keep something to yourself'))

    def test_subjects_lexical_possessives_and_unresolved_groups(self):
        self.assertFalse(pronoun_variants('somebody is in trouble'))
        self.assertNotIn('give me a hand', pronoun_variants('somebody gives something a hand'))
        self.assertIn('put her foot down', pronoun_variants('put your foot down'))
        self.assertNotIn('kick out them', pronoun_variants('kick out somebody', possessive_only=True))
        self.assertIn('blow out his brains', pronoun_variants("blow out somebody's brains", possessive_only=True))
        self.assertFalse(pronoun_variants('tuck sb up'))
        self.assertFalse(pronoun_variants('give somebody/something a hand'))
        self.assertNotIn('give Mary a hand', pronoun_variants('give somebody a hand'))


if __name__ == '__main__':
    unittest.main()
