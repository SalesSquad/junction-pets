"""V10 synthetic guard tests; real physics belongs to SHA-pinned CRACI archive."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("v10_contract_under_test", ROOT / "run.py")
assert SPEC is not None and SPEC.loader is not None
v10 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v10)


def obs():
    value = np.zeros(18, dtype=float)
    value[9] = 1
    value[7] = .1
    value[16] = .05
    return value


class SourceAndSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v9 = v10.load_frozen_v9()
        cls.v8 = cls.v9.checked_v8_trainer()

    def test_hardcoded_v8_literal_run_id_and_hashes(self):
        self.assertEqual(v10.V8_RUN_ID, "craci.43645486985.1.0627c4e23e4a1296")
        self.assertEqual(v10.V8_PINS["full_transitions.jsonl.gz"],
                         "cbaeacd5a7a2a46a30e6b63afeb12614552da032b68e78a6a90fa7d75c49101a")

    def test_self_hashed_fake_craci_receipt_cannot_become_authority(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "restored").mkdir()
            (root / "retained").mkdir()
            zip_path = root / "synthetic.zip"
            zip_path.write_bytes(b"self-consistent but fake")
            with self.assertRaisesRegex(ValueError, "V10_V8_IMMUTABLE_EXTERNAL_CRACI"):
                v10.verify_immutable_v8(root / "restored", root / "retained",
                                        zip_path, self.v9, self.v8)

    def test_public_policy_uses_only_original_seven_mask(self):
        for only in range(7):
            allowed = np.zeros(7, dtype=int)
            allowed[only] = 1
            agent = v10.FrozenV10LegalPolicy(np.zeros((4, 41, 7)), self.v8.PublicMemory())
            self.assertEqual(agent(obs(), allowed), only)

    def test_policy_deterministic_new_episode_and_no_hidden_args(self):
        legal = np.array([1, 1, 1, 1, 1, 1, 1])
        factory = lambda: v10.FrozenV10LegalPolicy(
            np.arange(4 * 41 * 7).reshape(4, 41, 7).astype(float), self.v8.PublicMemory())
        self.assertEqual(factory()(obs(), legal), factory()(obs(), legal))
        with self.assertRaises(TypeError):
            factory()(obs(), legal, seed=515000)

    def test_mask_float_or_empty_never_bypasses_shield(self):
        agent = v10.FrozenV10LegalPolicy(np.ones((4, 41, 7)), self.v8.PublicMemory())
        with self.assertRaisesRegex(ValueError, "V8_PUBLIC_18D_7MASK_ABI"):
            agent(obs(), np.ones(7, dtype=float))
        with self.assertRaisesRegex(ValueError, "V8_PUBLIC_18D_7MASK_ABI"):
            agent(obs(), np.zeros(7, dtype=int))
        with self.assertRaisesRegex(ValueError, "V8_PUBLIC_18D_7MASK_ABI"):
            agent(np.zeros(17), np.ones(7, dtype=int))

    def test_factory_rejects_any_unpinned_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "candidate-weights.json"
            fake.write_text('{"schema":"pretend","weights":[]}')
            with self.assertRaisesRegex(ValueError, "V10_POLICY_UNREVIEWED_OR_EDITED_WEIGHTS"):
                v10.policy_factory(fake)

    def test_actual_checkpoint_if_checked_into_repo(self):
        path = ROOT / "checkpoints" / "candidate-weights.json"
        if not path.is_file():
            self.skipTest("the generated model is uploaded in GitHub PR, absent in scratch")
        factory = v10.policy_factory(path)
        mask = np.array([0, 0, 0, 0, 1, 0, 0], dtype=int)
        self.assertEqual(factory()(obs(), mask), 4)


class WorldDisjointLearning(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v8 = v10.load_frozen_v9().checked_v8_trainer()

    def test_preregistered_fresh_515000_not_v9_514000(self):
        self.assertEqual(v10.NEXT_TRAIN_FIRST_SEED, 515000)
        self.assertEqual(v10.NEXT_TRAIN_LAST_SELECTION_SEED, 515511)
        self.assertEqual(len(v10.NEXT_COMPARATORS) * (v10.NEXT_NEAR + v10.NEXT_CLEAR), 800)

    def test_exactly_two_of_nine_fresh_goal_worlds_are_held(self):
        v8_goals = [513011, 513035, 513158, 513175, 513180, 513243,
                    513278, 513295, 513306]
        v7_goals = [512109, 512257]
        teacher_worlds = set(range(512000, 512074)) | set(range(513000, 513160))
        teacher_worlds.update(v8_goals)
        teacher_worlds.update(v7_goals)
        splits = v10.choose_world_splits(teacher_worlds, v8_goals, v7_goals)
        self.assertEqual(len(splits["fresh_goal_held_train_worlds"]), 2)
        self.assertEqual(len(splits["fresh_goal_train_fit_worlds"]), 7)
        self.assertTrue(set(v7_goals).issubset(splits["fit"]))
        self.assertTrue(set(splits["fit"]).isdisjoint(splits["held_train_diagnostic"]))
        self.assertTrue(set(splits["fit"]).isdisjoint(splits["inner_train_validation"]))

    def test_no_caller_added_tenth_goal_witness(self):
        with self.assertRaisesRegex(ValueError, "QUALIFIED_SAFE_GOAL_WITNESS"):
            v10.choose_world_splits(range(512000, 513500), range(513000, 513010),
                                    [512109, 512257])

    def test_goal_label_selects_only_actual_observed_teacher(self):
        rows = {(513011, "frozen_v5"): {"seed": 513011, "strategy": "frozen_v5",
                                              "observed_corridor": True},
                (513011, "v8_hierarchical"): {"seed": 513011,
                                                 "strategy": "v8_hierarchical",
                                                 "observed_corridor": True}}
        graph = {"safe": True, "safe_goal_dwell_any_path": True,
                 "any_signed_lateral25": False, "lateral25_after_contact": False,
                 "reopen_after_lateral25": False}
        graphs = {(513011, "frozen_v5"): graph,
                  (513011, "v8_hierarchical"): dict(graph, safe_goal_dwell_any_path=False)}
        selected = v10.select_teacher_rows(rows, graphs, {513011})
        self.assertEqual(set(selected), {(513011, "frozen_v5")})
        self.assertTrue(selected[513011, "frozen_v5"]["paired_v8_goal_loss"])

    def test_kl_softmax_gradient_vs_prior_on_world_disjoint_train(self):
        prior = np.zeros((41, 7), dtype=float)
        train, held = [], []
        for seed in range(100, 116):
            for _ in range(4):
                features = np.zeros(41, dtype=float)
                features[0] = 1
                sample = (seed, 3, features, np.ones(7, dtype=bool), 2, 1.0)
                (train if seed < 112 else held).append(sample)
        candidate, info = v10.train_kl_anchored_head(train, [], held,
                                                     prior, 3, self.v8)
        self.assertTrue(info["fit_improved"])
        self.assertTrue(info["held_train_improved"])
        self.assertTrue(np.linalg.norm(candidate - prior) > 0)


if __name__ == "__main__":
    unittest.main()
