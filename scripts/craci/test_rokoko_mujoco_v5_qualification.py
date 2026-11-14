"""Synthetic contract tests only; never a substitute for real CRACI physics."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE = Path(__file__).with_name("rokoko-mujoco-v5-learning-qualification.py")
spec = importlib.util.spec_from_file_location("craci_v5_learning_qual", MODULE)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
SOURCE = "a" * 40


def fixture():
    rollouts = [{"seed": 5290000, "transitions": [{"action": 2, "reward": 0.5,
                                                     "cost": 0}]}]
    weights = {"clearance": 0.066, "lane_distance": 0.031}
    digest = validator.canonical_sha256(rollouts)
    wsha = validator.canonical_sha256(weights)
    training = dict(executed_head=SOURCE, dataset_sha256=digest,
                    weights_sha256=wsha, actual_transition_count=1,
                    train_first_seed=5290000, train_episodes=48,
                    rollouts=rollouts, selected={"weights": weights})
    model = dict(weights_sha256=wsha, weights=weights)
    paired = []
    for i in range(80):
        row = {}
        for name in ("constant", "safe_v4", "learned_v5"):
            row[name] = dict(seed=129170+i, world_hash="world-hash-long-"+str(i),
                             success=(name == "learned_v5" and i < 24) or
                                     (name == "constant" and i < 13) or
                                     (name == "safe_v4" and i < 19),
                             unsafe=False, abstained=False,
                             zero_physics_abstain=False, physics_steps=100,
                             option_steps=1)
        paired.append(row)
    dev = dict(executed_head=SOURCE, split="dev", first_seed=129170,
               episodes=80, actual_physics_engine="mujoco-3.3.7",
               weights_sha256=wsha, dataset_sha256=digest,
               paired_worlds=paired, summaries={"learned_v5": {
                   "candidate_success": 24, "constant_success": 13,
                   "candidate_unsafe": 0, "constant_unsafe": 0,
                   "paired_bootstrap95_pp": [2.0, 25.0],
               }})
    return training, model, dev


class QualificationContracts(unittest.TestCase):
    def test_positive_fixture_is_only_review_candidate(self):
        t, m, d = fixture()
        r = validator.verify_dev_receipt(t, m, d, SOURCE)
        self.assertTrue(r["science_gate_passed"])
        self.assertFalse(r["promotion_authorized"])
        self.assertEqual(r["decision"], "review_candidate_on_dev_only")

    def test_wrong_training_window_fails_closed(self):
        t, m, d = fixture()
        t["train_first_seed"] = 129170
        with self.assertRaisesRegex(AssertionError, "UNREGISTERED_TRAIN_COHORT"):
            validator.verify_dev_receipt(t, m, d, SOURCE)

    def test_exposed_dev_seed_window_fails(self):
        t, m, d = fixture()
        d["first_seed"] = 129100
        with self.assertRaisesRegex(AssertionError, "EXPOSED_OR_WRONG_DEV"):
            validator.verify_dev_receipt(t, m, d, SOURCE)

    def test_model_swap_fails(self):
        t, m, d = fixture()
        m["weights_sha256"] = "f" * 64
        with self.assertRaisesRegex(AssertionError, "CANDIDATE_WEIGHT_BINDING"):
            validator.verify_dev_receipt(t, m, d, SOURCE)

    def test_forged_training_digest_fails(self):
        t, m, d = fixture()
        t["rollouts"][0]["transitions"][0]["reward"] = 5.0
        with self.assertRaisesRegex(AssertionError, "FORGED_TRAINING_DATASET"):
            validator.verify_dev_receipt(t, m, d, SOURCE)

    def test_forged_model_parameters_fail(self):
        t, m, d = fixture()
        m["weights"]["clearance"] = 0.05
        with self.assertRaisesRegex(AssertionError, "FORGED_CANDIDATE_WEIGHTS"):
            validator.verify_dev_receipt(t, m, d, SOURCE)

    def test_mismatched_world_fails(self):
        t, m, d = fixture()
        d["paired_worlds"][0]["learned_v5"]["world_hash"] = "different-valid-hash"
        with self.assertRaisesRegex(AssertionError, "UNMATCHED_MUJOCO"):
            validator.verify_dev_receipt(t, m, d, SOURCE)

    def test_zero_physics_cannot_be_scored_as_success(self):
        t, m, d = fixture()
        r = d["paired_worlds"][22]["learned_v5"]
        r.update(success=True, physics_steps=0, abstained=True, zero_physics_abstain=True)
        with self.assertRaisesRegex(AssertionError, "UNSAFE_OR_ABSTAINED_SUCCESS"):
            validator.verify_dev_receipt(t, m, d, SOURCE)

    def test_legitimate_zero_physics_refusal_is_failure(self):
        t, m, d = fixture()
        r = d["paired_worlds"][25]["learned_v5"]
        r.update(success=False, physics_steps=0, abstained=True, zero_physics_abstain=True,
                 option_steps=1)
        result = validator.verify_dev_receipt(t, m, d, SOURCE)
        self.assertEqual(result["counts"]["learned_v5"]["abstain"], 1)

    def test_unsafe_regression_blocks_science(self):
        t, m, d = fixture()
        d["paired_worlds"][30]["learned_v5"]["unsafe"] = True
        d["summaries"]["learned_v5"]["candidate_unsafe"] = 1
        result = validator.verify_dev_receipt(t, m, d, SOURCE)
        self.assertFalse(result["science_gate_passed"])

    def test_negative_confidence_interval_blocks_science(self):
        t, m, d = fixture()
        d["summaries"]["learned_v5"]["paired_bootstrap95_pp"] = [-2., 25.]
        self.assertFalse(validator.verify_dev_receipt(t, m, d, SOURCE)["science_gate_passed"])

    def test_scientific_red_proposes_only_new_training_and_dev_seeds(self):
        t, m, d = fixture()
        d["summaries"]["learned_v5"]["paired_bootstrap95_pp"] = [-2., 25.]
        result = validator.verify_dev_receipt(t, m, d, SOURCE)
        next_round = result["next_learning_round"]
        self.assertEqual(next_round["new_train_only_seed_start"], 5291000)
        self.assertEqual(next_round["new_fresh_dev_seed_start"], 129250)
        self.assertFalse(next_round["dispatch_authorized"])
        self.assertTrue(next_round["requires_new_source_and_weight_hashes"])

    def test_summary_forgery_fails(self):
        t, m, d = fixture()
        d["summaries"]["learned_v5"]["candidate_success"] += 1
        with self.assertRaisesRegex(AssertionError, "SUMMARY_COUNTS"):
            validator.verify_dev_receipt(t, m, d, SOURCE)


if __name__ == "__main__":
    unittest.main()
