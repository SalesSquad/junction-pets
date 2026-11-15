"""Portable R4 research scorer. A ranking is never physical identity authority.

The R model's score is a ranking utility, not a probability. The historical
ABO experiment cannot authorize production, even if its diagnostic score is high.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np


FEATURE_NAMES = (
    "f_visual", "f_adapted", "f_text", "f_reverse_rank", "f_density", "f_gap"
)


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"finite_number_required:{label}")
    return float(value)


def _vector(value, label):
    if not isinstance(value, list) or len(value) != len(FEATURE_NAMES):
        raise ValueError(f"six_values_required:{label}")
    return np.asarray([_number(v, label) for v in value], dtype=np.float64)


class ResearchReranker:
    """Load only an explicitly hash-bound, numeric model; never deserialize RDS."""

    def __init__(self, model, model_sha256):
        if model.get("schema_version") != 1 or model.get("kind") != "ridge_pairwise_logistic":
            raise ValueError("unsupported_model_schema")
        if tuple(model.get("feature_names", [])) != FEATURE_NAMES:
            raise ValueError("feature_order_mismatch")
        if model.get("action_authorized") is not False:
            raise ValueError("research_model_required")
        self.center = _vector(model.get("scaler", {}).get("center"), "center")
        self.scale = _vector(model.get("scaler", {}).get("scale"), "scale")
        if np.any(self.scale <= 0):
            raise ValueError("positive_scale_required")
        self.coefficients = _vector(model.get("coefficients"), "coefficients")
        self.intercept = _number(model.get("intercept", 0), "intercept")
        policy = model.get("policy")
        if not isinstance(policy, dict) or policy.get("qualification") is not False:
            raise ValueError("historical_experiment_cannot_qualify_runtime")
        if policy.get("score_field") != "top_score_plus_margin":
            raise ValueError("unsupported_confidence_function")
        self.threshold = policy.get("threshold")
        if self.threshold is not None:
            self.threshold = _number(self.threshold, "threshold")
        self.model_sha256 = model_sha256

    @classmethod
    def from_file(cls, path, *, expected_sha256):
        if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
            raise ValueError("expected_model_hash_required")
        p = Path(path)
        if p.is_symlink() or p.stat().st_size > 1_048_576:
            raise ValueError("bounded_regular_model_required")
        data = p.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected_sha256:
            raise ValueError("model_hash_mismatch")
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate_model_field")
                result[key] = value
            return result
        model = json.loads(data, object_pairs_hook=unique_object,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite_json")))
        return cls(model, digest)

    def rank(self, candidates, *, limit=10):
        if not isinstance(candidates, list) or not 1 <= len(candidates) <= 100:
            raise ValueError("one_to_100_candidates_required")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("bounded_limit_required")
        ids, matrix = [], []
        for item in candidates:
            if not isinstance(item, dict):
                raise ValueError("candidate_object_required")
            candidate_id = item.get("candidate_id")
            if not isinstance(candidate_id, str) or not candidate_id or len(candidate_id) > 256:
                raise ValueError("bounded_candidate_id_required")
            ids.append(candidate_id)
            matrix.append([_number(item.get(name), name) for name in FEATURE_NAMES])
        if len(set(ids)) != len(ids):
            raise ValueError("unique_candidates_required")
        features = np.asarray(matrix, dtype=np.float64)
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            scores = ((features - self.center) / self.scale) @ self.coefficients + self.intercept
        if not np.isfinite(scores).all():
            raise ValueError("nonfinite_rank_score")
        order = sorted(range(len(ids)), key=lambda i: (-float(scores[i]), ids[i]))
        top = float(scores[order[0]])
        # A missing runner-up supplies no evidence of separation.
        confidence = top + (top - float(scores[order[1]])) if len(order) >= 2 else None
        if confidence is not None and not math.isfinite(confidence):
            raise ValueError("nonfinite_confidence")
        above = bool(confidence is not None and self.threshold is not None and confidence >= self.threshold)
        return {
            "schema_version": 1,
            "status": "research_candidates_only",
            "candidates": [{"candidate_id": ids[i], "rank_score": float(scores[i])} for i in order[:limit]],
            "confidence": confidence,
            "confidence_is_probability": False,
            "diagnostic_threshold_pass": above,
            "accepted": False,
            "reason": "independent_r4_qualification_required",
            "model_sha256": self.model_sha256,
            "physical_identity_verified": False,
            "action_authorized": False,
        }
