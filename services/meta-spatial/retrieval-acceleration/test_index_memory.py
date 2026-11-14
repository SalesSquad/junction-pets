"""Bound norm-validation temporaries without changing copied features or errors."""
from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch

import numpy as np

import candidate_index as implementation
from contract import ContractError


class NormValidationMemoryTests(unittest.TestCase):
    def rows(self, count):
        result = np.zeros((count, 768), dtype=np.float32)
        result[:, 0] = 1
        return result

    def assert_code(self, value, code):
        with self.assertRaises(ContractError) as caught:
            implementation._feature_copy(value, "gallery", 50_000)
        self.assertEqual(caught.exception.code, code)

    def test_gallery_and_query_norm_temporaries_are_bounded(self):
        chunk = implementation.NORM_VALIDATION_CHUNK_ROWS
        self.assertEqual(chunk, 1024)
        features = self.rows(chunk * 2 + 1)
        observed = []
        original = np.linalg.norm

        def record_norm(array, *args, **kwargs):
            self.assertEqual(array.dtype, np.float64)
            self.assertEqual(array.shape[1], 768)
            self.assertLessEqual(array.shape[0], 1024)
            observed.append(array.shape[0])
            return original(array, *args, **kwargs)

        with patch.object(implementation.np.linalg, "norm", side_effect=record_norm):
            implementation._feature_copy(features, "gallery", 50_000)
            implementation._feature_copy(features, "query", 4096, query=True)
        self.assertEqual(observed, [1024, 1024, 1, 1024, 1024, 1])

    def test_chunk_boundaries_preserve_accepted_float32_bytes(self):
        chunk = implementation.NORM_VALIDATION_CHUNK_ROWS
        for count in (chunk - 1, chunk, chunk + 1, chunk * 2 + 1):
            with self.subTest(rows=count):
                features = self.rows(count)
                features[::2, 0] = np.float32(1.0009)
                features[1::2, 0] = np.float32(.9991)
                reference_norms = np.linalg.norm(features.astype(np.float64), axis=1)
                self.assertTrue(np.allclose(reference_norms, 1.0, rtol=0, atol=1e-3))
                copied = implementation._feature_copy(features, "gallery", 50_000)
                self.assertEqual(copied.dtype, np.dtype("<f4"))
                self.assertFalse(copied.flags.writeable)
                self.assertEqual(hashlib.sha256(copied.tobytes()).hexdigest(),
                                 hashlib.sha256(features.tobytes()).hexdigest())

    def test_late_zero_retains_priority_over_earlier_nonunit_row(self):
        features = self.rows(2049)
        features[0, 0] = 1.1
        features[2048] = 0
        self.assert_code(features, "zero_embeddings")

    def test_late_nonfinite_retains_priority_over_earlier_zero_row(self):
        features = self.rows(1025)
        features[0] = 0
        features[1024, 0] = np.inf
        self.assert_code(features, "nonfinite_embeddings")

    def test_nonunit_row_after_chunk_boundary_is_rejected(self):
        features = self.rows(1025)
        features[1024, 0] = 1.01
        self.assert_code(features, "unnormalized_embeddings")


if __name__ == "__main__":
    unittest.main()
