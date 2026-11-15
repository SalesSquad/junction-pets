"""Pure prospective TRAIN science contracts; no simulator mocks passed as physics."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np


MODULE = Path(__file__).with_name("rollout_train.py")
spec = importlib.util.spec_from_file_location("v8_prospective_train_contract", MODULE)
rollout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rollout)
v8 = rollout.v8


class FakeSelectionOnly:
    """Only exercises seed-selection logic; has no step() and no physics."""
    def reset(self, seed, ood=False):
        if ood:
            raise AssertionError("FORBIDDEN_OOD_RESET")
        self.seed = seed
        obs = np.zeros(18)
        obs[7] = .01 if seed < 513128 else .20
        return obs


def synthetic_cohort():
    return [{"seed": seed, "world_hash": str(seed),
             "initial_observed_obstacle_y": .01 if seed < 513128 else .20,
             "observed_corridor": seed < 513128}
            for seed in range(513000, 513160)]


def synthetic_transitions(contact_at=0, lateral_at=1, reopen_at=1, win=True):
    events = []
    for index in range(3):
        observation = np.zeros(18)
        observation[7] = .10
        final = observation.copy()
        final[1] = -.03 if index >= lateral_at else 0.
        final[16] = 0.
        final[17] = final[1] if win and index == 2 else .2
        events.append({"observation": observation.tolist(),
                       "next_observation": final.tolist(),
                       "contacts_cumulative": 1 if index >= contact_at else 0,
                       "dwell_ticks_current": 250 if win and index == 2 else 0,
                       "cost": 0, "success_info": win and index == 2,
                       "forward_reopened_after_side": index == reopen_at})
    return events


def synthetic_frozen():
    head = rollout.TRAINER_HEAD
    matrix = np.zeros((4, 41, 7))
    matrix[0, 0, 3] = 1.
    frozen = {"schema": v8.SCHEMA + ".weights", "source_head": head,
              "v7_source_head": v8.V7_SOURCE_SHA,
              "v7_training_sha256": v8.V7_PINNED_FILES["training.json"],
              "v7_full_transitions_sha256": v8.V7_PINNED_FILES["full_transitions.jsonl.gz"],
              "model_type": "four-stage masked-observation linear softmax",
              "feature_count": 41, "stages": 4, "actions": 7,
              "seed": v8.RANDOM_SEED, "weights": matrix.tolist()}
    receipt = {"schema": v8.SCHEMA + ".receipt", "executed_head": head,
               "model_weights_sha256": v8.digest(frozen),
               "v7_evidence_dataset_sha256": v8.V7_DATASET_SHA256,
               "actual_v7_raw_train_transitions": 68568,
               "model_weights_frozen": True,
               "dev_cal_test_ood_opened": False,
               "independent_science_qualification": False,
               "deployment_authorized": False,
               "next_fresh_train_seed": 513000,
               "gradient_epochs_per_stage": v8.EPOCHS}
    return frozen, receipt


class V8ProspectiveTrainContracts(unittest.TestCase):
    def test_lossless_640_trial_max_option_summary_below_capture_cap(self):
        # Deliberately full-precision 18D observations and V7's maximum
        # 60 options/28 sparse samples per row, not a toy short-action sample.
        # No real train outcome, hidden data, reduced options or field stripping.
        long_obs = [float(f"{(-1)**i * (i + 1) / 19:.17f}") for i in range(18)]
        terminal = [x + 0.0123456789012345 for x in long_obs]
        full = []
        for i in range(60):
            full.append({"observation": long_obs, "mask": [1, 1, 1, 1, 1, 1, 1],
                         "action": 3, "reward": -0.12345678901234567,
                         "cost": 0, "done": i == 59,
                         "contacts_cumulative": i // 10,
                         "dwell_ticks_current": i,
                         "dwell_ticks_cumulative": i,
                         "success_info": False,
                         "next_observation": terminal})
        indices = sorted(set(range(12)) | set(range(52, 60)) | set(range(0, 60, 5)))
        sparse = [full[i] for i in indices]
        self.assertEqual(len(sparse), 28)
        trials = []
        for world in synthetic_cohort():
            for strategy in rollout.STRATEGIES:
                trials.append({**world, "strategy": strategy,
                               "allocation_phase": "all_four_paired_prospective_train",
                               "success": False, "unsafe": False, "abstained": False,
                               "zero_physics_abstain": False, "physics_steps": 6000,
                               "option_steps": 60, "contacts": 5,
                               "side_contact_option_steps": [1, 10, 20, 30, 40, 50],
                               "dwell_ticks_final": 59,
                               "lateral_displacement": 0.12345678901234567,
                               "away_lateral_displacement": 0.12345678901234567,
                               "final_error": 0.12345678901234567,
                               "total_reward": -7.407407340740741,
                               "side_proposals": 60,
                               "forward_reopened_after_side": 5,
                               "forward_reopen_option_steps": [10, 20, 30, 40, 50],
                               "contact_to_forward_to_dwell": False,
                               "full_transition_count": 60,
                               "full_transition_sha256": "a" * 64,
                               "sparse_trace": True,
                               "sparse_transition_indices": indices,
                               "transitions": sparse,
                               "stage_funnel": {
                                   "contact": True, "any_signed_lateral25": True,
                                   "signed_lateral25_after_contact": True,
                                   "any_forward_reopen_after_side": True,
                                   "forward_reopen_after_lateral25": True,
                                   "full_contact_lateral_reopen_goal_dwell": False,
                                   "contact_first_option": 1,
                                   "lateral25_first_option": 2,
                                   "reopen_first_option": 10}})
        self.assertEqual(len(trials), 640)
        training = {"schema": rollout.SCHEMA + ".training", "executed_head": "a" * 40,
                    "actual_physics_engine": "mujoco-3.3.7",
                    "train_first_seed": 513000,
                    "selection_seed_limit": 512,
                    "selected_near_count": 128, "selected_clear_count": 32,
                    "selection_scan": [{"seed": r["seed"], "world_hash": r["world_hash"],
                                        "initial_observed_obstacle_y":
                                        r["initial_observed_obstacle_y"]}
                                       for r in synthetic_cohort()],
                    "strategies": list(rollout.STRATEGIES),
                    "no_dev_evaluation": True,
                    "actual_transition_count": 640 * 60,
                    "trials": trials, "dataset_sha256": v8.digest(trials)}
        with tempfile.TemporaryDirectory(prefix="v8-max-summary-") as directory:
            path = Path(directory) / "training.json"
            inflated = len(json.dumps(training, sort_keys=True, indent=2,
                                      ensure_ascii=False, allow_nan=False).encode("utf8")) + 1
            self.assertGreater(inflated, rollout.MAX_CAPTURED_JSON_BYTES,
                               "regression fixture must reproduce old pretty-print capture failure")
            size = rollout.write_compact_source_bound_training(path, training)
            self.assertEqual(path.stat().st_size, size)
            self.assertLessEqual(size, rollout.MAX_CAPTURED_JSON_BYTES)
            restored = json.loads(path.read_text())
            self.assertEqual(restored, training)
            self.assertEqual(v8.digest(restored["trials"]),
                             restored["dataset_sha256"])
            self.assertEqual(len(restored["trials"]), 640)
            with self.assertRaises(FileExistsError):
                rollout.write_compact_source_bound_training(path, training)

    def test_manifest_exact_two_raw_files_readout_only_auxiliary(self):
        with tempfile.TemporaryDirectory(prefix="v8-manifest-") as directory:
            folder = Path(directory)
            for name in ("full_transitions.jsonl.gz", "training.json",
                         "paired-readout.json"):
                (folder / name).write_text("contract-only")
            doc = rollout.build_source_bound_manifest(
                folder, "a" * 40, rollout.FROZEN_WEIGHTS_SHA256,
                {"source_sha256": {"run.py": "a" * 64}}, 640)
            self.assertEqual(set(doc["file_sha256"]),
                             {"training.json", "full_transitions.jsonl.gz"})
            self.assertEqual(set(doc["auxiliary_file_sha256"]),
                             {"paired-readout.json"})
            self.assertFalse(doc["promotion_authorized"])

    def test_forward_reopen_requires_immediate_side_causality(self):
        before_masked = [1, 0, 0, 1, 1, 0, 1]
        after_open = [1, 1, 1, 1, 1, 0, 1]
        already_open = [1, 1, 0, 1, 1, 0, 1]
        self.assertTrue(rollout.direct_side_reopened_forward(
            before_masked, after_open, 3))
        self.assertFalse(rollout.direct_side_reopened_forward(
            before_masked, after_open, 0))
        self.assertFalse(rollout.direct_side_reopened_forward(
            already_open, after_open, 3))
        self.assertFalse(rollout.direct_side_reopened_forward(
            before_masked, before_masked, 3))

    def test_all_worlds_train_only_first_128_near_32_clear(self):
        rollout.validate_train_bounds()
        env = FakeSelectionOnly()
        cohort, scanned = rollout.select_train_worlds(env, lambda instance: instance.seed)
        self.assertEqual(len(scanned), 160)
        self.assertEqual([r["seed"] for r in cohort], list(range(513000, 513160)))
        self.assertEqual(sum(r["observed_corridor"] for r in cohort), 128)
        self.assertEqual(sum(not r["observed_corridor"] for r in cohort), 32)
        plan = rollout.paired_plan(cohort)
        self.assertEqual(len(plan), 640)
        for offset in range(0, 640, 4):
            self.assertEqual(len({p[0]["seed"] for p in plan[offset:offset + 4]}), 1)
            self.assertEqual([p[1] for p in plan[offset:offset + 4]],
                             list(rollout.STRATEGIES))

    def test_signed_lateral_and_stage_order_is_chronological(self):
        complete = rollout.stage_funnel(synthetic_transitions(), [2])
        self.assertTrue(all(complete[key] for key in (
            "contact", "any_signed_lateral25", "signed_lateral25_after_contact",
            "any_forward_reopen_after_side", "forward_reopen_after_lateral25",
            "full_contact_lateral_reopen_goal_dwell")))
        out_of_order = rollout.stage_funnel(synthetic_transitions(
            contact_at=2, lateral_at=1, reopen_at=0), [1])
        self.assertTrue(out_of_order["any_signed_lateral25"])
        self.assertTrue(out_of_order["any_forward_reopen_after_side"])
        self.assertFalse(out_of_order["forward_reopen_after_lateral25"])
        self.assertFalse(out_of_order["full_contact_lateral_reopen_goal_dwell"])
        self.assertFalse(rollout.stage_funnel(
            synthetic_transitions(win=False), [2])["full_contact_lateral_reopen_goal_dwell"])

    def test_stable_independent_replay_policy_factory(self):
        # Contract only; actual MuJoCo replay must occur independently.
        matrix = np.zeros((4, 41, 7))
        class Source:
            @staticmethod
            def policy_factory(name):
                return lambda: name
        self.assertEqual(rollout.policy_factory("frozen_v5", matrix,
                                                 frozen_v7=Source())(), "frozen_v5")
        self.assertEqual(rollout.policy_factory("repeat_left", matrix,
                                                 frozen_v7=Source())(), "repeat_left")
        with self.assertRaisesRegex(ValueError, "UNREVIEWED_IN_MEMORY_MODEL"):
            rollout.policy_factory("v8_hierarchical", matrix, frozen_v7=Source())
        with self.assertRaisesRegex(ValueError, "UNREGISTERED_PROSPECTIVE_POLICY"):
            rollout.policy_factory("retreat_right", matrix, frozen_v7=Source())
        original = MODULE.parent / "checkpoints" / "weights.json"
        if original.exists():
            factory = rollout.policy_factory("v8_hierarchical", original)
            policy = factory()
            obs = np.zeros(18)
            obs[16] = .10
            self.assertIn(policy(obs, [1, 1, 1, 1, 1, 1, 1]), range(7))
            loaded_weights, _, _ = rollout.verify_frozen_model(
                original, original.with_name("training-receipt.json"),
                rollout.FROZEN_WEIGHTS_SHA256)
            factory_in_memory = rollout.policy_factory("v8_hierarchical", loaded_weights)
            self.assertIsNot(factory_in_memory(), factory_in_memory())

    def test_paired_near_loss_novel_and_unsafe_are_reported(self):
        rows = []
        for definition in synthetic_cohort():
            for strategy in rollout.STRATEGIES:
                seed = definition["seed"]
                baseline = ((seed == 513001 and strategy == "frozen_v5") or
                            (seed == 513002 and strategy == "frozen_v6"))
                new_model = (strategy == "v8_hierarchical" and seed in (513001, 513003))
                rows.append({**definition, "strategy": strategy,
                             "success": baseline or new_model,
                             "unsafe": strategy == "v8_hierarchical" and seed == 513004,
                             "abstained": False,
                             "stage_funnel": {"any_signed_lateral25": True,
                                              "signed_lateral25_after_contact": True,
                                              "forward_reopen_after_lateral25": True,
                                              "full_contact_lateral_reopen_goal_dwell":
                                              baseline or new_model}})
        readout = rollout.paired_readout(rows)
        self.assertEqual(readout["lost_frozen_v5_v6_safe_near_goal_seeds"], [513002])
        self.assertEqual(readout["novel_v8_safe_near_goal_seeds"], [513003])
        self.assertEqual(readout["v8_new_unsafe_vs_all_three_baselines_near_seeds"],
                         [513004])
        self.assertFalse(readout["model_promotion_authorized"])
        rows[10]["world_hash"] = "FABRICATED_UNPAIRED_WORLD"
        with self.assertRaisesRegex(ValueError, "UNPAIRED_REAL_WORLDS"):
            rollout.paired_readout(rows)

    def test_reviewed_weights_sha_receipt_and_source_gate(self):
        frozen, receipt = synthetic_frozen()
        with tempfile.TemporaryDirectory(prefix="v8-rollout-contract-") as directory:
            root = Path(directory)
            weights = root / "weights.json"
            proof = root / "training-receipt.json"
            weights.write_text(json.dumps(frozen))
            proof.write_text(json.dumps(receipt))
            # Explicit synthetic-only contract seam. Production accepts ONLY
            # historical 4b91... real frozen bytes and 9dd... reviewed model.
            model, doc, checksum = rollout._frozen_model_contract(
                weights, proof, frozen["source_head"], v8.digest(frozen),
                v8.file_sha256(weights), v8.file_sha256(proof))
            self.assertEqual(model.shape, (4, 41, 7))
            self.assertEqual(checksum, receipt["model_weights_sha256"])
            with self.assertRaisesRegex(ValueError, "REVIEWED_FROZEN_WEIGHTS_SHA_MISMATCH"):
                rollout.verify_frozen_model(weights, proof, v8.digest(frozen))
            with self.assertRaisesRegex(ValueError, "IMMUTABLE_FROZEN_MODEL_OR_RECEIPT_FILE_SHA"):
                rollout.verify_frozen_model(weights, proof, rollout.FROZEN_WEIGHTS_SHA256)
            receipt["deployment_authorized"] = True
            proof.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "FROZEN_PRIOR_TRAIN_EVIDENCE_MISMATCH"):
                rollout._frozen_model_contract(weights, proof, frozen["source_head"],
                                               v8.digest(frozen), v8.file_sha256(weights),
                                               v8.file_sha256(proof))

    def test_reject_incomplete_paired_plan_and_non_train_seed(self):
        all_worlds = synthetic_cohort()
        with self.assertRaisesRegex(ValueError, "BAD_COHORT"):
            rollout.paired_plan(all_worlds[:-1])
        all_worlds[0]["seed"] = 129330
        with self.assertRaisesRegex(ValueError, "BAD_COHORT"):
            rollout.paired_plan(all_worlds)


if __name__ == "__main__":
    unittest.main()
