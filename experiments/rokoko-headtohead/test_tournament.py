"""Unsealed contract tests. Do not import or sample locked simulator worlds."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from dataclasses import dataclass
from types import SimpleNamespace

from tournament import (ARENA_SHA256, SPLITS, TD_SOURCE, TD_WEIGHTS,
                        V2_SOURCE, V2_WEIGHTS, frozen_td_digest,
                        paired_metric, compare_one_split, sample_definition,
                        verify_shared_simulator)


class SplitContracts(unittest.TestCase):
    def test_dev_prelock_partial(self):
        self.assertEqual(sample_definition("dev", 4, False), ("dev", 128500, 4))

    def test_cal_prelock_full(self):
        self.assertEqual(sample_definition("cal", None, False), ("cal", 228500, 100))

    def test_reject_unconfirmed_test(self):
        with self.assertRaisesRegex(ValueError, "LOCKBOX"):
            sample_definition("locked_test", None, False)

    def test_reject_unconfirmed_ood(self):
        with self.assertRaisesRegex(ValueError, "LOCKBOX"):
            sample_definition("locked_ood", 300, False)

    def test_reject_partial_test_even_when_confirmed(self):
        with self.assertRaisesRegex(ValueError, "LOCKBOX"):
            sample_definition("locked_test", 499, True)

    def test_reject_partial_ood_even_when_confirmed(self):
        with self.assertRaisesRegex(ValueError, "LOCKBOX"):
            sample_definition("locked_ood", 100, True)

    def test_new_preregistered_full_windows(self):
        self.assertEqual(sample_definition("locked_test", None, True), ("test", 327000, 500))
        self.assertEqual(sample_definition("locked_ood", None, True), ("ood", 427000, 300))

    def test_reject_invalid_sizes_and_unknown(self):
        for arguments in (("dev", 0, False), ("dev", 101, False),
                          ("locked_test", 501, True), ("invalid", None, True)):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                sample_definition(*arguments)

    def test_reserved_windows_are_mutually_disjoint(self):
        original = ((320000, 320299), (420000, 420199),
                    (325000, 325299), (425000, 425199),
                    (326000, 326299), (426000, 426199),
                    (329000, 329199), (429000, 429199))
        ours = tuple((s[1], s[1]+s[2]-1) for k, s in SPLITS.items() if k.startswith("locked"))
        for left, right in ours:
            for other_left, other_right in original:
                self.assertTrue(right < other_left or left > other_right)

    def test_frozen_hashes_explicit(self):
        for digest in (V2_SOURCE, TD_SOURCE, V2_WEIGHTS, TD_WEIGHTS, ARENA_SHA256):
            self.assertRegex(digest, r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")

    def test_mismatched_simulator_reports_role_file_and_digest_before_scoring(self):
        with tempfile.TemporaryDirectory() as temp:
            v2 = Path(temp) / "v2"
            td = Path(temp) / "td"
            for root in (v2, td):
                source = root / "solutions/rokoko-teleoperation-gym/learning/action_necessity"
                source.mkdir(parents=True)
                (source / "arena.py").write_text("not-the-frozen-source\n")
                (source / "run.py").write_text("not-the-frozen-source\n")
            with self.assertRaisesRegex(ValueError,
                                        r"SHARED_SIMULATOR_SHA_MISMATCH role=v2 file=arena\.py "
                                        r"expected=[0-9a-f]{64} observed=[0-9a-f]{64}"):
                verify_shared_simulator(v2, td)


class MetricContracts(unittest.TestCase):
    def fixture(self):
        a = [{"seed": n, "success": n in (1, 2, 4), "unsafe": n == 0,
              "holds": 5+n, "refusals": 6+n, "aborted": False, "reobservations": 2+n}
             for n in range(5)]
        b = [{"seed": n, "success": n in (0, 2), "unsafe": n in (0, 3),
              "holds": 8+n, "refusals": 9+n, "aborted": False, "reobservations": 4+n}
             for n in range(5)]
        return a, b

    def test_paired_success_delta(self):
        a, b = self.fixture()
        result = paired_metric(a, b, "success", reps=200)
        self.assertEqual(result["a_minus_b_mean"], 20.0)
        self.assertEqual(result["units"], "percentage_points")

    def test_paired_hold_delta(self):
        a, b = self.fixture()
        result = paired_metric(a, b, "holds", reps=200)
        self.assertEqual(result["a_minus_b_mean"], -3.0)
        self.assertEqual(result["paired_bootstrap_95"], [-3.0, -3.0])

    def test_paired_unsafe_delta(self):
        a, b = self.fixture()
        self.assertEqual(paired_metric(a, b, "unsafe", reps=200)["a_minus_b_mean"], -20.0)

    def test_paired_metric_deterministic(self):
        a, b = self.fixture()
        self.assertEqual(paired_metric(a, b, "success", reps=200),
                         paired_metric(a, b, "success", reps=200))

    def test_paired_seed_mismatch_refused(self):
        a, b = self.fixture()
        b[2]["seed"] = 99
        with self.assertRaisesRegex(ValueError, "UNPAIRED"):
            paired_metric(a, b, "success", reps=200)

    def test_paired_unsupported_metric_refused(self):
        a, b = self.fixture()
        with self.assertRaisesRegex(ValueError, "UNREGISTERED"):
            paired_metric(a, b, "secret", reps=200)

    def test_paired_empty_and_length_mismatch_refused(self):
        a, b = self.fixture()
        with self.assertRaises(ValueError):
            paired_metric([], [], "success", reps=200)
        with self.assertRaises(ValueError):
            paired_metric(a, b[:-1], "success", reps=200)

    def test_td_digest_matches_producer_rounding(self):
        class Dummy:
            weights = [{("bias",): 0.123456789012345}, {("age", 1): -0.9}]
        expected = [[(repr(("bias",)), round(0.123456789012345, 12))],
                    [(repr(("age", 1)), round(-0.9, 12))]]
        checksum = hashlib.sha256(json.dumps(expected, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(frozen_td_digest(Dummy()), checksum)

    def test_shared_world_builder_uses_same_world_per_policy(self):
        @dataclass(frozen=True)
        class World:
            split: str
            seed: int

        seen = {}

        def fake_episode(world, policy, factory):
            seen.setdefault(world.seed, []).append(id(world))
            self.assertTrue(callable(factory()))
            return {"seed": world.seed, "policy": policy,
                    "success": policy != "shielded_forward", "unsafe": False,
                    "aborted": False, "holds": 1, "refusals": 2, "reobservations": 1}

        fake_arena = SimpleNamespace(make_world=lambda split, seed: World(split, seed),
                                     run_episode=fake_episode,
                                     constant_forward=lambda o: 0)
        fake_paired = SimpleNamespace(
            summarize=lambda rows: {"episodes": len(rows),
                                    "success": sum(int(r["success"]) for r in rows)},
            paired_bootstrap=lambda a, b: {"delta_pp": sum(int(x["success"])-int(y["success"])
                                                           for x, y in zip(a, b)) * 100 / len(a)},
        )
        fake_policy = SimpleNamespace(FittedForest=lambda trees: lambda o: 0)
        fake_td = SimpleNamespace(guarded_constant_forward=lambda o: 0)
        frozen_v2 = SimpleNamespace(trees=["read-only"])
        td_agent = SimpleNamespace(action=lambda o: 0)
        result = compare_one_split(fake_arena, fake_paired, fake_policy, fake_td,
                                   frozen_v2, td_agent, "dev", 128500, 2)
        self.assertEqual(result["seed_range"], [128500, 128501])
        self.assertEqual(result["summaries"]["v2"]["episodes"], 2)
        self.assertEqual(len(result["per_world"]["td"]), 2)
        self.assertEqual(len(result["world_fingerprints"]), 2)
        self.assertEqual(set(seen), {128500, 128501})
        self.assertTrue(all(len(v) == 4 and len(set(v)) == 1 for v in seen.values()))


if __name__ == "__main__":
    unittest.main()
