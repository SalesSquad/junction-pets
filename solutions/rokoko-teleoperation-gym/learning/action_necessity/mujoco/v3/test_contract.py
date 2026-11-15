"""Risk controller fixtures from observed positions, not sealed-world outcomes."""
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from risk_controller import RiskAwareController
import run


def obs(obj_x=0., obj_y=0., obstacle_x=.09, obstacle_y=.15):
    o = np.zeros(18, dtype=np.float32)
    o[:2] = [obj_x, obj_y]
    o[2:4] = [-.06, 0]
    o[6:8] = [obstacle_x, obstacle_y]
    o[9] = .99
    o[10:12] = 1
    return o


class RiskContract(unittest.TestCase):
    def test_medium_matches_baseline_when_clear(self):
        m = np.ones(7, dtype=bool)
        self.assertEqual(RiskAwareController()(obs(), m), 2)

    def test_model_veto_when_object_would_hit_obstacle(self):
        m = np.ones(7, dtype=bool)
        c = RiskAwareController()
        action = c(obs(obj_x=.071, obstacle_y=.035), m)
        self.assertEqual(action, 0)
        self.assertGreater(c.would_collide_rejections, 0)

    def test_side_approach_only_when_medium_and_slow_masked(self):
        c = RiskAwareController()
        m = np.array([True, False, False, True, True, True, True])
        self.assertEqual(c(obs(obstacle_y=.02), m), 3)
        self.assertEqual(RiskAwareController()(obs(obstacle_y=-.02), m), 4)

    def test_unsafe_side_path_waits_at_close_clearance(self):
        c = RiskAwareController()
        m = np.array([True, False, False, True, True, True, True])
        self.assertEqual(c(obs(obj_x=.068, obstacle_y=.035), m), 0)

    def test_never_reverses_side_after_medium_interval(self):
        c = RiskAwareController()
        blocked = np.array([True, False, False, True, True, True, True])
        self.assertEqual(c(obs(obstacle_y=.02), blocked), 3)
        self.assertEqual(c(obs(obstacle_y=.15), np.ones(7, dtype=bool)), 2)
        right_only = np.array([True, False, False, False, True, True, True])
        self.assertEqual(c(obs(obstacle_y=-.15), right_only), 0)

    def test_deadman_absolute_stop(self):
        m = np.array([False, False, False, False, False, False, True])
        self.assertEqual(RiskAwareController()(obs(), m), 6)

    def test_fresh_dev_only_enforced(self):
        with self.assertRaisesRegex(ValueError, "FRESH 129010"):
            run.main(["--split", "dev", "--episodes", "8",
                      "--output", "/tmp/unused-v3-locked.json"])

    def test_sealed_holdout_exact_pin_required(self):
        with self.assertRaises(PermissionError):
            run.source_identity(False, None, True)
        with self.assertRaises(PermissionError):
            run.source_identity(True, None, True)

    def test_independent_scientific_gate_same_as_v2(self):
        baseline = dict(delta_success_percentage_points=25.,
                        paired_bootstrap95_pp=[12.5, 50.],
                        constant_unsafe=0, candidate_unsafe=0)
        self.assertTrue(run.v2.qualification(baseline)["scientifically_qualifies"])
        self.assertFalse(run.v2.qualification({**baseline,
            "candidate_unsafe": 1})["scientifically_qualifies"])

    @unittest.skipUnless(importlib.util.find_spec("mujoco"),
                         "Real MuJoCo must run on CRACI CPU host")
    def test_physics_dev_smoke(self):
        from physics import MovingContactEnv
        env = MovingContactEnv(max_options=2)
        env.reset(129010)
        action = RiskAwareController()(env.observation(), env.mask())
        _, _, _, info = env.step(action)
        self.assertGreater(info["physics_steps"], 0)


if __name__ == "__main__":
    unittest.main()
