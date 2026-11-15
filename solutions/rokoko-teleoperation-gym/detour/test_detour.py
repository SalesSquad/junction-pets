import inspect
import unittest
import numpy as np
import planner
from env import DetourEnv
from evaluate import run


def observation(y=0.):
    return np.array([0., 0., -.06, 0., 0., 0., .09, y, 0., .99,
                     1., 1., 1., 0., 0., 0., .16, 0.])


class Tests(unittest.TestCase):
    def test_straight_blocked_lateral_allowed(self):
        o = observation()
        self.assertFalse(planner.clear(o[:2], o[16:18], o[6:8], .020))
        self.assertTrue(planner.mask(o)[0])
        self.assertGreater(len(planner.routes(o)), 0)

    def test_offset_not_global(self):
        self.assertTrue(planner.mask(observation(.065))[:5].any())

    def test_routes_clear(self):
        o = observation()
        for path in planner.routes(o):
            self.assertLessEqual(len(path)-1, 3)
            for a, b in zip([o[:2], *path], path):
                self.assertTrue(planner.clear(a, b, o[6:8], .020))

    def test_uncertainty_negative(self):
        # Starting inside inflated obstacle is unknown/unsafe for either sign.
        for shift in (-3*planner.SIGMA, 3*planner.SIGMA):
            o = observation(); o[6:8] = [shift, 0.]
            self.assertFalse(planner.mask(o)[:6].any())
        o = observation(); o[6] = np.nan
        self.assertFalse(planner.mask(o)[:6].any())

    def test_deadman_and_hold(self):
        for live, held in ((False, False), (True, True)):
            env = DetourEnv(); env.reset(150000, True)
            env.release = 0 if not live else -1
            env.held = held
            env.help = 0
            env.live = live
            target = env.target.copy()
            env.step(2)
            np.testing.assert_array_equal(env.target, target)

    def test_no_hidden_inputs(self):
        source = inspect.getsource(planner)
        for name in ('mujoco', 'body_mass', 'geom_friction', 'qpos', 'contactForce'):
            self.assertNotIn(name, source)

    def test_native_contact_and_replay(self):
        first = run(150001, 'detour')
        self.assertGreater(first['physics_steps'], 0)
        self.assertGreater(first['contacts'], 0)
        self.assertEqual(first, run(150001, 'detour'))


if __name__ == '__main__':
    unittest.main()
