"""Focused numerical, leakage and evidence-admission checks; no real training."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from features import (CSV_COLUMNS, FEATURE_NAMES, candidate_features, embedding_matrix,
                      multiview_scores, select_candidates, stable_ranks)
from prepare_candidates import (MODEL, export_partition, load_cache, sha256,
                                validate_records, validate_split_separation)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def record(pid, split, family=None):
    return {"product_id": pid, "family_id": family or "family_" + pid, "split": split,
            "views": [{"sha256": digest(pid + "gallery")}, {"sha256": digest(pid + "query")}]}


class FeatureNumerics(unittest.TestCase):
    def test_ranks_preserve_ties_in_both_directions(self):
        values = np.asarray([[.5, .5, .2], [.5, .1, .2]], dtype=np.float32)
        np.testing.assert_array_equal(stable_ranks(values), [[1, 2, 3], [1, 3, 2]])
        np.testing.assert_array_equal(stable_ranks(values, axis=0), [[1, 1, 1], [2, 2, 2]])

    def test_features_match_independent_scalar_reference(self):
        visual = np.asarray([[.9, .2, .1], [.8, .7, .3], [.1, .4, .6]], dtype=np.float32)
        adapted = np.asarray([[.7, .7, .1], [.2, .8, .3], [.6, .2, .4]], dtype=np.float32)
        text = visual / 2
        candidates = np.asarray([[0, 2], [1, 0], [2, 1]])
        actual = candidate_features(visual, adapted, text, candidates)
        for qi, choices in enumerate(candidates):
            for ci, gi in enumerate(choices):
                reverse_order = sorted(range(3), key=lambda index: (-visual[index, gi], index))
                best_other = max(float(adapted[qi, j]) for j in range(3) if j != gi)
                expected = [float(visual[qi, gi]), float(adapted[qi, gi]), float(text[qi, gi]),
                            1 / (reverse_order.index(qi) + 1),
                            float(visual[qi, gi]) - sum(float(v) for v in visual[:, gi]) / 3,
                            float(adapted[qi, gi]) - best_other]
                for name, target in zip(FEATURE_NAMES, expected):
                    self.assertAlmostEqual(float(actual[name][qi, ci]), target, places=7)

    def test_density_uses_ten_highest_queries_not_all_queries(self):
        visual = np.asarray([[i / 20, .1] for i in range(12)], dtype=np.float32)
        chosen = np.zeros((12, 1), dtype=np.int32)
        value = candidate_features(visual, visual, visual, chosen)["f_density"][0, 0]
        self.assertAlmostEqual(float(value), -float(np.mean(visual[2:, 0], dtype=np.float64)), places=7)

    def test_rrf_union_is_deterministic_capped_and_has_no_truth_input(self):
        visual = np.asarray([[.9, .8, .2, .1], [.1, .2, .9, .8]], dtype=np.float32)
        adapted = np.asarray([[.8, .9, .1, .2], [.2, .1, .8, .9]], dtype=np.float32)
        text = np.asarray([[.1, .2, .9, .8], [.9, .8, .1, .2]], dtype=np.float32)
        first, ranks = select_candidates(visual, adapted, text, ["a", "b", "c", "d"], limit=2)
        again, _ = select_candidates(visual, adapted, text, ["a", "b", "c", "d"], limit=2)
        np.testing.assert_array_equal(first, again)
        self.assertEqual(first.shape, (2, 2))
        for qi, row in enumerate(first):
            union = set(np.flatnonzero((ranks["visual"][qi] <= 2) | (ranks["adapted"][qi] <= 2) | (ranks["text"][qi] <= 2)))
            self.assertTrue(set(row).issubset(union))
            self.assertEqual(len(set(row)), 2)
        only, _ = select_candidates(visual, visual, visual, ["a", "b", "c", "d"], limit=1)
        np.testing.assert_array_equal(only[:, 0], [0, 2])

    def test_nonfinite_unscaled_and_duplicate_inputs_rejected(self):
        with self.assertRaises(ValueError):
            embedding_matrix(np.asarray([[2., 0.]], dtype=np.float32))
        bad = np.asarray([[float("nan"), .2]], dtype=np.float32)
        with self.assertRaises(ValueError):
            select_candidates(bad, bad, bad, ["a", "b"])
        good = np.asarray([[.1, .2]], dtype=np.float32)
        with self.assertRaises(ValueError):
            candidate_features(good, good, good, [[0, 0]])
        with self.assertRaises(ValueError):
            select_candidates(good, good, good, ["a", "a"])

    def test_explicit_adapted_topk_preserves_original_order_and_default_rrf(self):
        visual = np.asarray([[.9, .8, .1], [.1, .8, .9]], dtype=np.float32)
        adapted = np.asarray([[.6, .3, .7], [.7, .7, .2]], dtype=np.float32)
        ids = ["z", "a", "b"]
        before = adapted.copy()
        selected, ranks = select_candidates(visual, adapted, visual, ids, limit=2, policy="adapted_topk")
        np.testing.assert_array_equal(selected, [[2, 0], [0, 1]])
        np.testing.assert_array_equal(np.take_along_axis(ranks["adapted"], selected, axis=1), [[1, 2], [1, 2]])
        np.testing.assert_array_equal(adapted, before)
        default, _ = select_candidates(visual, adapted, visual, ids, limit=2)
        explicit, _ = select_candidates(visual, adapted, visual, ids, limit=2, policy="rrf")
        np.testing.assert_array_equal(default, explicit)
        with self.assertRaisesRegex(ValueError, "unknown_candidate_policy"):
            select_candidates(visual, adapted, visual, ids, policy="oracle")

    def test_multiview_pools_only_registered_views_and_rejects_query_leak(self):
        q = np.asarray([[1., 0.], [0., 1.]], dtype=np.float32)
        g = np.asarray([[1., 0.], [0., 1.], [-1., 0.]], dtype=np.float32)
        kwargs = {"query_image_sha256": [digest("q0"), digest("q1")],
                  "gallery_image_sha256": [digest("g0"), digest("g1"), digest("g2")]}
        ids, scores = multiview_scores(q, g, ["a", "a", "b"], **kwargs)
        self.assertEqual(ids, ["a", "b"])
        np.testing.assert_array_equal(scores, [[1, -1], [1, 0]])
        kwargs["gallery_image_sha256"][1] = kwargs["query_image_sha256"][0]
        with self.assertRaisesRegex(ValueError, "query_image"):
            multiview_scores(q, g, ["a", "a", "b"], **kwargs)


class SourceAdmission(unittest.TestCase):
    def test_family_and_image_leakage_are_independently_rejected(self):
        parts = {"train": [record("a", "train")], "test": [record("b", "test")]}
        self.assertTrue(validate_split_separation(parts)["family_disjoint"])
        same_family = copy.deepcopy(parts)
        same_family["test"][0]["family_id"] = same_family["train"][0]["family_id"]
        with self.assertRaisesRegex(ValueError, "family_split_overlap"):
            validate_split_separation(same_family)
        same_image = copy.deepcopy(parts)
        same_image["test"][0]["views"][1]["sha256"] = same_image["train"][0]["views"][0]["sha256"]
        with self.assertRaisesRegex(ValueError, "image_split_overlap"):
            validate_split_separation(same_image)

    def test_invalid_views_and_duplicate_products_rejected(self):
        r = record("a", "train")
        with self.assertRaisesRegex(ValueError, "unique_product"):
            validate_records([r, r], allowed_splits={"train"})
        r["views"][1] = r["views"][0]
        with self.assertRaisesRegex(ValueError, "distinct_image_hashes"):
            validate_records([r], allowed_splits={"train"})

    def test_cache_receipt_order_hash_and_model_binding(self):
        with tempfile.TemporaryDirectory(prefix="meta-r4-feature-test-") as temporary:
            root = Path(temporary)
            features = np.zeros((2, 768), dtype=np.float32)
            features[0, 0] = features[1, 1] = 1
            path = root / "features.npz"
            np.savez_compressed(path, query=features, gallery=features, text=features,
                                hint=np.asarray(["DO_NOT_LOAD"], dtype=object))
            records = [record("a", "train"), record("b", "train")]
            receipt = {**MODEL, "dataset_sha256": digest("dataset"), "feature_sha256": sha256(path),
                       "product_order": ["a", "b"], "encoder_frozen": True, "image_inference_executed": True,
                       "feature_shapes": {key: [2, 768] for key in ("query", "gallery", "text")}}
            receipt_path = path.with_suffix(".json")
            receipt_path.write_text(json.dumps(receipt))
            arrays, binding = load_cache(path, records, digest("dataset"))
            self.assertEqual(set(arrays), {"query", "gallery", "text"})
            self.assertFalse(binding["query_hint_array_loaded"])
            for key, changed in [("product_order", ["b", "a"]), ("feature_sha256", "0" * 64),
                                 ("model_revision", "unverified"), ("encoder_frozen", False)]:
                bad = {**receipt, key: changed}
                receipt_path.write_text(json.dumps(bad))
                with self.assertRaisesRegex(ValueError, "provenance_or_order"):
                    load_cache(path, records, digest("dataset"))

    def test_export_reports_missing_truth_without_injection_or_family_features(self):
        # Every query favors gallery0; two truth products will miss the cap1 pool.
        records = [record(pid, "train") for pid in ("a", "b", "c")]
        query = np.asarray([[1., 0.]] * 3, dtype=np.float32)
        gallery = np.asarray([[1., 0.], [0., 1.], [-1., 0.]], dtype=np.float32)
        def run(rows):
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
            writer.writeheader()
            report, diag = export_partition("train", rows, {"query": query, "gallery": gallery, "text": gallery},
                                            None, None, writer, limit=1)
            return report, diag, list(csv.DictReader(io.StringIO(output.getvalue())))
        report, diagnostics, original_rows = run(records)
        self.assertEqual(report["queries_missing_truth_candidate"], 2)
        self.assertEqual(sum(int(row["label"]) for row in original_rows), 1)
        self.assertEqual([d["truth_in_candidates"] for d in diagnostics], [True, False, False])
        changed = copy.deepcopy(records)
        for r in changed:
            r["family_id"] = "irrelevant_same_family"
            r["title"] = "FORBIDDEN_QUERY_TITLE"
            r["text_hint"] = "FORBIDDEN_QUERY_HINT"
        _, _, changed_rows = run(changed)
        self.assertEqual([[r[k] for k in FEATURE_NAMES] for r in original_rows],
                         [[r[k] for k in FEATURE_NAMES] for r in changed_rows])


if __name__ == "__main__":
    unittest.main()
