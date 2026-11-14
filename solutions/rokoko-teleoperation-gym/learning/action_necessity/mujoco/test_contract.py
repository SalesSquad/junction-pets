"""Fast source/ABI tests; optional real MuJoCo dev-only smoke test."""
import importlib.util
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
import run


class FixedContract(unittest.TestCase):
    def test_seed_groups_disjoint_and_fresh(self):
        groups = list(run.SEED_BANDS.items())
        for a, (low, high) in groups:
            self.assertLess(low, high)
            self.assertGreaterEqual(low, 120000)
            self.assertLess(high, 520000)
            for b, (other_low, other_high) in groups:
                if a != b:
                    self.assertTrue(high < other_low or other_high < low)
        self.assertGreaterEqual(run.SEED_BANDS["test"][0], 329000)
        self.assertGreaterEqual(run.SEED_BANDS["ood"][0], 429000)

    def test_scene_mocap_and_physics_controls(self):
        root = ET.parse(DIR / "moving_scene.xml").getroot()
        mover = root.find("./worldbody/body[@name='moving_obstacle']")
        self.assertIsNotNone(mover)
        self.assertEqual(mover.attrib["mocap"], "true")
        self.assertIsNotNone(mover.find("geom[@name='obstacle']"))
        self.assertEqual(root.find("option").attrib["timestep"], "0.002")
        controls = root.findall("./actuator/position")
        self.assertEqual([x.attrib["joint"] for x in controls], ["px", "py"])
        self.assertIsNotNone(root.find("./worldbody/body[@name='object']/freejoint"))

    def test_holdout_default_closed(self):
        args = run.parse_args(["--split", "test", "--output", "/tmp/unused.json"])
        self.assertFalse(args.permit_holdout)
        self.assertIsNone(args.expected_head)
        self.assertEqual(args.split, "test")

    def test_descriptive_paired_statistics(self):
        pairs = [dict(constant=dict(success=False, unsafe=False, physics_steps=100),
                      teacher=dict(success=True, unsafe=False, physics_steps=300,
                                   distinct_proposals=2)),
                 dict(constant=dict(success=True, unsafe=False, physics_steps=100),
                      teacher=dict(success=False, unsafe=True, physics_steps=200,
                                   distinct_proposals=1))]
        s = run.summarize(pairs, "teacher")
        self.assertEqual(s["candidate_success"], 1)
        self.assertEqual(s["constant_success"], 1)
        self.assertEqual(s["candidate_unsafe"], 1)
        self.assertEqual(s["delta_success_percentage_points"], 0)
        self.assertEqual(s["candidate_multi_action_episodes"], 1)

    @unittest.skipUnless(importlib.util.find_spec("mujoco"),
                         "MuJoCo unavailable locally; real-physics smoke must run on CPU host")
    def test_real_physics_dev_seed(self):
        from physics import MovingContactEnv
        env = MovingContactEnv(max_options=2)
        observation = env.reset(129000)
        self.assertEqual(observation.shape, (18,))
        before = float(env.data.time)
        _, _, done, info = env.step(0)
        self.assertGreater(info["physics_steps"], 0)
        self.assertGreater(float(env.data.time), before)
        self.assertLessEqual(info["physics_steps"], 100)
        self.assertIsInstance(done, bool)


if __name__ == "__main__":
    unittest.main()
