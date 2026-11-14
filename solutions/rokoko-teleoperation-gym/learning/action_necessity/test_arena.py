"""Contract tests; these never execute or tune sealed test/OOD seeds."""

import unittest
from dataclasses import replace

from arena import (ABORT, FWD, LEFT, REOBSERVE, Arena, RouteTeacher, SEEDS,
                   constant_forward, make_world, run_episode)
from run import evaluate, paired_bootstrap


class ActionNecessityContract(unittest.TestCase):
    def test_reserved_seed_boundaries(self):
        for split, start in SEEDS.items():
            self.assertEqual(make_world(split, start).seed, start)
            with self.assertRaises(ValueError):
                make_world(split, start-1)
            with self.assertRaises(ValueError):
                make_world(split, start+10000)

    def test_randomization_deterministic(self):
        a = make_world("dev", 120004)
        self.assertEqual(a, make_world("dev", 120004))
        self.assertNotEqual(a, make_world("dev", 120005))

    def test_policy_does_not_receive_friction_or_phase(self):
        obs = Arena(make_world("dev", 120000)).observe()
        self.assertFalse(hasattr(obs, "friction"))
        self.assertFalse(hasattr(obs, "moving_phase"))
        self.assertFalse(hasattr(obs, "seed"))

    def test_policies_share_same_world_and_shield(self):
        w = make_world("dev", 120013)
        t = run_episode(w, "teacher", RouteTeacher)
        n = run_episode(w, "constant", lambda: constant_forward)
        self.assertEqual(t["seed"], n["seed"])
        self.assertEqual(t["scenario"], n["scenario"])
        self.assertTrue(t["complete"] and n["complete"])

    def test_world_trajectory_changes_with_action(self):
        w = make_world("dev", 120001)
        a, b = Arena(w), Arena(w)
        a.step(FWD)
        b.step(LEFT)
        self.assertNotEqual((a.x, a.y), (b.x, b.y))

    def test_dropout_reobserve_cannot_fake_tracking(self):
        w = replace(make_world("dev", 120010), dropout_start=0, dropout_length=15)
        a = Arena(w)
        a.step(REOBSERVE)
        self.assertEqual(a.observe().quality, .4)
        self.assertEqual(a.reobservations, 1)

    def test_deadman_not_rearmed_by_teacher(self):
        w = replace(make_world("dev", 120010), deadman_release=0)
        obs = Arena(w).observe()
        self.assertFalse(obs.deadman)
        self.assertEqual(RouteTeacher()(obs), ABORT)

    def test_no_action_after_abort(self):
        a = Arena(make_world("dev", 120012))
        a.step(ABORT)
        self.assertTrue(a.done and a.aborted and not a.success)
        with self.assertRaises(RuntimeError):
            a.step(FWD)

    def test_invalid_policy_action(self):
        a = Arena(make_world("dev", 120012))
        for x in (-1, 8, 1.5, True):
            with self.assertRaises(ValueError):
                a.step(x)

    def test_paired_resampling_rejects_mismatched_worlds(self):
        with self.assertRaises(ValueError):
            paired_bootstrap([{"seed": 1, "success": True}], [{"seed": 2, "success": False}])

    def test_benchmark_smoke_is_descriptive(self):
        report = evaluate("dev", 4)
        self.assertEqual(report["worlds"], 4)
        self.assertEqual(report["teacher"]["episodes"], report["null"]["episodes"])
        self.assertFalse(report["action_necessity_demo"])


if __name__ == "__main__":
    unittest.main()
