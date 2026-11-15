#!/usr/bin/env python3
"""Adversarial source-only proof: V13 RIGHT4 counts require active burst mode.

This extracts the exact pure helper and science gate from the pinned CRACI
qualifier without importing MuJoCo or fabricating a hosted physics result.
"""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("rokoko-mujoco-v13-original-qualification.py")
ARMS = ("frozen_v5", "v12_phase_dwell_supported_actions",
        "train_only_right4_burst2", "train_only_right4_burst4")


def load_pure_contract():
    code = SOURCE.read_text(encoding="utf-8")
    parsed = ast.parse(code, filename=str(SOURCE))
    names = {"require", "safe_goal", "source_bound_burst_right4_instances",
             "independent_science_gate"}
    nodes = [node for node in parsed.body if isinstance(node, ast.FunctionDef)
             and node.name in names]
    if {node.name for node in nodes} != names:
        raise AssertionError("V13 original source-bound burst helpers missing")
    namespace = {"ARMS": ARMS}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"),
         namespace)
    return namespace, code


class V13ModeBoundOriginalAction4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ns, cls.source = load_pure_contract()
        cls.instances = staticmethod(ns["source_bound_burst_right4_instances"])
        cls.science = staticmethod(ns["independent_science_gate"])

    @staticmethod
    def step(action=4, legal=True):
        mask = [1] * 7
        if not legal:
            mask[4] = 0
        return {"action": action, "mask": mask}

    @staticmethod
    def worlds():
        seed = 519024
        rows = {}
        for arm in ARMS:
            rows[(seed, arm)] = {"seed": seed, "strategy": arm,
                                 "success": arm == ARMS[2],
                                 "unsafe": False, "abstained": False,
                                 "contacts": 1 if arm == ARMS[2] else 0,
                                 "terminal_dwell_ticks": 250 if arm == ARMS[2] else 0,
                                 "final_error": .01 if arm == ARMS[2] else 1.0}
        return rows

    def test_incidental_v5_fallback_right4_is_not_exploration(self):
        evidence = self.instances(519024, ARMS[2], [self.step(4)], ["frozen_v5"])
        self.assertEqual(evidence, [])
        self.assertIn("STOP", self.science(self.worlds(), evidence))

    def test_real_active_legal_burst_right4_is_attributed_to_same_arm(self):
        evidence = self.instances(
            519024, ARMS[2],
            [self.step(4), self.step(4)],
            ["frozen_v5", "UNTRAINED_RIGHT4_EXPLORATION_ONLY"])
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["option_index"], 1)
        self.assertEqual(evidence[0]["strategy"], ARMS[2])
        self.assertEqual(self.science(self.worlds(), evidence),
                         "TRAIN_ONLY_SCIENCE_HYPOTHESIS_REQUIRES_NEW_REVIEW")

    def test_unrelated_burst_arm_cannot_satisfy_novel_goal(self):
        evidence = self.instances(
            519024, ARMS[3], [self.step(4)],
            ["UNTRAINED_RIGHT4_EXPLORATION_ONLY"])
        self.assertIn("STOP", self.science(self.worlds(), evidence))

    def test_unrelated_world_burst_cannot_satisfy_novel_goal(self):
        evidence = self.instances(
            519025, ARMS[2], [self.step(4)],
            ["UNTRAINED_RIGHT4_EXPLORATION_ONLY"])
        with self.assertRaisesRegex(AssertionError, "V13_UNTRUSTED_BURST"):
            self.science(self.worlds(), evidence)

    def test_missing_or_short_mode_history_fails_closed(self):
        for modes in (None, [], ["frozen_v5", "frozen_v5"]):
            with self.subTest(modes=modes):
                with self.assertRaisesRegex(AssertionError, "V13_BURST_MODE_HISTORY"):
                    self.instances(519024, ARMS[2], [self.step()], modes)

    def test_unknown_mode_fails_closed(self):
        with self.assertRaisesRegex(AssertionError, "V13_BURST_MODE_OR_ORIGINAL"):
            self.instances(519024, ARMS[2], [self.step()], ["UNVERIFIED_BURST"])

    def test_mode_without_actual_action4_fails_closed(self):
        with self.assertRaisesRegex(AssertionError, "V13_BURST_MODE_REQUIRES"):
            self.instances(519024, ARMS[2], [self.step(3)],
                           ["UNTRAINED_RIGHT4_EXPLORATION_ONLY"])

    def test_mode_with_illegal_original_mask_fails_closed(self):
        with self.assertRaisesRegex(AssertionError, "V13_BURST_MODE_OR_ORIGINAL"):
            self.instances(519024, ARMS[2], [self.step(4, legal=False)],
                           ["UNTRAINED_RIGHT4_EXPLORATION_ONLY"])

    def test_non_burst_strategy_cannot_claim_mode(self):
        with self.assertRaisesRegex(AssertionError, "V13_BURST_MODE_HISTORY"):
            self.instances(519024, ARMS[0], [self.step()],
                           ["UNTRAINED_RIGHT4_EXPLORATION_ONLY"])

    def test_missing_or_fake_instances_cannot_pass_science(self):
        with self.assertRaisesRegex(AssertionError, "V13_UNTRUSTED_BURST"):
            self.science(self.worlds(), [{"seed": 519024, "strategy": ARMS[2],
                                         "option_index": 0, "original_seven_mask": [1]}])
        with self.assertRaisesRegex(AssertionError, "V13_UNTRUSTED_BURST"):
            self.science(self.worlds(), 1)

    def test_producer_and_replay_bind_same_pinned_mode_history(self):
        # A structural integration guard; actual original MuJoCo replay remains
        # a separate mandatory hosted qualification, never emulated here.
        self.assertIn('row["source_policy_mode_history"] = list(modes)', self.source)
        self.assertIn('replay_modes == row.get("source_policy_mode_history")', self.source)
        self.assertIn('source_bound_burst_right4_instances(\n                    doc["seed"]', self.source)
        self.assertIn('action4 == training["observed_exploration_action4_instances"]', self.source)
        self.assertIn('science = independent_science_gate(rows, replay["untrained_right4_actual_legal_instances"])', self.source)


if __name__ == "__main__":
    unittest.main()
