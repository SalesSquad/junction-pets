"""Fast non-physics contracts; no synthetic result is presented as a CRACI run."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("v10_prospective_under_test", HERE / "run.py")
prospective = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prospective)


class FakeWorld:
    def __init__(self, all_near=False):
        self.seed = None
        self.all_near = all_near

    def reset(self, seed, ood):
        assert ood is False
        self.seed = seed
        arr = np.zeros(18, dtype=np.float64)
        arr[7] = .04 if self.all_near or seed % 3 else .23
        return arr


def signature(env):
    return hashlib.sha256(str(env.seed).encode()).hexdigest()


def fake_rows():
    result = []
    for index in range(160):
        seed = prospective.FIRST_SEED + index
        near = index < 128
        for name in prospective.STRATEGIES:
            goal = (name == "frozen_v5" and index == 3 or
                    name == "v10_loss_informed" and index == 5)
            result.append({"seed": seed, "strategy": name,
                           "world_hash": signature(type("World", (), {"seed": seed})()),
                           "observed_corridor": near, "success": bool(goal),
                           "unsafe": False, "abstained": False,
                           "stage_funnel": {
                               "signed_lateral25_after_contact": False,
                               "forward_reopen_after_lateral25": False,
                               "full_contact_lateral_reopen_goal_dwell": False}})
    return result


class V10ProspectiveContracts(unittest.TestCase):
    def test_preregistered_seed_count_and_arm_order(self):
        prospective.validate_pre_registration()
        self.assertEqual(prospective.EXPECTED_TRIALS, 800)
        self.assertEqual(prospective.STRATEGIES, prospective.v10.NEXT_COMPARATORS)

    def test_frozen_registered_strategy_list_cannot_silently_change(self):
        with patch.object(prospective, "STRATEGIES", ("frozen_v5",)):
            with self.assertRaisesRegex(ValueError, "PRE_REGISTERED_TRAIN_COHORT_CHANGED"):
                prospective.validate_pre_registration()

    def test_fresh_cohort_selected_only_from_initial_public_observation(self):
        selected, scan = prospective.select_public_train_worlds(FakeWorld(), signature)
        self.assertEqual((len(selected), len(scan)), (160, 192))
        self.assertEqual(sum(r["observed_corridor"] for r in selected), 128)
        self.assertEqual(sum(not r["observed_corridor"] for r in selected), 32)
        self.assertEqual([r["seed"] for r in scan], list(range(515000, 515192)))
        self.assertTrue(all(set(r) == {"seed", "world_hash",
                                        "initial_observed_obstacle_y"} for r in scan))

    def test_incomplete_public_near_clear_cohort_is_a_hard_failure(self):
        with self.assertRaisesRegex(ValueError, "FRESH_COHORT_INCOMPLETE"):
            prospective.select_public_train_worlds(FakeWorld(all_near=True), signature)

    def test_five_arm_paired_schedule_has_all_world_strategy_pairs(self):
        cohort, _ = prospective.select_public_train_worlds(FakeWorld(), signature)
        schedule = prospective.paired_schedule(cohort)
        self.assertEqual(len(schedule), 800)
        self.assertEqual(len({(row["seed"], strategy) for row, strategy in schedule}), 800)
        self.assertEqual(set(s for _, s in schedule), set(prospective.STRATEGIES))

    def test_paired_readout_preserves_lost_frozen_success_and_new_win(self):
        outcome = prospective.paired_readout(fake_rows())
        self.assertEqual(outcome["lost_baseline_safe_near_goal_seeds"], [515003])
        self.assertEqual(outcome["novel_v10_safe_near_goal_seeds"], [515005])
        self.assertEqual(outcome["strategies"]["frozen_v5"]["safe_goals_near"], 1)
        self.assertEqual(outcome["strategies"]["v10_loss_informed"]["safe_goals_near"], 1)
        self.assertFalse(outcome["model_promotion_authorized"])

    def test_missing_arm_is_not_counted_as_a_successful_comparison(self):
        rows = fake_rows()
        rows.pop()
        with self.assertRaisesRegex(ValueError, "NOT_ALL_FIVE"):
            prospective.paired_readout(rows)

    def test_duplicate_seed_strategy_rejected(self):
        rows = fake_rows()
        rows[-1] = rows[0]
        with self.assertRaisesRegex(ValueError, "DUPLICATE_PAIRED_ARM"):
            prospective.paired_readout(rows)

    def test_unregistered_policy_cannot_execute(self):
        with self.assertRaisesRegex(ValueError, "UNREGISTERED_STRATEGY"):
            prospective.policy_factory("hidden_oracle", Path("checkpoint"), None)

    def test_prior_generic_run_module_collision_fails_closed(self):
        fake = types.ModuleType("run")
        fake.__file__ = "/tmp/not-the-frozen-v8-source/run.py"
        again = importlib.util.spec_from_file_location("isolated_v10_module_import", HERE / "run.py")
        module = importlib.util.module_from_spec(again)
        with patch.dict(sys.modules, {"run": fake}):
            with self.assertRaisesRegex(ValueError, "GENERIC_RUN_MODULE_COLLISION"):
                again.loader.exec_module(module)

    def test_v10_factory_receives_only_reviewed_candidate_checkpoint(self):
        expected = Path("reviewed-model.json")
        with patch.object(prospective.v10, "policy_factory",
                          return_value=lambda: "fresh_v10") as frozen:
            factory = prospective.policy_factory("v10_loss_informed", expected, None)
        frozen.assert_called_once_with(expected)
        self.assertEqual(factory(), "fresh_v10")

    def test_frozen_v8_factory_must_use_original_policy_name(self):
        with patch.object(prospective.v8, "policy_factory",
                          return_value=lambda: "old_v8") as old:
            factory = prospective.policy_factory("frozen_v8", Path("reviewed"), "weights")
        old.assert_called_once_with("v8_hierarchical", "weights", frozen_v7=None)
        self.assertEqual(factory(), "old_v8")

    def test_do_not_shrink_or_truncate_capture_to_fake_green(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "training.json"
            with patch.object(prospective, "MAX_SUMMARY_BYTES", 8):
                with self.assertRaisesRegex(ValueError, "QUALIFIER_CAP"):
                    prospective.write_original_summary(output, {"trials": [1]})
            self.assertFalse(output.exists())

    def test_original_summary_is_canonical_and_exact(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "training.json"
            payload = {"z": [3, 2, 1], "a": {"value": 1.234567890123}}
            size = prospective.write_original_summary(output, payload)
            self.assertEqual(output.read_bytes(), prospective.v8.v8.canonical_bytes(payload) + b"\n")
            self.assertEqual(size, output.stat().st_size)


if __name__ == "__main__":
    unittest.main()
