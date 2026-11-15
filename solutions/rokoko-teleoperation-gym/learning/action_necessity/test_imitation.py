"""Learning-pipeline contract checks on development-only worlds."""

import unittest

from arena import Arena, make_world
from imitation import (FEATURE_COUNT, TRAIN_SEED_START, SoftmaxPolicy,
                       collect_teacher_data, evaluate_fit, features, fit)


class BehaviorCloneTests(unittest.TestCase):
    def test_fit_changes_parameters(self):
        weights, train = fit(episodes=3, epochs=2)
        self.assertEqual(len(weights), 8)
        self.assertTrue(any(abs(v) > 1e-8 for row in weights for v in row))
        self.assertGreater(train["examples"], 0)

    def test_features_observable_only(self):
        obs = Arena(make_world("dev", TRAIN_SEED_START)).observe()
        self.assertEqual(len(features(obs, obs.moving_y)), FEATURE_COUNT)

    def test_train_disjoint_from_scored_dev(self):
        data, _ = collect_teacher_data(3)
        self.assertTrue(data)
        self.assertGreaterEqual(TRAIN_SEED_START, 120200)

    def test_fitted_policy_deterministic_on_same_observation(self):
        weights, _ = fit(episodes=3, epochs=1)
        obs = Arena(make_world("dev", 120008)).observe()
        self.assertEqual(SoftmaxPolicy(weights)(obs), SoftmaxPolicy(weights)(obs))

    def test_fitted_vs_null_paired_scores(self):
        weights, _ = fit(episodes=2, epochs=1)
        result = evaluate_fit(weights, "dev", 2)
        self.assertEqual(result["episodes"], 2)
        self.assertEqual(result["learned"]["episodes"], 2)
        self.assertIn("paired_bootstrap_95_pp", result["fitted_minus_constant"])


if __name__ == "__main__":
    unittest.main()
