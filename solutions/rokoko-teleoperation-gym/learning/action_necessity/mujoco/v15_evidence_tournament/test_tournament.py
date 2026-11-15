"""Targeted synthetic contracts; optional original ZIP qualification is manual."""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
import unittest

from evidence import (V5, PHASE, EXPLORATORY, ORIGINAL_ZIP_SHA256,
                      read_v12, read_unsafe_v13_manifest)
from tournament import (candidate_grammar, choose_on_fit, fold_for_world,
                        metrics, run_tournament, uncertainty_bounds, _choice)


def sample_world(seed: int, delta: int = 6, y: float | None = None,
                 phase_goal: bool = False, base_goal: bool = False,
                 phase_unsafe: bool = False) -> dict:
    obs = [.0] * 18
    obs[7] = float(y if y is not None else .12 + .002 * (seed % 23))
    base = {"safe_goal": base_goal, "unsafe": False,
            "options": 30, "physics_ticks": 3000}
    phase = {"safe_goal": phase_goal, "unsafe": phase_unsafe,
             "options": 30 + delta, "physics_ticks": 3000 + delta * 100}
    return {"seed": seed,
            "world_hash": f"sha256-not-actual-test-world-{seed:04}",
            "public_initial_observation": obs,
            "original_mask": [1] * 7,
            "outcomes": {V5: base, PHASE: phase,
                         EXPLORATORY: {"safe_goal": base_goal,
                                       "unsafe": False,
                                       "options": 29, "physics_ticks": 2900}}}


def quarantined() -> dict:
    return {"source": "V13_INCOMPLETE_QUARANTINED",
            "training_rows_accepted": 0,
            "efficacy_rows_accepted": 0,
            "physics_dispatch_allowed": False,
            "manifest_sha256": "pinned-source-only-test"}


class EvidenceLearningTests(unittest.TestCase):
    def test_world_partition_grouped_and_no_action_output(self):
        all_worlds = [sample_world(seed) for seed in range(518000, 518048)]
        self.assertEqual(sum(fold_for_world(w) == 2 for w in all_worlds), 10)
        self.assertEqual(_choice({"kind": "always_v5"}, all_worlds[0]), V5)
        self.assertEqual(_choice({"kind": "threshold_le", "threshold": .5},
                                 all_worlds[0]), PHASE)

    def test_threshold_training_uses_only_public_obstacle(self):
        w = sample_world(518001, delta=-8, y=.03)
        rule = {"kind": "threshold_le", "threshold": .05}
        self.assertEqual(_choice(rule, w), PHASE)
        w["hidden_future_success"] = True
        w["seed"] = 123456  # Neither seed nor future label is a feature.
        self.assertEqual(_choice(rule, w), PHASE)
        w["public_initial_observation"][7] = .2
        self.assertEqual(_choice(rule, w), V5)

    def test_no_untrained_right4_in_learned_grammar(self):
        worlds = [sample_world(seed, y=.10 + .01 * (seed % 7))
                  for seed in range(518000, 518030)]
        for rule in candidate_grammar(worlds):
            self.assertTrue(all(_choice(rule, w) in (V5, PHASE) for w in worlds))

    def test_completely_negative_training_retains_v5(self):
        worlds = [sample_world(seed, delta=9) for seed in range(518000, 518040)]
        rule, m = choose_on_fit(worlds)
        self.assertEqual(rule, {"kind": "always_v5"})
        self.assertEqual(m["option_delta_candidate_minus_v5"], 0)

    def test_train_chooses_rule_when_real_factual_paired_benefit_exists(self):
        worlds = [sample_world(seed, delta=-5, y=.04 + .001 * (seed % 20),
                               phase_goal=True, base_goal=True)
                  for seed in range(518000, 518040)]
        rule, m = choose_on_fit(worlds)
        self.assertNotEqual(rule["kind"], "always_v5")
        self.assertLess(m["option_delta_candidate_minus_v5"], 0)
        self.assertEqual(m["lost_baseline_goal_worlds"], 0)

    def test_train_rejects_fast_but_goal_losing_policy(self):
        worlds = [sample_world(seed, delta=-15, phase_goal=False, base_goal=True)
                  for seed in range(518000, 518040)]
        rule, _ = choose_on_fit(worlds)
        self.assertEqual(rule["kind"], "always_v5")

    def test_train_rejects_fast_but_unsafe_policy(self):
        worlds = [sample_world(seed, delta=-15, phase_goal=True,
                               base_goal=True, phase_unsafe=True)
                  for seed in range(518000, 518040)]
        rule, _ = choose_on_fit(worlds)
        self.assertEqual(rule["kind"], "always_v5")

    def test_paired_efficiency_measured_in_world_units(self):
        worlds = [sample_world(seed, delta=-2) for seed in range(518000, 518010)]
        m = metrics({"kind": "public_corridor"}, worlds)
        # obs Y 0.12..0.138: only Y=.120,.122? 0.120 is in corridor.
        self.assertEqual(m["phase_selected_worlds"], 1)
        self.assertEqual(m["option_delta_candidate_minus_v5"], -2)

    def test_duplicate_worlds_rejected(self):
        w = sample_world(518000)
        with self.assertRaisesRegex(ValueError, "DUPLICATED"):
            metrics({"kind": "always_v5"}, [w, copy.deepcopy(w)])

    def test_unknown_candidate_grammar_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "UNREVIEWED"):
            _choice({"kind": "copy_future_reward"}, sample_world(518000))

    def test_bootstrap_world_level_and_deterministic(self):
        self.assertEqual(uncertainty_bounds([0] * 48), [0.0, 0.0])
        self.assertEqual(uncertainty_bounds([-1, 1] * 24),
                         uncertainty_bounds([-1, 1] * 24))

    def test_zero_gain_crossfit_measured_not_promoted(self):
        worlds = [sample_world(seed, delta=7) for seed in range(518000, 518048)]
        e = {"worlds": worlds, "actual_real_episodes": 144,
             "actual_mask_legal_options": 4228,
             "original_zip_sha256": ORIGINAL_ZIP_SHA256}
        r = run_tournament(e, quarantined())
        self.assertEqual(r["adaptive_rule_training"]["crossfit_diagnostic"]
                         ["factual_world_paired_option_delta"], 0)
        self.assertFalse(r["robot_motor_execution_authorized"])
        self.assertFalse(r["model_promotion_authorized"])
        self.assertEqual(r["science_decision"],
                         "STOP_V13_UNSAFE_AND_V12_ZERO_NOVEL_GOAL")
        self.assertEqual(len(r["adaptive_rule_training"]["folds"]), 5)

    def test_unsafely_training_on_v13_hard_fails(self):
        e = {"worlds": [sample_world(seed) for seed in range(518000, 518048)],
             "actual_real_episodes": 144, "actual_mask_legal_options": 4228}
        q = quarantined()
        q["training_rows_accepted"] = 1
        with self.assertRaisesRegex(ValueError, "QUARANTINED"):
            run_tournament(e, q)

    def test_v12_zip_bytes_must_be_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fake.zip"
            path.write_bytes(b"not-original")
            with self.assertRaisesRegex(ValueError, "ZIP_SHA_CHANGED"):
                read_v12(path)

    def test_v13_sha_packet_must_be_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fake-v13.json"
            path.write_text(json.dumps({"status": "INCOMPLETE_STOP"}))
            with self.assertRaisesRegex(ValueError, "PACKET_SHA_CHANGED"):
                read_unsafe_v13_manifest(path)

    def test_no_new_physics_or_paid_dispatch_api(self):
        from tournament import __dict__ as exports
        self.assertNotIn("dispatch_craci", exports)
        self.assertNotIn("execute_action", exports)
        self.assertNotIn("train_on_v13", exports)


if __name__ == "__main__":
    unittest.main()
