import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from runtime import FEATURE_NAMES, ResearchReranker


class RuntimeTests(unittest.TestCase):
    def model(self):
        return {"schema_version": 1, "kind": "ridge_pairwise_logistic",
                "feature_names": list(FEATURE_NAMES),
                "scaler": {"center": [1, 0, 0, 0, 0, 0], "scale": [2, 1, 1, 1, 1, 1]},
                "coefficients": [2, 0, 0, 0, 0, 0], "intercept": 0,
                "policy": {"threshold": 0.0, "score_field": "top_score_plus_margin", "qualification": False},
                "action_authorized": False}

    def row(self, candidate_id, visual):
        return {"candidate_id": candidate_id, **dict(zip(FEATURE_NAMES, [visual, 0, 0, 0, 0, 0]))}

    def test_numeric_parity_and_no_authorization(self):
        model = ResearchReranker(self.model(), "a" * 64)
        result = model.rank([self.row("wrong", 1), self.row("correct", 3)])
        self.assertEqual(result["candidates"][0], {"candidate_id": "correct", "rank_score": 2.0})
        self.assertEqual(result["confidence"], 4.0)
        self.assertTrue(result["diagnostic_threshold_pass"])
        self.assertFalse(result["accepted"])
        self.assertFalse(result["physical_identity_verified"])
        self.assertFalse(result["action_authorized"])

    def test_feature_and_authority_admission(self):
        bad = self.model(); bad["feature_names"][0] = "label"
        with self.assertRaises(ValueError): ResearchReranker(bad, "a" * 64)
        bad = self.model(); bad["policy"]["qualification"] = True
        with self.assertRaises(ValueError): ResearchReranker(bad, "a" * 64)
        bad = self.model(); bad["scaler"]["scale"][0] = 0
        with self.assertRaises(ValueError): ResearchReranker(bad, "a" * 64)
        model = ResearchReranker(self.model(), "a" * 64)
        with self.assertRaises(ValueError): model.rank([self.row("x", float("nan"))])
        with self.assertRaises(ValueError): model.rank([self.row("x", True)])
        with self.assertRaises(ValueError): model.rank([self.row("x", 1), self.row("x", 2)])
        one = model.rank([self.row("x", 100)])
        self.assertIsNone(one["confidence"])
        self.assertFalse(one["diagnostic_threshold_pass"])

    def test_hash_and_duplicate_field_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            data = json.dumps(self.model()).encode(); path.write_bytes(data)
            ResearchReranker.from_file(path, expected_sha256=hashlib.sha256(data).hexdigest())
            with self.assertRaises(ValueError): ResearchReranker.from_file(path, expected_sha256="0" * 64)
            duplicate = b'{"schema_version":1,"schema_version":1}'
            path.write_bytes(duplicate)
            with self.assertRaises(ValueError):
                ResearchReranker.from_file(path, expected_sha256=hashlib.sha256(duplicate).hexdigest())

    def test_finite_ranks_cannot_overflow_confidence(self):
        config = self.model()
        config["scaler"] = {"center": [0] * 6, "scale": [1] * 6}
        config["coefficients"] = [1e308, 0, 0, 0, 0, 0]
        model = ResearchReranker(config, "a" * 64)
        with self.assertRaisesRegex(ValueError, "nonfinite_confidence"):
            model.rank([self.row("x", 1), self.row("y", -1)])


if __name__ == "__main__":
    unittest.main()
