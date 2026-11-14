"""Fail-closed R3 consumer for precomputed, unit-normalized SigLIP2 embeddings.

Qualification covers the public ABO experiment only. Rankings are research
suggestions, and even a qualified candidate never verifies physical identity or
authorizes an action. This module does not capture images or call a provider.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Literal, Sequence, TypedDict

import numpy as np

from visual_adapter import load_selected, project_features


class RankedCandidate(TypedDict):
    product_id: str
    similarity: float


class RetrievalDecision(TypedDict):
    kind: Literal["candidate", "abstain"]
    reason: Literal["threshold_met", "qualification_failed", "no_qualified_threshold", "below_threshold"]
    accepted_candidate: str | None
    research_ranking: list[RankedCandidate]
    confidence_score: float
    threshold: float | None
    qualification: Literal["PASS", "FAIL"]
    selection_sha256: str
    evaluation_report_sha256: str
    evidence_domain: Literal["public_abo_catalog_only"]
    caller_embedding_provenance_verified: Literal[False]
    confidence_is_probability: Literal[False]
    physical_identity_verified: Literal[False]
    action_authorized: Literal[False]


def _read_bound_json(root: Path, name: str):
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("artifact_path_outside_root")
    payload = path.read_bytes()
    return json.loads(payload), hashlib.sha256(payload).hexdigest()


def _embedding_matrix(value, *, query: bool):
    array = np.asarray(value)
    if np.iscomplexobj(array):
        raise ValueError("real_embeddings_required")
    array = np.asarray(array, dtype=np.float32)
    if query and array.ndim == 1:
        array = array[None, :]
    if array.ndim != 2 or not len(array) or array.shape[1] != 768 or not np.isfinite(array).all():
        raise ValueError("finite_nonempty_768_dimensional_embeddings_required")
    norms = np.linalg.norm(array.astype(np.float64), axis=1, keepdims=True)
    if np.any(norms < 1e-12) or not np.isfinite(norms).all():
        raise ValueError("nonzero_finite_embeddings_required")
    if not np.allclose(norms, 1.0, rtol=0.0, atol=1e-3):
        raise ValueError("unit_normalized_embeddings_required")
    # Match evaluation's float32 arithmetic exactly. Re-normalization here can
    # change a near-tied score or cross a frozen calibration threshold.
    return array


@dataclass(frozen=True)
class VisualRetrievalAdapter:
    """Use from_artifacts to bind one frozen primary selection and its policy."""

    _weights: dict[str, np.ndarray] | None
    threshold: float | None
    qualification: Literal["PASS", "FAIL"]
    selection_sha256: str
    evaluation_report_sha256: str

    @classmethod
    def from_artifacts(cls, training_root: str | Path, evaluation_root: str | Path):
        training_root, evaluation_root = Path(training_root).resolve(), Path(evaluation_root).resolve()
        selection, selection_sha = _read_bound_json(training_root, "selection.json")
        report, report_sha = _read_bound_json(evaluation_root, "report.json")
        frozen, _ = _read_bound_json(evaluation_root, "frozen-policies.json")
        if report.get("schema_version") != 1 or report.get("kind") != "meta.visual_adapter.r3.fresh_evaluation":
            raise ValueError("unexpected_evaluation_contract")
        if report.get("selection_sha256") != selection_sha or frozen.get("selection_sha256") != selection_sha:
            raise ValueError("evaluation_selection_hash_mismatch")
        if report.get("selection") != selection.get("primary"):
            raise ValueError("evaluation_primary_selection_mismatch")
        if frozen.get("fresh_test_scores_observed") is not False or frozen.get("policies") != report.get("policies"):
            raise ValueError("frozen_policy_binding_mismatch")
        policy = report["policies"]["primary_visual"]
        threshold = policy.get("threshold")
        if policy.get("confidence_is_probability") is not False:
            raise ValueError("probability_claim_not_supported")
        if threshold is not None and (isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not np.isfinite(threshold)):
            raise ValueError("invalid_policy_threshold")
        gate = report.get("product_gate", {})
        qualification = gate.get("status")
        required_checks = {"recall_at_least_fixed_hybrid", "coverage_at_least_20_percent",
                           "zero_wrong_present_accepted", "combined_family_upper95_at_most_1_percent"}
        if qualification not in {"PASS", "FAIL"}:
            raise ValueError("unexpected_qualification_status")
        checks = gate.get("checks", {})
        if qualification == "PASS" and (set(checks) != required_checks or any(value is not True for value in checks.values())):
            raise ValueError("inconsistent_pass_qualification")
        weights = load_selected(selection, training_root)
        if weights is not None:
            weights = {key: value.copy() for key, value in weights.items()}
            for value in weights.values():
                value.flags.writeable = False
        return cls(weights, float(threshold) if threshold is not None else None,
                   qualification, selection_sha, report_sha)

    def propose(self, query_embeddings, gallery_embeddings,
                product_ids: Sequence[str]) -> list[RetrievalDecision]:
        """Rank unit-normalized 768-dimensional embeddings; never infer provenance."""
        query = _embedding_matrix(query_embeddings, query=True)
        gallery = _embedding_matrix(gallery_embeddings, query=False)
        if isinstance(product_ids, (str, bytes)):
            raise ValueError("unique_product_id_sequence_required")
        ids = list(product_ids)
        if len(ids) != len(gallery) or len(ids) < 2 or any(not isinstance(pid, str) or not pid.strip() for pid in ids) or len(set(ids)) != len(ids):
            raise ValueError("unique_product_ids_must_match_gallery")
        # Identity uses raw verified feature values. Trained candidates apply
        # the same shared projection to both views, exactly as evaluation does.
        scores = (query @ gallery.T if self._weights is None else
                  project_features(query, self._weights) @ project_features(gallery, self._weights).T)
        if not np.isfinite(scores).all():
            raise ValueError("nonfinite_retrieval_scores")
        order = np.argsort(-scores, axis=1, kind="stable")
        decisions = []
        for row, ranking in zip(scores, order):
            top, second = row[ranking[:2]]
            confidence = float(np.float32(top + np.float32(top - second)))
            reason = ("qualification_failed" if self.qualification != "PASS" else
                      "no_qualified_threshold" if self.threshold is None else
                      "below_threshold" if confidence < self.threshold else "threshold_met")
            accepted = reason == "threshold_met"
            decisions.append({
                "kind": "candidate" if accepted else "abstain", "reason": reason,
                "accepted_candidate": ids[int(ranking[0])] if accepted else None,
                "research_ranking": [{"product_id": ids[int(i)], "similarity": float(row[i])} for i in ranking[:5]],
                "confidence_score": confidence, "threshold": self.threshold,
                "qualification": self.qualification, "selection_sha256": self.selection_sha256,
                "evaluation_report_sha256": self.evaluation_report_sha256,
                "evidence_domain": "public_abo_catalog_only",
                "caller_embedding_provenance_verified": False, "confidence_is_probability": False,
                "physical_identity_verified": False, "action_authorized": False,
            })
        return decisions


def from_artifacts(training_root: str | Path, evaluation_root: str | Path) -> VisualRetrievalAdapter:
    return VisualRetrievalAdapter.from_artifacts(training_root, evaluation_root)
