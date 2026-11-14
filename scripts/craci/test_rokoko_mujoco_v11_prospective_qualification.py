"""Synthetic-only V11 independent CRACI qualification contract tests.

Not evidence of actual MuJoCo execution. The hosted source-bound experiment
must run the genuine product, original V7 raw verifier and real physical replay.
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "v11_independent_qualification_contract",
    HERE / "rokoko-mujoco-v11-prospective-qualification.py")
qual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qual)


class FakeV7Canonical:
    @staticmethod
    def canonical_sha(value):
        return hashlib.sha256(json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def fixture():
    first = qual.TRAIN_FIRST
    scan = []
    for index in range(512):
        observation = [0.] * 18
        observation[7] = 0.1 if index < 128 else 0.3
        scan.append({"seed": first + index, "observation": observation,
                     "mask": [1, 0, 0, 0, 0, 0, 0],
                     "world_hash": hashlib.sha256(str(index).encode()).hexdigest()})
    cohort = [
        {"seed": row["seed"], "world_hash": row["world_hash"],
         "initial_observed_obstacle_y": row["observation"][7],
         "observed_corridor": index < 128}
        for index, row in enumerate(scan[:160])
    ]
    trials = []
    for world in cohort:
        for arm in qual.EXPECTED_STRATEGIES:
            trials.append({"seed": world["seed"], "world_hash": world["world_hash"],
                           "strategy": arm, "observed_corridor": world["observed_corridor"],
                           "success": arm == "frozen_v5" and world["seed"] == first,
                           "unsafe": False, "abstained": False})
    training = {"schema": qual.TRAINING_SCHEMA,
                "executed_head": "a" * 40, "training_only": True,
                "no_dev_test_ood": True, "model_promotion_authorized": False,
                "all_512_public_initial_scans": scan, "cohort": cohort,
                "strategies": list(qual.EXPECTED_STRATEGIES),
                "actual_trials": 800, "actual_option_transitions": 1000,
                "candidate_source_gate_sha256": qual.V11_GATE_SHA,
                "trials": trials}
    manifest = {"schema": qual.MANIFEST_SCHEMA, "executed_head": "a" * 40,
                "training_only": True, "model_promotion_authorized": False,
                "new_qualification_performed": False, "dev_cal_test_ood_opened": False,
                "gateSha256": qual.V11_GATE_SHA, "planSha256": qual.V11_PLAN_SHA,
                "actual_trials": 800, "actual_option_transitions": 1000,
                "file_sha256": {n: "b" * 64 for n in (
                    "training.json", "full_transitions.jsonl.gz",
                    "paired-readout.json")}}
    readout = {
        "schema": qual.READOUT_SCHEMA,
        "physical_goal250_tick_dwell_primary": True,
        "new_model_promotion_authorized": False,
        "dev_cal_test_ood_opened": False,
        "strategies": {
            name: {"safe_goals": int(name == "frozen_v5"),
                   "unsafe": 0, "near_safe_goals": int(name == "frozen_v5"),
                   "clear_safe_goals": 0}
            for name in qual.EXPECTED_STRATEGIES},
        "lost_frozen_v5_goal_seed_ids": [first],
        "novel_v11_safe_goal_seed_ids": [],
        "unsafe_v11_seed_ids": [],
        "source_only_preliminary_training_gate": "NO_GO_LOST_GOAL_UNSAFE_OR_ZERO_NOVEL",
    }
    return training, manifest, readout


class FakeClearPhysics:
    def reset(self, seed, ood):
        self.done = False
        self.dwell = self.contacts = self.steps = self.physics_steps = 0
        return [0.] * 18

    @staticmethod
    def mask(observation):
        return [1, 0, 0, 0, 0, 0, 0]

    def step(self, action):
        self.done = True
        self.dwell = 250
        self.contacts = self.steps = 1
        self.physics_steps = 100
        after = [0.] * 18
        after[0] = .1
        return after, 1., True, {"cost": 0, "contacts": 1, "success": True,
                                  "unsafe": False, "abstained": False, "error": .1}


class V11QualificationContracts(unittest.TestCase):
    def test_frozen_source_cohort_contract(self):
        self.assertEqual(qual.TRAIN_FIRST, 517000)
        self.assertEqual(qual.EXPECTED_TRIALS, 800)
        self.assertEqual(qual.EXPECTED_STRATEGIES, (
            "frozen_v5", "frozen_v6", "frozen_v8",
            "v10_loss_informed", "v11_goal_preserving"))

    def test_raw_v11_to_v7_metadata_view_only(self):
        training, manifest, _ = fixture()
        snapshot = json.dumps(training, sort_keys=True)
        original_manifest = json.dumps(manifest, sort_keys=True)
        legacy, legacy_manifest = qual.derive_legacy_read_only_view(
            training, manifest, FakeV7Canonical)
        self.assertEqual([s["seed"] for s in legacy["selection_scan"]],
                         list(range(517000, 517160)))
        self.assertEqual(legacy["selection_seed_limit"], 512)
        self.assertEqual(legacy["dataset_sha256"],
                         FakeV7Canonical.canonical_sha(training["trials"]))
        self.assertEqual(set(legacy_manifest["file_sha256"]),
                         {"training.json", "full_transitions.jsonl.gz"})
        self.assertEqual(json.dumps(training, sort_keys=True), snapshot)
        self.assertEqual(json.dumps(manifest, sort_keys=True), original_manifest)

    def test_missing_public_start_is_refused(self):
        training, manifest, _ = fixture()
        training["all_512_public_initial_scans"].pop()
        with self.assertRaisesRegex(AssertionError, "COHORT_DRIFT"):
            qual.derive_legacy_read_only_view(training, manifest, FakeV7Canonical)

    def test_heldout_unlock_is_refused(self):
        training, manifest, _ = fixture()
        training["no_dev_test_ood"] = False
        with self.assertRaisesRegex(AssertionError, "SCOPE_DRIFT"):
            qual.derive_legacy_read_only_view(training, manifest, FakeV7Canonical)

    def test_invalid_third_original_sha_cannot_be_skipped(self):
        training, manifest, _ = fixture()
        del manifest["file_sha256"]["paired-readout.json"]
        with self.assertRaisesRegex(AssertionError, "COHORT_DRIFT"):
            qual.derive_legacy_read_only_view(training, manifest, FakeV7Canonical)

    def test_v11_goal_preservation_science_counts_not_faked(self):
        training, _, readout = fixture()
        qual.verify_readout(training, readout)
        readout["strategies"]["v11_goal_preserving"]["safe_goals"] = 1
        with self.assertRaisesRegex(AssertionError, "SCIENCE_COUNTS_NOT_RAW"):
            qual.verify_readout(training, readout)

    def test_lost_goal_cannot_be_dropped(self):
        training, _, readout = fixture()
        readout["lost_frozen_v5_goal_seed_ids"] = []
        with self.assertRaisesRegex(AssertionError, "WIN_LOSS_NOT_FROM_ORIGINAL"):
            qual.verify_readout(training, readout)

    def test_public_initial_start_physics_contract(self):
        training, _, _ = fixture()
        # A synthetic 512-reset environment suffices to exercise rejection.
        class Fake:
            @staticmethod
            def reset(seed, ood):
                observation = [0.] * 18
                observation[7] = .1 if seed - 517000 < 128 else .3
                return observation
            @staticmethod
            def mask(observation):
                return [1, 0, 0, 0, 0, 0, 0]
        signature = lambda _: "unexpected-sha"
        with self.assertRaisesRegex(AssertionError, "PUBLIC_STARTS_DIFFER"):
            qual.replay_all_512_initial_public_worlds(
                training, Fake, signature,
                lambda x, y: list(x) == list(y))

    def test_clear_goal_replay_checks_exact_frozen_action(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            start = [0.] * 18
            after = start.copy()
            after[0] = .1
            trace = [{"observation": start, "mask": [1, 0, 0, 0, 0, 0, 0],
                      "action": 0, "next_observation": after, "reward": 1.,
                      "done": True, "cost": 0, "contacts_cumulative": 1,
                      "success_info": True, "dwell_ticks_cumulative": 250,
                      "dwell_ticks_current": 250}]
            row = {"seed": 517130, "strategy": "frozen_v5",
                   "observed_corridor": False, "success": True,
                   "unsafe": False, "abstained": False,
                   "world_hash": "fixture", "option_steps": 1,
                   "physics_steps": 100, "contacts": 1, "final_error": .1}
            with gzip.open(root / "full_transitions.jsonl.gz", "wt") as out:
                out.write(json.dumps({"seed": row["seed"], "strategy": row["strategy"],
                                      "transitions": trace}) + "\n")
            good = lambda _: (lambda: (lambda obs, mask: 0))
            result = qual.replay_clear_goal_successes(
                root, {"trials": [row]}, FakeClearPhysics,
                good, lambda env: "fixture", lambda a, b: list(a) == list(b))
            self.assertEqual(result["replayed_safe_clear_goal_trajectories"], 1)
            bad = lambda _: (lambda: (lambda obs, mask: 2))
            with self.assertRaisesRegex(AssertionError, "POLICY_ACTION_NOT_REPRODUCED"):
                qual.replay_clear_goal_successes(
                    root, {"trials": [row]}, FakeClearPhysics,
                    bad, lambda env: "fixture", lambda a, b: list(a) == list(b))


if __name__ == "__main__":
    unittest.main()
