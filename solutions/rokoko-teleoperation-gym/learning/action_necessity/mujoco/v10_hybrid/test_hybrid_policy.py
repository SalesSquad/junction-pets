#!/usr/bin/env python3
"""Portable, privacy- and shield-focused contracts for frozen hybrid policies."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("hybrid_under_test", HERE / "hybrid_policy.py")
assert spec is not None and spec.loader is not None
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def public_observation(distance=1., obstacle_y=.1):
    obs = np.zeros(18, dtype=np.float64)
    obs[7] = obstacle_y
    obs[16] = float(distance)
    return obs


def mask(*, forward=False, side=True, stop=True):
    return np.asarray([1, int(forward), int(forward), int(side),
                       int(side), 1, int(stop)], dtype=np.int64)


def factory(action, count=None):
    def make():
        if count is not None:
            count["new"] = count.get("new", 0) + 1
        return lambda obs, legal: action
    return make


class HybridContracts(unittest.TestCase):
    def test_strict_public_shape_and_mask(self):
        good = public_observation()
        for obs, maskbits in (
            (np.zeros(17), mask()),
            (np.full(18, np.nan), mask()),
            (good, np.ones(6, dtype=int)),
            (good, np.zeros(7, dtype=int)),
            (good, np.ones(7, dtype=float)),
            (good, np.asarray([1, 0, 0, 1, 1, 1, 2])),
        ):
            with self.subTest(shape=np.asarray(obs).shape):
                with self.assertRaises(h.HybridContractError):
                    h.original_public_inputs(obs, maskbits)

    def test_original_v5_action_untouched_when_forward_legal(self):
        controller = h.ConservativeHybrid(factory(1), factory(3))
        for _ in range(5):
            self.assertEqual(controller(public_observation(), mask(forward=True)), 1)
        self.assertEqual(controller.rescue_rounds, 0)

    def test_forward_legal_does_not_override_v5_abstention(self):
        controller = h.ConservativeHybrid(factory(6), factory(3))
        self.assertEqual(controller(public_observation(), mask(forward=True)), 6)
        self.assertEqual(controller.rescue_rounds, 0)

    def test_both_modes_preserve_terminal_near_goal_abstain(self):
        for mode in h.MODES:
            controller = h.ConservativeHybrid(factory(6), factory(3), mode)
            self.assertEqual(controller(public_observation(distance=.02), mask()), 6)
            self.assertEqual(controller.rescue_rounds, 0)

    def test_early_public_mask_rescue_preempts_v5_before_abstain(self):
        c = h.ConservativeHybrid(factory(1), factory(3))
        self.assertEqual(c(public_observation(), mask()), 3)
        self.assertTrue(c.rescue_active)
        self.assertEqual(c.rescue_sides, 1)
        self.assertEqual(c.rescue_rounds, 1)

    def test_public_mask_reopening_reenters_new_v5(self):
        calls = {"new": 0}
        actions = [1]
        def baseline():
            calls["new"] += 1
            return lambda obs, legal: actions[0]
        c = h.ConservativeHybrid(baseline, factory(3))
        self.assertEqual(c(public_observation(), mask()), 3)
        self.assertEqual(c(public_observation(), mask(forward=True)), 1)
        self.assertFalse(c.rescue_active)
        self.assertEqual(calls["new"], 2)

    def test_broad_mode_can_rescue_outside_observed_near_corridor(self):
        c = h.ConservativeHybrid(factory(6), factory(3), "early-side-mask-rescue")
        self.assertEqual(c(public_observation(obstacle_y=.15), mask()), 3)
        self.assertEqual(c.rescue_rounds, 1)

    def test_near_mode_preserves_v5_outside_observed_near_corridor(self):
        c = h.ConservativeHybrid(factory(6), factory(3))
        self.assertEqual(c(public_observation(obstacle_y=.15), mask()), 6)
        self.assertEqual(c.rescue_rounds, 0)

    def test_no_lateral_options_cannot_be_rescued(self):
        c = h.ConservativeHybrid(factory(6), factory(3))
        # Actual terminal masks are most often exactly this shape.
        self.assertEqual(c(public_observation(), [0, 0, 0, 0, 0, 0, 1]), 6)
        self.assertEqual(c.rescue_rounds, 0)

    def test_first_viable_side_masks_reach_v8_without_v5_call(self):
        def poison_baseline():
            def no_call(obs, mask):
                raise AssertionError("V5 was called despite intentional preemption")
            return no_call
        c = h.ConservativeHybrid(poison_baseline, factory(3))
        self.assertEqual(c(public_observation(), mask()), 3)

    def test_rescue_budget_is_bounded_without_hidden_feedback(self):
        c = h.ConservativeHybrid(factory(6), factory(3))
        for _ in range(40):
            self.assertIn(c(public_observation(), mask()), (3, 6))
        self.assertLessEqual(c.rescue_rounds, h.MAX_RESCUE_ROUNDS)
        self.assertEqual(c(public_observation(), mask()), 6)

    def test_unshielded_baseline_proposal_fail_closed(self):
        c = h.ConservativeHybrid(factory(1), factory(3))
        with self.assertRaisesRegex(h.HybridContractError, "SEVEN_OPTION_SHIELD"):
            c(public_observation(), [0, 0, 0, 0, 0, 0, 1])

    def test_unshielded_rescue_proposal_fail_closed(self):
        c = h.ConservativeHybrid(factory(6), factory(1))
        with self.assertRaisesRegex(h.HybridContractError, "SEVEN_OPTION_SHIELD"):
            c(public_observation(), mask(forward=False))

    def test_booleans_and_numpy_ints_are_not_policy_actions(self):
        for invalid in (True, np.int64(3), 9, None):
            with self.subTest(invalid=repr(invalid)):
                with self.assertRaises(h.HybridContractError):
                    h.checked_action(invalid, mask())

    def test_frozen_original_v8_byte_pins(self):
        self.assertEqual(h.sha256_file(h.V8 / "rollout_train.py"),
                         h.V8_RUNNER_SHA256)
        self.assertEqual(h.sha256_file(h.V8 / "run.py"), h.V8_TRAINER_SHA256)
        self.assertEqual(h.sha256_file(h.V8 / "checkpoints/weights.json"),
                         h.V8_WEIGHTS_FILE_SHA256)
        self.assertEqual(h.sha256_file(h.V8 / "checkpoints/training-receipt.json"),
                         h.V8_RECEIPT_FILE_SHA256)

    def test_forged_weights_are_rejected_before_loading_models(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "weights.json"
            p.write_text("{}\n")
            with self.assertRaisesRegex(h.HybridContractError, "UNREVIEWED"):
                h.frozen_factories(p, h.V8 / "checkpoints/training-receipt.json")

    def test_missing_factory_mode_rejected(self):
        with self.assertRaises(h.HybridContractError):
            h.ConservativeHybrid(factory(6), factory(3), "unreviewed-rl")
        with self.assertRaises(h.HybridContractError):
            h.policy_factory("unreviewed-rl", Path("x"), Path("y"))


if __name__ == "__main__":
    unittest.main()
