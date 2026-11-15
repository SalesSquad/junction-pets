"""Portable contract tests; real readout is separately checked on CRACI V7 raw bytes."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE = Path(__file__).with_name("rokoko-mujoco-v7-stage-readout.py")
spec = importlib.util.spec_from_file_location("craci_v7_stage_readout", MODULE)
readout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(readout)


class LearningReadoutContracts(unittest.TestCase):
    def test_continuous_quantiles_not_threshold_rewriting(self):
        self.assertEqual(readout.quantile([.0, .03, .01, .02], .5), .015)
        self.assertEqual(readout.quantile([.0, .01], .95), .0095)
        self.assertIsNone(readout.quantile([], .5))

    def test_canonical_trial_hash_deterministic(self):
        self.assertEqual(readout.digest([{"b": 2, "a": 1}]),
                         readout.digest([{"a": 1, "b": 2}]))

    def test_incomplete_or_heldout_evidence_cannot_be_mined(self):
        with tempfile.TemporaryDirectory(prefix="v7-readout-negative-") as directory:
            root = Path(directory)
            raw = root / "full_transitions.jsonl.gz"
            raw.write_bytes(b"invalid untrusted fake raw")
            training = root / "training.json"
            training.write_text(json.dumps({"no_dev_evaluation": False}))
            (root / "manifest.json").write_text("{}")
            (root / "independent-qualification.json").write_text(json.dumps({
                "experiment_complete": False, "dev_cal_test_ood_opened": True,
                "promotion_authorized": False}))
            (root / "independent-positive-replay.json").write_text(json.dumps({
                "claim_verified": False, "no_dev_cal_test_ood": False}))
            (root / "receipt.json").write_text("{}")
            with self.assertRaisesRegex(AssertionError,
                                        "TRAIN_ONLY_INDEPENDENT_QUALIFICATION_REQUIRED"):
                readout.readout(training, raw, root, root / "receipt.json")


if __name__ == "__main__":
    unittest.main()
