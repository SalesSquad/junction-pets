"""Focused split, numerical and refusal checks using owned synthetic roots."""
import copy
import math
import unittest

import numpy as np

from prepare_data import group_records, split_for
from retrieval import (apply_residual, bm25_scores, calibrate_threshold,
                       candidate_proposal, policy_metrics, retrieval_metrics,
                       upper_false_accept_bound, validate_dataset)


def fixture():
    records = []
    for s, split in enumerate(("train", "dev", "cal", "test", "ood")):
        for j in range(20):
            records.append({"product_id": f"product-{s}-{j}", "family_id": f"family-{s}-{j}", "split": split, "category": "OOD" if split == "ood" else "known", "views": [{"sha256": f"{10000*s+2*j:064x}"}, {"sha256": f"{10000*s+2*j+1:064x}"}]})
    return {"kind": "meta.public-abo-retrieval", "license": "CC-BY-4.0", "ood_categories": ["OOD"], "counts": {s: 20 for s in ("train", "dev", "cal", "test", "ood")}, "records": records}


class RetrievalTests(unittest.TestCase):
    def test_split_and_image_leakage_are_rejected(self):
        good = fixture()
        self.assertEqual(validate_dataset(good)["products"], 100)
        for field, value, message in (("family_id", good["records"][0]["family_id"], "family_split_leak"), ("category", "OOD", "ood_category_leak")):
            bad = copy.deepcopy(good)
            bad["records"][20][field] = value
            with self.assertRaisesRegex(ValueError, message):
                validate_dataset(bad)
        bad = copy.deepcopy(good)
        bad["records"][20]["views"][0]["sha256"] = bad["records"][0]["views"][0]["sha256"]
        with self.assertRaisesRegex(ValueError, "image_split_leak"):
            validate_dataset(bad)

    def test_perfect_and_inverted_retrieval(self):
        perfect = retrieval_metrics(np.eye(4))
        self.assertEqual(perfect["recall_at_1"], 1)
        inverted = retrieval_metrics(-np.eye(4))
        self.assertEqual(inverted["recall_at_1"], 0)
        self.assertEqual(inverted["mrr"], 0.25)

    def test_projection_zero_is_identity_and_nonfinite_rejected(self):
        x = np.array([[1., 0.], [0., 1.]])
        np.testing.assert_array_equal(apply_residual(x, np.ones((2, 1)), np.zeros((1, 2))), x)
        with self.assertRaisesRegex(ValueError, "finite_matrix"):
            apply_residual(x, np.ones((2, 1)), np.array([[math.nan, 0.]]))

    def test_lexical_baseline_uses_documents(self):
        scores = bm25_scores(["red mug", "blue sofa"], ["red ceramic mug", "soft blue sofa"])
        self.assertEqual(list(scores.argmax(1)), [0, 1])

    def test_insufficient_negative_support_abstains(self):
        scores = np.eye(20, dtype=np.float32)
        families = [str(i) for i in range(20)]
        policy = calibrate_threshold(scores, families, 0.01)
        self.assertIsNone(policy["threshold"])
        self.assertEqual(policy_metrics(scores, families, policy)["coverage"], 0)
        proposal = candidate_proposal([1,0], ["a", "b"], policy)
        self.assertEqual(proposal["decision"], "abstain")
        self.assertFalse(proposal["identity_verified"])
        self.assertFalse(proposal["action_authorized"])

    def test_calibration_excludes_unknown_family_and_reports_bound(self):
        scores = np.eye(320, dtype=np.float32)
        families = [str(i) for i in range(320)]
        policy = calibrate_threshold(scores, families, 0.01)
        self.assertIsNotNone(policy["threshold"])
        measured = policy_metrics(scores, families, policy)
        self.assertEqual(measured["coverage"], 1)
        self.assertEqual(measured["absent_family_false_accepts"], 0)
        self.assertLess(measured["absent_family_upper95"], 0.01)
        shifted = np.full_like(scores, 2.0)
        np.fill_diagonal(shifted, -1)
        self.assertGreater(policy_metrics(shifted, families, policy)["absent_family_false_accepts"], 0)
        self.assertAlmostEqual(upper_false_accept_bound(0,320), 1 - 0.05**(1/320))

    def test_family_components_and_ood_are_indivisible(self):
        records = [{"product_id": "a", "image_ids": ["x","y"], "title": "Four words red ceramic cup", "category": "CUP", "brand": "brand", "variant_attributes": ["red"]}, {"product_id": "b", "image_ids": ["z","t"], "title": "Four words blue ceramic cup", "category": "CUP", "brand": "brand", "variant_attributes": ["blue"]}]
        groups = group_records(records)
        self.assertEqual(len(groups), 1)
        family = records[0]["family_id"]
        self.assertEqual(family, records[1]["family_id"])
        self.assertEqual(split_for(family, ["CUP"], ["CUP"]), "ood")

    def test_duplicate_variant_ties_cannot_hide_wrong_present_acceptance(self):
        families = [str(i) for i in range(320) for _ in range(2)]
        f = np.asarray(families)
        scores = (f[:,None] == f[None,:]).astype(np.float32)
        # Historical first-row-per-family sampling falsely reported 100%.
        permissive = policy_metrics(scores, families, {"threshold": 1.0})
        self.assertEqual(permissive["accepted"], 640)
        self.assertEqual(permissive["wrong_present_accepted"], 320)
        self.assertEqual(permissive["accepted_precision"], 0.5)
        self.assertEqual(permissive["present_families_with_any_accepted_error"], 320)
        self.assertFalse(permissive["conditional_accepted_error_certified"])
        calibrated = calibrate_threshold(scores, families, 0.01)
        final = policy_metrics(scores, families, calibrated)
        self.assertEqual(final["wrong_present_accepted"], 0)
        self.assertEqual(final["accepted"], 0)


if __name__ == "__main__":
    unittest.main()
