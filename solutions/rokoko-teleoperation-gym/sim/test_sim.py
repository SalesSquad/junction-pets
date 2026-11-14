"""Small decisive contract/negative checks, runnable with standard-library Python."""
import copy
import json
from pathlib import Path
import unittest
from experiment import Hold, score, decision
from decisions import observed, validate_request, validate_answer, guarded_choice, normalize_response


class SafetyTests(unittest.TestCase):
    def test_latched_hold_requires_two_healthy_and_ack(self):
        h = Hold()
        self.assertTrue(h.update(False, 0, 1, True, True))
        self.assertTrue(h.update(True, 0, 1, True, True))
        self.assertTrue(h.update(True, 0, 1, True, False))
        self.assertFalse(h.update(True, 0, 1, True, True))
        self.assertTrue(h.update(True, 0.121, 1, True, True))
        self.assertTrue(h.update(True, 0, 1, False, True))

    def test_false_success_and_contact_required(self):
        self.assertFalse(score(0, False, 0, 0, False))
        self.assertFalse(score(0, True, 1, 0, False))
        self.assertFalse(score(0, False, 1, 1, False))
        self.assertFalse(score(0, False, 1, 0, True))
        self.assertFalse(score(0.1, False, 1, 0, False))
        self.assertTrue(score(0.01, False, 1, 0, False))

    def test_offline_fixtures_and_hostile_answers(self):
        f = json.loads((Path(__file__).parent/'decision-fixtures.json').read_text())
        o = dict(object=[0,0],age=0,quality=1,deadman=True,inside=True,obstacle_distance=0.1)
        for item in f['fixtures']:
            validate_request(item['provider'],item['request']['body'])
            a = validate_answer(item['normalized_offline_response'])
            self.assertEqual(normalize_response(item['provider'],item['wire_response_excerpt']),a)
            self.assertEqual(guarded_choice(dict(o,deadman=False),2,a),'HALT')
            self.assertEqual(guarded_choice(dict(o,inside=False),2,a),'HALT')
            self.assertEqual(guarded_choice(dict(o,age=1),2,a),'REOBSERVE')
            self.assertEqual(guarded_choice(o,2,dict(a,confidence=0.2)),'REOBSERVE')
            bad = copy.deepcopy(a)
            bad['probabilities']['CONTINUE'] = float('nan')
            self.assertEqual(guarded_choice(o,2,bad),'REOBSERVE')
            with self.assertRaises(ValueError):
                validate_answer(dict(a,choice='ACTUATE'))
        with self.assertRaises(ValueError):
            observed(dict(o,ground_truth_reward=1))
        self.assertEqual(decision(dict(o,obstacle_distance=0),0),'HALT')
        self.assertEqual(decision(dict(o,obstacle_distance=0),2),'REQUEST_HUMAN')


if __name__ == '__main__':
    unittest.main()
