"""Decisive small MuJoCo campaign correctness tests, not a blanket full-suite."""
import math
import unittest

# The real runner is a script named experiment.py that imports the older M3
# experiment.py by basename. Load it with a distinct test-only module name
# so the two modules are not mistaken for one partially initialized module.
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location("rokoko_mega_runner", Path(__file__).with_name("experiment.py"))
runner_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner_module)
Runner = runner_module.Runner
scenario = runner_module.scenario
feedback_target = runner_module.feedback_target
interpolate_progress = runner_module.interpolate_progress
distance_segment_to_point = runner_module.distance_segment_to_point
FRAGILITY_IMPULSE_NS = runner_module.FRAGILITY_IMPULSE_NS


class MegaSimTests(unittest.TestCase):
    def test_model_reuse_is_deterministic_without_hidden_state_leak(self):
        r = Runner()
        a = r.run(100, 345600, "nominal", "contact_feedback", [0.0, 0.5, 1.0])
        # In between, change mass, friction, pose and obstacle through a different regime.
        _ = r.run(101, 345601, "adversarial", "guarded_feedback", [0, 0.5, 1])
        b = r.run(100, 345600, "nominal", "contact_feedback", [0.0, 0.5, 1.0])
        self.assertEqual(a, b)
        self.assertGreater(a["pusher_object_contact_steps"], 0)
        self.assertEqual(a["unsafe_deadman_target_updates"], 0)

    def test_safe_abstain_does_not_create_robot_contact(self):
        r = Runner()
        for idx, regime in enumerate(("nominal", "adversarial", "sensor_dropout")):
            x = r.run(idx, 446610 + idx, regime, "safe_abstain", [0, .5, 1])
            self.assertEqual(x["pusher_object_contact_steps"], 0)
            self.assertEqual(x["synthetic_human_requests"], 0)
            self.assertEqual(x["unsafe_deadman_target_updates"], 0)
            self.assertEqual(x["safe_success"], 0)
            self.assertEqual(x["abstained"], 1)

    def test_observation_only_guard_and_contact_geometry(self):
        obs = {"object": (0.02, 0.0), "mapped_obstacle_y": 0.0}
        pusher = (-0.06, 0.0)
        target, stop = feedback_target(obs, pusher, guarded=True)
        self.assertTrue(stop)
        self.assertEqual(target, pusher)
        _, stop2 = feedback_target(obs, pusher, guarded=False)
        self.assertFalse(stop2)
        self.assertAlmostEqual(FRAGILITY_IMPULSE_NS, 0.006)
        self.assertLess(distance_segment_to_point((0, 0), (.16, 0), (.09, 0)), .043)
        self.assertEqual(interpolate_progress([0, .5, 1], 1), 1)

    def test_pairing_world_is_policy_independent(self):
        seed = 800017
        for regime in ("nominal", "lateral_shift", "friction_mass",
                       "sensor_dropout", "adversarial"):
            self.assertEqual(scenario(seed, regime), scenario(seed, regime))
        x = scenario(seed, "adversarial")
        self.assertTrue(math.isfinite(x["friction"]))
        self.assertIn(x["deadman_release"], (-1, 150, 190))


if __name__ == "__main__":
    unittest.main()
