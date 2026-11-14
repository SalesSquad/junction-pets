"""CRACI's real size/extension caps remain fixed; v7 stores exact ZIP parts."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


MODULE = Path(__file__).with_name("rokoko-mujoco-v7-retain-evidence.py")
spec = importlib.util.spec_from_file_location("craci_v7_retention", MODULE)
retained = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retained)


def fixture(root, corrupt_manifest=False):
    artifacts = root / "artifacts" / "rokoko-mujoco-v7-feasibility"
    artifacts.mkdir(parents=True)
    originals = {"training.json": b'{"trials":[1,2,3]}\n' * 41,
                 "full_transitions.jsonl.gz": bytes(range(256)) * 4}
    for name, raw in originals.items():
        (artifacts / name).write_bytes(raw)
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in originals.items()}
    if corrupt_manifest:
        hashes["training.json"] = "f" * 64
    (artifacts / "manifest.json").write_text(json.dumps({
        "executed_head": "a" * 40, "file_sha256": hashes}) + "\n", encoding="utf8")
    (artifacts / "qualification.json").write_text("{}\n", encoding="utf8")
    return artifacts, originals


class ExactRetentionContracts(unittest.TestCase):
    def test_all_raw_bytes_survive_collector_safe_valid_zips_and_restore(self):
        with tempfile.TemporaryDirectory(prefix="craci-v7-retention-") as directory:
            root = Path(directory) / "evidence"
            artifacts, originals = fixture(root)
            report = retained.package_evidence(root, Path(directory) / "staging",
                                               chunk_bytes=128)
            self.assertEqual(len(report["sources"]), 2)
            self.assertTrue(retained.verify_parts(artifacts, report))
            self.assertFalse(any((artifacts / name).exists() for name in originals))
            for source in report["sources"]:
                self.assertGreater(len(source["parts"]), 1)
                self.assertTrue(all(p["archive"].endswith(".zip") and
                                    p["archive_bytes"] < retained.MAX_FILE_BYTES
                                    for p in source["parts"]))
            restored = Path(directory) / "restored"
            retained.restore_parts(artifacts, restored)
            for name, value in originals.items():
                self.assertEqual((restored / name).read_bytes(), value)

    def test_mismatch_is_rejected_before_relocation(self):
        with tempfile.TemporaryDirectory(prefix="craci-v7-retention-") as directory:
            root = Path(directory) / "evidence"
            artifacts, originals = fixture(root, corrupt_manifest=True)
            with self.assertRaisesRegex(AssertionError, "SOURCE_EVIDENCE_SHA_MISMATCH"):
                retained.package_evidence(root, Path(directory) / "staging",
                                          chunk_bytes=128)
            self.assertTrue(all((artifacts / name).exists() for name in originals))

    def test_tampered_zip_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="craci-v7-retention-") as directory:
            root = Path(directory) / "evidence"
            artifacts, _ = fixture(root)
            report = retained.package_evidence(root, Path(directory) / "staging",
                                               chunk_bytes=128)
            part = artifacts / report["sources"][0]["parts"][0]["archive"]
            with part.open("ab") as dest:
                dest.write(b"tamper")
            with self.assertRaisesRegex(AssertionError, "ARCHIVE_TAMPERED"):
                retained.verify_parts(artifacts, report)

    def test_global_collector_cap_is_never_relaxed(self):
        with tempfile.TemporaryDirectory(prefix="craci-v7-retention-") as directory:
            root = Path(directory) / "evidence"
            artifacts, originals = fixture(root)
            with patch.object(retained, "MAX_COLLECTOR_BYTES", 100):
                with self.assertRaisesRegex(AssertionError,
                                            "EVIDENCE_PACK_EXCEEDS_COLLECTOR_CAP"):
                    retained.package_evidence(root, Path(directory) / "staging",
                                              chunk_bytes=128)
            self.assertTrue(all((artifacts / name).exists() for name in originals))

    def test_original_training_above_20mib_becomes_legal_small_archives(self):
        with tempfile.TemporaryDirectory(prefix="craci-v7-large-retention-") as directory:
            root = Path(directory) / "evidence"
            artifacts, _ = fixture(root)
            training = artifacts / "training.json"
            training.write_bytes(b"V7 synthetic contract fixture." * (21 * 1024 * 1024 // 30 + 1))
            self.assertGreater(training.stat().st_size, retained.MAX_FILE_BYTES)
            manifest = json.loads((artifacts / "manifest.json").read_text(encoding="utf8"))
            manifest["file_sha256"]["training.json"] = retained.sha_file(training)
            (artifacts / "manifest.json").write_text(
                json.dumps(manifest) + "\n", encoding="utf8")
            report = retained.package_evidence(root, Path(directory) / "staging")
            self.assertTrue(retained.verify_parts(artifacts, report))
            self.assertGreater(len(report["sources"][0]["parts"]), 3)
            self.assertTrue(all(part["archive_bytes"] < retained.MAX_FILE_BYTES
                                for item in report["sources"] for part in item["parts"]))


if __name__ == "__main__":
    unittest.main()
