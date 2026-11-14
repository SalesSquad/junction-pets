"""Scoped tests for local scheduled source-bound ingestion plumbing."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).with_name("auto_sync.py")
spec = importlib.util.spec_from_file_location("auto_sync", SOURCE)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class SyncTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.owner = self.root / "owner"
        self.source = self.root / "repo"
        api.owner_dir(self.owner)
        api.owner_dir(self.owner / "inbox")
        (self.source / "ops/experiments/runs").mkdir(parents=True)

    def make_event(self, name, match=True):
        run = {"runId": name, "status": "incomplete"}
        file = self.owner / "inbox" / (name + ".json")
        file.write_text(json.dumps({"schemaVersion": 1, "run": run, "receipt": {}}))
        if match:
            (self.source / "ops/experiments/runs" / (name + ".json")).write_text(json.dumps(run))
        return file

    def test_moves_only_exact_main_records_and_preserves_bytes(self):
        yes = self.make_event("verda.auto-good", match=True)
        no = self.make_event("verda.auto-not-yet", match=False)
        before = yes.read_bytes()
        self.assertEqual(api.archive_merged_envelopes(self.owner, self.source), 1)
        self.assertFalse(yes.exists())
        self.assertEqual((self.owner / "archive" / yes.name).read_bytes(), before)
        self.assertTrue(no.exists())
        self.assertEqual(api.archive_merged_envelopes(self.owner, self.source), 0)

    def test_conflicting_main_does_not_archive(self):
        file = self.make_event("verda.auto-conflict")
        target = self.source / "ops/experiments/runs" / file.name
        target.write_text(json.dumps({"runId": "verda.auto-conflict", "status": "succeeded"}))
        self.assertEqual(api.archive_merged_envelopes(self.owner, self.source), 0)
        self.assertTrue(file.exists())

    def test_rejects_untrusted_owner_folder_permissions(self):
        bad = self.root / "bad"
        bad.mkdir(mode=0o755)
        bad.chmod(0o755)
        with self.assertRaises(ValueError):
            api.owner_dir(bad)


if __name__ == "__main__":
    unittest.main()
