"""Synthetic contracts only. Actual V7 physics proof is the separate pinned run."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np


SOURCE = Path(__file__).resolve().parent / "run.py"
SPEC = importlib.util.spec_from_file_location("v9_tested_learning", SOURCE)
assert SPEC is not None and SPEC.loader is not None
v9 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v9)


def observation(y=0.0):
    v = [0.0] * 18
    v[1] = y
    v[7] = .10  # away direction is negative y
    v[9] = 1.0
    return v


def event(before, after, action=3, mask=None, contacts=1,
          dwell=0, success=False, done=False):
    return {"observation": observation(before), "next_observation": observation(after),
            "action": action, "mask": mask or [1, 0, 0, 1, 1, 1, 1],
            "contacts_cumulative": contacts, "cost": 0, "done": done,
            "dwell_ticks_current": dwell, "success_info": success}


def successful_stage_trace():
    return [
        event(0, -.005, contacts=0),
        event(-.005, -.015, contacts=1),
        event(-.015, -.030),
        event(-.030, -.031),
        event(-.031, -.04, action=1, mask=[1, 1, 1, 1, 1, 1, 1],
              dwell=256, success=True, done=True),
    ]


def row(success=True):
    return {"success": success, "unsafe": False, "abstained": False,
            "contacts": 1, "option_steps": 5}


class ImmutableEvidenceContracts(unittest.TestCase):
    def test_previous_v8_trainer_byte_exact(self):
        verified = v9.checked_v8_trainer()
        self.assertEqual(verified.V7_CRACI_RUN_ID, v9.V7_RUN_ID)

    def test_arbitrary_self_hasher_cannot_unlock_v8(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "V9_V8_UNSEEN"):
                v9.verify_v8_locked_evidence(Path(d))

    def test_forged_v7_artifact_cannot_change_known_pin(self):
        previous = v9.checked_v8_trainer()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            restored, retained = p / "restored", p / "retained"
            restored.mkdir()
            retained.mkdir()
            archive = p / "download.zip"
            archive.write_bytes(b"rehashed synthetic archive")
            with self.assertRaisesRegex(ValueError, "V9_V7_IMMUTABLE_CRACI_BYTES"):
                with v9.immutable_v7_evidence(restored, retained, archive, previous):
                    self.fail("forged source unexpectedly accepted")

    def test_stage_graph_uses_chronological_contact_lateral_reopen_dwell(self):
        graph = v9.grade_stage_graph(successful_stage_trace(), row())
        self.assertEqual(graph["milestone_option_indices"], [1, 2, 3, 4])
        self.assertTrue(graph["full_stage_safe_goal_dwell"])

    def test_reopen_before_lateral_does_not_count(self):
        trace = successful_stage_trace()
        trace[0]["mask"] = [1, 1, 1, 1, 1, 1, 1]
        trace[2]["mask"] = [1, 1, 1, 1, 1, 1, 1]
        trace[3]["mask"] = [1, 1, 1, 1, 1, 1, 1]
        graph = v9.grade_stage_graph(trace, row())
        self.assertTrue(graph["lateral25_after_contact"])
        self.assertFalse(graph["reopen_after_lateral25"])
        self.assertFalse(graph["full_stage_safe_goal_dwell"])

    def test_rejected_masked_teacher_action(self):
        trace = successful_stage_trace()
        trace[0]["mask"][3] = 0
        with self.assertRaisesRegex(ValueError, "V9_FULL_TRACE_PUBLIC_SHIELD"):
            v9.grade_stage_graph(trace, row())

    def test_no_safe_dwell_claim_from_nonreopened_goal(self):
        trace = successful_stage_trace()
        for step in trace:
            step["mask"][1] = 1
        graph = v9.grade_stage_graph(trace, row())
        self.assertTrue(graph["safe_goal_dwell_any_path"])
        self.assertFalse(graph["full_stage_safe_goal_dwell"])

    def test_never_overwrite_prior_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "existing"
            target.mkdir()
            with self.assertRaisesRegex(ValueError, "V9_REFUSE_OVERWRITE"):
                v9.save_outputs(target, {}, {}, {})


class AdaptiveLearningContracts(unittest.TestCase):
    def test_diagnostic_seeds_are_deterministic_world_level(self):
        first = v9.diagnostic_worlds(range(512000, 512074))
        second = v9.diagnostic_worlds(reversed(list(range(512000, 512074))))
        self.assertEqual(first, second)
        self.assertEqual(len(first), 14)
        self.assertFalse(first.intersection(range(513000, 513512)))

    def test_rare_real_goal_witnesses_are_fitted_not_held_train(self):
        protected = (512109, 512257)
        seeds = [*range(512000, 512074), *protected]
        held = v9.diagnostic_worlds(seeds, protected)
        self.assertTrue(held)
        self.assertTrue(set(protected).isdisjoint(held))
        # Invalid caller may not inject a fabricated protected 'teacher' seed.
        with self.assertRaisesRegex(ValueError, "SUCCESS_PROTECTION_NOT_FROM_TRAIN"):
            v9.diagnostic_worlds(seeds, (*protected, 999999))

    def test_curriculum_is_fixed_fresh_training_only(self):
        readout = {"strategies": {"repeat_left": {
            "chronological_counts": {"contact": 128, "lateral25_after_contact": 74,
                                     "reopen_after_lateral25": 40,
                                     "full_stage_safe_goal_dwell": 0},
            "unsafe_near": 0}}}
        curriculum = v9.adaptive_curriculum(readout, "V7_ONLY_V8_UNSEEN")
        self.assertEqual(curriculum["selected_training_focus"],
                         "forward_reopen_to_250_tick_safe_goal_dwell")
        self.assertEqual(curriculum["next_seed_policy"]["train_seed_start"], 514000)
        self.assertEqual(curriculum["next_seed_policy"]["paired_real_physics_episodes"],
                         800)
        self.assertFalse(curriculum["qualification"]["no_model_promotion_authorized"] is False)

    def test_masked_softmax_observed_actions_gradient_learns(self):
        previous = v9.checked_v8_trainer()
        mask = np.array([1, 1, 1, 1, 1, 1, 1], dtype=bool)
        samples = []
        for seed in range(800, 832):
            for step in range(5):
                features = np.zeros(previous.FEATURE_COUNT)
                features[0] = 1.0
                features[1] = (seed - 800) / 32.0
                samples.append((seed, 0, features.copy(), mask.copy(), 3, 1.0))
        weights, checks, diagnostic = v9.fit_stage_weighted(samples, previous)
        self.assertEqual(weights.shape, (4, 41, 7))
        self.assertTrue(checks[0]["fit_improved"])
        self.assertTrue(checks[0]["held_train_improved"])
        self.assertTrue(diagnostic)
        self.assertEqual(checks[3]["fit_examples"], 0)


if __name__ == "__main__":
    unittest.main()
