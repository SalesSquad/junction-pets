"""Portable contracts; actual physics qualification must run in CRACI."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import math
import tempfile
import time
import unittest
from unittest.mock import patch

import policy

spec = importlib.util.spec_from_file_location("mujoco_v5_learning_runner_contract", Path(__file__).with_name("run.py"))
assert spec is not None and spec.loader is not None
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


class ModelContracts(unittest.TestCase):
    def test_frozen_policy_has_only_four_bounded_weights(self):
        self.assertEqual(len(policy.DEFAULT), 4)
        self.assertEqual(policy.validate_weights(policy.DEFAULT), policy.DEFAULT)

    def test_no_privileged_inference_weight_accepted(self):
        with self.assertRaisesRegex(ValueError, "MODEL_PARAMETER_SCHEMA_MISMATCH"):
            policy.validate_weights({**policy.DEFAULT, "hidden_obstacle_phase": .2})

    def test_nonfinite_rejected(self):
        with self.assertRaisesRegex(ValueError, "NONFINITE"):
            policy.validate_weights({**policy.DEFAULT, "LANE_DISTANCE": math.nan})

    def test_bool_rejected(self):
        with self.assertRaisesRegex(ValueError, "NONFINITE"):
            policy.validate_weights({**policy.DEFAULT, "LANE_DISTANCE": True})

    def test_out_of_bounds_rejected(self):
        with self.assertRaisesRegex(ValueError, "OUT_OF_BOUNDS"):
            policy.validate_weights({**policy.DEFAULT, "LANE_DISTANCE": .9})

    def test_instance_weights_do_not_mutate_global_parent(self):
        weights = {**policy.DEFAULT, "LANE_DISTANCE": .043}
        p = policy.make_factory(weights)()
        self.assertAlmostEqual(p.LANE_DISTANCE, .043)
        self.assertEqual(policy.DEFAULT["LANE_DISTANCE"], .031)

    def test_source_bands_are_disjoint(self):
        self.assertGreater(run.TRAIN_FIRST_SEED, run.v4.v3.v2.v1.SEED_BANDS["ood"][1])
        self.assertEqual(run.DEV_FIRST_SEED, 129170)
        self.assertLess(run.DEV_LAST_SEED, run.v4.v3.v2.v1.SEED_BANDS["dev"][1])

    def test_default_cli_contract(self):
        args = run.parse_args([
            "--mode", "train-dev", "--require-git",
            "--expected-head", "a" * 40, "--output-dir", "/tmp/fake-out"])
        self.assertEqual((args.train_episodes, args.dev_episodes), (48, 80))
        run.validate_args(args)

    def test_heldout_override_not_exposed(self):
        with self.assertRaises(SystemExit):
            run.parse_args(["--mode", "train-dev", "--permit-holdout"])

    def test_invalid_budgets_fail(self):
        args = run.parse_args([
            "--mode", "train-dev", "--expected-head", "a" * 40,
            "--output-dir", "/tmp/fake-out", "--train-episodes", "200"])
        with self.assertRaisesRegex(ValueError, "TRAIN_COUNT"):
            run.validate_args(args)

    def test_source_identity_requires_git_even_if_SHA_shape_correct(self):
        with self.assertRaises(PermissionError):
            run.source_identity(False, "a" * 40)

    def test_canonical_dataset_hash_is_stable(self):
        self.assertEqual(run.digest({"x": 1, "y": 2}), run.digest({"y": 2, "x": 1}))
        self.assertNotEqual(run.digest([1, 2]), run.digest([2, 1]))

    def test_output_accepts_existing_empty_dir_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            self.assertEqual(run.output_root(out), out)
            run.write_new(out / "training.json", {"x": 1})
            with self.assertRaises(FileExistsError):
                run.write_new(out / "training.json", {"x": 2})
            with self.assertRaises(FileExistsError):
                run.output_root(out)

    def test_train_score_penalizes_unsafe_more_than_success(self):
        win = run.score_training([dict(success=True, unsafe=False,
                                       abstained=False,total_reward=5.)])
        unsafe = run.score_training([dict(success=True, unsafe=True,
                                          abstained=False,total_reward=5.)])
        self.assertGreater(win["objective"], unsafe["objective"])

    def test_optimizer_uses_six_reward_driven_training_candidates(self):
        def fake_episode(_env, seed, weights):
            return dict(seed=seed, transitions=[dict(reward=1)], success=False,
                        unsafe=False, abstained=False,
                        total_reward=weights["LANE_DISTANCE"] * 10,
                        world_hash="training-only")
        with patch.object(run, "training_episode", side_effect=fake_episode) as call:
            learned = run.learn(object(), 2, time.monotonic() + 5)
        self.assertEqual(len(learned["experiments"]), 6)
        self.assertEqual(len(learned["rollouts"]), 12)
        self.assertEqual(call.call_count, 12)
        self.assertEqual(learned["seeds"], [5290000, 5290001])
        self.assertEqual(learned["winner"]["objective"],
                         max(x["objective"] for x in learned["experiments"]))

    def test_training_taxonomy_proposes_only_train_seeds(self):
        rows = [dict(success=False, unsafe=True, abstained=False,
                     transitions=[dict(reward=-1)]),
                dict(success=False, unsafe=False, abstained=True,
                     transitions=[dict(reward=-1)])]
        result = run.taxonomy_and_curriculum(rows)
        self.assertEqual(result["failure_taxonomy"]["unsafe_collision_or_bounds"], 1)
        self.assertEqual(result["failure_taxonomy"]["explicit_safe_abstain"], 1)
        self.assertEqual(result["curriculum_next"]["next_train_first_seed"], 5291000)
        self.assertFalse(result["curriculum_next"]["automatic_rerun"])

    def test_scientific_gate_preserves_original_and_v4_safety(self):
        summary = dict(delta_success_percentage_points=10.,
                       paired_bootstrap95_pp=[1., 20.],
                       candidate_success=60, constant_success=52,
                       candidate_unsafe=1, constant_unsafe=1)
        rows = [dict(safe_v4={"unsafe": False}) for _ in range(80)]
        gate = run.scientific_gate(rows, {"learned_v5": summary})
        self.assertFalse(gate["scientifically_qualifies"])
        self.assertFalse(gate["no_unsafe_regression_vs_v4"])

    def test_scientific_gate_requires_positive_paired_lower_bound(self):
        summary = dict(delta_success_percentage_points=10.,
                       paired_bootstrap95_pp=[0., 20.],
                       candidate_success=60, constant_success=52,
                       candidate_unsafe=0, constant_unsafe=0)
        rows = [dict(safe_v4={"unsafe": False}) for _ in range(80)]
        self.assertFalse(run.scientific_gate(rows, {"learned_v5":summary})[
            "scientifically_qualifies"])


if __name__ == "__main__":
    unittest.main()
