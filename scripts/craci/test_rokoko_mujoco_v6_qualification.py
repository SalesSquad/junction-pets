"""Synthetic contract tests only; never a substitute for real CRACI physics."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import unittest


MODULE = Path(__file__).with_name("rokoko-mujoco-v6-learning-qualification.py")
spec = importlib.util.spec_from_file_location("craci_v6_learning_qual", MODULE)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
SOURCE = "a" * 40


def fixture():
    event = {"observation": [0.0] * 18, "next_observation": [0.0] * 18,
             "mask": [1] * 7, "action": 2, "action_name": "PUSH_FAST",
             "reward": 0.5, "cost": 0, "done": True}
    rollouts = [{"generation": generation, "candidate": candidate,
                 "seed": seed, "world_hash": hashlib.sha256(str(seed).encode()).hexdigest(),
                 "transitions": [dict(event)]}
                for generation in range(2) for candidate in range(3)
                for seed in range(511000, 511048)]
    weights = {"clearance": 0.066, "lane_distance": 0.031}
    digest = validator.canonical_sha256(rollouts)
    wsha = validator.canonical_sha256(weights)
    training = dict(executed_head=SOURCE, dataset_sha256=digest,
                    weights_sha256=wsha, actual_transition_count=len(rollouts),
                    train_first_seed=511000, train_episodes=48,
                    actual_physics_engine="mujoco-3.3.7",
                    rollouts=rollouts, selected={"weights": weights})
    model = dict(executed_head=SOURCE, weights_sha256=wsha,
                 dataset_sha256=digest, weights=weights)
    paired = []
    for i in range(80):
        row = {}
        for name in ("constant", "learned_v5", "learned_v6"):
            row[name] = dict(seed=129250+i,
                             world_hash=hashlib.sha256(str(129250+i).encode()).hexdigest(),
                             success=(name == "learned_v6" and i < 24) or
                                     (name == "constant" and i < 13) or
                                     (name == "learned_v5" and i < 19),
                             unsafe=False, abstained=False,
                             zero_physics_abstain=False, physics_steps=100,
                             option_steps=1)
        paired.append(row)
    ci = validator.paired_ci_from_worlds(paired)
    dev = dict(executed_head=SOURCE, split="dev", first_seed=129250,
               episodes=80, actual_physics_engine="mujoco-3.3.7",
               weights_sha256=wsha, dataset_sha256=digest,
               paired_worlds=paired, summaries={"learned_v6": {
                   "candidate_success": 24, "constant_success": 13,
                   "candidate_unsafe": 0, "constant_unsafe": 0,
                   "paired_bootstrap95_pp": ci,
               }})
    return training, model, dev


class QualificationContracts(unittest.TestCase):
    def test_positive_fixture_is_only_review_candidate(self):
        t, m, d = fixture()
        r = validator.verify_dev_receipt(t, m, d, SOURCE)
        self.assertTrue(r["science_gate_passed"])
        self.assertFalse(r["promotion_authorized"])
        self.assertEqual(r["decision"], "review_candidate_on_dev_only")

    def test_four_only_new_world_wins_do_not_qualify_macro_skill(self):
        t, m, d = fixture()
        d["paired_worlds"][23]["learned_v6"]["success"] = False
        d["summaries"]["learned_v6"]["candidate_success"] = 23
        d["summaries"]["learned_v6"]["paired_bootstrap95_pp"] = (
            validator.paired_ci_from_worlds(d["paired_worlds"]))
        result = validator.verify_dev_receipt(t, m, d, SOURCE)
        self.assertEqual(result["failure_mining"]["candidate_new_wins_v5_misses"], 4)
        self.assertFalse(result["science_gate_passed"])

    def test_baseline_overlap_cannot_fake_five_genuinely_new_world_wins(self):
        t, m, d = fixture()
        # The candidate still wins five worlds v5 lost, but one was also won
        # by constant, so the genuinely novel improvement is only four.
        d["paired_worlds"][12]["constant"]["success"] = False
        d["paired_worlds"][23]["constant"]["success"] = True
        d["summaries"]["learned_v6"]["paired_bootstrap95_pp"] = (
            validator.paired_ci_from_worlds(d["paired_worlds"]))
        result = validator.verify_dev_receipt(t, m, d, SOURCE)
        self.assertEqual(result["failure_mining"]["candidate_new_wins_v5_misses"], 5)
        self.assertEqual(result["failure_mining"]["candidate_new_wins_both_baselines_miss"], 4)
        self.assertFalse(result["science_gate_passed"])

    def test_losing_frozen_v5_win_is_not_accepted_even_with_net_gain(self):
        t, m, d = fixture()
        d["paired_worlds"][18]["learned_v6"]["success"] = False
        d["paired_worlds"][24]["learned_v6"]["success"] = True
        d["summaries"]["learned_v6"]["paired_bootstrap95_pp"] = (
            validator.paired_ci_from_worlds(d["paired_worlds"]))
        result = validator.verify_dev_receipt(t, m, d, SOURCE)
        self.assertEqual(result["failure_mining"]["candidate_loses_worlds_v5_wins"], 1)
        self.assertFalse(result["science_gate_passed"])

    def test_unsafe_shift_between_worlds_cannot_fake_zero_hazard_regression(self):
        t, m, d = fixture()
        # Same total hazards for all arms but different *paired* worlds.
        d["paired_worlds"][50]["constant"]["unsafe"] = True
        d["paired_worlds"][50]["learned_v5"]["unsafe"] = True
        d["paired_worlds"][51]["learned_v6"]["unsafe"] = True
        d["summaries"]["learned_v6"]["constant_unsafe"] = 1
        d["summaries"]["learned_v6"]["candidate_unsafe"] = 1
        result = validator.verify_dev_receipt(t, m, d, SOURCE)
        self.assertEqual(result["failure_mining"]["candidate_new_hazard_worlds_vs_baselines"], 1)
        self.assertFalse(result["science_gate_passed"])

    def test_wrong_training_window_fails_closed(self):
        t, m, d = fixture()
        t["train_first_seed"] = 129250
        with self.assertRaisesRegex(AssertionError, "UNREGISTERED_TRAIN_COHORT"):
            validator.verify_dev_receipt(t, m, d, SOURCE)

    def test_train_seed_leak_cannot_hide_behind_recomputed_dataset_sha(self):
        t, m, d = fixture()
        t["rollouts"][0]["seed"] = 129250
        rehashed = validator.canonical_sha256(t["rollouts"])
        t["dataset_sha256"] = m["dataset_sha256"] = d["dataset_sha256"] = rehashed
        with self.assertRaisesRegex(AssertionError, "TRAINING_ROLLOUT_CONTAINS_EXPOSED"):
            validator.verify_dev_receipt(t, m, d, SOURCE)

    def test_mask_bypass_in_training_fails(self):
        t, m, d = fixture()
        t["rollouts"][0]["transitions"][0]["mask"][2] = 0
        with self.assertRaisesRegex(AssertionError, "BYPASSED_SHARED_SHIELD"):
            validator.verify_dev_receipt(t, m, d, SOURCE)

    def test_unrecorded_training_rollouts_fail(self):
        t, m, d = fixture()
        t["rollouts"].pop()
        with self.assertRaises(AssertionError):
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
        d["paired_worlds"][0]["learned_v6"]["world_hash"] = "f" * 64
        with self.assertRaisesRegex(AssertionError, "UNMATCHED_MUJOCO"):
            validator.verify_dev_receipt(t, m, d, SOURCE)

    def test_zero_physics_cannot_be_scored_as_success(self):
        t, m, d = fixture()
        r = d["paired_worlds"][22]["learned_v6"]
        r.update(success=True, physics_steps=0, abstained=True, zero_physics_abstain=True)
        with self.assertRaisesRegex(AssertionError, "UNSAFE_OR_ABSTAINED_SUCCESS"):
            validator.verify_dev_receipt(t, m, d, SOURCE)

    def test_legitimate_zero_physics_refusal_is_failure(self):
        t, m, d = fixture()
        r = d["paired_worlds"][25]["learned_v6"]
        r.update(success=False, physics_steps=0, abstained=True, zero_physics_abstain=True,
                 option_steps=1)
        result = validator.verify_dev_receipt(t, m, d, SOURCE)
        self.assertEqual(result["counts"]["learned_v6"]["abstain"], 1)

    def test_unsafe_regression_blocks_science(self):
        t, m, d = fixture()
        d["paired_worlds"][30]["learned_v6"]["unsafe"] = True
        d["summaries"]["learned_v6"]["candidate_unsafe"] = 1
        result = validator.verify_dev_receipt(t, m, d, SOURCE)
        self.assertFalse(result["science_gate_passed"])

    def test_negative_confidence_interval_blocks_science(self):
        t, m, d = fixture()
        for i, row in enumerate(d["paired_worlds"]):
            row["learned_v6"]["success"] = i < 14
        d["summaries"]["learned_v6"]["candidate_success"] = 14
        d["summaries"]["learned_v6"]["paired_bootstrap95_pp"] = (
            validator.paired_ci_from_worlds(d["paired_worlds"]))
        self.assertFalse(validator.verify_dev_receipt(t, m, d, SOURCE)["science_gate_passed"])

    def test_forged_positive_confidence_interval_fails_closed(self):
        t, m, d = fixture()
        for i, row in enumerate(d["paired_worlds"]):
            row["learned_v6"]["success"] = i < 14
        d["summaries"]["learned_v6"]["candidate_success"] = 14
        d["summaries"]["learned_v6"]["paired_bootstrap95_pp"] = [2., 25.]
        with self.assertRaisesRegex(AssertionError, "PRODUCER_CONFIDENCE_INTERVAL"):
            validator.verify_dev_receipt(t, m, d, SOURCE)

    def test_scientific_red_proposes_only_new_training_and_dev_seeds(self):
        t, m, d = fixture()
        for i, row in enumerate(d["paired_worlds"]):
            row["learned_v6"]["success"] = i < 14
        d["summaries"]["learned_v6"]["candidate_success"] = 14
        d["summaries"]["learned_v6"]["paired_bootstrap95_pp"] = (
            validator.paired_ci_from_worlds(d["paired_worlds"]))
        result = validator.verify_dev_receipt(t, m, d, SOURCE)
        next_round = result["next_learning_round"]
        self.assertEqual(next_round["new_train_only_seed_start"], 512000)
        self.assertEqual(next_round["new_fresh_dev_seed_start"], 129330)
        self.assertFalse(next_round["dispatch_authorized"])
        self.assertTrue(next_round["requires_new_source_and_weight_hashes"])

    def test_summary_forgery_fails(self):
        t, m, d = fixture()
        d["summaries"]["learned_v6"]["candidate_success"] += 1
        with self.assertRaisesRegex(AssertionError, "SUMMARY_COUNTS"):
            validator.verify_dev_receipt(t, m, d, SOURCE)


if __name__ == "__main__":
    unittest.main()
