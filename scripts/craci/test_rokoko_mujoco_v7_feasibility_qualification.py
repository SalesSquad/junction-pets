"""Synthetic fail-closed tests for v7 evidence only; NOT a physics substitute."""
from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE = Path(__file__).with_name("rokoko-mujoco-v7-feasibility-qualification.py")
spec = importlib.util.spec_from_file_location("craci_v7_feasibility_qualification", MODULE)
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)
SOURCE = "a" * 40
STRATEGIES = [f"frozen_strategy_{i}" for i in range(8)]


def make_fixture(root: Path):
    scan, trials, full = [], [], []
    for offset in range(160):
        seed = 512000 + offset
        y = .08 if offset < 128 else .16
        wh = hashlib.sha256(str(seed).encode()).hexdigest()
        scan.append(dict(seed=seed, initial_observed_obstacle_y=y, world_hash=wh))
        for name in STRATEGIES:
            obs = [0.] * 18
            obs[7] = y
            event = dict(observation=obs, mask=[1] * 7, action=6, reward=-.01,
                         cost=0, done=True, next_observation=list(obs),
                         contacts_cumulative=0, success_info=False,
                         dwell_ticks_cumulative=0)
            seq = [event]
            row = dict(seed=seed, world_hash=wh, initial_observed_obstacle_y=y,
                       observed_corridor=offset < 128, strategy=name,
                       success=False, unsafe=False, abstained=True,
                       physics_steps=0, option_steps=1, contacts=0,
                       lateral_displacement=0., final_error=.1,
                       total_reward=-.01, transitions=list(seq),
                       full_transition_count=1, full_transition_sha256=q.canonical_sha(seq),
                       sparse_trace=True, sparse_transition_indices=[0])
            trials.append(row)
            full.append(dict(seed=seed, strategy=name, transitions=seq))
    training = dict(executed_head=SOURCE, actual_physics_engine="mujoco-3.3.7",
                    train_first_seed=512000, selection_seed_limit=512,
                    selected_near_count=128, selected_clear_count=32,
                    no_dev_evaluation=True, strategies=list(STRATEGIES),
                    selection_scan=scan, trials=trials, actual_transition_count=len(trials))
    return training, full


def persist(root: Path, training: dict, full: list[dict]):
    training["dataset_sha256"] = q.canonical_sha(training["trials"])
    tpath = root / "training.json"
    rawpath = root / "full_transitions.jsonl.gz"
    tpath.write_text(json.dumps(training, sort_keys=True), encoding="utf8")
    with gzip.open(rawpath, "wt", encoding="utf8") as stream:
        for row in full:
            stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    manifest = dict(executed_head=SOURCE, file_sha256={
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ("training.json", "full_transitions.jsonl.gz")})
    return manifest


class FeasibilityContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="craci-v7-fixture-")
        cls.root = Path(cls.tmp.name)
        cls.base_training, cls.base_full = make_fixture(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def verify(self, training=None, full=None):
        t = copy.deepcopy(self.base_training if training is None else training)
        f = copy.deepcopy(self.base_full if full is None else full)
        m = persist(self.root, t, f)
        return q.verify_training(t, m, SOURCE, self.root)

    def test_completed_negative_capability_is_honest_valid_experiment(self):
        result = self.verify()
        self.assertTrue(result["experiment_complete"])
        self.assertFalse(result["mechanism_positive"])
        self.assertEqual(result["selected_near_worlds"], 128)
        self.assertEqual(result["selected_clear_worlds"], 32)
        self.assertEqual(result["actual_real_option_transitions"], 1280)
        self.assertFalse(result["promotion_authorized"])

    def test_heldout_seed_leak_fails_even_with_rehashed_dataset(self):
        t = copy.deepcopy(self.base_training)
        t["trials"][0]["seed"] = 129250
        with self.assertRaisesRegex(AssertionError, "TRIAL_USES_EXPOSED"):
            self.verify(t)

    def test_missing_strategy_world_fails_full_pairing(self):
        t = copy.deepcopy(self.base_training)
        t["trials"].pop()
        with self.assertRaisesRegex(AssertionError, "INCOMPLETE_OR_UNBOUNDED"):
            self.verify(t)

    def test_changed_world_initial_hash_fails(self):
        t = copy.deepcopy(self.base_training)
        t["trials"][1]["world_hash"] = "f" * 64
        with self.assertRaisesRegex(AssertionError, "STRATEGY_ARMS_NOT_SAME_INITIAL_WORLD"):
            self.verify(t)

    def test_scan_cannot_skip_unfavorable_candidate_seed(self):
        t = copy.deepcopy(self.base_training)
        t["selection_scan"][3]["seed"] += 1
        with self.assertRaisesRegex(AssertionError, "NONCONSECUTIVE"):
            self.verify(t)

    def test_mask_bypass_in_full_trace_fails(self):
        t = copy.deepcopy(self.base_training)
        full = copy.deepcopy(self.base_full)
        full[0]["transitions"][0]["mask"][6] = 0
        t["trials"][0]["transitions"][0]["mask"][6] = 0
        t["trials"][0]["full_transition_sha256"] = q.canonical_sha(full[0]["transitions"])
        with self.assertRaisesRegex(AssertionError, "BYPASSED_FROZEN_SEVEN_ACTION_SHIELD"):
            self.verify(t, full)

    def test_full_trace_digest_mismatch_fails(self):
        full = copy.deepcopy(self.base_full)
        full[0]["transitions"][0]["reward"] = 100.
        with self.assertRaisesRegex(AssertionError, "FORGED_FULL_ACTION_DATASET_SHA"):
            self.verify(full=full)

    def test_sparse_trace_cannot_diverge_from_full(self):
        t = copy.deepcopy(self.base_training)
        t["trials"][0]["transitions"][0]["reward"] = 9.
        with self.assertRaisesRegex(AssertionError, "SPARSE_TRACE_DOES_NOT_MATCH"):
            self.verify(t)

    def test_unsafe_zero_physics_positive_claim_rejected(self):
        t = copy.deepcopy(self.base_training)
        t["trials"][0]["success"] = True
        with self.assertRaisesRegex(AssertionError, "UNSAFE_OR_ABORTED_SUCCESS"):
            self.verify(t)

    def test_observed_corridor_label_cannot_be_forged(self):
        t = copy.deepcopy(self.base_training)
        t["trials"][0]["observed_corridor"] = False
        with self.assertRaisesRegex(AssertionError, "FORGED_OBSERVED_CORRIDOR_LABEL"):
            self.verify(t)

    def test_forged_positive_lateral_progress_is_not_mechanism_evidence(self):
        t = copy.deepcopy(self.base_training)
        t["trials"][0]["lateral_displacement"] = .04
        with self.assertRaisesRegex(AssertionError, "FORGED_OBSTACLE_AWAY_LATERAL_DISPLACEMENT"):
            self.verify(t)

    def test_toward_obstacle_movement_is_not_away_displacement(self):
        t = copy.deepcopy(self.base_training)
        full = copy.deepcopy(self.base_full)
        # Public obstacle is above the object; moving up must be negative.
        seq = []
        for i in range(60):
            obs = [0.] * 18
            obs[7] = .08
            obs[1] = 0. if i == 0 else .03
            after = list(obs)
            after[1] = .03
            seq.append(dict(observation=obs, next_observation=after,
                            mask=[1] * 7, action=3, cost=0, reward=0.,
                            done=i == 59, contacts_cumulative=0,
                            success_info=False, dwell_ticks_cumulative=0))
        full[0]["transitions"] = seq
        t["trials"][0].update(
            transitions=[seq[i] for i in q.sparse_indices(60)],
            sparse_transition_indices=q.sparse_indices(60),
            full_transition_count=60, full_transition_sha256=q.canonical_sha(seq),
            physics_steps=6000, option_steps=60, abstained=False,
            lateral_displacement=-.03, total_reward=0.)
        t["actual_transition_count"] += 59
        result = self.verify(t, full)
        self.assertEqual(result["worlds_safe_lateral_displacement_ge_25mm"], 0)

    def test_no_physics_abstain_cannot_move_object(self):
        t = copy.deepcopy(self.base_training)
        full = copy.deepcopy(self.base_full)
        full[0]["transitions"][0]["next_observation"][1] = .03
        t["trials"][0]["transitions"][0]["next_observation"][1] = .03
        t["trials"][0]["lateral_displacement"] = -.03
        t["trials"][0]["full_transition_sha256"] = q.canonical_sha(full[0]["transitions"])
        with self.assertRaisesRegex(AssertionError, "ZERO_PHYSICS_CANNOT_MOVE"):
            self.verify(t, full)

    def test_forged_contacts_are_not_physical_progress(self):
        t = copy.deepcopy(self.base_training)
        t["trials"][0]["contacts"] = 999
        with self.assertRaisesRegex(AssertionError, "FORGED_CONTACT_COUNT_NOT_BOUND"):
            self.verify(t)

    def test_goal_success_cannot_be_claimed_without_dwell_and_contact(self):
        t = copy.deepcopy(self.base_training)
        full = copy.deepcopy(self.base_full)
        row = t["trials"][0]
        event = full[0]["transitions"][0]
        event.update(action=0, success_info=True)
        row.update(physics_steps=100, success=True, abstained=False,
                   full_transition_sha256=q.canonical_sha(full[0]["transitions"]),
                   transitions=copy.deepcopy(full[0]["transitions"]))
        with self.assertRaisesRegex(AssertionError, "UNPHYSICAL_DWELL_OR_CONTACT_SUCCESS"):
            self.verify(t, full)

    def test_no_dev_or_heldout_artifacts_allowed(self):
        (self.root / "dev.json").write_text("{}", encoding="utf8")
        try:
            with self.assertRaisesRegex(AssertionError, "HELDOUT_OR_DEVELOPMENT"):
                self.verify()
        finally:
            (self.root / "dev.json").unlink()


if __name__ == "__main__":
    unittest.main()
