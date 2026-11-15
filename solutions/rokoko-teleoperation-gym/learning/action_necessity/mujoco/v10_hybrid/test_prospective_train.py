#!/usr/bin/env python3
"""Portable source/paired-qualification contracts; does NOT mock physical success."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("v10_hybrid_prospective_unit", HERE / "prospective_train.py")
assert spec is not None and spec.loader is not None
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PublicSelectionFixture:
    def __init__(self):
        self.seed = None
        self.calls = []

    def reset(self, *, seed, ood):
        if ood:
            raise AssertionError("TRAIN-only selector attempted OOD")
        self.seed = seed
        self.calls.append(seed)
        obs = np.zeros(18, dtype=np.float64)
        obs[7] = .09 if seed < p.FIRST_TRAIN_SEED + 128 else .2
        return obs


def synthetic_trial(seed, strategy, goal=False, unsafe=False, corridor=True):
    # This is a unit fixture for readout *arithmetic*, not simulated physics.
    return {"seed": seed, "strategy": strategy, "world_hash": f"h-{seed}",
            "observed_corridor": corridor, "success": bool(goal),
            "unsafe": bool(unsafe), "abstained": False,
            "dwell_ticks_final": 250 if goal else 0,
            "physics_steps": 1, "full_transition_count": 3,
            "full_transition_sha256": f"t-{seed}",
            "forward_reopened_after_side": 1 if strategy == "v8_hierarchical" else 0}


def fake_complete_trials():
    rows = []
    for i in range(160):
        seed = p.FIRST_TRAIN_SEED + i
        near = i < 128
        for arm in p.STRATEGIES:
            # 0: new hybrid goal; 1: original V5 lost under hybrid.
            goal = (i == 0 and arm == "near-early-side-mask-rescue") or (
                i == 1 and arm in ("frozen_v5", "rescue_off_v5"))
            rows.append(synthetic_trial(seed, arm, goal, corridor=near))
    return rows


class ProspectiveScientificContracts(unittest.TestCase):
    def test_fresh_train_seed_and_four_frozen_arms(self):
        self.assertEqual(p.FIRST_TRAIN_SEED, 516_000)
        self.assertEqual(p.LAST_SCANNED_SEED, 516_511)
        self.assertEqual(p.EXPECTED_TRIALS, 640)
        self.assertEqual(p.MAX_OPTIONS, 60)
        self.assertEqual(p.SCHEMA, "junction.rokoko.mujoco-v10-hybrid-prospective.v1")
        self.assertEqual(p.EVIDENCE_PARTS_SCHEMA, "junction.rokoko.mujoco-v10-hybrid-evidence-parts.v1")

    def test_strict_public_18d_first_observation(self):
        for bad in (np.zeros(17), np.full(18, np.nan), np.zeros((1, 18))):
            with self.assertRaisesRegex(ValueError, "ORIGINAL_18D"):
                p.public_selection(bad)
        obs = np.zeros(18)
        obs[7] = .1219
        self.assertTrue(p.public_selection(obs)[1])
        obs[7] = .122
        self.assertFalse(p.public_selection(obs)[1])

    def test_cohort_uses_only_public_first_observation_no_outcomes(self):
        env = PublicSelectionFixture()
        cohort, scan = p.select_fresh_train_worlds(env, lambda e: f"proof-{e.seed}")
        self.assertEqual(len(cohort), 160)
        self.assertEqual(len(scan), 160)
        self.assertEqual(len(env.calls), 160)
        self.assertEqual(sum(x["observed_corridor"] for x in cohort), 128)
        self.assertEqual(len(p.paired_schedule(cohort)), 640)
        self.assertTrue(all(p.FIRST_TRAIN_SEED <= x["seed"] <= p.LAST_SCANNED_SEED
                            for x in cohort))
        self.assertEqual([arm for _, arm in p.paired_schedule(cohort)[:4]],
                         list(p.STRATEGIES))

    def test_unit_readout_distinguishes_new_goals_from_lost_v5(self):
        r = p.paired_readout(fake_complete_trials())
        self.assertEqual(r["novel_hybrid_safe_goal_seeds_vs_v5"], [516000])
        self.assertEqual(r["lost_v5_safe_goal_seeds_under_hybrid"], [516001])
        self.assertEqual(r["strategies"]["frozen_v5"]["safe_near_goals"], 1)
        self.assertEqual(r["strategies"]["near-early-side-mask-rescue"]["safe_near_goals"], 1)
        self.assertEqual(r["hybrid_new_unsafe_seeds_vs_v5"], [])
        self.assertTrue(r["strict_original_v5_placebo_raw_trace_identical"])
        self.assertFalse(r["promotion_authorized"])

    def test_placebo_divergence_blocks_scientific_readout(self):
        rows = fake_complete_trials()
        row = next(x for x in rows if x["strategy"] == "rescue_off_v5")
        row["full_transition_sha256"] = "unexpected-drift"
        with self.assertRaisesRegex(ValueError, "PLACEBO_TRACE_MISMATCH"):
            p.paired_readout(rows)

    def test_missing_paired_policy_blocks_scientific_readout(self):
        rows = fake_complete_trials()
        rows.pop()
        with self.assertRaisesRegex(ValueError, "MISSING_OR_UNPAIRED_WORLD"):
            p.paired_readout(rows)

    def test_never_treat_unsafe_as_safe_goal(self):
        row = synthetic_trial(516001, "frozen_v5", goal=True, unsafe=True)
        self.assertFalse(p.safe_goal(row))
        row["unsafe"] = False
        row["dwell_ticks_final"] = 249
        self.assertFalse(p.safe_goal(row))
        row["dwell_ticks_final"] = 250
        self.assertTrue(p.safe_goal(row))

    def test_compact_summary_is_lossless_bounded_and_non_overwriting(self):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "summary.json"
            n = p.write_compact_json(out, {"x": [1, 2], "goal": False},
                                     lambda x: b'{"goal":false,"x":[1,2]}')
            self.assertEqual(out.read_bytes(), b'{"goal":false,"x":[1,2]}\n')
            self.assertEqual(n, out.stat().st_size)
            with self.assertRaises(FileExistsError):
                p.write_compact_json(out, {"goal": False}, lambda x: b'{}')
            with patch.object(p, "MAX_SUMMARY_BYTES", 3):
                with self.assertRaisesRegex(ValueError, "TOO_LARGE"):
                    p.write_compact_json(Path(root) / "other.json", {}, lambda x: b'{"x":1}')


if __name__ == "__main__":
    unittest.main()
