"""Guard the boundary between finite lookup heads and unsupported deletion."""
import unittest
from audit_phrase_responsibility import entrances, usable


class LookupHeadBoundaryTest(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
