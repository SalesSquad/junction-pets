"""Positive/negative synthetic adapter tests; never touches an actual Verda account."""
from pathlib import Path
import importlib.util
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
import hashlib
import sys

MODULE = Path(__file__).with_name("verda_collect.py")
spec = importlib.util.spec_from_file_location("verda_collect", MODULE)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class VerdaCollectorTests(unittest.TestCase):
    def setUp(self):
        self.context = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.addCleanup(self.context.cleanup)
        self.root = Path(self.context.name)
        self.db = self.root / "jobs.sqlite3"
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE jobs (job_id TEXT, state TEXT, gpus INTEGER, updated REAL, spec TEXT)")
        con.commit()
        con.close()
        self.reg = self.root / "registry"
        (self.reg / "runs").mkdir(parents=True)
        self.inbox = self.root / "inbox"
        self.receipts = self.root / "receipts"

    def insert(self, job_id="test-gpu-001", state="stopped", updated=1794610012.234, gpus=1):
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO jobs VALUES (?,?,?,?,?)", (job_id, state, gpus, updated,
                    json.dumps({"source_commit": "a" * 40, "ssh_key_id": "PRIVATE-SHOULD-NOT-APPEAR"})))
        con.commit()
        con.close()

    def test_emits_no_secret_and_replays_immutably(self):
        self.insert()
        out = adapter.emit_jobs(self.db, self.reg, self.inbox, self.receipts)
        self.assertEqual(out["envelopesCreated"], 1)
        envelope = next(self.inbox.glob("*.json"))
        e = json.loads(envelope.read_text())
        self.assertEqual(e["run"]["status"], "incomplete")
        self.assertFalse(e["run"]["status"] == "succeeded")
        self.assertNotIn("PRIVATE-SHOULD-NOT-APPEAR", envelope.read_text())
        self.assertEqual((self.inbox.stat().st_mode & 0o077), 0)
        self.assertEqual((self.receipts.stat().st_mode & 0o077), 0)
        receipt = self.receipts / e["receipt"]["path"]
        self.assertEqual(hashlib.sha256(receipt.read_bytes()).hexdigest(), e["receipt"]["sha256"])
        self.assertEqual(adapter.emit_jobs(self.db, self.reg, self.inbox, self.receipts)["existing"], 1)
        a = subprocess.run(["node", str(MODULE.with_name("inbox.mjs")), "--inbox", str(self.inbox),
                            "--receipts-root", str(self.receipts), "--root", str(self.reg)],
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(a.returncode, 0, a.stdout + a.stderr)
        self.assertEqual(json.loads(a.stdout)["created"], 1)
        self.assertEqual(json.loads(subprocess.run(
            ["node", str(MODULE.with_name("inbox.mjs")), "--inbox", str(self.inbox),
             "--receipts-root", str(self.receipts), "--root", str(self.reg)],
            capture_output=True, text=True, timeout=20).stdout)["existing"], 1)

    def test_original_legacy_record_prevents_duplicate(self):
        self.insert()
        legacy = self.reg / "runs" / "verda.lease.test-gpu-001.json"
        legacy.write_text(json.dumps({"capturedAt": "2026-11-14T00:06:52.234Z"}))
        # Legacy expected timestamp uses actual job.updated; update above to match.
        import datetime as dt
        con = sqlite3.connect(self.db)
        value = con.execute("SELECT updated FROM jobs").fetchone()[0]
        con.close()
        t = dt.datetime.fromtimestamp(value, tz=dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        legacy.write_text(json.dumps({"capturedAt": t}))
        out = adapter.emit_jobs(self.db, self.reg, self.inbox, self.receipts)
        self.assertEqual(out["envelopesCreated"], 0)
        self.assertEqual(out["existing"], 1)

    def test_invalid_identifier_and_bad_source_are_skipped(self):
        self.insert(job_id="../../secret")
        self.insert(job_id="good-job", gpus=0)
        out = adapter.emit_jobs(self.db, self.reg, self.inbox, self.receipts)
        self.assertEqual(out["envelopesCreated"], 0)
        self.assertEqual(out["unadmitted"], 2)
        self.assertEqual(list(self.inbox.glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
