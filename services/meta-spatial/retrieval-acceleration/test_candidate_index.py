"""Bounded synthetic checks for prepared candidates, not model qualification."""
from __future__ import annotations

import hashlib
import json
import unittest
from unittest.mock import patch
import warnings

import numpy as np

import candidate_index as ci
from contract import ContractError, strict_json_loads


def unit_rows(rows, seed):
    x = np.random.default_rng(seed).normal(size=(rows, 768)).astype(np.float32)
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def residual_reference(x, a, b):
    result = x + (x @ a) @ b
    return result / np.linalg.norm(result, axis=1, keepdims=True)


class CandidateIndexTests(unittest.TestCase):
    def setUp(self):
        self.gallery = unit_rows(41, 801)
        self.queries = unit_rows(19, 802)
        self.gids = [f"gallery-{i}" for i in range(41)]
        self.qids = [f"query-{i}" for i in range(19)]
        rng = np.random.default_rng(803)
        self.a = rng.normal(0, .01, (768, 64)).astype(np.float32)
        self.b = rng.normal(0, .01, (64, 768)).astype(np.float32)

    def test_independent_full_sort_reference_identity_and_residual(self):
        for trained in (False, True):
            with self.subTest(trained=trained):
                index = ci.PreparedCandidateIndex(self.gallery, self.gids,
                                                  self.a if trained else None,
                                                  self.b if trained else None)
                q = residual_reference(self.queries, self.a, self.b) if trained else self.queries
                g = residual_reference(self.gallery, self.a, self.b) if trained else self.gallery
                full_scores = q @ g.T
                full_order = np.argsort(-full_scores, axis=1, kind="stable")[:, :13]
                for batch in (1, 7, 128):
                    actual = index.search(self.queries, self.qids, top_k=13, batch_size=batch)
                    for row, found in enumerate(actual["queries"]):
                        self.assertEqual(found["query_id"], self.qids[row])
                        self.assertEqual([c["gallery_index"] for c in found["candidates"]], full_order[row].tolist())
                        self.assertEqual([c["candidate_id"] for c in found["candidates"]],
                                         [self.gids[i] for i in full_order[row]])
                        np.testing.assert_allclose([c["score"] for c in found["candidates"]],
                                                   full_scores[row, full_order[row]], rtol=0, atol=2e-6)

    def test_partial_top_k_boundary_ties_and_full_gallery(self):
        row = np.asarray([.3, .8, .8, .4, .8, .4, -.1, .4], dtype=np.float32)
        for k in (1, 2, 4, 5, 8):
            np.testing.assert_array_equal(ci._stable_top_k(row, k), np.argsort(-row, kind="stable")[:k])
        identical = np.zeros((140, 768), dtype=np.float32)
        identical[:, 0] = 1
        index = ci.PreparedCandidateIndex(identical, [str(i) for i in range(140)])
        out = index.search(identical[:1], ["same"], top_k=128)
        self.assertEqual([c["gallery_index"] for c in out["queries"][0]["candidates"]], list(range(128)))

    def test_identity_does_not_renormalize_supplied_rows(self):
        gallery = np.zeros((3, 768), dtype=np.float32)
        gallery[:, 0] = np.asarray([1.0005, 1.0006, 1.0004], dtype=np.float32)
        query = np.zeros(768, dtype=np.float32); query[0] = np.float32(1.0005)
        index = ci.PreparedCandidateIndex(gallery, ["a", "b", "c"])
        result = index.search(query, ["q"], top_k=3)
        expected = query[None, :] @ gallery.T
        order = np.argsort(-expected[0], kind="stable")
        self.assertEqual([c["candidate_id"] for c in result["queries"][0]["candidates"]], ["b", "a", "c"])
        np.testing.assert_array_equal([c["score"] for c in result["queries"][0]["candidates"]], expected[0, order])

    def test_immutable_copies_and_actual_byte_bindings(self):
        original_g = self.gallery.copy()
        original_a = self.a.copy()
        index = ci.PreparedCandidateIndex(self.gallery, self.gids, self.a, self.b)
        before = index.search(self.queries, self.qids, top_k=9)
        desc = index.describe()
        self.assertEqual(desc["bindings"]["gallery_features_sha256"], hashlib.sha256(original_g.astype("<f4").tobytes()).hexdigest())
        self.assertEqual(desc["bindings"]["adapter_a_sha256"], hashlib.sha256(original_a.astype("<f4").tobytes()).hexdigest())
        self.gallery[:] = 0; self.a[:] = 0; self.b[:] = 0; self.gids[0] = "mutated"
        desc["bindings"]["gallery_features_sha256"] = "mutated"
        after = index.search(self.queries, self.qids, top_k=9)
        self.assertEqual(before, after)
        self.assertNotEqual(index.describe()["bindings"]["gallery_features_sha256"], "mutated")
        with self.assertRaises(ValueError):
            index._gallery.flags.writeable = True
        with self.assertRaises(ValueError):
            index._a[0, 0] = 1

    def test_input_and_id_order_changes_change_bindings(self):
        first = ci.PreparedCandidateIndex(self.gallery, self.gids).describe()["bindings"]
        reverse = ci.PreparedCandidateIndex(self.gallery[::-1], self.gids[::-1]).describe()["bindings"]
        ids_only = ci.PreparedCandidateIndex(self.gallery, self.gids[::-1]).describe()["bindings"]
        trained = ci.PreparedCandidateIndex(self.gallery, self.gids, self.a, self.b).describe()["bindings"]
        self.assertNotEqual(first["index_sha256"], reverse["index_sha256"])
        self.assertNotEqual(first["index_sha256"], ids_only["index_sha256"])
        self.assertNotEqual(first["index_sha256"], trained["index_sha256"])
        self.assertEqual(first["gallery_features_sha256"], ids_only["gallery_features_sha256"])
        self.assertNotEqual(first["gallery_id_order_sha256"], ids_only["gallery_id_order_sha256"])

    def test_query_chunks_and_gallery_projected_once(self):
        calls = []
        original = ci._project
        def counting(features, a, b):
            calls.append(len(features))
            return original(features, a, b)
        with patch.object(ci, "_project", side_effect=counting):
            index = ci.PreparedCandidateIndex(self.gallery, self.gids, self.a, self.b)
            self.assertEqual(calls, [41])
            result = index.search(self.queries, self.qids, top_k=4, batch_size=7)
            self.assertEqual(calls, [41, 7, 7, 5])
            index.search(self.queries[:2], self.qids[:2], top_k=4, batch_size=1)
            self.assertEqual(calls, [41, 7, 7, 5, 1, 1])
        self.assertEqual(result["query_chunks"], 3)
        self.assertEqual(result["largest_score_chunk_rows"], 7)
        self.assertEqual(index.describe()["gallery_projection_count"], 1)

    def test_malformed_and_unbounded_inputs_fail_with_contract_errors(self):
        invalid = [np.zeros((2, 768), dtype=np.float32), np.ones((2, 768), dtype=np.float32),
                   np.zeros((1, 767), dtype=np.float32), np.empty((0, 768), dtype=np.float32),
                   self.gallery.astype(np.complex64), [["x"] * 768], self.gallery.astype(bool),
                   [[1], [1, 2]]]
        nonfinite = self.gallery.copy(); nonfinite[0, 0] = np.nan; invalid.append(nonfinite)
        for value in invalid:
            with self.subTest(shape=getattr(value, "shape", None)):
                with self.assertRaises(ContractError): ci.PreparedCandidateIndex(value, self.gids)
        large = np.broadcast_to(self.gallery[0], (ci.MAX_GALLERY_ROWS + 1, 768))
        with self.assertRaises(ContractError): ci.PreparedCandidateIndex(large, [])
        for ids in ("not-a-sequence", self.gids[:-1], ["duplicate"] * 41,
                    ["x" * 257] + self.gids[1:], ["\ud800"] + self.gids[1:]):
            with self.assertRaises(ContractError): ci.PreparedCandidateIndex(self.gallery, ids)
        index = ci.PreparedCandidateIndex(self.gallery, self.gids)
        for k in (0, -1, 42, 129, True, 1.5):
            with self.assertRaises(ContractError): index.search(self.queries, self.qids, top_k=k)
        for size in (0, 129, True, 1.5):
            with self.assertRaises(ContractError): index.search(self.queries, self.qids, top_k=1, batch_size=size)
        too_many_queries = np.broadcast_to(self.queries[0], (ci.MAX_QUERY_ROWS + 1, 768))
        with self.assertRaises(ContractError): index.search(too_many_queries, [], top_k=1)
        with self.assertRaises(ContractError): index.search(self.queries, ["duplicate"] * 19, top_k=1)

    def test_bad_weights_and_degenerate_projection_rejected(self):
        with self.assertRaises(ContractError): ci.PreparedCandidateIndex(self.gallery, self.gids, self.a, None)
        with self.assertRaises(ContractError): ci.PreparedCandidateIndex(self.gallery, self.gids, self.a.astype(np.float64), self.b)
        with self.assertRaises(ContractError): ci.PreparedCandidateIndex(self.gallery, self.gids, self.a[:, :1], self.b[:1])
        bad = self.a.copy(); bad[0, 0] = np.inf
        with self.assertRaises(ContractError): ci.PreparedCandidateIndex(self.gallery, self.gids, bad, self.b)
        gallery = np.zeros((2, 768), dtype=np.float32); gallery[:, 0] = 1
        a = np.zeros((768, 64), dtype=np.float32); a[0, 0] = 1
        b = np.zeros((64, 768), dtype=np.float32); b[0, 0] = -1
        with self.assertRaises(ContractError): ci.PreparedCandidateIndex(gallery, ["a", "b"], a, b)
        b[0, 0] = np.float32(1e30)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            with self.assertRaises(ContractError): ci.PreparedCandidateIndex(gallery, ["a", "b"], a, b)

    def test_json_ready_advisory_outputs_and_single_candidate(self):
        index = ci.PreparedCandidateIndex(self.gallery[:1], ["one"])
        result = index.search(self.queries[:1], ["q"], top_k=1)
        parsed = strict_json_loads(json.dumps(result, allow_nan=False))
        self.assertEqual(parsed["kind"], "meta.retrieval-acceleration.candidates")
        for item in (parsed, parsed["index"]):
            self.assertEqual(item["schema_version"], 1)
            for field in ("qualification", "action_authorized", "physical_identity_verified"):
                self.assertIs(item[field], False)
        self.assertIsNone(parsed["accepted_candidate"])
        self.assertFalse(parsed["scores_are_probabilities"])
        self.assertEqual(parsed["queries"][0]["candidates"][0]["candidate_id"], "one")


if __name__ == "__main__":
    unittest.main()
