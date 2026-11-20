"""Guard the boundary between finite lookup heads and unsupported deletion."""
import unittest
from phrase_lookup_heads import entrances, usable, collect_heads, phrasal_particle_choices


class LookupHeadBoundaryTest(unittest.TestCase):
    def test_explicit_phrasal_particle_choices_do_not_guess_other_slashes(self):
        self.assertEqual(phrasal_particle_choices('swing around/round'), {'swing around','swing round'})
        self.assertEqual(phrasal_particle_choices('fire/police station'), set())
        self.assertEqual(phrasal_particle_choices('go to show/prove'), set())
        self.assertEqual(phrasal_particle_choices('turn somebody out/in'), set())

    def accepted(self, text):
        return {k for k in entrances(text) if usable(k)}

    def test_lexical_material_and_internal_arguments_are_preserved(self):
        self.assertEqual(self.accepted('give somebody a hand'), set())
        self.assertEqual(self.accepted('endear somebody to somebody'), set())
        self.assertEqual(self.accepted('put something at something'), set())
        self.assertEqual(self.accepted("cramp somebody's style"), set())
        self.assertEqual(self.accepted('how can somebody do something?'), set())

    def test_only_terminal_slot_and_initial_copula_can_be_dropped(self):
        self.assertEqual(self.accepted('look after somebody/something'), {'look after'})
        self.assertEqual(self.accepted('be out of your depth'), {'out of your depth'})
        self.assertEqual(self.accepted('be attached to something'),
                         {'be attached to', 'attached to'})

    def test_source_marker_and_content_collisions_control_internal_omission(self):
        heads = collect_heads(
            [('kick somebody out', {'kick somebody out'}),
             ('put something at something', {'put something at something'})],
            [('kick somebody \u2194 out', 'kick somebody out'),
             ('put something at something', 'put something at something')], set())
        self.assertEqual(set(heads), {'kick out', 'put at'})
        self.assertEqual(heads['kick out']['kick somebody out'], {'explicit_separable_phrasal_head'})
        self.assertFalse(collect_heads([], [('kick somebody \u2194 out', 'kick somebody out')], {'KICK OUT'}))

    def test_source_heads_merge_targets_and_preserve_fixed_words(self):
        heads = collect_heads([('put somebody away', {'put somebody away'})], [
            ('put somebody/something away', 'put somebody/something away'),
            ('put something away', 'put something away'),
            ('drag something out of somebody', 'drag something out of somebody'),
            ("cramp somebody's style", "cramp somebody's style"),
            ('give somebody a hand', 'give somebody a hand')], set())
        self.assertEqual(set(heads['put away']),
                         {'put somebody/something away', 'put something away'})
        self.assertIn('drag out of', heads)
        self.assertIn('give a hand', heads)  # Only when explicitly a phrvbhwd.
        self.assertNotIn('cramp style', heads)
        self.assertNotIn('endear to', heads)


if __name__ == '__main__':
    unittest.main()
