"""Portable replay contract tests with a fake environment; real runs use MuJoCo."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

from test_rokoko_mujoco_v7_feasibility_qualification import make_fixture, persist


MODULE = Path(__file__).with_name("rokoko-mujoco-v7-positive-replay.py")
spec = importlib.util.spec_from_file_location("craci_v7_positive_replay", MODULE)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class FakeExactContactEnv:
    """Safety-negative deterministic stub; never masquerades as real physics."""
    def __init__(self):
        self.done = False
        self.steps = 0
        self.physics_steps = 0
        self.dwell = 0
        self.observation = None

    def reset(self, seed, ood=False):
        self.seed = seed
        self.done = False
        self.steps = self.physics_steps = self.dwell = 0
        self.observation = [0.] * 18
        self.observation[7] = .08 if seed < 512128 else .16
        return list(self.observation)

    def mask(self, observation):
        return [True] * 7

    def step(self, action):
        if action != 6:
            raise AssertionError("FAKE_ENV_HAS_NO_POSITIVE_ACTIONS")
        self.done = True
        self.steps = 1
        info = dict(success=False, unsafe=False, abstained=True, cost=0,
                    contacts=0, error=.1)
        return list(self.observation), -.01, True, info


class ReplayContracts(unittest.TestCase):
    @staticmethod
    def fake_policy_factory(_name):
        return lambda: lambda _obs, _mask: 6

    @staticmethod
    def fake_world_signature(env):
        return hashlib.sha256(str(env.seed).encode()).hexdigest()

    def test_empty_positive_claim_set_is_honest_negative(self):
        with tempfile.TemporaryDirectory(prefix="craci-v7-replay-") as directory:
            root = Path(directory)
            training, full = make_fixture(root)
            persist(root, training, full)
            result = replay.replay_positive(root, FakeExactContactEnv,
                                            self.fake_policy_factory,
                                            self.fake_world_signature)
            self.assertTrue(result["claim_verified"])
            self.assertEqual(result["selection_scan_replayed"], 160)
            self.assertEqual(result["fully_replayed_positive_train_trials"], 0)
            self.assertEqual(result["verified_near_corridor_success_worlds"], 0)

    def test_forged_positive_cannot_pass_independent_true_step_replay(self):
        with tempfile.TemporaryDirectory(prefix="craci-v7-replay-") as directory:
            root = Path(directory)
            training, full = make_fixture(root)
            # The producer text claims a success, but exact independent step
            # still returns a safe ABSTAIN, never goal/contact success.
            training["trials"][0]["success"] = True
            training["trials"][0]["abstained"] = False
            persist(root, training, full)
            with self.assertRaisesRegex(AssertionError, "REPLAY_|TERMINAL"):
                replay.replay_positive(root, FakeExactContactEnv,
                                       self.fake_policy_factory,
                                       self.fake_world_signature)

    def test_forged_lateral_displacement_cannot_pass_physics_replay(self):
        with tempfile.TemporaryDirectory(prefix="craci-v7-replay-") as directory:
            root = Path(directory)
            training, full = make_fixture(root)
            training["trials"][0]["lateral_displacement"] = .03
            persist(root, training, full)
            with self.assertRaisesRegex(AssertionError, "REPLAY_OBSTACLE_AWAY_PROGRESS"):
                replay.replay_positive(root, FakeExactContactEnv,
                                       self.fake_policy_factory,
                                       self.fake_world_signature)

    def test_forged_public_selection_scan_fails_recomputed_world(self):
        with tempfile.TemporaryDirectory(prefix="craci-v7-replay-") as directory:
            root = Path(directory)
            training, full = make_fixture(root)
            training["selection_scan"][0]["initial_observed_obstacle_y"] = .17
            persist(root, training, full)
            with self.assertRaisesRegex(AssertionError, "PREOUTCOME_WORLD_SELECTION"):
                replay.replay_positive(root, FakeExactContactEnv,
                                       self.fake_policy_factory,
                                       self.fake_world_signature)


if __name__ == "__main__":
    unittest.main()
