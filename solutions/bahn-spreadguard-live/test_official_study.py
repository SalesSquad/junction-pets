"""Concrete preflight/resume safety checks; never create a sponsor world."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from official_study import freeze_entry, resolve_configuration, run_practice, validate_freeze


class StudyPreflight(unittest.TestCase):
    def args(self, **changes):
        data = dict(model=None, late_threshold=None, policy="baseline")
        data.update(changes)
        return argparse.Namespace(**data)

    def test_environment_threshold_is_frozen_into_effective_config(self):
        with patch.dict(os.environ, {"SPREAD_RELIABILITY_MODEL": "",
                                     "SPREAD_RELIABILITY_LATE_THRESHOLD": "0.02",
                                     "SPREAD_GUARD_POLICY": "risk_budget"}):
            args = self.args()
            resolve_configuration(args)
            self.assertEqual(args.late_threshold, 0.02)
            os.environ["SPREAD_RELIABILITY_LATE_THRESHOLD"] = "0.15"
            resolve_configuration(args)
            self.assertEqual(args.late_threshold, 0.02)

    def test_invalid_threshold_never_opens_client(self):
        with patch.dict(os.environ, {"SPREAD_RELIABILITY_MODEL": "",
                                     "SPREAD_RELIABILITY_LATE_THRESHOLD": "nan"}), \
                patch("official_study.Client") as client:
            with self.assertRaisesRegex(ValueError, "finite"):
                run_practice(self.args())
            client.assert_not_called()

    def test_missing_learned_model_never_opens_client(self):
        with patch.dict(os.environ, {"SPREAD_RELIABILITY_MODEL": ""}), \
                patch("official_study.Client") as client:
            with self.assertRaisesRegex(ValueError, "requires"):
                run_practice(self.args(policy="learned"))
            client.assert_not_called()

    def test_incompatible_fee_policy_never_opens_client(self):
        with patch.dict(os.environ, {"SPREAD_RELIABILITY_MODEL": "",
                                     "SPREAD_RELIABILITY_LATE_THRESHOLD": "",
                                     "SPREAD_GUARD_POLICY": "greedy"}), \
                patch("official_study.Client") as client:
            with self.assertRaisesRegex(ValueError, "risk_budget"):
                run_practice(self.args())
            client.assert_not_called()

    def test_second_writer_cannot_open_client_or_overwrite_receipt(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"SPREAD_RELIABILITY_MODEL": "",
                                        "SPREAD_RELIABILITY_LATE_THRESHOLD": "",
                                        "SPREAD_GUARD_POLICY": "risk_budget"}), \
                patch("official_study.Client") as client:
            receipt = Path(tmp) / "run.json"
            receipt.write_text('{"sentinel":"other writer owns this directory"}')
            with (Path(tmp) / ".study.lock").open("a") as first:
                fcntl.flock(first, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):
                    run_practice(self.args(output=tmp))
            client.assert_not_called()
            self.assertEqual(receipt.read_text(), '{"sentinel":"other writer owns this directory"}')

    def test_changed_source_or_threshold_fails_before_client_creation(self):
        source = {"source_sha": "a" * 40, "files_sha256": {"policy.py": "b" * 64},
                  "model_sha256": None}
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"SPREAD_RELIABILITY_MODEL": "",
                                        "SPREAD_RELIABILITY_LATE_THRESHOLD": "",
                                        "SPREAD_GUARD_POLICY": "risk_budget"}), \
                patch("official_study.Client") as client, \
                patch("official_study.provenance", return_value=source):
            path = Path(tmp) / "freeze.json"
            args = self.args(output=tmp, late_threshold=0.05, freeze_manifest=str(path))
            valid = {"schemaVersion": 1, "source_sha": source["source_sha"],
                     "policies": {"baseline": freeze_entry(args, source)}}
            path.write_text(json.dumps(valid))
            self.assertEqual(len(validate_freeze(args, source)), 64)
            for key, value in [("late_threshold", 0.02),
                               ("files_sha256", {"policy.py": "c" * 64}),
                               ("model_sha256", "d" * 64)]:
                changed = json.loads(json.dumps(valid))
                changed["policies"]["baseline"][key] = value
                path.write_text(json.dumps(changed))
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, "frozen"):
                    run_practice(args)
            client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
