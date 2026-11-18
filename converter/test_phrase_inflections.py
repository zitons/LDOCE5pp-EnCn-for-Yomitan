import unittest

from phrase_inflections import inflection_variants


class PhraseInflectionTests(unittest.TestCase):
    def test_source_first_and_no_implicit_pos(self):
        self.assertEqual(inflection_variants("work permit"), {})
        self.assertEqual(inflection_variants("work permit", noun={"countable": True}),
                         {"work permits": {"regular_noun_plural"}})
        forms = inflection_variants("give somebody a hand", verb={
            "past": {"gave"}, "participle": {"given"}})
        self.assertIn("gave somebody a hand", forms)
        self.assertIn("given somebody a hand", forms)
        self.assertIn("giving somebody a hand", forms)
        self.assertNotIn("gived somebody a hand", forms)
        self.assertNotIn("given Mary a hand", forms)

    def test_hang_and_irregular_safeguard(self):
        forms = inflection_variants("hang by a thread", verb={"past": {"hung"}})
        self.assertIn("hanging by a thread", forms)
        self.assertIn("hung by a thread", forms)
        self.assertNotIn("hanged by a thread", forms)
        self.assertNotIn("bringed up", inflection_variants("bring up", verb={}))

    def test_cvc_doubles_only_one_syllable_stems(self):
        forms = inflection_variants("stop short", verb={})
        self.assertIn("stopped short", forms)
        self.assertIn("stopping short", forms)
        self.assertNotIn("stoped short", forms)
        # Stress-final doubling is declared by the source and replaces this.
        forms = inflection_variants("refer it", verb={"past": {"referred"}, "ing": {"referring"}})
        self.assertIn("referred it", forms)
        self.assertNotIn("refered it", forms)
        for word in ("order", "father", "visit", "open"):
            forms = inflection_variants(word + " it", verb={"syllables": 1})
            self.assertIn(word + "ed it", forms)
            self.assertIn(word + "ing it", forms)
        forms = inflection_variants("reset it", verb={})
        self.assertIn("resetting it", forms)
        self.assertNotIn("reseted it", forms)
        self.assertNotIn("resetted it", forms)
        self.assertIn("tie-ins", inflection_variants("tie-in", noun={"countable": True}))
        self.assertIn("sell-by dates", inflection_variants("sell-by date", noun={"countable": True}))
        self.assertEqual(inflection_variants("passer-by", noun={"countable": True}), {})
        self.assertEqual(inflection_variants("mother-in-law", noun={"countable": True}), {})
        self.assertIn("playing up", inflection_variants("play up", verb={}))
        self.assertIn("mixing up", inflection_variants("mix up", verb={}))

    def test_y_e_and_grammar_exceptions(self):
        self.assertIn("tried out", inflection_variants("try out", verb={}))
        self.assertIn("tries out", inflection_variants("try out", verb={}))
        self.assertIn("making up", inflection_variants("make up", verb={}))
        self.assertIn("dyeing wool", inflection_variants("dye wool", verb={}))
        self.assertIn("dying out", inflection_variants("die out", verb={}))
        self.assertIn("singeing hair", inflection_variants("singe hair", verb={}))
        self.assertIn("agreed on", inflection_variants("agree on", verb={}))
        self.assertIn("doing away with", inflection_variants("do away with", verb={}))
        self.assertIn("went on", inflection_variants("go on", verb={}))
        forms = inflection_variants("be up to", verb={})
        self.assertTrue({"was up to", "were up to", "been up to", "being up to",
                         "is up to"}.issubset(forms))

    def test_plural_source_and_compound_safeguards(self):
        self.assertIn("fire engines", inflection_variants("fire engine", noun={"countable": True}))
        self.assertIn("children", inflection_variants("child", noun={"plurals": {"children"}}))
        self.assertIn("courts martial", inflection_variants("court martial", noun={
            "plurals": {"courts martial"}, "countable": True}))
        self.assertEqual(inflection_variants("court martial", noun={"countable": True}), {})
        self.assertEqual(inflection_variants("mother in law", noun={"countable": True}), {})
        self.assertEqual(inflection_variants("fire engine", noun={"countable": False}), {})
        self.assertIn("fire engines", inflection_variants("fire engine", noun={
            "last_plurals": {"engines"}}))
        self.assertIn("toy factories", inflection_variants("toy factory", noun={"countable": True}))
        self.assertEqual(inflection_variants("sharp knife", noun={"countable": True}), {})
        self.assertIn("sharp knives", inflection_variants("sharp knife", noun={
            "last_plurals": {"knives"}, "countable": True}))

    def test_case_and_evidence_merge(self):
        forms = inflection_variants("GIVE a hand", verb={"past": {"gave"}})
        self.assertIn("GAVE a hand", forms)
        self.assertIn("Giving a hand", inflection_variants("Give a hand", verb={}))
        self.assertIn("Fire Engines", inflection_variants("Fire Engine", noun={"countable": True}))
        self.assertIn("COURTS MARTIAL", inflection_variants("COURT MARTIAL", noun={
            "plurals": {"courts martial"}}))
        forms = inflection_variants("work up", verb={"past": {"worked"}, "participle": {"worked"}})
        self.assertEqual(forms["worked up"], {"source_verb_past", "source_verb_participle"})

    def test_caller_selected_noun_head(self):
        self.assertEqual(inflection_variants("point of order", noun={"countable": True}), {})
        forms = inflection_variants("point of order", noun={"countable": True, "head_index": 0})
        self.assertEqual(forms, {"points of order": {"regular_noun_head_plural"}})
        self.assertNotIn("point of orders", forms)
        forms = inflection_variants("Man of war", noun={
            "head_index": 0, "head_plurals": {"men"}})
        self.assertEqual(forms, {"Men of war": {"source_noun_head_plural"}})
        self.assertEqual(inflection_variants("point of order", noun={
            "countable": True, "head_index": 8}), {})
        self.assertEqual(inflection_variants("point of order", noun={
            "countable": True, "head_index": -1}), {})
        self.assertEqual(inflection_variants("court martial", noun={
            "head_index": 1, "plurals": {"courts martial"}, "countable": True}),
            {"courts martial": {"source_noun_plural"}})


if __name__ == "__main__":
    unittest.main()
