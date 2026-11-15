"""Bounded contract tests; MUST NOT execute the reserved test/OOD worlds."""

import sys
from dataclasses import replace
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arena import ABORT, FWD, REOBSERVE, Arena, make_world, constant_forward
from td_agent import (TDAgent, TRAIN_START, FROZEN_TEST_START,
                      FROZEN_OOD_START, DEVELOPMENT_START, CALIBRATION_START,
                      score, tile_features, train)


class RewardLearningTests(unittest.TestCase):
    def setUp(self):
        self.observation = Arena(make_world('dev', DEVELOPMENT_START)).observe()

    def test_training_and_holdout_intervals_do_not_overlap(self):
        self.assertGreaterEqual(TRAIN_START, 122000)
        self.assertLess(TRAIN_START + 6000, 130001)
        self.assertGreaterEqual(FROZEN_TEST_START, 325000)
        self.assertLess(FROZEN_TEST_START + 300, 330000)
        self.assertGreaterEqual(FROZEN_OOD_START, 425000)
        self.assertLess(FROZEN_OOD_START + 200, 430000)
        self.assertEqual(CALIBRATION_START, 220000)

    def test_features_do_not_see_hidden_world_state(self):
        self.assertEqual(tile_features(self.observation),
                         tile_features(replace(self.observation)))
        self.assertNotIn('friction', self.observation.__dict__)
        self.assertNotIn('drift', self.observation.__dict__)

    def test_reward_td_update_changes_only_executed_action(self):
        a = TDAgent()
        fs = tile_features(self.observation)
        a.update(self.observation, FWD, 10., self.observation, True, .3, .1)
        self.assertGreater(a.q(fs, FWD), 0.)
        self.assertEqual(a.q(fs, REOBSERVE), 0.)

    def test_rl_action_selection_honors_deadman_and_quality(self):
        a = TDAgent()
        self.assertEqual(a.action(replace(self.observation, deadman=False)), ABORT)
        self.assertEqual(a.action(replace(self.observation, quality=.1)), REOBSERVE)
        self.assertEqual(a.action(replace(self.observation, age=9)), REOBSERVE)

    def test_train_never_queries_test_or_ood(self):
        from unittest.mock import patch
        import td_agent
        original = td_agent.make_world
        observed = []

        def checked(split, seed):
            self.assertEqual(split, 'dev')
            self.assertLess(seed, 130000)
            observed.append(seed)
            return original(split, seed)

        with patch.object(td_agent, 'make_world', side_effect=checked):
            result, receipt = train(20)
        self.assertEqual(len(observed), 20)
        self.assertEqual(receipt['teacher_actions_seen'], 0)
        self.assertTrue(any(result.weights))

    def test_train_is_reproducible_for_frozen_seed(self):
        a, x = train(20)
        b, y = train(20)
        self.assertEqual(a.weights, b.weights)
        self.assertEqual(x, y)

    def test_holdout_start_cannot_be_changed_silently(self):
        with self.assertRaises(ValueError):
            score(TDAgent(), 'test', 320000, 1)
        with self.assertRaises(ValueError):
            score(TDAgent(), 'ood', 420000, 1)

    def test_original_null_is_unchanged(self):
        self.assertEqual(constant_forward(self.observation), FWD)


if __name__ == '__main__':
    unittest.main()
