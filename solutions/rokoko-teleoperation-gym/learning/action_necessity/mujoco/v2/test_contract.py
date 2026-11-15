"""V2 safety/source contract + decision tests; real CPU smoke optional."""
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from controller import AdaptiveController
import run


def obs(obstacle_y=.10):
    x = np.zeros(18, dtype=np.float32)
    x[0] = 0
    x[2] = -.06
    x[6:8] = [.09, obstacle_y]
    x[9] = .99
    x[10] = 1
    x[11] = 1
    return x


class ControllerContract(unittest.TestCase):
    def test_medium_fallback_not_slow(self):
        m = np.ones(7, dtype=bool)
        c = AdaptiveController()
        self.assertEqual(c(obs(), m), 2)
        self.assertEqual(c(obs(), m), 2)

    def test_medium_proximity_veto_uses_slow(self):
        m = np.ones(7, dtype=bool)
        m[2] = False
        self.assertEqual(AdaptiveController()(obs(), m), 1)

    def test_only_blocked_path_uses_side(self):
        m = np.array([True, False, False, True, True, True, True])
        self.assertEqual(AdaptiveController()(obs(obstacle_y=.02), m), 3)
        self.assertEqual(AdaptiveController()(obs(obstacle_y=-.02), m), 4)

    def test_deadman_not_overridden(self):
        m = np.array([False, False, False, False, False, False, True])
        self.assertEqual(AdaptiveController()(obs(), m), 6)

    def test_near_goal_still_pushes_for_dwell(self):
        o = obs()
        o[:2] = [.151, 0]
        self.assertEqual(AdaptiveController()(o, np.ones(7, dtype=bool)), 2)

    def test_controller_resets_between_worlds(self):
        m = np.array([True, False, False, True, True, True, True])
        a = AdaptiveController()
        for _ in range(15):
            a(obs(.02), m)
        b = AdaptiveController()
        self.assertEqual(b(obs(.02), m), AdaptiveController()(obs(.02), m))
        self.assertEqual(b.decisions, 1)

    def test_scientific_gate_denies_negative_or_unsafe(self):
        base = dict(delta_success_percentage_points=12.5,
                    paired_bootstrap95_pp=[1.0, 40.0],
                    candidate_unsafe=0, constant_unsafe=0)
        self.assertTrue(run.qualification(base)["scientifically_qualifies"])
        self.assertFalse(run.qualification({**base,
            "delta_success_percentage_points": -12.5})["scientifically_qualifies"])
        self.assertFalse(run.qualification({**base,
            "candidate_unsafe": 1})["scientifically_qualifies"])
        self.assertFalse(run.qualification({**base,
            "paired_bootstrap95_pp": [0., 30.]})["scientifically_qualifies"])

    def test_holdout_requires_exact_pin(self):
        with self.assertRaises(PermissionError):
            run.source_identity(False, None, True)
        with self.assertRaises(PermissionError):
            run.source_identity(True, None, True)

    @unittest.skipUnless(importlib.util.find_spec("mujoco"),
                         "MuJoCo wheel unavailable; real physics needs CRACI CPU")
    def test_real_physics_dev_option(self):
        from physics import MovingContactEnv
        env = MovingContactEnv(max_options=2)
        env.reset(129008)
        option = AdaptiveController()(env.observation(), env.mask())
        _, _, _, info = env.step(option)
        self.assertGreater(info["physics_steps"], 0)
        self.assertGreater(float(env.data.time), 0)


if __name__ == "__main__":
    unittest.main()
