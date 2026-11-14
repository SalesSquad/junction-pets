"""Concrete preflight/resume safety checks; never create a sponsor world."""
import argparse
import os
import unittest
from unittest.mock import patch

from official_study import resolve_configuration, run_practice


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


if __name__ == "__main__":
    unittest.main()
