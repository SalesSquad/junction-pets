"""V4 swept-lane policy and sealed-source contract, not physics qualification."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from safety_controller import SweptLaneController  # noqa: E402

# safety_controller loads the frozen sibling v3 directory, which also contains
# run.py. Bind this test to V4's file explicitly; never risk testing v3 again.
_spec = importlib.util.spec_from_file_location(
    "rokoko_mujoco_safe_v4_run", Path(__file__).with_name("run.py"))
if _spec is None or _spec.loader is None:
    raise ImportError("V4 run.py missing")
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)


def observation(obj_x=0., obj_y=0., pusher_x=-.06,
                obstacle_x=.09, obstacle_y=.15):
    o = np.zeros(18, dtype=np.float32)
    o[:2] = [obj_x, obj_y]
    o[2:4] = [pusher_x, obj_y]
    o[6:8] = [obstacle_x, obstacle_y]
    o[9] = .99
    o[10:12] = 1
    return o


class SweptLaneContract(unittest.TestCase):
    def test_clear_world_preserves_medium_push(self):
        c = SweptLaneController()
        self.assertEqual(c(observation(obstacle_y=.15), np.ones(7, bool)), 2)
        self.assertEqual(c.phase, "normal")

    def test_threat_steers_early_left_before_corridor(self):
        c = SweptLaneController()
        self.assertEqual(c(observation(obstacle_y=.065), np.ones(7, bool)), 3)
        self.assertEqual(c.phase, "early_lane_setup")

    def test_negative_mover_steers_away_to_positive_lane(self):
        c = SweptLaneController()
        self.assertEqual(c(observation(obstacle_y=-.065), np.ones(7, bool)), 4)

    def test_late_centerline_entry_abstains(self):
        c = SweptLaneController()
        self.assertEqual(c(observation(obj_x=.081, obstacle_y=.065),
                           np.ones(7, bool)), 6)
        self.assertEqual(c.phase, "crossing_swept_corridor")
        self.assertEqual(c.risk_abstentions, 1)

    def test_negative_lane_uses_guarded_forward(self):
        c = SweptLaneController()
        self.assertEqual(c(observation(obj_x=.081, obj_y=-.04,
                                       obstacle_y=.065), np.ones(7, bool)), 2)
        self.assertEqual(c.phase, "crossing_swept_corridor")

    def test_pusher_clearance_extends_after_object_exit(self):
        c = SweptLaneController()
        self.assertEqual(c(observation(obj_x=.145, obj_y=-.04, pusher_x=.09,
                                       obstacle_y=.065), np.ones(7, bool)), 2)
        self.assertEqual(c.phase, "pusher_clearance")

    def test_threat_latch_survives_oscillation(self):
        c = SweptLaneController()
        c(observation(obstacle_y=.065), np.ones(7, bool))
        self.assertEqual(c(observation(obj_x=.08, obstacle_y=.15),
                           np.ones(7, bool)), 6)
        self.assertTrue(c.threat_latched)

    def test_deadman_and_shield_remain_absolute(self):
        c = SweptLaneController()
        mask = np.array([False] * 6 + [True])
        self.assertEqual(c(observation(obstacle_y=.065), mask), 6)
        self.assertEqual(c.phase, "deadman_or_shielded")

    def test_input_ABI_and_mask_nonmutation(self):
        c = SweptLaneController()
        with self.assertRaisesRegex(ValueError, "ABI"):
            c(np.zeros(17), np.ones(7, bool))
        mask = np.ones(7, bool)
        before = mask.copy()
        c(observation(obstacle_y=.065), mask)
        np.testing.assert_array_equal(mask, before)

    def test_swept_uncertainty_is_wider_than_frozen_v3(self):
        c = SweptLaneController()
        from risk_controller import RiskAwareController
        old = RiskAwareController()
        o = observation(obj_x=.045, obj_y=-.03, obstacle_y=.055)
        c._observe(o)
        old._observe(o)
        self.assertLessEqual(c._clearance(o, 2), old._clearance(o, 2))

    def test_swept_horizon_covers_real_ten_tick_servo_motion(self):
        # The public MuJoCo servo target can move up to .002 m per tick,
        # ten ticks per option. V3's .011 m prediction missed this geometry.
        from risk_controller import RiskAwareController
        o = observation(obj_x=0., obj_y=0., obstacle_x=.023, obstacle_y=0.)
        robust = SweptLaneController()
        old = RiskAwareController()
        robust._observe(o)
        old._observe(o)
        self.assertLess(robust._clearance(o, 2), .003)
        self.assertGreater(old._clearance(o, 2), .010)

    def test_dev_and_exposed_cal_windows_blocked(self):
        with self.assertRaisesRegex(ValueError, "FRESH dev seed offset"):
            run.main(["--split", "dev", "--episodes", "8",
                      "--output", "/tmp/unused-v4-dev.json"])
        with self.assertRaisesRegex(ValueError, "prior v4 30..99 batch exposed"):
            run.main(["--split", "dev", "--seed-offset", "30",
                      "--episodes", "70", "--output", "/tmp/unused-v4-old-dev.json"])
        with self.assertRaisesRegex(ValueError, "independent calibration offset"):
            run.main(["--split", "cal", "--episodes", "8",
                      "--output", "/tmp/unused-v4-cal.json"])

    def test_sealed_physics_holdout_still_requires_explicit_authorization(self):
        with self.assertRaises(PermissionError):
            run.source_identity(False, None, True)
        with self.assertRaises(PermissionError):
            run.main(["--split", "test", "--episodes", "1",
                      "--output", "/tmp/unused-v4-sealed.json"])

    def test_candidate_unsafe_always_blocks_science_promotion(self):
        good = dict(delta_success_percentage_points=25.,
                    paired_bootstrap95_pp=[10., 40.],
                    constant_unsafe=0, candidate_unsafe=0)
        self.assertTrue(run.v3.v2.qualification(good)["scientifically_qualifies"])
        self.assertFalse(run.v3.v2.qualification({**good,
                          "candidate_unsafe": 1})["scientifically_qualifies"])

    def test_post_step_forensics_never_needed_for_controller(self):
        self.assertEqual(run.post_step_unsafe_diagnostic(None, {"unsafe": False}),
                         {"unsafe": False, "post_step_obstacle_pair": False,
                          "post_step_bounds": False})

    def test_first_option_abstain_is_zero_physics_scored_failure(self):
        env = SimpleNamespace(
            done=True, abstained=True, unsafe=False, steps=1, physics_steps=0,
            last=6, data=SimpleNamespace(xpos=np.array([[0., 0., .021]])), obj=0)
        err = AssertionError("safe_v4 failed real MuJoCo physics-step gate on world 129100")
        with mock.patch.object(run.v3.v2, "episode", side_effect=err):
            with mock.patch.object(run.v3.v2.v1, "_world_signature",
                                   return_value="matching-latent-world"):
                row = run.episode_with_explicit_safe_abort(
                    env, 129100, False, "safe_v4", lambda: None)
        self.assertEqual(row["world_hash"], "matching-latent-world")
        self.assertEqual(row["physics_steps"], 0)
        self.assertEqual(row["option_steps"], 1)
        self.assertEqual(row["proposal_counts"], {"ABSTAIN": 1})
        self.assertTrue(row["zero_physics_abstain"])
        self.assertTrue(row["abstained"])
        self.assertFalse(row["success"])
        self.assertFalse(row["unsafe"])

    def test_zero_step_exception_rejected_for_other_arms_or_not_first(self):
        env = SimpleNamespace(
            done=True, abstained=True, unsafe=False, steps=1, physics_steps=0,
            last=6, data=SimpleNamespace(xpos=np.array([[0., 0., .021]])), obj=0)
        with mock.patch.object(run.v3.v2, "episode",
                               side_effect=AssertionError(
                                   "constant failed real MuJoCo physics-step gate on world 129100")):
            with self.assertRaises(AssertionError):
                run.episode_with_explicit_safe_abort(
                    env, 129100, False, "constant", lambda: None)
        env.steps = 2
        with mock.patch.object(run.v3.v2, "episode",
                               side_effect=AssertionError(
                                   "safe_v4 failed real MuJoCo physics-step gate on world 129100")):
            with self.assertRaises(AssertionError):
                run.episode_with_explicit_safe_abort(
                    env, 129100, False, "safe_v4", lambda: None)

    def test_unexpected_physics_assertions_still_fail_closed(self):
        env = SimpleNamespace(
            done=True, abstained=True, unsafe=False, steps=1, physics_steps=0,
            last=6, data=SimpleNamespace(xpos=np.array([[0., 0., .021]])), obj=0)
        with mock.patch.object(run.v3.v2, "episode",
                               side_effect=AssertionError("SOURCE_WORLD_MISMATCH")):
            with self.assertRaisesRegex(AssertionError, "SOURCE_WORLD_MISMATCH"):
                run.episode_with_explicit_safe_abort(
                    env, 129100, False, "safe_v4", lambda: None)

    @unittest.skipUnless(importlib.util.find_spec("mujoco"),
                         "Actual MuJoCo CPU dynamics are mandatory on CRACI")
    def test_one_new_dev_world_actual_physics(self):
        from physics import MovingContactEnv
        env = MovingContactEnv(max_options=1)
        env.reset(seed=129030)
        act = SweptLaneController()(env.observation(), env.mask())
        _, _, _, info = env.step(act)
        self.assertGreater(info["physics_steps"], 0)


if __name__ == "__main__":
    unittest.main()
