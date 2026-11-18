import sqlite3
import unittest
from collections import defaultdict

from apply_phrase_inflections import apply_inflections


class ApplyInflectionsTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
          CREATE TABLE lexical_pos(word,pos);
          CREATE TABLE source_head_grammar(word,pos,gram,syllables,record_id);
          CREATE TABLE source_word_forms(word,form,kind,record_id,xpath);
          CREATE TABLE occurrences(phrase,kind);
        """)
        self.graph = defaultdict(lambda: defaultdict(set))

    def tearDown(self):
        self.db.close()

    def lexical(self, word, pos):
        self.db.execute("INSERT INTO lexical_pos VALUES(?,?)", (word, pos))

    def head(self, word, pos, gram="", syllables=None):
        self.db.execute("INSERT INTO source_head_grammar VALUES(?,?,?,?,1)",
                        (word, pos, gram, syllables))

    def form(self, word, form, kind):
        self.db.execute("INSERT INTO source_word_forms VALUES(?,?,?,1,'/')", (word, form, kind))

    def test_noun_only_blocks_ambiguous_verb_and_uncountable(self):
        self.lexical("work", "verb")
        self.lexical("permit", "noun")
        self.head("work permit", "noun", "[countable]")
        self.head("work experience", "noun", "[uncountable]")
        self.lexical("experience", "noun")
        stats = apply_inflections(self.db, {"work permit", "work experience"}, self.graph, {"work": "verb"})
        self.assertIn("work permits", self.graph)
        self.assertNotIn("worked permit", self.graph)
        self.assertNotIn("work experiences", self.graph)
        self.assertGreater(stats["noun_only_verb_blocked"], 0)

    def test_source_verb_forms_and_snapshot_no_recursion(self):
        self.lexical("give", "verb")
        self.lexical("gave", "verb")  # Even with this entry, generated aliases aren't inputs.
        self.head("give", "verb", syllables=1)
        self.form("give", "gave", "past")
        self.form("give", "given", "participle")
        self.form("give", "past tense mistake", "past")
        self.graph["give a hand"]["give somebody a hand"].add("existing")
        self.graph["give him a hand"]["give somebody a hand"].add("finite_pronoun")
        apply_inflections(self.db, {"give somebody a hand"}, self.graph, {"give": "verb", "gave": "verb"})
        self.assertEqual(self.graph["gave a hand"]["give somebody a hand"], {"source_verb_past"})
        self.assertIn("giving somebody a hand", self.graph)
        self.assertEqual(self.graph["gave him a hand"]["give somebody a hand"], {"source_verb_past"})
        self.assertNotIn("gaved a hand", self.graph)
        self.assertNotIn("past tense mistake a hand", self.graph)

    def test_declared_phrasal_overrides_first_preferred_noun(self):
        self.lexical("book", "noun")
        self.lexical("book", "verb")
        self.db.execute("INSERT INTO occurrences VALUES('book in','phrvbhwd')")
        apply_inflections(self.db, {"book in", "book cover"}, self.graph, {"book": "noun"})
        self.assertIn("booking in", self.graph)
        self.assertNotIn("booking cover", self.graph)

    def test_compounds_explicit_priority_body_wins_and_targets(self):
        for word in ("point", "order", "court", "martial"):
            self.lexical(word, "noun")
        self.head("point of order", "noun", "[countable]")
        self.head("court martial", "noun", "[countable]")
        self.form("court martial", "courts martial", "plural")
        self.graph["point of orders"]["missing target"].add("bad_existing_target")
        keys = {"point of order", "court martial", "points of order"}
        stats = apply_inflections(self.db, keys, self.graph, {})
        self.assertNotIn("points of order", self.graph)
        self.assertEqual(self.graph["courts martial"]["court martial"], {"source_noun_plural"})
        self.assertNotIn("court martials", self.graph)
        self.assertNotIn("point of orderses", self.graph)
        self.assertGreater(stats["canonical_body_wins"], 0)

    def test_postpositive_not_mistaken_for_final_noun(self):
        self.lexical("general", "noun")
        self.head("attorney general", "noun", "[countable]")
        self.form("general", "generals", "plural")
        apply_inflections(self.db, {"attorney general"}, self.graph, {})
        self.assertNotIn("attorney generals", self.graph)

    def test_sense_context_decides_word_class(self):
        self.db.executescript("""
          DROP TABLE occurrences;
          CREATE TABLE occurrences(phrase,record_id,parent,kind,xpath);
          CREATE TABLE source_entry_pos(record_id,div,pos);
          INSERT INTO source_entry_pos VALUES(1,'/html/body/div[1]','verb'),(1,'/html/body/div[2]','noun');
          INSERT INTO occurrences VALUES('hang by a thread',1,'hang','lexunit','/html/body/div[1]/span/span[9]');
          INSERT INTO occurrences VALUES('leap of faith',1,'leap','lexunit','/html/body/div[2]/span/span[7]');
        """)
        for word in ("hang", "leap"):
            self.lexical(word, "verb"); self.lexical(word, "noun")
        self.head("leap", "noun", "[countable]")
        self.form("hang", "hung", "past")
        apply_inflections(self.db, {"hang by a thread", "leap of faith"}, self.graph,
                          {"hang": "verb", "leap": "verb"})
        self.assertIn("hung by a thread", self.graph)
        self.assertIn("leaps of faith", self.graph)
        self.assertNotIn("leaping of faith", self.graph)
        self.assertNotIn("leaped of faith", self.graph)

    def test_notation_headless_and_dehyphenated_forms(self):
        self.lexical("given", "verb"); self.lexical("give", "verb"); self.lexical("tie", "verb")
        self.lexical("tie-in", "noun"); self.lexical("pull", "verb")
        self.form("give", "given", "participle")
        self.head("tie-in", "noun", "[countable]")
        self.db.execute("INSERT INTO occurrences VALUES('pull somebody in','phrvbhwd')")
        self.graph["given to doing"]["be given to doing"].add("lookup_omit_initial_be")
        self.graph["tie in"]["tie-in"].add("source_orthographic_variant")
        self.graph["pull sb in"]["pull somebody in"].add("placeholder_abbreviation")
        self.graph["pull somebody ↔ in"]["pull somebody in"].add("source_separability_notation")
        apply_inflections(self.db, {"be given to doing", "tie-in", "pull somebody in"}, self.graph,
                          {"given": "verb", "tie": "verb", "pull": "verb"})
        self.assertNotIn("givens to doing", self.graph)
        self.assertNotIn("ties in", self.graph)
        self.assertNotIn("tying in", self.graph)
        self.assertEqual(self.graph["tie-ins"]["tie-in"], {"regular_noun_plural"})
        self.assertEqual(self.graph["tie ins"]["tie-in"], {"regular_noun_plural"})
        self.assertIn("pulled somebody in", self.graph)
        self.assertNotIn("pulled sb in", self.graph)
        self.assertNotIn("pulled somebody ↔ in", self.graph)

    def test_complete_adjective_head_blocks_verb_and_old_metadata(self):
        self.lexical("light", "verb")
        self.head("light blue", "adjective")
        stats = apply_inflections(self.db, {"light blue"}, self.graph, {"light": "verb"})
        self.assertFalse(self.graph)
        self.assertEqual(stats["nonverb_head_blocked"], 1)
        self.db.execute("DROP TABLE source_word_forms")
        self.assertEqual(apply_inflections(self.db, {"light blue"}, self.graph, {}),
                         {"metadata_absent": 1})


if __name__ == "__main__":
    unittest.main()
