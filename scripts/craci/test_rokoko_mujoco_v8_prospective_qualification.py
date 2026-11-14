"""Portable source/weight and paired TRAIN-only qualification contracts."""
from __future__ import annotations

import importlib.util
import gzip
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


MODULE = Path(__file__).with_name("rokoko-mujoco-v8-prospective-qualification.py")
spec = importlib.util.spec_from_file_location("craci_v8_prospective_qual", MODULE)
qualification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)


class V8StrictProspectiveQualification(unittest.TestCase):
    def test_checkpoint_pins_original_trainer_and_all_bytes(self):
        weights = {"source_head": qualification.HISTORICAL_TRAINER_SHA,
                   "v7_source_head": "127ceb9be4374ba46908cd398ced6b740275a434"}
        receipt = {"executed_head": qualification.HISTORICAL_TRAINER_SHA,
                   "model_weights_sha256": qualification.FROZEN_MODEL_SHA256,
                   "dev_cal_test_ood_opened": False,
                   "deployment_authorized": False,
                   "model_weights_frozen": True}
        with patch.object(qualification, "sha_file", side_effect=[
                qualification.WEIGHTS_FILE_SHA256,
                qualification.TRAIN_RECEIPT_FILE_SHA256]), patch.object(
                    qualification, "load_json", side_effect=[weights, receipt]):
            returned_weights, returned_receipt = qualification.verify_checkpoint(
                Path("weights.json"), Path("training-receipt.json"))
        self.assertEqual(returned_weights, weights)
        self.assertEqual(returned_receipt, receipt)

    def test_self_rehashed_or_substituted_model_rejected(self):
        with patch.object(qualification, "sha_file", side_effect=[
                "a" * 64, qualification.TRAIN_RECEIPT_FILE_SHA256]):
            with self.assertRaisesRegex(AssertionError, "CHECKPOINT_BYTES_MISMATCH"):
                qualification.verify_checkpoint(
                    Path("weights.json"), Path("training-receipt.json"))

    def test_checkpoint_cannot_claim_dev_opened_or_deployed(self):
        good_weights = {"source_head": qualification.HISTORICAL_TRAINER_SHA,
                        "v7_source_head":
                        "127ceb9be4374ba46908cd398ced6b740275a434"}
        for tampering in [
                {"dev_cal_test_ood_opened": True},
                {"deployment_authorized": True},
                {"model_weights_sha256": "f" * 64},
                {"executed_head": "0" * 40}]:
            receipt = {"executed_head": qualification.HISTORICAL_TRAINER_SHA,
                       "model_weights_sha256": qualification.FROZEN_MODEL_SHA256,
                       "dev_cal_test_ood_opened": False,
                       "deployment_authorized": False,
                       "model_weights_frozen": True, **tampering}
            with self.subTest(tampering=tampering):
                with patch.object(qualification, "sha_file", side_effect=[
                        qualification.WEIGHTS_FILE_SHA256,
                        qualification.TRAIN_RECEIPT_FILE_SHA256]), patch.object(
                            qualification, "load_json",
                            side_effect=[good_weights, receipt]):
                    with self.assertRaisesRegex(
                            AssertionError, "PROVENANCE_INVALID"):
                        qualification.verify_checkpoint(
                            Path("weights.json"), Path("training-receipt.json"))

    def test_fresh_predeclared_paired_cohort_and_reused_true_physics_contract(self):
        trials = [{
            "strategy": name, "observed_corridor": index < 128,
            "success": False, "unsafe": False,
            "lateral_displacement": 0.0,
            "forward_reopened_after_side": 0,
        } for index in range(160) for name in qualification.STRATEGIES]
        training = {
            "schema": "junction.rokoko.mujoco-v8.prospective-train.v1.training",
            "train_first_seed": qualification.NEW_TRAIN_FIRST,
            "selected_near_count": 128, "selected_clear_count": 32,
            "strategies": list(qualification.STRATEGIES), "trials": trials,
        }
        def fake_existing_verifier(_training, _manifest, _sha, _folder):
            return {"trials": 640, "selected_near_worlds": 128,
                    "selected_clear_worlds": 32,
                    "strategies": {name: 160 for name in qualification.STRATEGIES}}
        previous = SimpleNamespace(
            TRAIN_FIRST=512_000, MIN_STRATEGIES=8,
            verify_training=fake_existing_verifier)
        result = qualification.verify_paired_train_result(
            training, {}, "a" * 40, Path("evidence"), previous)
        self.assertEqual(previous.TRAIN_FIRST, 513_000)
        self.assertEqual(previous.MIN_STRATEGIES, 4)
        self.assertFalse(result["independentHoldout"])
        self.assertFalse(result["model_improvement_independently_verified"])
        self.assertEqual(result["candidate_v8_safe_goal_difference_vs_best_frozen_baseline"], 0)
        self.assertEqual(result["next_experiment_advisory"]["new_train_seed_start"],
                         514_000)
        self.assertEqual(result["schema"],
                         "junction.rokoko.mujoco-v8-prospective.craci.train.v1")
        training["strategies"] = ["v8_hierarchical"]
        with self.assertRaisesRegex(AssertionError, "COHORT_CHANGED"):
            qualification.verify_paired_train_result(
                training, {}, "a" * 40, Path("evidence"), previous)

    def test_all_raw_option_masks_and_reopen_indices_are_independently_checked(self):
        class PublicOnlyMask:
            def reset(self, seed, ood):
                return None

            def mask(self, observation):
                return np.array([1, int(observation[0] >= .5), 0, 1, 1, 1, 1],
                                dtype=bool)

        before = [0.0] * 18
        after = [1.0] + [0.0] * 17
        row = {
            "seed": 513000, "strategy": "repeat_left", "observed_corridor": True,
            "forward_reopened_after_side": 1,
            "forward_reopen_option_steps": [1],
            "stage_funnel": {"any_forward_reopen_after_side": True},
        }
        event = {"observation": before, "next_observation": after,
                 "mask": [1, 0, 0, 1, 1, 1, 1], "action": 3}
        with tempfile.TemporaryDirectory(prefix="v8-raw-replay-") as tmp:
            evidence = Path(tmp)
            with gzip.open(evidence / "full_transitions.jsonl.gz",
                           "wt", encoding="utf8") as stream:
                stream.write(json.dumps({"seed": 513000, "strategy": "repeat_left",
                                         "transitions": [event]}) + "\n")
            result = qualification.independently_verify_all_masks_and_reopening(
                evidence, {"trials": [row]}, PublicOnlyMask)
            self.assertEqual(result["repeat_left"], 1)
            self.assertEqual(result["v8_hierarchical"], 0)

            row["forward_reopened_after_side"] = 2
            with self.assertRaisesRegex(
                    AssertionError, "REOPEN_COUNTER_NOT_DERIVED"):
                qualification.independently_verify_all_masks_and_reopening(
                    evidence, {"trials": [row]}, PublicOnlyMask)
            row["forward_reopened_after_side"] = 1
            event["mask"][1] = 1
            with gzip.open(evidence / "full_transitions.jsonl.gz",
                           "wt", encoding="utf8") as stream:
                stream.write(json.dumps({"seed": 513000, "strategy": "repeat_left",
                                         "transitions": [event]}) + "\n")
            with self.assertRaisesRegex(
                    AssertionError, "SHIELD_NOT_REAL_PHYSICS"):
                qualification.independently_verify_all_masks_and_reopening(
                    evidence, {"trials": [row]}, PublicOnlyMask)


if __name__ == "__main__":
    unittest.main()
