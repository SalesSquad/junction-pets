"""Synthetic, deterministic candidate-policy checks.  NO MuJoCo or rollout."""

from __future__ import annotations

import json
import math
import unittest

from guard import ABSTAIN, Assumptions, SOURCE_V13_SHA, decide, propose_one_fork


def public_frame(*, obj=(0., 0.), pusher=(-.06, 0.), mapped=(.09, .15),
                 age=0., quality=.99, live=1, inside=1, held=0, clock=.1):
    return [*obj, *pusher, 0., 0., *mapped, age, quality, live, inside,
            1., clock, 0., held, .16, 0.]


class SweptShieldCandidateTests(unittest.TestCase):
    def test_global_physics_bounds_include_ood_without_hidden_flag(self):
        a = Assumptions()
        self.assertEqual((a.max_mover_amplitude_m, a.max_mover_frequency_hz), (.045, 1.))
        self.assertAlmostEqual(a.max_obstacle_speed_mps, 2 * math.pi * .045, places=12)
        self.assertAlmostEqual(a.obstacle_sweep_m, 2 * math.pi * .045 * .2, places=12)
        self.assertGreater(a.object_clearance_m, .14)

    def test_known_hazard_geometry_vetoes_original_legal_push_without_claiming_efficacy(self):
        # Rounded source-observable geometry at a moving-obstacle approach.
        # This is a safety regression, NOT an evaluation or test-world result.
        obs = public_frame(obj=(.094, .005), pusher=(.063, .009), mapped=(.090, .078))
        decision = decide(obs, [1] * 7, 2)
        self.assertTrue(decision.would_veto_requested)
        self.assertEqual(decision.shadow_fallback_action, ABSTAIN)
        self.assertEqual(decision.disposition, "SHADOW_VETO_NOT_EXECUTED")
        self.assertIn("object_within_predictive_swept_obstacle_tube",
                      decision.action_risks[2].causes)
        self.assertEqual(decision.action_risks[2].originally_allowed, True)
        self.assertEqual(decision.source_v13_sha, SOURCE_V13_SHA)
        self.assertEqual(decision.suggested_motor_actions, ())
        self.assertIn("NO_EFFICACY_CLAIM", decision.result_scope)

    def test_benign_distant_obstacle_keeps_original_requested_motor(self):
        decision = decide(public_frame(), [1] * 7, 1)
        self.assertFalse(decision.would_veto_requested)
        self.assertIsNone(decision.shadow_fallback_action)
        self.assertEqual(decision.disposition, "SHADOW_PASS_NOT_EXECUTED")
        self.assertFalse(decision.action_risks[1].veto)
        self.assertEqual(decision.suggested_motor_actions, (3, 4, 5))

    def test_original_mask_never_reopened_even_with_benign_geometry(self):
        mask = [1] * 7
        mask[2] = 0
        decision = decide(public_frame(), mask, 2)
        self.assertTrue(decision.would_veto_requested)
        self.assertEqual(decision.shadow_fallback_action, ABSTAIN)
        self.assertIn("original_mask_forbids", decision.action_risks[2].causes)
        self.assertFalse(decision.action_risks[2].originally_allowed)

    def test_pusher_segment_is_separate_from_object_hazard(self):
        obs = public_frame(obj=(0., 0.), pusher=(.09, .14), mapped=(.09, .15))
        decision = decide(obs, [1] * 7, 2)
        self.assertGreater(decision.action_risks[2].object_margin_m, 0.)
        self.assertLess(decision.action_risks[2].pusher_path_margin_m, 0.)
        self.assertTrue(decision.would_veto_requested)
        self.assertEqual(decision.shadow_fallback_action, ABSTAIN)
        self.assertIn("pusher_option_path_within_predictive_swept_obstacle_tube",
                      decision.action_risks[2].causes)

    def test_low_quality_stale_held_or_deadman_each_veto(self):
        for kwargs in ({"quality": .4}, {"age": .12}, {"held": 1}, {"live": 0},
                       {"inside": 0}):
            with self.subTest(kwargs=kwargs):
                decision = decide(public_frame(**kwargs), [1] * 7, 1)
                self.assertTrue(decision.would_veto_requested)
                self.assertEqual(decision.shadow_fallback_action, ABSTAIN)
                self.assertIn("public_deadman_quality_age_or_hold_unhealthy",
                              decision.action_risks[1].causes)

    def test_unavailable_original_abstain_returns_no_command_not_motor(self):
        decision = decide(public_frame(obj=(.094, .005), mapped=(.09, .078)),
                          [0, 0, 1, 0, 0, 0, 0], 2)
        self.assertTrue(decision.would_veto_requested)
        self.assertIsNone(decision.shadow_fallback_action)
        self.assertEqual(decision.disposition, "SHADOW_VETO_NOT_EXECUTED")
        self.assertEqual(decision.suggested_motor_actions, ())

    def test_requested_abstain_never_becomes_a_motor_command(self):
        decision = decide(public_frame(), [1] * 7, ABSTAIN)
        self.assertFalse(decision.would_veto_requested)
        self.assertIsNone(decision.shadow_fallback_action)
        self.assertEqual(decision.disposition, "SHADOW_ORIGINAL_ABSTAIN")

    def test_previous_public_map_only_adds_uncertainty_never_future_knowledge(self):
        old = public_frame(mapped=(.09, .17), clock=.1)
        current = public_frame(mapped=(.09, .15), clock=.11666666666666667)
        normal = decide(current, [1] * 7, 1, previous_public18d=old)
        self.assertTrue(normal.history_consistent)
        self.assertAlmostEqual(normal.observed_obstacle_displacement_m, .02)
        self.assertFalse(normal.would_veto_requested)

        incompatible = public_frame(mapped=(-.2, -.2), clock=.11666666666666667)
        cautious = decide(incompatible, [1] * 7, 1, previous_public18d=current)
        self.assertFalse(cautious.history_consistent)
        self.assertTrue(cautious.would_veto_requested)
        self.assertIn("previous_public_obstacle_map_inconsistent",
                      cautious.action_risks[1].causes)

    def test_regressed_time_fails_closed_without_phase_or_seed(self):
        previous = public_frame(clock=.4)
        current = public_frame(clock=.2)
        decision = decide(current, [1] * 7, 1, previous_public18d=previous)
        self.assertFalse(decision.history_consistent)
        self.assertTrue(decision.would_veto_requested)

    def test_invalid_public_or_mask_does_not_issue_an_action(self):
        invalid = public_frame()
        invalid[10] = .5
        for obs, mask, action in (
            (invalid, [1] * 7, 1),
            (public_frame(), [1] * 6, 1),
            (public_frame(), [1, 1, 2, 1, 1, 1, 1], 1),
            (public_frame(), [1] * 7, True),
            (public_frame(), [1] * 7, 7),
        ):
            with self.subTest(action=action):
                with self.assertRaises(ValueError):
                    decide(obs, mask, action)

    def test_deterministic_json_evidence_and_advice_never_auto_executes(self):
        obs = public_frame()
        a, b = decide(obs, [1] * 7, 2), decide(obs, [1] * 7, 2)
        self.assertEqual(a.log_record(), b.log_record())
        self.assertFalse(a.would_veto_requested)
        self.assertEqual(a.suggested_motor_actions, (3, 4, 5))
        body = json.dumps(a.log_record(), sort_keys=True, allow_nan=False)
        self.assertIn("gaussian_noise_tails_unbounded", body)
        self.assertIn(SOURCE_V13_SHA, body)

    def test_default_v5_always_unchanged_without_research_opt_in(self):
        obs = public_frame(obj=(.094, .005), mapped=(.09, .078))
        for baseline_action in range(7):
            with self.subTest(baseline_action=baseline_action):
                result = propose_one_fork(obs, [1] * 7, baseline_action)
                self.assertEqual(result.baseline_action_unchanged, baseline_action)
                self.assertIsNone(result.experimental_action_advisory_only)
                self.assertFalse(result.opted_in)
                self.assertFalse(result.external_execution_authorized)
                self.assertFalse(result.experimental_original_physics_qualified)

    def test_research_never_targets_original_baseline_motor_action(self):
        result = propose_one_fork(public_frame(), [1] * 7, 2,
                                  opt_in=True, experimental_action=3)
        self.assertEqual(result.baseline_action_unchanged, 2)
        self.assertFalse(result.source_public_trigger_valid)
        self.assertIsNone(result.experimental_action_advisory_only)

    def test_public_early_live_abstain_allows_only_advisory_single_fork(self):
        # Early V5 ABSTAIN while public live=1, held=0, motor mask nonempty.
        result = propose_one_fork(public_frame(), [1] * 7, ABSTAIN,
                                  opt_in=True, experimental_action=2)
        self.assertTrue(result.source_public_trigger_valid)
        self.assertEqual(result.baseline_action_unchanged, ABSTAIN)
        self.assertEqual(result.experimental_action_advisory_only, 2)
        self.assertEqual(result.per_world_max_candidate_forks, 1)
        self.assertFalse(result.external_execution_authorized)

    def test_public_trigger_hazard_preserves_v5_original_abstain(self):
        obs = public_frame(obj=(.094, .005), pusher=(.063, .009), mapped=(.09, .078))
        result = propose_one_fork(obs, [1] * 7, ABSTAIN,
                                  opt_in=True, experimental_action=2)
        self.assertTrue(result.source_public_trigger_valid)
        self.assertEqual(result.baseline_action_unchanged, ABSTAIN)
        self.assertIsNone(result.experimental_action_advisory_only)
        self.assertTrue(result.risk.would_veto_requested)

    def test_public_deadman_or_hold_excludes_research_fork(self):
        for kwargs in ({"live": 0}, {"held": 1}):
            with self.subTest(kwargs=kwargs):
                result = propose_one_fork(public_frame(**kwargs), [1] * 7,
                                          ABSTAIN, opt_in=True, experimental_action=2)
                self.assertFalse(result.source_public_trigger_valid)
                self.assertEqual(result.baseline_action_unchanged, ABSTAIN)
                self.assertIsNone(result.experimental_action_advisory_only)

    def test_experimental_action_requires_explicit_opt_in(self):
        with self.assertRaises(ValueError):
            propose_one_fork(public_frame(), [1] * 7, ABSTAIN,
                             experimental_action=2)


if __name__ == "__main__":
    unittest.main()
