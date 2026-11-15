#!/usr/bin/env python3
"""Source-only V12 historical78f RIGHT4 exploration-loss regression contract.

Loads three pure validation functions through AST to avoid MuJoCo imports or
running the expensive frozen 144-episode actual physics during unit tests.
"""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("rokoko-mujoco-v12-pilot-qualification.py")
ARMS = ("frozen_v5", "v12_phase_dwell_supported_actions",
        "v12_right_side_action4_exploration_train_only")
EXPECTED = 144


def load_pure_contract():
    root = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    names = {"require", "safe_goal", "independent_exploration_only_lost_v5_goals"}
    pure = [node for node in root.body
            if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in pure} != names:
        raise AssertionError("V12 independent source contract functions missing")
    ns = {"ARMS": ARMS, "EXPECTED": EXPECTED}
    exec(compile(ast.Module(body=pure, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns["independent_exploration_only_lost_v5_goals"]


class V12HistoricalExplorationLossContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loss = staticmethod(load_pure_contract())

    @staticmethod
    def fixture():
        cohort = [{"seed": 518000 + i, "world_hash": f"source-world-{i}"}
                  for i in range(48)]
        rows = {}
        for world in cohort:
            for arm in ARMS:
                rows[(world["seed"], arm)] = {
                    "seed": world["seed"], "strategy": arm,
                    "world_hash": world["world_hash"], "success": False,
                    "unsafe": False, "abstained": False}
        return cohort, rows

    def test_completed_48_worlds_and_144_rows_no_loss(self):
        worlds, rows = self.fixture()
        self.assertEqual(self.loss(rows, worlds), [])

    def test_exploration_loss_recomputed_not_silent_missing_key_default(self):
        worlds, rows = self.fixture()
        seed = worlds[0]["seed"]
        rows[(seed, ARMS[0])]["success"] = True
        self.assertEqual(self.loss(rows, worlds), [seed])
        rows[(seed, ARMS[2])]["success"] = True
        self.assertEqual(self.loss(rows, worlds), [])

    def test_missing_exploration_arm_must_stop(self):
        worlds, rows = self.fixture()
        del rows[(worlds[0]["seed"], ARMS[2])]
        with self.assertRaisesRegex(AssertionError, "V12_EXPLORATION_LOSS"):
            self.loss(rows, worlds)

    def test_malformed_boolean_must_stop(self):
        worlds, rows = self.fixture()
        rows[(worlds[0]["seed"], ARMS[2])]["unsafe"] = 0
        with self.assertRaisesRegex(AssertionError, "V12_EXPLORATION_LOSS"):
            self.loss(rows, worlds)

    def test_mismatched_world_hash_must_stop(self):
        worlds, rows = self.fixture()
        rows[(worlds[0]["seed"], ARMS[2])]["world_hash"] = "replaced-world"
        with self.assertRaisesRegex(AssertionError, "V12_EXPLORATION_LOSS"):
            self.loss(rows, worlds)

    def test_duplicate_world_fails_even_with_complete_rows(self):
        worlds, rows = self.fixture()
        worlds[1] = dict(worlds[0])
        with self.assertRaisesRegex(AssertionError, "V12_EXPLORATION_LOSS"):
            self.loss(rows, worlds)


if __name__ == "__main__":
    unittest.main()
