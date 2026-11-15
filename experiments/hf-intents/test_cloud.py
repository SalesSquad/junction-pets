import datetime as dt
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("intent_cloud", Path(__file__).with_name("cloud.py"))
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


class CloudBoundaries(unittest.TestCase):
    def test_deadline_refuses_equality_and_after(self):
        end = cloud.instant(cloud.DEADLINE)
        cloud.before(cloud.DEADLINE, end - dt.timedelta(microseconds=1))
        for now in (end, end + dt.timedelta(days=1)):
            with self.assertRaises(ValueError):
                cloud.before(cloud.DEADLINE, now)

    def test_identity_and_source_binding(self):
        for source, run, tag in (("bad", "123", cloud.TAG), ("a" * 40, "../123", cloud.TAG),
                                  ("a" * 40, "123", "another-campaign")):
            with self.assertRaises(ValueError):
                cloud.identities(source, run, tag)
        receipt = {"source_sha": "a" * 40, "run_id": "123", "dataset": "banking77", "lane": "word_svm"}
        cloud.binding(receipt, "a" * 40, "123", "banking77", "word_svm")
        with self.assertRaises(ValueError):
            cloud.binding(receipt, "b" * 40, "123", "banking77", "word_svm")
        with self.assertRaises(ValueError):
            cloud.binding(receipt, "a" * 40, "124", "banking77", "word_svm")

    def package(self, root, extra=None):
        model = b"not executed: opaque skops test data"
        best = {"source_sha": "a" * 40, "run_id": "123", "dataset": "banking77", "lane": "word_svm",
                "model_sha256": hashlib.sha256(model).hexdigest()}
        metadata = dict(best, manifest_sha256="m" * 64,
                        history_sha256=hashlib.sha256(b"").hexdigest())
        members = {"best.skops": model, "best.json": json.dumps(best).encode(),
                   "metadata.json": json.dumps(metadata).encode(), "history.jsonl": b""}
        if extra:
            members.update(extra)
        path = root / "checkpoint.tar.gz"
        cloud.pack_checkpoint(members, path)
        return path

    def test_archive_success_does_not_execute_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = self.package(root)
            best = cloud.unpack_checkpoint(archive, root / "unpacked", "a" * 40, "123", "banking77", "word_svm", "m" * 64)
            self.assertEqual(best["dataset"], "banking77")
            self.assertTrue((root / "unpacked" / "best.skops").is_file())

    def test_archive_path_traversal_and_unknown_members_refused(self):
        for name in ("../escape", "/tmp/escape", "extra.py"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                archive = self.package(root, {name: b"not executed"})
                with self.assertRaises(ValueError):
                    cloud.unpack_checkpoint(archive, root / "unpacked", "a" * 40, "123", "banking77", "word_svm", "m" * 64)
                self.assertFalse((root / "escape").exists())

    def test_archive_symlink_and_oversize_refused(self):
        for symbolic in (True, False):
            with self.subTest(symbolic=symbolic), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                archive = root / "bad.tar.gz"
                with tarfile.open(archive, "w:gz") as package:
                    for name in ("best.skops", "best.json", "metadata.json", "history.jsonl"):
                        member = tarfile.TarInfo(name)
                        data = b""
                        if name == "best.skops" and symbolic:
                            member.type, member.linkname = tarfile.SYMTYPE, "/etc/passwd"
                        elif name == "best.json" and not symbolic:
                            data = b"x" * (cloud.MEMBER_LIMITS[name] + 1)
                            member.size = len(data)
                        package.addfile(member, io.BytesIO(data))
                with self.assertRaises(ValueError):
                    cloud.unpack_checkpoint(archive, root / "out", "a" * 40, "123", "banking77", "word_svm", "m" * 64)
                if not symbolic:
                    self.assertFalse((root / "out" / "best.json").exists())

    def test_checkpoint_source_mismatch_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = self.package(root)
            with self.assertRaises(ValueError):
                cloud.unpack_checkpoint(archive, root / "out", "b" * 40, "123", "banking77", "word_svm", "m" * 64)

    def test_history_and_model_tampering_refused(self):
        for member in ("best.skops", "history.jsonl"):
            with self.subTest(member=member), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                archive = self.package(root, {member: b"different bytes"})
                with self.assertRaises(ValueError):
                    cloud.unpack_checkpoint(archive, root / "out", "a" * 40, "123", "banking77", "word_svm", "m" * 64)

    def test_latest_sequence_not_lexicographic_or_cross_lane(self):
        items = [{"name": "banking77-word_svm-s0002.tar.gz"}, {"name": "banking77-word_svm-s0010.tar.gz"},
                 {"name": "banking77-char_svm-s0003.tar.gz"}, {"name": "banking77-word_svm-s0009.tar.gz.old"}]
        selected = cloud.latest_checkpoints(items)
        self.assertEqual(selected[("banking77", "word_svm")][0], 10)
        self.assertEqual(selected[("banking77", "char_svm")][0], 3)

    def test_child_does_not_receive_publication_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = root / "environment.json"
            program = "import os,json,sys;open(sys.argv[1],'w').write(json.dumps(dict(os.environ)))"
            with patch.dict("os.environ", {"GH_TOKEN": "test-secret", "GITHUB_TOKEN": "another-secret",
                                           "ACTIONS_RUNTIME_TOKEN": "runtime-secret", "RUNNER_TRACKING_ID": "task-tracking"}):
                status = cloud.run_child([sys.executable, "-c", program, str(result)], root / "child.log", 3)
            self.assertEqual(status, 0)
            child = json.loads(result.read_text())
            for secret in ("GH_TOKEN", "GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN"):
                self.assertNotIn(secret, child)
            self.assertEqual(child["RUNNER_TRACKING_ID"], "task-tracking")

    def test_child_time_bound_delivers_termination(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = root / "terminated"
            program = ("import signal,time,sys;"
                       "signal.signal(signal.SIGTERM,lambda *_:(open(sys.argv[1],'w').write('terminated'),sys.exit(0)));"
                       "time.sleep(20)")
            with self.assertRaises(subprocess.TimeoutExpired):
                cloud.run_child([sys.executable, "-c", program, str(result)], root / "child.log", 1)
            self.assertEqual(result.read_text(), "terminated")

    def test_credential_bearing_upload_redirect_refused(self):
        request = cloud.urllib.request.Request("https://uploads.github.com/", headers={"Authorization": "Bearer test"})
        with self.assertRaises(ValueError):
            cloud.NoGitHubRedirects().redirect_request(request, None, 302, "Found", {}, "https://another.example/")


if __name__ == "__main__":
    unittest.main()
