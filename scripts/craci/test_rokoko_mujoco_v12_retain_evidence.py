"""Synthetic-only lossless V12 private original and early-stop receipt tests."""
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
    "v12_lossless_packer_synthetic_contract",
    HERE / "rokoko-mujoco-v12-retain-evidence.py")
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def complete_fixture(folder, big=False):
    private = folder / "private-complete"
    private.mkdir()
    (private / "training.json").write_bytes(
        b"a" * (21 * 1024 * 1024) if big else
        b'{"fixture":"not physics"}\n')
    with gzip.open(private / "full_transitions.jsonl.gz", "wb") as out:
        out.write(b'{"fixture":"not physics"}\n')
    save(private / "paired-readout.json", {
        "totalOriginalRealEpisodes": 144,
        "modelPromotionAuthorized": False, "devCalTestOodOpened": False})
    source = "a" * 40
    hashes = {name: pack.sha(private / name) for name in (
        *pack.COMPLETE_SOURCES, "paired-readout.json")}
    save(private / "manifest.json", {
        "schema": pack.ORIGINAL_SCHEMA + ".manifest",
        "executed_head": source, "actual_trials": 144,
        "promotion_authorized": False, "file_sha256": hashes})
    save(private / "independent-qualification.json", {
        "schema": pack.ORIGINAL_SCHEMA + ".independent-qualification",
        "executed_head": source, "actual_trials": 144,
        "original_sha256": hashes,
        "new_model_promotion_authorized": False,
        "dev_cal_test_ood_opened": False,
        "full_144_real_episode_physics_replay": {
            "all_512_public_initial_worlds_replayed": True,
            "all_144_complete_real_episodes_replayed": True,
            "claim_verified": True}})
    return private


def incomplete_fixture(folder):
    private = folder / "private-incomplete"
    private.mkdir()
    raw = private / "full_transitions.jsonl.gz"
    with gzip.open(raw, "wt", encoding="utf8") as out:
        out.write(json.dumps({
            "seed": 518000, "strategy": "frozen_v5",
            "transitions": [{"mask": [1, 0, 0, 0, 0, 0, 0],
                             "action": 0}]}) + "\n")
    save(private / "partial_training.json", {
        "schema": pack.ORIGINAL_SCHEMA + ".incomplete",
        "executed_head": "b" * 40, "status": "INCOMPLETE_STOP",
        "stop_reason": "CANDIDATE_LOST_ACTUAL_FROZEN_V5_GOAL",
        "real_completed_episodes": 1, "raw_real_option_transitions": 1,
        "complete_real_trial_rows": [{
            "seed": 518000, "strategy": "frozen_v5",
            "full_transition_count": 1}],
        "promotion_authorized": False,
        "no_automatic_retry_or_seed_fishing": True})
    save(private / "early_stop.json", {
        "schema": pack.ORIGINAL_SCHEMA + ".early-stop",
        "status": "INCOMPLETE_STOP",
        "executed_head": "b" * 40,
        "reason": "CANDIDATE_LOST_ACTUAL_FROZEN_V5_GOAL",
        "completed_episodes": 1, "expected_episodes": 144,
        "promotion_authorized": False,
        "raw_sha256": {name: pack.sha(private / name) for name in pack.PARTIAL_SOURCES}})
    return private


class V12RetentionTests(unittest.TestCase):
    def test_large_complete_original_exact_reassembly_below_legacy_caps(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            original = complete_fixture(base, big=True)
            collector = base / "collector" / "artifacts" / "v12"
            report = pack.publish_qualified(original, collector)
            self.assertEqual(report["original_sha256"]["training.json"],
                             pack.sha(original / "training.json"))
            self.assertEqual(report["exact_source_sha"], "a" * 40)
            self.assertFalse((collector / "training.json").exists())
            self.assertTrue(all(x.stat().st_size < pack.MAX_FILE_BYTES
                                for x in collector.iterdir()))
            retained = json.loads((collector / "retention-manifest.json").read_text())
            self.assertEqual(retained["status"], "COMPLETE_TRAIN_ONLY")
            self.assertEqual(pack.verify_reassembled(collector, retained)["archives"],
                             report["archives"])

    def test_early_stop_is_losslessly_published_as_incomplete_only(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            original = incomplete_fixture(base)
            collector = base / "collector" / "v12"
            report = pack.publish_early_stop(original, collector)
            self.assertEqual(report["exact_source_sha"], "b" * 40)
            retained = json.loads((collector / "retention-manifest.json").read_text())
            self.assertEqual(retained["status"], "INCOMPLETE_STOP")
            self.assertEqual(len(retained["sources"]), 2)
            self.assertNotIn("independent-qualification.json", retained["proof_sha256"])
            self.assertFalse((collector / "partial_training.json").exists())

    def test_early_stop_cannot_be_promoted_to_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            original = incomplete_fixture(base)
            with self.assertRaisesRegex(AssertionError, "COMPLETE_EXACT_ORIGINALS"):
                pack.publish_qualified(original, base / "collector")

    def test_final_144th_unsafe_episode_preserves_complete_raw_as_incomplete_stop(self):
        """Original safety STOP on the last arm must not destroy all evidence."""
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            original = incomplete_fixture(base)
            arms = ("frozen_v5", "v12_phase_dwell_supported_actions",
                    "v12_right_side_action4_exploration_train_only")
            rows = []
            with gzip.open(original / "full_transitions.jsonl.gz", "wt",
                           encoding="utf8") as out:
                for index in range(144):
                    row = {"seed": 518000 + index // 3,
                           "strategy": arms[index % 3],
                           "full_transition_count": 1}
                    rows.append(row)
                    out.write(json.dumps({"seed": row["seed"],
                                          "strategy": row["strategy"],
                                          "transitions": [{"mask": [1, 0, 0, 0, 0, 0, 0],
                                                           "action": 0}]}) + "\n")
            partial = json.loads((original / "partial_training.json").read_text())
            partial["stop_reason"] = "OBSERVED_UNSAFE_ACTUAL_MUJOCO_COST"
            partial["real_completed_episodes"] = 144
            partial["raw_real_option_transitions"] = 144
            partial["complete_real_trial_rows"] = rows
            save(original / "partial_training.json", partial)
            stop = json.loads((original / "early_stop.json").read_text())
            stop["reason"] = partial["stop_reason"]
            stop["completed_episodes"] = 144
            stop["raw_sha256"] = {n: pack.sha(original / n) for n in pack.PARTIAL_SOURCES}
            save(original / "early_stop.json", stop)
            collector = base / "collector"
            report = pack.publish_early_stop(original, collector)
            self.assertEqual(report["exact_source_sha"], "b" * 40)
            receipt = json.loads((collector / "retention-manifest.json").read_text())
            self.assertEqual(receipt["status"], "INCOMPLETE_STOP")
            self.assertFalse((collector / "independent-qualification.json").exists())
            self.assertEqual(len(receipt["sources"]), 2)

    def test_partial_dropped_raw_trace_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            original = incomplete_fixture(base)
            partial = json.loads((original / "partial_training.json").read_text())
            partial["complete_real_trial_rows"] = []
            save(original / "partial_training.json", partial)
            stop = json.loads((original / "early_stop.json").read_text())
            stop["raw_sha256"]["partial_training.json"] = pack.sha(
                original / "partial_training.json")
            save(original / "early_stop.json", stop)
            with self.assertRaisesRegex(AssertionError, "PARTIAL_CANNOT_PRETEND"):
                pack.publish_early_stop(original, base / "collector")

    def test_zip_part_byte_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            original = complete_fixture(base)
            collector = base / "collector"
            pack.publish_qualified(original, collector)
            receipt = json.loads((collector / "retention-manifest.json").read_text())
            with (collector / receipt["sources"][0]["parts"][0]["archive"]).open("ab") as out:
                out.write(b"tamper")
            with self.assertRaisesRegex(AssertionError, "TAMPERED_OR_OVERLIMIT"):
                pack.verify_reassembled(collector, receipt)

    def test_unchanged_collector_63m_cap_cannot_be_bypassed(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            original = complete_fixture(base)
            with patch.object(pack, "MAX_COLLECTOR_BYTES", 10):
                with self.assertRaisesRegex(AssertionError, "UNCHANGED_COLLECTOR_CAP"):
                    pack.publish_qualified(original, base / "collector")
            self.assertFalse((base / "collector").exists())

    def test_packing_inside_private_original_root_is_prohibited(self):
        with tempfile.TemporaryDirectory() as folder:
            original = incomplete_fixture(Path(folder))
            with self.assertRaisesRegex(AssertionError, "NEW_SEPARATE_PRIVATE"):
                pack.publish_early_stop(original, original / "collector")

    def test_symlinked_alias_to_private_root_cannot_hide_collector_inside_it(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            original = incomplete_fixture(base)
            alias = base / "private-alias"
            alias.symlink_to(original, target_is_directory=True)
            with self.assertRaisesRegex(AssertionError, "NEW_SEPARATE_PRIVATE"):
                pack.publish_early_stop(original, alias / "collector")
            self.assertFalse((original / "collector").exists())


if __name__ == "__main__":
    unittest.main()
