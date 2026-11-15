"""Focused Jev L2 shadow safety/contract tests; no network or provider charge."""
import json
import math
import unittest

from jev_shadow import (
    CHOICES, QUESTIONS, OBS_FIELDS, SPECS, admit_shielded,
    api_request, build_cases, frozen_rule, validate_answer, visible_state,
)
from env import ACTIONS, ContactEnv


class JevShadowSafetyTests(unittest.TestCase):
    @staticmethod
    def sample_answer(choice="CONTINUE", confidence=1.0, human=0.2):
        return {
            "model": "jev-1.14.0",
            "answers": {
                "next_step": {
                    "type": "choice", "choice": choice,
                    "confidence": confidence,
                    "probabilities": {
                        k: float(k == choice) for k in CHOICES
                    },
                },
                "needs_review": {"type": "noul", "noul": human},
            },
            "usage": {"input_tokens": 499, "output_tokens": 88},
        }

    def test_cases_are_source_bound_observations_only(self):
        cases = build_cases()
        self.assertEqual(len(cases), len(SPECS))
        self.assertEqual(len(set(x["id"] for x in cases)), len(cases))
        self.assertEqual(len(set(x["seed"] for x in cases)), len(cases))
        self.assertTrue(all(120000 <= x["seed"] < 121000 for x in cases))
        self.assertTrue(any(x["source"].startswith("INJECTED_") for x in cases))
        self.assertTrue(any(x["source"].startswith("ACTUAL_") for x in cases))
        for case in cases:
            state = case["state"]
            self.assertEqual(set(state), OBS_FIELDS)
            self.assertEqual(case["rule"], frozen_rule(state))
            request = json.loads(api_request(state, "jev-latest"))
            self.assertEqual(request["state"], state)
            self.assertEqual(set(request), {"model", "state", "questions"})
            self.assertEqual(set(request["questions"]), set(QUESTIONS))
            self.assertNotIn("seed", request["state"])
            self.assertNotIn("ground_truth", request["state"])
            self.assertNotIn("friction", request["state"])
            self.assertNotIn("contact_force", request["state"])
            self.assertNotIn("unsafe", request["state"])
            self.assertNotIn("api_key", request["state"])
        self.assertEqual(
            frozen_rule(next(x["state"] for x in cases
                             if x["mode"] == "deadman")), "HALT")
        self.assertEqual(
            frozen_rule(next(x["state"] for x in cases
                             if x["mode"] == "dropout")), "REOBSERVE")

    def test_unsafe_jev_model_cannot_override_rules(self):
        for case in build_cases():
            state = case["state"]
            hard = case["rule"]
            decision = admit_shielded(state, "CONTINUE", 1.0)
            if hard in ("HALT", "REOBSERVE", "REQUEST_HUMAN", "REPLAN"):
                self.assertEqual(decision, hard)
            # Any model confidence must leave mandatory HALT unchanged.
            if hard == "HALT":
                self.assertEqual(admit_shielded(state, "REPLAN", 1.0), "HALT")
                self.assertEqual(admit_shielded(state, "CONTINUE", 1.0), "HALT")
        self.assertEqual(
            admit_shielded(next(x["state"] for x in build_cases()
                                if x["mode"] == "reset"), "HALT", .2),
            "REOBSERVE")

    def test_response_must_be_valid_typed_distribution(self):
        result = validate_answer(self.sample_answer("REPLAN", .8, .9))
        self.assertEqual(result["choice"], "REPLAN")
        self.assertEqual(result["model"], "jev-1.14.0")
        self.assertEqual(result["usage"]["input_tokens"], 499)
        broken = self.sample_answer()
        broken["answers"]["next_step"]["probabilities"]["CONTINUE"] = float("nan")
        with self.assertRaises(ValueError):
            validate_answer(broken)
        broken = self.sample_answer()
        del broken["answers"]["needs_review"]
        with self.assertRaises(ValueError):
            validate_answer(broken)
        broken = self.sample_answer()
        broken["answers"]["next_step"]["choice"] = "MOVE_MOTOR"
        with self.assertRaises(ValueError):
            validate_answer(broken)
        broken = self.sample_answer()
        broken["answers"]["next_step"]["confidence"] = 1.2
        with self.assertRaises(ValueError):
            validate_answer(broken)
        broken = self.sample_answer()
        broken["usage"]["input_tokens"] = "100"
        with self.assertRaises(ValueError):
            validate_answer(broken)

    def test_real_mujoco_snapshot_18_features(self):
        env = ContactEnv(max_options=30)
        obs = env.reset(120650)
        state = visible_state(obs, env.mask(obs))
        self.assertEqual(len(state), len(OBS_FIELDS))
        self.assertTrue(all(option in ACTIONS for option
                            in state["enabled_options"]))
        self.assertTrue(math.isfinite(state["mapped_obstacle_clearance_m"]))


if __name__ == "__main__":
    unittest.main()
