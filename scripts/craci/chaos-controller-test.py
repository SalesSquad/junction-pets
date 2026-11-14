#!/usr/bin/env python3
"""Offline controller chaos tests. Every GitHub call is mocked; no spending."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name("chaos-controller.py")
spec = importlib.util.spec_from_file_location("chaos_controller", SOURCE)
ctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctl)


class ControllerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="craci-chaos-controller-test-")
        self.addCleanup(self.temp.cleanup)
        self.journal = Path(self.temp.name) / "journal.jsonl"
        ctl.record(self.journal, type="dispatched", epoch=3, runId=123)
        self.run = {"databaseId": 123, "status": "completed", "conclusion": "success"}

    @staticmethod
    def github(args):
        if args[:2] == ["run", "view"]:
            return {"jobs": [{"name": f"Chaos Lab / {name} / seed {i}", "conclusion": "success"}
                             for i, name in enumerate(ctl.PROFILES)]}
        if args[:1] == ["api"] and str(args[1]).endswith("/artifacts"):
            return {"artifacts": [{"name": f"craci-chaos-chaos-3-{name}-123-1",
                                   "expired": False} for name in ctl.PROFILES]}
        raise AssertionError(f"Unexpected GitHub mock request: {args}")

    def test_four_valid_source_bounded_receipts_unlock_next_epoch(self):
        with patch.object(ctl,"gh_json",side_effect=self.github):
            self.assertTrue(ctl.verified_owned(self.journal,[self.run]))
        events = ctl.journal_rows(self.journal)
        self.assertEqual(events[-1]["type"],"verified-success")
        self.assertEqual(events[-1]["receipts"],4)

    def test_previous_wave_still_running_does_not_unlock(self):
        self.assertFalse(ctl.verified_owned(self.journal,[{**self.run,"status":"in_progress"}]))
        self.assertEqual(len(ctl.journal_rows(self.journal)),1)

    def test_any_failed_cloud_job_blocks_further_spend(self):
        with self.assertRaisesRegex(RuntimeError,"FAILED_RUN_123"):
            ctl.verified_owned(self.journal,[{**self.run,"conclusion":"failure"}])

    def test_missing_artifact_is_never_success(self):
        def missing(args):
            result=self.github(args)
            if args[:1] == ["api"]:
                result["artifacts"].pop()
            return result
        with patch.object(ctl,"gh_json",side_effect=missing):
            with self.assertRaisesRegex(RuntimeError,"MISSING_RECEIPTS_123"):
                ctl.verified_owned(self.journal,[self.run])

    def test_missing_run_is_ambiguous_and_stops(self):
        with self.assertRaisesRegex(RuntimeError,"UNVERIFIED_RUN_123"):
            ctl.verified_owned(self.journal,[])

    def test_credit_closed_is_hard_stop(self):
        with patch.object(ctl,"gh_json",return_value={"value":"false"}):
            with self.assertRaisesRegex(RuntimeError,"CREDIT_WINDOW_CLOSED"):
                ctl.verify_remote("a"*40)

    def test_remote_sha_drift_is_hard_stop(self):
        values=iter([{"value":"true"},{"object":{"sha":"b"*40}}])
        with patch.object(ctl,"gh_json",side_effect=lambda _:next(values)):
            with self.assertRaisesRegex(RuntimeError,"SOURCE_PIN_CHANGED"):
                ctl.verify_remote("a"*40)

    def test_cancel_only_this_controllers_active_run(self):
        active=[{"databaseId":123,"status":"in_progress"},
                {"databaseId":999,"status":"in_progress"}]
        with patch.object(ctl,"recent_runs",return_value=active), patch.object(ctl,"gh") as call:
            ctl.cancel_own_active(self.journal)
            call.assert_called_once_with(["run","cancel","123","--repo",ctl.REPO])

    def test_restart_stops_on_lost_dispatch_ack(self):
        rows=[{"type":"dispatch-attempt","epoch":4}]
        with self.assertRaisesRegex(RuntimeError,"UNRESOLVED_DISPATCH_INTENT"):
            ctl.validate_intent_history(rows)

    def test_restart_stops_on_duplicate_intent(self):
        rows=[{"type":"dispatch-attempt","epoch":4},
              {"type":"dispatch-attempt","epoch":4},
              {"type":"dispatched","epoch":4,"runId":321}]
        with self.assertRaisesRegex(RuntimeError,"DUPLICATE_DISPATCH_LEDGER"):
            ctl.validate_intent_history(rows)

    def test_restart_accepts_exact_one_to_one_intent_ack(self):
        rows=[{"type":"dispatch-attempt","epoch":3},
              {"type":"dispatched","epoch":3,"runId":123}]
        self.assertIsNone(ctl.validate_intent_history(rows))


if __name__ == "__main__":
    unittest.main()
