"""Focused integrity tests for the open-data training contract."""
import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parent


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load("open3d_prepare", "hf_open3d_prepare.py")
train = load("open3d_train", "hf_open3d_train.py")
features = load("open3d_features", "hf_open3d_features.py")
summary = load("open3d_summary", "hf_open3d_summarize.py")


class DataContract(unittest.TestCase):
    def test_reviewed_manifest_sources_and_group_count(self):
        manifest = json.loads((ROOT / "fixtures/hf-open3d-manifest.json").read_text())
        prepare.validate_manifest(manifest)
        self.assertGreaterEqual(len({r["participant_group"] for r in manifest["robo"]}), 5)
        altered = json.loads(json.dumps(manifest))
        altered["licenses"]["v2d"]["revision"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "source or license"):
            prepare.validate_manifest(altered)

    def test_motion_samples_respect_invalid_endpoints(self):
        series = np.arange(90, dtype=np.float32).reshape(30, 3)
        valid = np.ones(30, dtype=bool)
        valid[5] = False
        X, Y, baseline = prepare.motion_examples(series, valid, 1, 2, 1, 100)
        self.assertEqual(len(X), 24)
        self.assertTrue(np.allclose(Y, 6))
        self.assertTrue(np.allclose(baseline, 6))

    def test_features_restore_rejects_tampered_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            src, packed = base / "src", base / "packed"
            src.mkdir()
            report = {"lines": {}}
            for line in features.LINES:
                data = (line + " sample").encode()
                (src / (line + ".npz")).write_bytes(data)
                report["lines"][line] = {"bytes": len(data), "sha256": features.sha(data)}
            (src / "preparation.json").write_text(json.dumps(report))
            features.transfer(src, packed, True)
            features.transfer(packed, base / "restored", False)
            (packed / "v2d.zip").write_bytes((packed / "g1.zip").read_bytes())
            with self.assertRaisesRegex(ValueError, "unexpected feature archive"):
                features.transfer(packed, base / "tampered", False)

    def test_training_rejects_changed_features(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            np.savez_compressed(base / "g1.npz", X=np.zeros((100, 2), dtype=np.float32),
                                Y=np.zeros((100, 1), dtype=np.float32),
                                baseline=np.zeros((100, 1), dtype=np.float32),
                                groups=np.repeat(np.arange(5), 20))
            data = {"lines": {"g1": {"sha256": "0" * 64, "examples": 100, "groups": 5}},
                    "datasets": {}}
            (base / "preparation.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "digest changed"):
                train.train(base, base / "out", "g1", 0, "ridge", threads=1)

    def test_incomplete_campaign_cannot_be_summarized_as_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "expected 45 unique cells"):
                summary.summarize(Path(folder), Path(folder) / "out")

    def test_complete_campaign_validates_parts_and_group_weighted_metrics(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            artifacts = base / "cells"
            artifacts.mkdir()
            for line in summary.LINES:
                for fold in range(5):
                    for method in summary.METHODS:
                        cell = artifacts / f"{line}-{fold}-{method}"
                        cell.mkdir()
                        chunk = f"{line}-{fold}-{method}".encode()
                        part = cell / "model.part000.zip"
                        with zipfile.ZipFile(part, "x") as archive:
                            archive.writestr("model.part000", chunk)
                        metric = {"rmse": float(fold + 1)}
                        baseline = {"rmse": 7.0}
                        row = {
                            "line": line, "fold": fold, "method": method,
                            "promotion_authorized": False, "feature_sha256": "a" * 64,
                            "group_overlap": 0, "fit_groups": 4, "heldout_groups": 1,
                            "fit_examples": 80, "heldout_examples": 10 * (fold + 1),
                            "moving_examples": 1, "units": "test",
                            "model": metric, "persistence": baseline, "constant_velocity": baseline,
                            "heldout_group_metrics": [{
                                "group": fold, "examples": 10 * (fold + 1), "model": metric,
                                "persistence": baseline, "constant_velocity": baseline,
                            }],
                            "trained_model": {"sha256": hashlib.sha256(chunk).hexdigest(), "parts": [{
                                "file": part.name, "entry": "model.part000", "bytes": len(chunk),
                                "sha256": hashlib.sha256(chunk).hexdigest(),
                                "archive_sha256": hashlib.sha256(part.read_bytes()).hexdigest(),
                            }]},
                        }
                        (cell / "result.json").write_text(json.dumps(row))
            result = summary.summarize(artifacts, base / "out")
            for line in summary.LINES:
                for method in summary.METHODS:
                    row = result["lines"][line][method]
                    self.assertEqual(row["heldout_groups"], 5)
                    self.assertEqual(row["macro_group_rmse"], 3.0)
                    self.assertEqual(row["groups_better_than_constant_velocity"], 5)


if __name__ == "__main__":
    unittest.main()
