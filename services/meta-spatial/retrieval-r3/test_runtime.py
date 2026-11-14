"""Artifact binding and abstention checks using only synthetic inputs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from runtime import from_artifacts


CHECKS = {"recall_at_least_fixed_hybrid": True, "coverage_at_least_20_percent": True,
          "zero_wrong_present_accepted": True, "combined_family_upper95_at_most_1_percent": True}


def vector(index=0):
    result = np.zeros(768, dtype=np.float32)
    result[index] = 1
    return result


def write_artifacts(root, *, status="FAIL", threshold=0.5, candidate=None):
    train, evaluation = root / "training", root / "evaluation"
    train.mkdir(exist_ok=True)
    evaluation.mkdir(exist_ok=True)
    candidate = candidate or {"kind": "identity", "epoch": 0, "checkpoint": None, "checkpoint_sha256": None}
    selection = {"schema_version": 1, "kind": "meta.visual_adapter.r3.selection",
                 "fresh_cal_test_evaluated": False, "primary": candidate,
                 "confirmation_candidate": candidate}
    payload = json.dumps(selection).encode()
    (train / "selection.json").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    policies = {"primary_visual": {"threshold": threshold, "confidence_is_probability": False,
                                    "risk_target": 0.01}}
    report = {"schema_version": 1, "kind": "meta.visual_adapter.r3.fresh_evaluation",
              "selection_sha256": digest, "selection": candidate, "policies": policies,
              "product_gate": {"status": status, "checks": CHECKS if status == "PASS" else
                               {**CHECKS, "coverage_at_least_20_percent": False}}}
    (evaluation / "report.json").write_text(json.dumps(report))
    (evaluation / "frozen-policies.json").write_text(json.dumps({"selection_sha256": digest,
        "fresh_test_scores_observed": False, "policies": policies}))
    return train, evaluation


class RuntimeTests(unittest.TestCase):
    def test_failed_qualification_always_abstains_even_exact_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = from_artifacts(*write_artifacts(Path(tmp)))
            result = adapter.propose(vector(), [vector(), vector(1)], ["exact", "other"])[0]
            self.assertEqual(result["reason"], "qualification_failed")
            self.assertEqual(result["kind"], "abstain")
            self.assertIsNone(result["accepted_candidate"])
            self.assertEqual(result["research_ranking"][0]["product_id"], "exact")
            self.assertEqual(result["confidence_score"], 2.0)
            for flag in ("confidence_is_probability", "physical_identity_verified", "action_authorized"):
                self.assertIs(result[flag], False)

    def test_qualified_candidate_still_makes_no_identity_or_action_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = from_artifacts(*write_artifacts(Path(tmp), status="PASS", threshold=1.5))
            results = adapter.propose([vector(), vector(1)], [vector(), vector(1)], ["a", "b"])
            self.assertEqual([r["accepted_candidate"] for r in results], ["a", "b"])
            self.assertTrue(all(r["kind"] == "candidate" and r["action_authorized"] is False
                                and r["physical_identity_verified"] is False for r in results))

    def test_identical_gallery_features_have_zero_margin_and_stable_tie(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = from_artifacts(*write_artifacts(Path(tmp), status="PASS", threshold=1.1))
            result = adapter.propose(vector(), [vector(), vector()], ["first", "second"])[0]
            self.assertEqual(result["confidence_score"], 1.0)
            self.assertEqual(result["reason"], "below_threshold")
            self.assertEqual(result["research_ranking"][0]["product_id"], "first")

    def test_missing_threshold_abstains(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = from_artifacts(*write_artifacts(Path(tmp), status="PASS", threshold=None))
            self.assertEqual(adapter.propose(vector(), [vector(), vector(1)], ["a", "b"])[0]["reason"],
                             "no_qualified_threshold")

    def test_identity_preserves_raw_float32_near_tie_scores_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = from_artifacts(*write_artifacts(Path(tmp)))
            query = vector() * np.float32(1 + 2 ** -20)
            gallery = np.stack([vector() * np.float32(1 + 2 ** -19),
                                vector() * np.float32(1 + 2 ** -20)])
            raw_scores = query[None, :] @ gallery.T
            expected_confidence = float(raw_scores[0, 0] + (raw_scores[0, 0] - raw_scores[0, 1]))
            result = adapter.propose(query, gallery, ["first", "second"])[0]
            self.assertEqual(result["research_ranking"][0]["similarity"], float(raw_scores[0, 0]))
            self.assertEqual(result["research_ranking"][1]["similarity"], float(raw_scores[0, 1]))
            self.assertEqual(result["confidence_score"], expected_confidence)
            self.assertGreater(raw_scores[0, 0], raw_scores[0, 1])

    def test_malformed_embeddings_and_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = from_artifacts(*write_artifacts(Path(tmp)))
            malformed = [np.zeros(768), np.full(768, np.nan), np.ones(767), np.empty((0, 768)),
                         np.ones(768, dtype=np.complex64), vector() * 2]
            for query in malformed:
                with self.subTest(shape=query.shape), self.assertRaises(ValueError):
                    adapter.propose(query, [vector(), vector(1)], ["a", "b"])
            for ids in (["a", "a"], ["a"], ["a", ""], "ab"):
                with self.subTest(ids=ids), self.assertRaises(ValueError):
                    adapter.propose(vector(), [vector(), vector(1)], ids)

    def test_selection_file_change_invalidates_evaluation_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            train, evaluation = write_artifacts(Path(tmp))
            with (train / "selection.json").open("a") as stream:
                stream.write("\n")
            with self.assertRaisesRegex(ValueError, "evaluation_selection_hash_mismatch"):
                from_artifacts(train, evaluation)

    def test_policy_mutation_invalidates_frozen_policy_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            train, evaluation = write_artifacts(Path(tmp))
            path = evaluation / "report.json"
            report = json.loads(path.read_text())
            report["policies"]["primary_visual"]["threshold"] = -10
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "frozen_policy_binding_mismatch"):
                from_artifacts(train, evaluation)

    def test_selected_checkpoint_hash_is_checked_before_loading(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = {"kind": "adapter", "epoch": 1, "checkpoint": "wrong.safetensors",
                         "checkpoint_sha256": "0" * 64}
            train, evaluation = write_artifacts(Path(tmp), candidate=candidate)
            (train / "wrong.safetensors").write_bytes(b"synthetic corrupted checkpoint")
            with self.assertRaisesRegex(ValueError, "selected_checkpoint_hash_mismatch"):
                from_artifacts(train, evaluation)

    @unittest.skipUnless(importlib.util.find_spec("safetensors"), "safetensors dependency absent on local executor")
    def test_real_safetensors_loader_projects_both_query_and_gallery(self):
        from safetensors.numpy import save_file
        from visual_adapter import project_features
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            train = root / "training"
            train.mkdir()
            a, b = np.zeros((768, 64), dtype=np.float32), np.zeros((64, 768), dtype=np.float32)
            a[0, 0], b[0, 1] = 1, 1
            weights = {"a": a, "b": b}
            path = train / "adapter.safetensors"
            save_file(weights, str(path))
            candidate = {"kind": "adapter", "epoch": 1, "checkpoint": path.name,
                         "checkpoint_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            adapter = from_artifacts(*write_artifacts(root, candidate=candidate))
            query, gallery = np.stack([vector()]), np.stack([vector(), vector(1)])
            scores = project_features(query, weights) @ project_features(gallery, weights).T
            result = adapter.propose(query, gallery, ["a", "b"])[0]
            self.assertAlmostEqual(result["research_ranking"][0]["similarity"], float(scores[0, 0]), places=6)
            self.assertAlmostEqual(result["research_ranking"][1]["similarity"], float(scores[0, 1]), places=6)
            self.assertEqual(result["reason"], "qualification_failed")


if __name__ == "__main__":
    unittest.main()
