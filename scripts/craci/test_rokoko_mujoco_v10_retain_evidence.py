"""Synthetic-only integrity contracts for private-first V10 collector packing."""
from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "v10_private_packer_fixture_only", HERE / "rokoko-mujoco-v10-retain-evidence.py")
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def source_fixture(base: Path, big=False):
    private = base / "original-private-traces"
    private.mkdir()
    original_summary = private / "training.json"
    # Intentionally >20 MiB to exercise lossless private-first publication.
    original_summary.write_bytes((b"a" * (21 * 1024 * 1024) if big else
                                  b'{"synthetic_contract_fixture":true}\n'))
    raw = private / "full_transitions.jsonl.gz"
    with gzip.open(raw, "wb") as stream:
        stream.write(b'{"synthetic_contract_fixture":"not real MuJoCo"}\n')
    source_sha = "c" * 40
    write_json(private / "paired-readout.json", {
        "executed_head": source_sha, "dataset_sha256": "d" * 64,
        "strategies": {name: {"safe_goals_clear": 0} for name in (
            "frozen_v5", "frozen_v6", "repeat_left", "frozen_v8", "v10_loss_informed")},
        "model_promotion_authorized": False})
    manifest = {"schema": pack.MANIFEST_SCHEMA, "executed_head": source_sha,
                "file_sha256": {n: pack.sha_file(private / n) for n in pack.SOURCE_FILES},
                "auxiliary_file_sha256": {
                    "paired-readout.json": pack.sha_file(private / "paired-readout.json")}}
    write_json(private / "manifest.json", manifest)
    near_replay = {"claim_verified": True, "model_promotion_authorized": False,
              "fully_replayed_positive_train_trials": 1}
    clear_replay = {"claim_verified": True, "model_promotion_authorized": False,
                    "dev_cal_test_ood_opened": False,
                    "claimed_safe_clear_goal_trajectories": 0,
                    "replayed_safe_clear_goal_trajectories": 0}
    write_json(private / "independent-positive-replay.json", near_replay)
    write_json(private / "independent-clear-goal-replay.json", clear_replay)
    write_json(private / "independent-qualification.json", {
        "schema": pack.QUALIFIED_SCHEMA,
        "decision": "valid_source_bound_five_way_train_only_evidence",
        "experiment_complete": True, "producer_exit_code": 0,
        "independent_full_trace_public_mask_replay": True,
        "promotion_authorized": False, "dev_cal_test_ood_opened": False,
        "exact_source_sha": source_sha, "trials": 800,
        "actual_real_option_transitions": 1000,
        "full_transition_archive_sha256": manifest["file_sha256"]["full_transitions.jsonl.gz"],
        "dataset_sha256": "d" * 64,
        "independent_true_physics_positive_replay": near_replay,
        "independent_true_physics_clear_goal_replay": clear_replay})
    return private


class V10PrivateOriginalPackingTests(unittest.TestCase):
    def test_over_twenty_mib_original_is_losslessly_packed_below_original_caps(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            private = source_fixture(base, big=True)
            collector = base / "collector" / "artifacts" / "rokoko-mujoco-v10-prospective"
            hashes = {n: pack.sha_file(private / n) for n in pack.SOURCE_FILES}
            report = pack.publish_private_source(private, collector)
            self.assertEqual(report["source_count"], 2)
            self.assertEqual(report["original_sha256"], hashes)
            self.assertTrue(pack.verify_archive_parts(
                collector, json.loads((collector / "retention-manifest.json").read_text())))
            self.assertFalse((collector / "training.json").exists())
            self.assertFalse((collector / "full_transitions.jsonl.gz").exists())
            self.assertTrue(all(f.stat().st_size < pack.MAX_FILE_BYTES
                                for f in collector.iterdir() if f.is_file()))
            self.assertTrue(all(pack.sha_file(private / n) == hashes[n]
                                for n in pack.SOURCE_FILES))

    def test_tampered_part_is_rejected_after_publishing(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            private = source_fixture(base)
            collector = base / "collector" / "artifacts" / "v10"
            pack.publish_private_source(private, collector)
            report = json.loads((collector / "retention-manifest.json").read_text())
            part = collector / report["sources"][0]["parts"][0]["archive"]
            with part.open("ab") as stream:
                stream.write(b"corruption")
            with self.assertRaisesRegex(AssertionError, "ARCHIVE_BYTES_OR_SHA_INVALID"):
                pack.verify_archive_parts(collector, report)

    def test_tampered_small_independent_proof_is_sha_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            private = source_fixture(base)
            collector = base / "collector" / "artifacts" / "v10"
            pack.publish_private_source(private, collector)
            report = json.loads((collector / "retention-manifest.json").read_text())
            with (collector / "independent-clear-goal-replay.json").open("ab") as stream:
                stream.write(b"tampered small proof")
            with self.assertRaisesRegex(AssertionError, "INDEPENDENT_PROOF_BYTES_CHANGED"):
                pack.verify_archive_parts(collector, report)

    def test_source_receipt_without_positive_replay_cannot_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            private = source_fixture(base)
            (private / "independent-positive-replay.json").unlink()
            collector = base / "collector" / "v10"
            with self.assertRaisesRegex(AssertionError, "EXPECTED_FULL_SOURCE"):
                pack.publish_private_source(private, collector)
            self.assertFalse(collector.exists())

    def test_wrong_original_digest_cannot_be_rehashed_into_report(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            private = source_fixture(base)
            with (private / "training.json").open("ab") as stream:
                stream.write(b"attack")
            with self.assertRaisesRegex(AssertionError, "RAW_MANIFEST_SHA_MISMATCH"):
                pack.publish_private_source(private, base / "collector" / "v10")

    def test_unchanged_global_collector_cap_stops_large_original(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            private = source_fixture(base)
            collector = base / "collector" / "v10"
            with patch.object(pack, "MAX_COLLECTOR_BYTES", 10):
                with self.assertRaisesRegex(AssertionError, "ORIGINAL_COLLECTOR_CAP"):
                    pack.publish_private_source(private, collector)
            self.assertFalse(collector.exists())

    def test_no_public_archive_written_under_private_source(self):
        with tempfile.TemporaryDirectory() as folder:
            private = source_fixture(Path(folder))
            with self.assertRaisesRegex(AssertionError, "SEPARATE_FRESH_EVIDENCE_TREE"):
                pack.publish_private_source(private, private / "published")


if __name__ == "__main__":
    unittest.main()
