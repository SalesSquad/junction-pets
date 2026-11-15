"""Prepared, bounded visual candidates; ranks never grant task authority.

The float32 residual matches R3's arithmetic. Different GEMM batch shapes may
change last bits and therefore arbitrary near-tie ranks; no bitwise cross-device
or cross-batch guarantee is made. Exact score ties use original gallery order.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from types import MappingProxyType
from typing import Mapping

import numpy as np

from contract import ContractError, advisory_fields, sha256_bytes

DIMENSION = 768
ADAPTER_RANK = 64
MAX_GALLERY_ROWS = 50_000
MAX_QUERY_ROWS = 4_096
MAX_TOP_K = 128
MAX_BATCH_SIZE = 128
MAX_ID_UTF8_BYTES = 256
UNIT_NORM_TOLERANCE = 1e-3
NORM_VALIDATION_CHUNK_ROWS = 1024
FEATURE_ENCODING = "little-endian float32, C row-major"


def _error(code: str, message: str):
    raise ContractError(code, message)


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _immutable_float32(value: np.ndarray) -> np.ndarray:
    # Immutable bytes, rather than only writeable=False on owned ndarray memory,
    # also prevent a caller from re-enabling writes through an exposed view.
    raw = np.asarray(value, dtype="<f4", order="C").tobytes(order="C")
    return np.frombuffer(raw, dtype="<f4").reshape(value.shape)


def _feature_copy(value, label: str, maximum: int, *, query=False) -> np.ndarray:
    # Bound sized inputs before converting a possibly large Python sequence.
    try:
        outer_size = len(value)
    except (TypeError, ValueError):
        _error("invalid_embeddings", f"{label} must be a sized numeric array")
    if outer_size > maximum and not (query and outer_size == DIMENSION):
        _error("embedding_limit", f"{label} exceeds {maximum} rows")
    try:
        array = np.asarray(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ContractError("invalid_embeddings", f"{label} is not a numeric matrix") from exc
    if query and array.ndim == 1:
        array = array[None, :]
    if (array.ndim != 2 or not 1 <= array.shape[0] <= maximum
            or array.shape[1] != DIMENSION or array.dtype.kind not in "fiu"):
        _error("invalid_embeddings", f"{label} requires 1..{maximum} real numeric rows of dimension 768")
    # The digest describes exactly this copied float32 representation, not a
    # caller's different original dtype, strides or subsequent mutations.
    copied = _immutable_float32(array)
    if not np.isfinite(copied).all():
        _error("nonfinite_embeddings", f"{label} has a non-finite float32 value")
    nonunit = False
    for offset in range(0, len(copied), NORM_VALIDATION_CHUNK_ROWS):
        norms = np.linalg.norm(copied[offset:offset + NORM_VALIDATION_CHUNK_ROWS].astype(np.float64), axis=1)
        if not np.isfinite(norms).all() or np.any(norms < 1e-12):
            _error("zero_embeddings", f"{label} contains a zero or invalid norm")
        # Preserve the original whole-matrix error priority: a later zero/invalid
        # norm still takes precedence over an earlier merely nonunit row.
        nonunit |= not np.allclose(norms, 1.0, rtol=0.0, atol=UNIT_NORM_TOLERANCE)
    if nonunit:
        _error("unnormalized_embeddings", f"{label} must already be unit normalized")
    return copied


def _ids(value, count: int, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)):
        _error("invalid_ids", f"{label} must be a sized ID sequence")
    try:
        if len(value) != count:
            _error("id_count_mismatch", f"{label} must match the embedding row count")
        ids = tuple(value)
    except TypeError as exc:
        raise ContractError("invalid_ids", f"{label} must be a sized ID sequence") from exc
    if len(ids) != count:
        _error("id_count_mismatch", f"{label} changed while being copied")
    for item in ids:
        if not isinstance(item, str) or not item.strip():
            _error("invalid_ids", f"{label} must contain nonempty strings")
        try:
            size = len(item.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise ContractError("invalid_ids", f"{label} must contain valid UTF-8 strings") from exc
        if size > MAX_ID_UTF8_BYTES:
            _error("id_size_limit", f"{label} exceeds {MAX_ID_UTF8_BYTES} bytes per ID")
    if len(set(ids)) != count:
        _error("duplicate_ids", f"{label} must be unique")
    return ids


def _weights(a, b):
    if a is None and b is None:
        return None, None
    if a is None or b is None:
        _error("incomplete_adapter", "Both residual matrices are required")
    result = []
    for value, shape in ((a, (DIMENSION, ADAPTER_RANK)),
                         (b, (ADAPTER_RANK, DIMENSION))):
        try:
            array = np.asarray(value)
        except (TypeError, ValueError) as exc:
            raise ContractError("invalid_adapter", "Residual matrices must be float32 arrays") from exc
        if array.shape != shape or array.dtype != np.float32:
            _error("invalid_adapter", "Residual matrices must have float32 shapes (768,64) and (64,768)")
        if not np.isfinite(array).all():
            _error("nonfinite_adapter", "Residual matrices must be finite")
        result.append(_immutable_float32(array))
    return tuple(result)


def _project(features: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    # Retain R3's operation order and float32 normalization. Warnings are not
    # suppressed; actual nonfinite or degenerate results fail explicitly.
    residual = features + (features @ a) @ b
    if not np.isfinite(residual).all():
        _error("invalid_projection", "Residual projection produced non-finite values")
    norms = np.linalg.norm(residual, axis=1, keepdims=True)
    if not np.isfinite(norms).all() or np.any(norms < 1e-12):
        _error("invalid_projection", "Residual projection produced a zero or non-finite norm")
    result = residual / norms
    if not np.isfinite(result).all():
        _error("invalid_projection", "Residual normalization produced non-finite values")
    return result


def _bounded_integer(value, label: str, maximum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        _error("invalid_limit", f"{label} must be an integer")
    value = int(value)
    if not 1 <= value <= maximum:
        _error("invalid_limit", f"{label} must be between 1 and {maximum}")
    return value


def _stable_top_k(row: np.ndarray, top_k: int) -> np.ndarray:
    if top_k == len(row):
        return np.argsort(-row, kind="stable")
    # Partition finds the boundary, but arbitrarily selects tied boundary rows.
    # Reconstruct that tie set in original order before sorting at most top_k.
    partition = np.argpartition(row, len(row) - top_k)[-top_k:]
    boundary = np.min(row[partition])
    better = np.flatnonzero(row > boundary)
    tied = np.flatnonzero(row == boundary)[:top_k - len(better)]
    selected = np.concatenate((better, tied))
    return selected[np.lexsort((selected, -row[selected]))]


@dataclass(frozen=True, slots=True, init=False, eq=False)
class PreparedCandidateIndex:
    """Own one immutable projected gallery; every result is research-only."""

    _gallery: np.ndarray
    _gallery_ids: tuple[str, ...]
    _a: np.ndarray | None
    _b: np.ndarray | None
    _bindings: Mapping[str, object]

    def __init__(self, gallery_features, gallery_ids, a=None, b=None):
        features = _feature_copy(gallery_features, "gallery", MAX_GALLERY_ROWS)
        ids = _ids(gallery_ids, len(features), "gallery_ids")
        a_copy, b_copy = _weights(a, b)
        feature_sha = sha256_bytes(features.tobytes(order="C"))
        projected = (features if a_copy is None else
                     _immutable_float32(_project(features, a_copy, b_copy)))
        bindings = {
            "feature_encoding": FEATURE_ENCODING,
            "dimension": DIMENSION,
            "gallery_count": len(features),
            "gallery_features_sha256": feature_sha,
            "projected_gallery_sha256": sha256_bytes(projected.tobytes(order="C")),
            "gallery_id_order_sha256": sha256_bytes(_canonical(ids)),
            "adapter_a_sha256": None if a_copy is None else sha256_bytes(a_copy.tobytes(order="C")),
            "adapter_b_sha256": None if b_copy is None else sha256_bytes(b_copy.tobytes(order="C")),
            "adapter_rank": 0 if a_copy is None else ADAPTER_RANK,
        }
        bindings["index_sha256"] = sha256_bytes(_canonical(bindings))
        object.__setattr__(self, "_gallery", projected)
        object.__setattr__(self, "_gallery_ids", ids)
        object.__setattr__(self, "_a", a_copy)
        object.__setattr__(self, "_b", b_copy)
        object.__setattr__(self, "_bindings", MappingProxyType(bindings))

    def describe(self) -> dict:
        return {
            **advisory_fields("meta.retrieval-acceleration.prepared-index"),
            "gallery_count": len(self._gallery_ids),
            "dimension": DIMENSION,
            "adapter_rank": 0 if self._a is None else ADAPTER_RANK,
            "gallery_projection_count": 0 if self._a is None else 1,
            "bindings": dict(self._bindings),
            "limits": {"max_gallery_rows": MAX_GALLERY_ROWS, "max_query_rows": MAX_QUERY_ROWS,
                       "max_top_k": MAX_TOP_K, "max_batch_size": MAX_BATCH_SIZE,
                       "max_id_utf8_bytes": MAX_ID_UTF8_BYTES,
                       "maximum_score_chunk_bytes": MAX_BATCH_SIZE * len(self._gallery_ids) * 4},
            "ranking": "descending float32 similarity; exact ties by original gallery row",
            "numerical_contract": "R3 float32 residual and normalization; raw normalized identity inputs are preserved",
            "batching_limit": "GEMM batch shapes may change last bits and arbitrary near-tie rankings",
            "binding_scope": "supplied copied-byte consistency; not signature, provenance or execution attestation",
            "scores_are_probabilities": False,
            "model_quality_evaluated": False,
        }

    def search(self, query_features, query_ids, top_k=32, batch_size=16) -> dict:
        top_k = _bounded_integer(top_k, "top_k", min(MAX_TOP_K, len(self._gallery_ids)))
        batch_size = _bounded_integer(batch_size, "batch_size", MAX_BATCH_SIZE)
        queries = _feature_copy(query_features, "query", MAX_QUERY_ROWS, query=True)
        ids = _ids(query_ids, len(queries), "query_ids")
        results = []
        chunks = 0
        for offset in range(0, len(queries), batch_size):
            chunk = queries[offset:offset + batch_size]
            projected = chunk if self._a is None else _project(chunk, self._a, self._b)
            scores = projected @ self._gallery.T
            if not np.isfinite(scores).all():
                _error("nonfinite_scores", "Retrieval produced non-finite scores")
            for local_row, row in enumerate(scores):
                selected = _stable_top_k(row, top_k)
                results.append({"query_id": ids[offset + local_row],
                                "candidates": [{"candidate_id": self._gallery_ids[int(index)],
                                                "gallery_index": int(index), "score": float(row[index])}
                                               for index in selected]})
            chunks += 1
        return {
            **advisory_fields("meta.retrieval-acceleration.candidates"),
            "index": self.describe(),
            "query_count": len(queries), "top_k": top_k, "batch_size": batch_size,
            "query_chunks": chunks,
            "largest_score_chunk_rows": min(batch_size, len(queries)),
            "query_features_sha256": sha256_bytes(queries.tobytes(order="C")),
            "query_id_order_sha256": sha256_bytes(_canonical(ids)),
            "scores_are_probabilities": False,
            "accepted_candidate": None,
            "model_quality_evaluated": False,
            "queries": results,
        }
