import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("audit_cloud", Path(__file__).with_name("cloud.py"))
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


class TransportBoundaries(unittest.TestCase):
    def package(self, source=b"def f(): return 1\n", name="source/app.py", symlink=False, wrong_hash=False):
        entry = {"repository": "SalesSquad/example", "source_sha": "a" * 40}
        inventory = {**entry, "files": [{"path": "app.py", "bytes": len(source),
                                       "sha256": "f" * 64 if wrong_hash else cloud.digest(source)}]}
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:gz") as out:
            for member_name, payload in [("files.json", json.dumps(inventory).encode()), (name, source)]:
                item = tarfile.TarInfo(member_name)
                item.size = len(payload)
                if symlink and member_name == name:
                    item.type, item.linkname, item.size = tarfile.SYMTYPE, "/etc/passwd", 0
                out.addfile(item, io.BytesIO(payload))
        return data.getvalue(), entry

    def test_verified_source_roundtrip_and_tamper_refusal_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data, entry = self.package()
            inventory = cloud.unpack(data, root / "valid", entry)
            self.assertEqual(len(inventory["files"]), 1)
            self.assertEqual((root / "valid/source/app.py").read_bytes(), b"def f(): return 1\n")
            data, entry = self.package(wrong_hash=True)
            with self.assertRaises(ValueError):
                cloud.unpack(data, root / "invalid", entry)
            self.assertFalse((root / "invalid").exists())

    def test_traversal_and_symlinks_refused_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i, kwargs in enumerate(({"name": "source/../../escape.py"}, {"symlink": True})):
                data, entry = self.package(**kwargs)
                target = root / str(i)
                with self.assertRaises(ValueError):
                    cloud.unpack(data, target, entry)
                self.assertFalse(target.exists())
            self.assertFalse((root / "escape.py").exists())

    def test_analyzers_do_not_receive_publishing_or_provider_credentials(self):
        with patch.dict(os.environ, {"PATH": "/bin", "GH_TOKEN": "fake-test-token", "GITHUB_TOKEN": "fake-test-token",
                                    "OPENAI_API_KEY": "fake-test-key", "PYTHONPATH": "/tmp/untrusted", "LD_PRELOAD": "bad"}, clear=True):
            env = cloud.child_environment()
            self.assertEqual(env["PATH"], "/bin")
            self.assertFalse(set(env) & {"GH_TOKEN", "GITHUB_TOKEN", "OPENAI_API_KEY", "PYTHONPATH", "LD_PRELOAD"})

    def test_admission_refuses_another_run(self):
        with patch.object(cloud, "context", return_value=("a" * 40, "123")), patch.object(cloud, "download", return_value=json.dumps({
            "harness_sha": "a" * 40, "run_id": "456", "manifest_sha256": "b" * 64, "deadline": cloud.DEADLINE}).encode()):
            with self.assertRaises(ValueError):
                cloud.admission("craci-repo-audit-20261115-01", "b" * 64)

    def test_public_or_shared_source_destination_refused(self):
        with patch.object(cloud, "_PRIVATE", False), patch.object(cloud, "gh", return_value={"full_name": cloud.REPO, "private": False}):
            with self.assertRaises(ValueError):
                cloud.private_destination()
        with patch.object(cloud, "_PRIVATE", False), patch.object(cloud, "gh", side_effect=[
            {"full_name": cloud.REPO, "private": True}, [{"login": "SalesSquad"}, {"login": "another-user"}]]):
            with self.assertRaises(ValueError):
                cloud.private_destination(owner_only=True)


if __name__ == "__main__":
    unittest.main()
