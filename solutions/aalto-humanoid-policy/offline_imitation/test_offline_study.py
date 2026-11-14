"""Focused source-only guards for the Aalto state/action study."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import hashlib
import json

import numpy as np

import offline_study as s
import vision_probe as v


class SplitAndMetrics(unittest.TestCase):
    def test_episode_split_disjoint_deterministic(self):
        a = s.episode_split()
        b = s.episode_split()
        self.assertEqual(a, b)
        self.assertEqual([len(a[x]) for x in ("train", "validation", "test")], [12, 4, 4])
        sets = [set(a[x]) for x in a]
        self.assertEqual(set.union(*sets), set(range(20)))
        self.assertEqual(sum(map(len, sets)), 20)
        for i in range(3):
            for j in range(i + 1, 3):
                self.assertFalse(sets[i] & sets[j])

    def test_noninteger_or_too_few_rejected(self):
        with self.assertRaises(ValueError):
            s.episode_split(8)
        with self.assertRaises(ValueError):
            s.episode_split(seed=True)

    def test_oracle_never_reads_across_episode_boundary(self):
        y = np.arange(4 * s.DIM, dtype=np.float32).reshape(4, s.DIM)
        result = s.previous_action_oracle(y, np.array([2, 2, 5, 5]),
                                          np.array([0, 1, 0, 1]),
                                          np.full(s.DIM, -99, dtype=np.float32))
        self.assertTrue(np.all(result[[0, 2]] == -99))
        self.assertTrue(np.array_equal(result[1], y[0]))
        self.assertTrue(np.array_equal(result[3], y[2]))

    def test_nearest_neighbor_uses_only_train_actions(self):
        x = np.array([[0] * s.DIM, [2] * s.DIM], dtype=np.float32)
        y = np.array([[1] * s.DIM, [3] * s.DIM], dtype=np.float32)
        p = s.nearest_state_actions(x, y, np.array([[1.9] * s.DIM], dtype=np.float32))
        self.assertTrue(np.array_equal(p, y[1:2]))

    def test_ridge_fit_recovers_synthetic_linear_relation(self):
        rng = np.random.default_rng(4)
        x = rng.normal(size=(200, s.DIM)).astype(np.float32)
        y = (2 * x + 0.4).astype(np.float32)
        model = s.ridge_fit(x[:150], y[:150], 0.001)
        error = np.abs(s.ridge_predict(model, x[150:]) - y[150:]).mean()
        self.assertLess(error, 0.001)

    def test_metric_shape_and_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            s.grouped_metrics(np.zeros((2, 4)), np.zeros((2, 4)), np.array([1, 2]))
        x = np.zeros((2, s.DIM))
        x[0, 0] = np.inf
        with self.assertRaises(ValueError):
            s.grouped_metrics(x, np.zeros_like(x), np.array([1, 2]))

    def test_duplicate_episode_frame_rejected(self):
        ep = np.repeat(np.arange(20), 2)
        fi = np.tile(np.array([0, 0]), 20)
        states = np.zeros((40, s.DIM), np.float32)
        with patch.object(s, "N_FRAMES", 40):
            with self.assertRaisesRegex(ValueError, "duplicate/missing"):
                s.validate_vectors(ep, fi, states, states)


class MetadataGuard(unittest.TestCase):
    def test_exact_card_and_info_bytes_required(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "meta").mkdir()
            (root / "data/chunk-000").mkdir(parents=True)
            feature = {"dtype": "float32", "shape": [28], "names": [[f"j{i}" for i in range(28)]]}
            info = {"codebase_version": "v3.0", "total_episodes": 20,
                    "total_frames": 11720, "fps": 30,
                    "features": {"observation.state": feature, "action": feature}}
            raw = json.dumps(info).encode()
            (root / "meta/info.json").write_bytes(raw)
            (root / "README.md").write_text("sponsor card", encoding="utf-8")
            (root / "data/chunk-000/file-000.parquet").write_bytes(b"stub")
            with patch.object(s, "INFO_SHA256", hashlib.sha256(raw).hexdigest()), \
                 patch.object(s, "README_SHA256", hashlib.sha256(b"sponsor card").hexdigest()):
                good = s.dataset_preflight(root)
                self.assertEqual(len(good["joint_names"]), 28)
                info["features"]["action"] = {**feature, "names": [list(reversed(feature["names"][0]))]}
                edited = json.dumps(info).encode()
                (root / "meta/info.json").write_bytes(edited)
                with patch.object(s, "INFO_SHA256", hashlib.sha256(edited).hexdigest()):
                    with self.assertRaisesRegex(ValueError, "joint order"):
                        s.dataset_preflight(root)


class VisionHelpers(unittest.TestCase):
    def test_episode_uniform_frame_selection(self):
        ep = np.repeat(np.arange(20), 30)
        frame = np.tile(np.arange(30), 20)
        chosen = v.balanced_indices(ep, frame, 3, 8)
        self.assertEqual(len(chosen), 160)
        self.assertEqual(set(np.unique(ep[chosen])), set(range(20)))
        self.assertTrue(np.all(frame[chosen] % 3 == 0))
        with self.assertRaises(ValueError):
            v.balanced_indices(ep, frame, 6, 8)

    def test_dual_ridge_on_frozen_embedding_shape(self):
        rng = np.random.default_rng(23)
        x = rng.normal(size=(200, 9)).astype(np.float32)
        y = np.concatenate([x, x, x, x[:, :1]], axis=1)
        # Grouped metrics require 28-dimensional outputs; the helper itself is generic.
        fitted = v.dual_ridge_fit(x[:150], y[:150], 0.0001)
        forecast = v.dual_ridge_predict(fitted, x[150:])
        self.assertEqual(forecast.shape, y[150:].shape)
        self.assertLess(float(np.abs(forecast - y[150:]).mean()), 0.002)

    def test_corrupt_resume_cache_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            np.savez_compressed(root / "embeddings.partial.npz",
                                rows=np.array([1, 2]), embeddings=np.zeros((2, 12)))
            with self.assertRaisesRegex(ValueError, "mismatched"):
                v.recover_progress(root, np.array([1, 2, 3]))


if __name__ == "__main__":
    unittest.main()
