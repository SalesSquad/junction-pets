"""Label-free candidate features for the declared, transductive R4 catalog run.

Functions in this module never take query titles, family labels, or ground truth.
Reverse rank and density use unlabeled query images within the SAME split. This
is a batch-catalog research protocol, not a qualified streaming-camera feature.
"""
from __future__ import annotations

import re
from typing import Sequence

import numpy as np

FEATURE_NAMES = ("f_visual", "f_adapted", "f_text", "f_reverse_rank", "f_density", "f_gap")
REQUIRED_COLUMNS = ("split", "query_id", "query_family", "candidate_id", "candidate_family", "label",
                    *FEATURE_NAMES, "baseline_rank")
CSV_COLUMNS = (*REQUIRED_COLUMNS, "visual_rank", "text_rank")
RRF_CONSTANT = 60


def embedding_matrix(value, *, rows=None, dimension=None):
    """Validate actual unit-normalized float32 cache values without changing them."""
    array = np.asarray(value)
    if array.dtype != np.float32 or array.ndim != 2 or min(array.shape) < 1:
        raise ValueError("nonempty_float32_embedding_matrix_required")
    if rows is not None and array.shape[0] != rows:
        raise ValueError("embedding_count_mismatch")
    if dimension is not None and array.shape[1] != dimension:
        raise ValueError("embedding_dimension_mismatch")
    if not np.isfinite(array).all():
        raise ValueError("nonfinite_embedding")
    norms = np.linalg.norm(array.astype(np.float64), axis=1)
    if not np.allclose(norms, 1.0, rtol=0.0, atol=0.001):
        raise ValueError("unit_normalized_embeddings_required")
    return array


def score_matrix(value):
    array = np.asarray(value)
    if array.ndim != 2 or array.shape[0] < 1 or array.shape[1] < 2 or not np.issubdtype(array.dtype, np.floating):
        raise ValueError("finite_score_matrix_with_two_candidates_required")
    if not np.isfinite(array).all():
        raise ValueError("nonfinite_scores")
    return array


def stable_ranks(scores, *, axis=1):
    """1-based ranks; exact ties retain the source-bound input ordering."""
    scores = score_matrix(scores)
    if axis not in (0, 1):
        raise ValueError("rank_axis_must_be_zero_or_one")
    order = np.argsort(-scores, axis=axis, kind="stable")
    ranks = np.empty(scores.shape, dtype=np.int32)
    values = np.arange(1, scores.shape[axis] + 1, dtype=np.int32)
    values = values[:, None] if axis == 0 else values[None, :]
    np.put_along_axis(ranks, order, np.broadcast_to(values, order.shape), axis=axis)
    return ranks


def select_candidates(visual, adapted, text, candidate_ids: Sequence[str], *, limit=100):
    """Top-limit RRF of each retriever's top-limit union; never inject a positive."""
    visual, adapted, text = (score_matrix(x) for x in (visual, adapted, text))
    if visual.shape != adapted.shape or visual.shape != text.shape:
        raise ValueError("retriever_score_shapes_must_match")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("candidate_limit_must_be_one_to_100")
    ids = list(candidate_ids)
    if len(ids) != visual.shape[1] or any(not isinstance(v, str) or not v for v in ids) or len(set(ids)) != len(ids):
        raise ValueError("unique_candidate_ids_must_match_gallery")
    ranks = {name: stable_ranks(matrix) for name, matrix in
             (("visual", visual), ("adapted", adapted), ("text", text))}
    count = min(limit, len(ids))
    selected = np.empty((len(visual), count), dtype=np.int32)
    string_ids = np.asarray(ids)
    for qi in range(len(visual)):
        union = np.flatnonzero(np.logical_or.reduce([r[qi] <= count for r in ranks.values()]))
        rrf = sum(1.0 / (RRF_CONSTANT + ranks[name][qi, union].astype(np.float64))
                  for name in ("visual", "adapted", "text"))
        ordering = np.lexsort((string_ids[union], ranks["text"][qi, union], ranks["visual"][qi, union],
                               ranks["adapted"][qi, union], -rrf))
        selected[qi] = union[ordering[:count]]
    return selected, ranks


def candidate_features(visual, adapted, text, candidates, *, ranks=None):
    """Compute only the six allowlisted fields; labels cannot affect this function."""
    visual, adapted, text = (score_matrix(x) for x in (visual, adapted, text))
    if visual.shape != adapted.shape or visual.shape != text.shape:
        raise ValueError("retriever_score_shapes_must_match")
    candidates = np.asarray(candidates)
    if (candidates.ndim != 2 or candidates.shape[0] != len(visual) or not candidates.shape[1]
            or not np.issubdtype(candidates.dtype, np.integer)
            or np.any(candidates < 0) or np.any(candidates >= visual.shape[1])):
        raise ValueError("invalid_candidate_indices")
    if any(len(set(row.tolist())) != len(row) for row in candidates):
        raise ValueError("duplicate_candidate_indices")
    reverse = stable_ranks(visual, axis=0)
    top_count = min(10, len(visual))
    density_mean = np.partition(visual, len(visual) - top_count, axis=0)[-top_count:].mean(axis=0, dtype=np.float64)
    adapted_order = np.argsort(-adapted, axis=1, kind="stable")[:, :2]
    top_two = np.take_along_axis(adapted, adapted_order, axis=1)
    rows = np.arange(len(visual))[:, None]
    best_other = np.where(candidates == adapted_order[:, :1], top_two[:, 1:2], top_two[:, :1])
    result = {
        "f_visual": visual[rows, candidates],
        "f_adapted": adapted[rows, candidates],
        "f_text": text[rows, candidates],
        "f_reverse_rank": 1.0 / reverse[rows, candidates],
        "f_density": visual[rows, candidates].astype(np.float64) - density_mean[candidates],
        "f_gap": adapted[rows, candidates] - best_other,
    }
    if any(not np.isfinite(value).all() for value in result.values()):
        raise ValueError("nonfinite_candidate_feature")
    return result


def multiview_scores(query_embeddings, gallery_embeddings, gallery_product_ids,
                     *, query_image_sha256, gallery_image_sha256):
    """Optional max-over-views helper with byte separation, not used by R4 caches.

    These hashes must come from admitted input records. Their syntax alone does
    not authenticate images. The exporter does not call this helper or claim
    that its historical two-view source contains multiview enrollment.
    """
    query = embedding_matrix(query_embeddings)
    gallery = embedding_matrix(gallery_embeddings, dimension=query.shape[1])
    ids, qhash, ghash = list(gallery_product_ids), list(query_image_sha256), list(gallery_image_sha256)
    if len(ids) != len(gallery) or any(not isinstance(v, str) or not v for v in ids):
        raise ValueError("gallery_product_ids_must_match_views")
    if len(qhash) != len(query) or len(ghash) != len(gallery):
        raise ValueError("image_hashes_must_match_embeddings")
    if any(not isinstance(v, str) or re.fullmatch(r"[0-9a-f]{64}", v) is None for v in qhash + ghash):
        raise ValueError("image_sha256_required")
    if set(qhash) & set(ghash):
        raise ValueError("query_image_cannot_be_gallery_enrollment")
    if len(set(ghash)) != len(ghash):
        raise ValueError("duplicate_gallery_image_bytes")
    product_ids = list(dict.fromkeys(ids))
    raw = query @ gallery.T
    if not np.isfinite(raw).all():
        raise ValueError("nonfinite_multiview_scores")
    scores = np.column_stack([raw[:, np.flatnonzero(np.asarray(ids) == pid)].max(axis=1) for pid in product_ids])
    return product_ids, scores
