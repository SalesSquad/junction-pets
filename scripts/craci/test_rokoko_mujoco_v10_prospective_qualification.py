"""Non-physics guard tests for immutable V10 CRACI prospective wrapper."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "v10_independent_qualifier_contract", HERE / "rokoko-mujoco-v10-prospective-qualification.py")
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)


def trial(seed, name, near):
    return {"seed": seed, "strategy": name, "observed_corridor": near,
            "success": name == "frozen_v5" and seed == 515000,
            "unsafe": False, "abstained": False,
            "stage_funnel": {
                "signed_lateral25_after_contact": False,
                "forward_reopen_after_lateral25": False,
                "full_contact_lateral_reopen_goal_dwell": False}}


def fake_training():
    rows = [trial(515000 + i, name, i < 128)
            for i in range(160) for name in qualifier.EXPECTED_STRATEGIES]
    return {"schema": "junction.rokoko.mujoco-v10.prospective-train.v1.training",
            "executed_head": "a" * 40, "training_only": True,
            "train_first_seed": 515000, "strategies": list(qualifier.EXPECTED_STRATEGIES),
            "actual_trials": 800, "trials": rows, "selected_near_count": 128,
            "selected_clear_count": 32, "dev_cal_test_ood_opened": False,
            "model_promotion_authorized": False,
            "candidate_v10_weights_file_sha256": qualifier.V10_WEIGHTS_FILE_SHA,
            "actual_transition_count": 1000, "dataset_sha256": "b" * 64}


def fake_readout(training):
    summary = {}
    for name in qualifier.EXPECTED_STRATEGIES:
        rows = [r for r in training["trials"] if r["strategy"] == name]
        summary[name] = {"paired_trials": len(rows), "unsafe": 0,
                         "abstained": 0,
                         "safe_goals_all": sum(r["success"] for r in rows),
                         "safe_goals_near": sum(r["success"] and r["observed_corridor"]
                                                for r in rows),
                         "safe_goals_clear": sum(r["success"] and
                                                 not r["observed_corridor"] for r in rows),
                         "safe_near_lateral25_after_contact": 0,
                         "safe_near_forward_reopen_after_lateral": 0,
                         "safe_near_dwell_after_reopen": 0}
    return {"schema": "junction.rokoko.mujoco-v10.prospective-train.v1.readout",
            "executed_head": training["executed_head"],
            "dataset_sha256": training["dataset_sha256"],
            "candidate_v10_weights_file_sha256": qualifier.V10_WEIGHTS_FILE_SHA,
            "model_promotion_authorized": False, "dev_cal_test_ood_opened": False,
            "strategies": summary,
            "near_seeds": list(range(515000, 515128)),
            "clear_seeds": list(range(515128, 515160)),
            "lost_baseline_safe_near_goal_seeds": [515000],
            "novel_v10_safe_near_goal_seeds": [],
            "v10_new_unsafe_vs_frozen_controls": []}


class V10ProspectiveQualificationTest(unittest.TestCase):
    def test_registered_five_strategies_and_800_real_episode_requirement(self):
        self.assertEqual(qualifier.EXPECTED_TRIALS, 800)
        self.assertEqual(len(qualifier.EXPECTED_STRATEGIES), 5)
        self.assertEqual(qualifier.TRAIN_FIRST, 515000)

    def test_independent_paired_raw_readout_contract(self):
        training = fake_training()
        qualifier.verify_readout(training, fake_readout(training))

    def test_unregistered_unsafe_claim_rejected(self):
        training = fake_training()
        bad = fake_readout(training)
        bad["strategies"]["v10_loss_informed"]["unsafe"] = 1
        with self.assertRaisesRegex(AssertionError, "SCIENCE_COUNTS_NOT_RAW"):
            qualifier.verify_readout(training, bad)

    def test_false_novel_win_rejected(self):
        training = fake_training()
        bad = fake_readout(training)
        bad["novel_v10_safe_near_goal_seeds"] = [515020]
        with self.assertRaisesRegex(AssertionError, "WIN_LOSS_NOT_FROM_ORIGINAL"):
            qualifier.verify_readout(training, bad)

    def test_omitted_failed_world_rejected_before_comparison(self):
        training = fake_training()
        bad = fake_readout(training)
        bad["near_seeds"].remove(515000)
        with self.assertRaisesRegex(AssertionError, "COHORT_LISTS_NOT_RAW_OBSERVATIONS"):
            qualifier.verify_readout(training, bad)

    def test_fake_stage_funnel_gain_rejected(self):
        training = fake_training()
        bad = fake_readout(training)
        bad["strategies"]["v10_loss_informed"]["safe_near_forward_reopen_after_lateral"] = 4
        with self.assertRaisesRegex(AssertionError, "SCIENCE_COUNTS_NOT_RAW"):
            qualifier.verify_readout(training, bad)

    def test_product_cannot_claim_promotion_or_unlock_heldout(self):
        training = fake_training()
        manifest = {"schema": "junction.rokoko.mujoco-v10.prospective-train.v1.manifest",
                    "immutable_v10_training_head": qualifier.V10_TRAIN_HEAD,
                    "candidate_v10_weights_file_sha256": qualifier.V10_WEIGHTS_FILE_SHA,
                    "promotion_authorized": False}
        training["model_promotion_authorized"] = True
        with self.assertRaisesRegex(AssertionError, "SCIENCE_SCOPE_DRIFT"):
            qualifier.verify_independent_comparison(training, manifest, "a" * 40,
                                                    Path("unused"), None)

    def test_missing_fifth_arm_rejected_before_shared_full_trace_checker(self):
        training = fake_training()
        training["trials"].pop()
        manifest = {"schema": "junction.rokoko.mujoco-v10.prospective-train.v1.manifest",
                    "immutable_v10_training_head": qualifier.V10_TRAIN_HEAD,
                    "candidate_v10_weights_file_sha256": qualifier.V10_WEIGHTS_FILE_SHA,
                    "promotion_authorized": False}
        with self.assertRaisesRegex(AssertionError, "PRE_REGISTERED_FIVE_WAY"):
            qualifier.verify_independent_comparison(training, manifest, "a" * 40,
                                                    Path("unused"), None)


if __name__ == "__main__":
    unittest.main()
