"""Fake fixtures only. No MuJoCo execution, training, dispatch, or model calls."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent

def module(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

policy = module('rokoko_v13_test_burst', 'policy.py')
protocol = module('rokoko_v13_test_protocol', 'protocol.py')
MODEL = HERE.parent / 'v12_learning/frozen-real-train-v10-v11-final/model.json'


def observation():
    o = [0.] * 18
    o[16] = 1.
    return o


def worlds():
    result = []
    for i, seed in enumerate(range(519024, 519536)):
        o = observation()
        o[0] = i / 10000
        o[7] = .1 if i < 178 else .2
        result.append({'seed': seed, 'world_hash': hashlib.sha256(str(seed).encode()).hexdigest(),
                       'observation': o, 'mask': [1, 0, 0, 1, 1, 0, 1]})
    return result


class V13Tests(unittest.TestCase):
    def setUp(self):
        self.plan = protocol.load_plan(HERE / 'v13-plan.json')
        self.worlds = worlds()
        self.cohort = protocol.derive_cohort(self.worlds, self.plan)
        self.trials = []
        for w in self.cohort:
            for arm in protocol.ARMS:
                self.trials.append(dict(seed=w['seed'], world_hash=w['world_hash'], strategy=arm,
                    success=False, unsafe=False, abstained=False,
                    contact_dwell_ticks=0, contacts=0, final_error_m=.1))

    def readout(self):
        return protocol.paired_physical_goal_readout(self.trials, self.cohort, self.worlds, self.plan)

    def win(self, index):
        self.trials[index].update(success=True, unsafe=False, abstained=False,
                                  contact_dwell_ticks=250, contacts=1, final_error_m=.019)

    def test_plan_and_original_source_pins(self):
        self.assertEqual(self.plan['trainSeedRangeInclusive'], [519024, 519535])
        for key in ('originalV12ModelSha256', 'originalV12PlanSha256', 'parentHead'):
            p = copy.deepcopy(self.plan)
            p[key] = 'changed'
            with self.assertRaises(ValueError):
                protocol.derive_cohort(self.worlds, p)
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / 'plan.json'
            bad.write_text(json.dumps(self.plan))
            with self.assertRaises(ValueError):
                protocol.load_plan(bad)
        with patch.object(policy.v12, 'model_score', side_effect=AssertionError('no scoring')):
            self.assertTrue(callable(policy.right_burst_factory(lambda: lambda o, m: 0, MODEL, 2)))
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / 'model.json'
            bad.write_text('{}')
            with self.assertRaises(ValueError):
                policy.right_burst_factory(lambda: lambda o, m: 0, bad, 2)

    def test_original_source_tamper_and_generic_import_collision(self):
        read = Path.read_bytes
        original = HERE.parent / 'v12_learning/policy.py'
        def tampered(path):
            return b'changed' if path == original else read(path)
        with patch.object(Path, 'read_bytes', tampered):
            with self.assertRaises(ValueError):
                protocol.load_plan(HERE / 'v13-plan.json')
            with self.assertRaises(ValueError):
                module('rokoko_v13_tampered_import', 'policy.py')
        sentinel = object()
        with patch.dict(sys.modules, {'policy': sentinel}):
            loaded = module('rokoko_v13_collision_check', 'policy.py')
            self.assertIs(sys.modules['policy'], sentinel)
            self.assertTrue(callable(loaded.v12.gate_input))

    def test_cohort_first40_first8(self):
        self.assertEqual(len(self.cohort), 48)
        self.assertEqual([w['seed'] for w in self.cohort],
                         list(range(519024, 519064)) + list(range(519202, 519210)))

    def burst(self, length):
        resets = []
        def factory():
            resets.append(1)
            return lambda o, m: 0
        p = policy.right_burst_factory(factory, MODEL, length)()
        return p, resets

    def test_burst2_and_burst4_exact_and_reset_no_repeat(self):
        for length in (2, 4):
            p, resets = self.burst(length)
            o, m = observation(), [1, 0, 0, 1, 1, 0, 1]
            with patch.object(policy.v12, 'model_score', side_effect=AssertionError('no action4 weights')):
                actions = [p(o, m) for _ in range(p.gate['min_streak'] + length + 8)]
            self.assertEqual(actions.count(4), length)
            start = actions.index(4)
            self.assertEqual(actions[start:start+length], [4]*length)
            self.assertEqual(len(resets), 2)

    def test_original_mask_checked_each_step_abort_reset(self):
        p, resets = self.burst(4)
        for _ in range(p.gate['min_streak']):
            action = p(observation(), [1, 0, 0, 1, 1, 0, 1])
        self.assertEqual(action, 4)
        self.assertEqual(p(observation(), [1, 0, 0, 1, 0, 0, 1]), 0)
        self.assertEqual(len(resets), 2)
        self.assertEqual([p(observation(), [1, 0, 0, 1, 1, 0, 1]) for _ in range(10)], [0]*10)

    def test_gate_loss_aborts_and_ineligible_never_bursts(self):
        p, resets = self.burst(2)
        m = [1, 0, 0, 1, 1, 0, 1]
        clear = observation()
        clear[7] = .5
        self.assertEqual([p(clear, m) for _ in range(10)], [0]*10)
        for _ in range(p.gate['min_streak']):
            p(observation(), m)
        self.assertEqual(p(clear, m), 0)
        self.assertEqual(len(resets), 2)

    def test_bad_burst_and_illegal_baseline_fail_closed(self):
        for length in (True, 0, 1, 3, 5, 2.):
            with self.assertRaises(ValueError):
                policy.right_burst_factory(lambda: lambda o, m: 0, MODEL, length)
        p = policy.right_burst_factory(lambda: lambda o, m: 1, MODEL, 2)()
        with self.assertRaises(ValueError):
            p(observation(), [1, 0, 0, 1, 1, 0, 1])

    def test_contact250_positive_preliminary_never_promotion(self):
        self.win(2)
        result = self.readout()
        self.assertFalse(result['hardStopNoFurtherPhysics'])
        self.assertEqual(result['scienceDecision'], 'REVIEW_PRELIMINARY_TRAIN_ONLY')
        for key in ('modelPromotionAuthorized', 'independentPhysicsReplayQualified',
                    'deviceSafeOperationQualified', 'devCalTestOodOpened'):
            self.assertIs(result[key], False)

    def test_249_ticks_zero_contacts_error_boundary_abstain_and_forgery(self):
        for update in ({'contact_dwell_ticks':249}, {'contacts':0}, {'final_error_m':.02},
                       {'abstained':True}, {'unsafe':True}):
            self.win(2)
            self.trials[2].update(update)
            with self.assertRaises(ValueError):
                self.readout()
            self.trials[2]['success'] = False
            self.assertTrue(self.readout()['hardStopNoFurtherPhysics'])

    def test_duplicate_shuffled_incomplete_trials_rejected(self):
        good = copy.deepcopy(self.trials)
        for malformed in (good[:-1], good + [good[0]], [good[0]] + good[:-1],
                          [good[1],good[0]] + good[2:]):
            self.trials = malformed
            with self.assertRaises(ValueError):
                self.readout()

    def test_scan_duplicate_shuffled_wrong_range_or_selection_rejected(self):
        good = copy.deepcopy(self.worlds)
        for malformed in (good[:-1], [good[1],good[0]] + good[2:], [good[0]] + good[:-1]):
            with self.assertRaises(ValueError):
                protocol.derive_cohort(malformed, self.plan)
        self.worlds[0]['seed'] = 520000
        with self.assertRaises(ValueError):
            self.readout()
        self.worlds = copy.deepcopy(good)
        self.worlds[1]['world_hash'] = self.worlds[0]['world_hash']
        with self.assertRaises(ValueError):
            self.readout()
        self.worlds = copy.deepcopy(good)
        self.worlds[1]['observation'] = self.worlds[0]['observation'][:]
        with self.assertRaises(ValueError):
            self.readout()
        self.worlds = good
        self.cohort = self.cohort[::-1]
        with self.assertRaises(ValueError):
            self.readout()

    def test_lost_v5_any_arm_even_with_novel_burst_stops(self):
        self.win(6)  # a novel burst2 goal on another world
        for lost_arm in (1, 2, 3):
            for j in range(4):
                self.win(j)
            self.trials[lost_arm].update(success=False, contact_dwell_ticks=0)
            result = self.readout()
            self.assertEqual(result['scienceDecision'], 'STOP')
            self.assertEqual(result['lostV5GoalsByStrategy'][protocol.ARMS[lost_arm]], [519024])

    def test_unsafe_any_arm_and_zero_new_stop(self):
        self.assertEqual(self.readout()['scienceDecision'], 'STOP')
        self.win(2)
        for arm in range(4):
            self.trials[4+arm]['unsafe'] = True
            self.assertEqual(self.readout()['scienceDecision'], 'STOP')
            self.trials[4+arm]['unsafe'] = False

    def test_nonfinite_bool_ticks_and_extra_fields_rejected(self):
        for field, value in (('final_error_m', float('nan')), ('contact_dwell_ticks', True),
                             ('contacts', -1), ('success', 1), ('modelPromotionAuthorized', True)):
            original = copy.deepcopy(self.trials[0])
            self.trials[0][field] = value
            with self.assertRaises(ValueError):
                self.readout()
            self.trials[0] = original


if __name__ == '__main__':
    unittest.main()
