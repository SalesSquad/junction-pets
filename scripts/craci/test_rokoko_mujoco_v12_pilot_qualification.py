"""Synthetic-only V12 pilot protocol/early-stop tests, never physics evidence."""
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
    "v12_pilot_wrapper_synthetic_contract",
    HERE / "rokoko-mujoco-v12-pilot-qualification.py")
v12 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v12)


def checksum(seed):
    return hashlib.sha256(str(seed).encode()).hexdigest()


class FakePublicPhysics:
    def __init__(self, max_options=60):
        self.max_options = max_options

    def reset(self, seed, ood):
        self.seed = seed
        obs = [0.] * 18
        obs[7] = .1 if seed - 518000 < 40 else .3
        return obs

    @staticmethod
    def mask(obs):
        return [1, 1, 1, 1, 1, 1, 1]


class FakeProtocol:
    @staticmethod
    def derive_cohort(scans, plan, stage):
        if stage != "pilot":
            raise ValueError("only fake pilot")
        return [
            {"seed": w["seed"], "world_hash": w["world_hash"],
             "initial_public_obstacle_y": w["observation"][7],
             "initial_mask": w["mask"],
             "observed_corridor": i < 40}
            for i, w in enumerate(scans[:48])
        ]


class FakeV8:
    MAX_OPTIONS = 60

    def __init__(self, candidate_success):
        self.arms_executed = []
        self.candidate_success = candidate_success

    def run_real_episode(self, env, seed, arm, factory, signature, deadline, v7):
        obs = env.reset(seed=seed, ood=False)
        self.arms_executed.append((seed, arm))
        success = arm == v12.ARMS[0] or (
            arm == v12.ARMS[1] and self.candidate_success)
        after = obs.copy()
        trace = [{"observation": obs, "mask": env.mask(obs),
                  "action": 0, "next_observation": after, "reward": 1.,
                  "cost": 0, "done": True, "contacts_cumulative": 1,
                  "success_info": success, "dwell_ticks_current": 250 if success else 0,
                  "dwell_ticks_cumulative": 250 if success else 0}]
        row = {"seed": seed, "strategy": arm, "world_hash": checksum(seed),
               "success": success, "unsafe": False, "abstained": False,
               "full_transition_count": 1, "option_steps": 1,
               "full_transition_sha256": v12.digest(trace),
               "transitions": trace, "physics_steps": 100,
               "contacts": 1, "final_error": .01}
        return row, trace


class V12PilotSourceOnlyTests(unittest.TestCase):
    def test_source_pilot_limits_and_public_three_arms(self):
        self.assertEqual(v12.FIRST, 518000)
        self.assertEqual(v12.SCAN, 512)
        self.assertEqual(v12.EXPECTED, 144)
        self.assertEqual(v12.ARMS, (
            "frozen_v5", "v12_phase_dwell_supported_actions",
            "v12_right_side_action4_exploration_train_only"))

    def test_public_scan_uses_all_512_no_privileged_reward(self):
        scans = v12.scan_real_public_starts(FakePublicPhysics(),
                                            lambda env: checksum(env.seed))
        self.assertEqual(len(scans), 512)
        self.assertEqual(scans[0]["seed"], 518000)
        self.assertEqual(scans[-1]["seed"], 518511)
        self.assertEqual(len(scans[0]["observation"]), 18)
        self.assertEqual(len(scans[0]["mask"]), 7)
        self.assertNotIn("reward", scans[0])

    def test_adversarial_forged_600000_seed_cohort_rejected(self):
        scans = v12.scan_real_public_starts(FakePublicPhysics(),
                                            lambda env: checksum(env.seed))
        cohort = FakeProtocol.derive_cohort(scans, {}, "pilot")
        self.assertTrue(v12.independent_first_public_cohort(scans, cohort))
        cohort[0]["seed"] = 600000
        with self.assertRaisesRegex(AssertionError, "CANNOT_BE_FORGED"):
            v12.independent_first_public_cohort(scans, cohort)

    def test_truncated_or_malformed_public_512_scan_fails_closed(self):
        scans = v12.scan_real_public_starts(FakePublicPhysics(),
                                            lambda env: checksum(env.seed))
        cohort = FakeProtocol.derive_cohort(scans, {}, "pilot")
        with self.assertRaisesRegex(AssertionError, "CANONICAL_518000"):
            v12.independent_first_public_cohort(scans[:-1], cohort)
        scans[0]["mask"] = [1] * 6
        with self.assertRaisesRegex(AssertionError, "PUBLIC_18D_7MASK"):
            v12.independent_first_public_cohort(scans, cohort)

    def test_v5_safe_goal_regression_stops_before_right4_and_preserves_two_real_rows(self):
        with tempfile.TemporaryDirectory() as base:
            original = Path(base) / "private-originals"
            fake = FakeV8(candidate_success=False)
            result = v12.run_pilot_originals(
                Path(base), original, None, {}, None,
                FakeProtocol, {name: object for name in v12.ARMS},
                fake, None, FakePublicPhysics,
                lambda env: checksum(env.seed), "a" * 40)
            self.assertFalse(result["complete"])
            self.assertEqual(result["reason"], "CANDIDATE_LOST_ACTUAL_FROZEN_V5_GOAL")
            self.assertEqual(result["completed_episodes"], 2)
            self.assertEqual(fake.arms_executed, [
                (518000, v12.ARMS[0]), (518000, v12.ARMS[1])])
            stop = json.loads((original / "early_stop.json").read_text())
            self.assertEqual(stop["status"], "INCOMPLETE_STOP")
            self.assertEqual(stop["expected_episodes"], 144)
            self.assertEqual(stop["completed_episodes"], 2)
            self.assertFalse(stop["promotion_authorized"])
            with gzip.open(original / "full_transitions.jsonl.gz", "rt") as source:
                lines = [json.loads(line) for line in source]
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[1]["strategy"], v12.ARMS[1])
            self.assertEqual(v12.sha(original / "full_transitions.jsonl.gz"),
                             stop["raw_sha256"]["full_transitions.jsonl.gz"])
            self.assertFalse((original / "training.json").exists())
            self.assertFalse((original / "manifest.json").exists())

    def test_safe_goal_cannot_be_credited_for_forward_proxy(self):
        self.assertFalse(v12.safe_goal({
            "success": False, "unsafe": False, "abstained": False,
            "forward_reopened_after_side": 12}))
        self.assertFalse(v12.safe_goal({
            "success": True, "unsafe": True, "abstained": False}))

    def test_real_physics_replay_fails_on_missing_144_stream(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with gzip.open(root / "full_transitions.jsonl.gz", "wt") as source:
                source.write("")
            training = {"all_512_public_initial_scans": [
                {"seed": 518000 + i, "world_hash": checksum(518000 + i),
                 "observation": [0.] * 18, "mask": [1] * 7}
                for i in range(512)], "actual_option_transitions": 0,
                "observed_exploration_action4_instances": [],
                "observed_exploration_action4_executions": 0}
            with self.assertRaisesRegex(AssertionError, "ALL512_INITIAL"):
                v12.independent_true_physics_replay(
                    root, training, {}, {}, None,
                    FakePublicPhysics, lambda env: checksum(env.seed))


if __name__ == "__main__":
    unittest.main()
