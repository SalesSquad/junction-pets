"""Corrupt R-output fixtures must not pass the cross-language verifier."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

from run_experiment import verify_scores
from runtime import FEATURE_NAMES


class ParityAdmissionTests(unittest.TestCase):
    def fixture(self, root, *, confidence="2", duplicate=False):
        training = root / "training"
        training.mkdir()
        model = {"schema_version": 1, "kind": "ridge_pairwise_logistic",
                 "feature_names": list(FEATURE_NAMES),
                 "scaler": {"center": [0] * 6, "scale": [1] * 6},
                 "coefficients": [1, 0, 0, 0, 0, 0], "intercept": 0,
                 "action_authorized": False,
                 "policy": {"qualification": False, "threshold": None,
                            "score_field": "top_score_plus_margin"}}
        (training / "model.json").write_text(json.dumps(model))
        rows = [{"split": "test", "query_id": "query", "candidate_id": name,
                 **dict(zip(FEATURE_NAMES, [score, 0, 0, 0, 0, 0]))}
                for name, score in [("top", 1), ("second", 0)]]
        def write_csv(path, values):
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(values[0]))
                writer.writeheader(); writer.writerows(values)
        candidates = root / "candidates.csv"
        write_csv(candidates, rows)
        write_csv(training / "predictions.csv", [
            {"split": r["split"], "query_id": r["query_id"],
             "candidate_id": r["candidate_id"], "rank_score": r["f_visual"]} for r in rows])
        query = {"split": "test", "query_id": "query", "candidate_id": "top", "confidence": confidence}
        write_csv(training / "query_metrics.csv", [query, query] if duplicate else [query])
        return candidates, training

    def test_valid_outputs_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = verify_scores(*self.fixture(Path(tmp)))
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["candidate_rows"], 2)
            self.assertEqual(result["queries"], 1)

    def test_duplicate_query_summary_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "duplicate_query_metric"):
                verify_scores(*self.fixture(Path(tmp), duplicate=True))

    def test_nonfinite_reference_confidence_is_rejected(self):
        for value in ("NaN", "Inf", "-Inf"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(ValueError, "nonfinite_reference_confidence"):
                    verify_scores(*self.fixture(Path(tmp), confidence=value))


if __name__ == "__main__":
    unittest.main()
