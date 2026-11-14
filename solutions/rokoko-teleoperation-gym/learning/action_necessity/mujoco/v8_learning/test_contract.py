"""Portable V8 source/learning contracts; synthetic data is never physics evidence."""
from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


MODULE = Path(__file__).with_name("run.py")
spec = importlib.util.spec_from_file_location("rokoko_v8_learner", MODULE)
v8 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v8)


def synthetic_observation(seed):
    o = [0.] * 18
    o[6] = .09
    o[7] = .05 if seed < 512128 else .18
    o[16] = .16
    o[17] = 0.
    return o


def fixture(folder):
    """Fabricated boundary contract only; NOT a MuJoCo training result."""
    folder.mkdir(parents=True)
    rows = []
    traces = []
    for seed in range(512000, 512160):
        for strategy in v8.EXPECTED_STRATEGIES:
            success = seed in (512001, 512002) and strategy == "frozen_v5"
            progress = strategy == "repeat_left" and seed < 512074
            events = []
            for index, action in enumerate((3, 1)):
                o = synthetic_observation(seed)
                if index == 1 and progress:
                    o[1] = -.03
                event = {"observation": o, "mask": [1] * 7,
                         "action": action, "reward": 0., "cost": 0,
                         "done": index == 1,
                         "contacts_cumulative": 1 if index else 0,
                         "dwell_ticks_current": 250 if success and index else 0,
                         "dwell_ticks_cumulative": 250 if success and index else 0,
                         "success_info": success and index == 1,
                         "next_observation": o}
                events.append(event)
            rows.append({"seed": seed, "strategy": strategy,
                         "world_hash": hashlib.sha256(str(seed).encode()).hexdigest(),
                         "unsafe": False, "success": success, "abstained": False,
                         "observed_corridor": seed < 512128,
                         "away_lateral_displacement": .03 if progress else 0.,
                         "full_transition_count": len(events),
                         "full_transition_sha256": v8.digest(events)})
            traces.append({"seed": seed, "strategy": strategy, "transitions": events})
    training = {"schema": v8.V7_TRAIN_SCHEMA,
                "executed_head": v8.V7_SOURCE_SHA,
                "actual_physics_engine": "mujoco-3.3.7",
                "no_dev_evaluation": True, "selected_near_count": 128,
                "selected_clear_count": 32,
                "train_first_seed": v8.TRAIN_SEED_MIN,
                "strategies": list(v8.EXPECTED_STRATEGIES),
                "actual_transition_count": 2560,
                "trials": rows, "dataset_sha256": v8.digest(rows)}
    (folder / "training.json").write_bytes(v8.canonical_bytes(training) + b"\n")
    with gzip.open(folder / "full_transitions.jsonl.gz", "wb") as out:
        for trace in traces:
            out.write(v8.canonical_bytes(trace) + b"\n")
    manifest = {"executed_head": v8.V7_SOURCE_SHA,
                "file_sha256": {name: v8.file_sha256(folder / name)
                                for name in ("training.json", "full_transitions.jsonl.gz")}}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf8")
    qual = {"schema": v8.V7_QUAL_SCHEMA,
            "exact_source_sha": v8.V7_SOURCE_SHA,
            "experiment_complete": True, "dev_cal_test_ood_opened": False,
            "promotion_authorized": False, "producer_exit_code": 0,
            "trials": 1280, "actual_real_option_transitions": 2560,
            "dataset_sha256": training["dataset_sha256"]}
    (folder / "independent-qualification.json").write_text(json.dumps(qual),
                                                               encoding="utf8")
    replay = {"claim_verified": True, "model_promotion_authorized": False,
              "no_dev_cal_test_ood": True, "selection_scan_replayed": 160,
              "fully_replayed_positive_train_trials": 3}
    (folder / "independent-positive-replay.json").write_text(json.dumps(replay),
                                                                encoding="utf8")
    # Trust-boundary adversary: fabricate a plausible successful source-bound
    # receipt and archive, then rehash every file. The production gate MUST
    # still reject this complete self-consistent fake V7 run.
    (folder / "artifact.zip").write_bytes(b"synthetic-unit-contract-not-real-CRACI")
    binding = {"runId": v8.V7_CRACI_RUN_ID, "sourceSha": v8.V7_SOURCE_SHA,
               "harnessSha": v8.V7_HARNESS_SHA, "repository": "SalesSquad/junction-pets",
               "workload": "rokoko-mujoco-v7-feasibility"}
    receipt = {"runId": v8.V7_CRACI_RUN_ID, "binding": binding,
               "status": "succeeded", "jobStatus": "success",
               "sourceVerified": True, "harnessVerified": True, "issues": [],
               "command": {"binding": binding, "exitCode": 0,
                           "wrapperExitCode": 0, "state": "completed"},
               "manifest": {"sha256": "1bfddb3fbb91888ba6e8b3196572938387c7a629bfe948b128e9a3e5f12bc3e0"}}
    (folder / "receipt.json").write_bytes(v8.canonical_bytes(receipt))
    return training, {name: v8.file_sha256(folder / name)
                      for name in v8.EVIDENCE_DIR_FILES}


class V8LearningContracts(unittest.TestCase):
    def test_exact_checkout_refuses_untracked_source(self):
        with patch.object(v8.subprocess, "check_output",
                          side_effect=[v8.V7_SOURCE_SHA + "\n", "?? untracked-script.py\n"]):
            with self.assertRaisesRegex(ValueError, "SOURCE_DIRTY_INCLUDING_UNTRACKED"):
                v8.source_identity(v8.V7_SOURCE_SHA)

    def test_public_observation_features_and_original_shield(self):
        o = synthetic_observation(512001)
        m = [0, 0, 0, 1, 0, 0, 1]
        memory = v8.PublicMemory()
        stage, f, legal = memory.features(o, m)
        self.assertEqual(stage, 0)
        self.assertEqual(f.shape, (41,))
        self.assertEqual(legal.sum(), 2)
        policy = v8.HierarchicalPolicy(np.zeros((4, 41, 7)))
        self.assertEqual(policy(o, m), 3)
        self.assertEqual(policy.memory.last_action, 3)

    def test_hidden_world_or_seed_cannot_enter_inference_contract(self):
        policy = v8.HierarchicalPolicy(np.zeros((4, 41, 7)))
        with self.assertRaisesRegex(ValueError, "PUBLIC_18D_7MASK"):
            policy([0.] * 19, [True] * 7)
        with self.assertRaisesRegex(ValueError, "PUBLIC_18D_7MASK"):
            policy([0.] * 18, [False] * 7)
        with self.assertRaisesRegex(ValueError, "PUBLIC_18D_7MASK"):
            policy([0.] * 18, [0, 0, 0, 2, 0, 0, 1])
        with self.assertRaisesRegex(ValueError, "PUBLIC_18D_7MASK"):
            policy([0.] * 18, [0, 0, 0, "yes", 0, 0, 1])

    def test_full_1280_synthetic_boundary_and_gradient_updates(self):
        with tempfile.TemporaryDirectory(prefix="v8-contract-") as directory:
            root = Path(directory) / "evidence"
            training, fixture_hashes = fixture(root)
            training, _, _, _, rows = v8._v7_evidence_contract(
                root, fixture_hashes, training["dataset_sha256"])
            self.assertEqual(len(rows), 1280)
            examples, witnesses, n = v8.training_examples(root, rows)
            self.assertEqual(n, 2560)
            self.assertEqual(witnesses["frozen_v5"], 2)
            self.assertEqual(witnesses["repeat_left"], 74)
            trained, logs, diagnostics = v8.learn(examples, {512001, 512002})
            self.assertEqual(trained.shape, (4, 41, 7))
            self.assertGreater(np.linalg.norm(trained), 0)
            self.assertNotIn(512001, diagnostics)
            self.assertNotIn(512002, diagnostics)
            self.assertTrue(all(item["train_samples"] >= 0 for item in logs))
            self.assertTrue(any(item["trained"] and
                                item["fit_cross_entropy"] <
                                item["initial_fit_cross_entropy"] for item in logs))

    def test_training_sha_mismatch_aborts_before_learning(self):
        with tempfile.TemporaryDirectory(prefix="v8-contract-") as directory:
            root = Path(directory) / "evidence"
            synthetic, trusted = fixture(root)
            training = root / "training.json"
            with training.open("ab") as out:
                out.write(b"changed")
            with self.assertRaisesRegex(ValueError, "PINNED_CRACI_ARTIFACT_SHA_MISMATCH"):
                v8._v7_evidence_contract(root, trusted, synthetic["dataset_sha256"])

    def test_nonqualified_independent_replay_aborts(self):
        with tempfile.TemporaryDirectory(prefix="v8-contract-") as directory:
            root = Path(directory) / "evidence"
            training, _ = fixture(root)
            replay = root / "independent-positive-replay.json"
            payload = json.loads(replay.read_text(encoding="utf8"))
            payload["claim_verified"] = False
            replay.write_text(json.dumps(payload), encoding="utf8")
            # The contract-only seam tests semantic replay rejection using a
            # newly calculated synthetic hash. The production gate would fail
            # earlier against the independently pinned real file digest.
            trusted = {name: v8.file_sha256(root / name)
                       for name in v8.EVIDENCE_DIR_FILES}
            with self.assertRaisesRegex(ValueError, "INDEPENDENT_POSITIVE_PHYSICS"):
                v8._v7_evidence_contract(root, trusted, training["dataset_sha256"])

    def test_self_consistent_forgery_cannot_pass_production_gate(self):
        with tempfile.TemporaryDirectory(prefix="v8-forged-") as directory:
            root = Path(directory) / "evidence"
            training, trusted = fixture(root)
            self.assertEqual(
                len(v8._v7_evidence_contract(root, trusted,
                                             training["dataset_sha256"])[4]), 1280)
            with self.assertRaisesRegex(ValueError, "PINNED_CRACI_ARTIFACT_SHA_MISMATCH"):
                v8.verified_v7_evidence(root)

    def test_unsafe_and_abstained_policies_not_training_teachers(self):
        seed = 512001
        row = {"observed_corridor": True, "unsafe": False,
               "abstained": False, "success": False,
               "strategy": "repeat_left", "away_lateral_displacement": .03}
        self.assertTrue(v8.safe_training_witness(row))
        self.assertFalse(v8.safe_training_witness({**row, "unsafe": True}))
        self.assertFalse(v8.safe_training_witness({**row, "abstained": True}))
        self.assertFalse(v8.safe_training_witness({**row, "strategy": "repeat_right"}))
        self.assertFalse(v8.safe_training_witness({**row, "away_lateral_displacement": .024}))


if __name__ == "__main__":
    unittest.main()
