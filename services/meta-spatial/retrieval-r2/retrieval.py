"""Numerical retrieval/evaluation utilities. Suggestions never grant authority."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter

import numpy as np


def normalize(x):
    x = np.asarray(x, dtype=np.float32)
    if x.ndim != 2 or not np.isfinite(x).all():
        raise ValueError("finite_matrix_required")
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    if np.any(norms < 1e-12):
        raise ValueError("zero_embedding")
    return x / norms


def apply_residual(x, a, b):
    x, a, b = (np.asarray(v, dtype=np.float32) for v in (x, a, b))
    if x.ndim != 2 or a.shape[0] != x.shape[1] or b.shape != (a.shape[1], x.shape[1]):
        raise ValueError("adapter_shape_mismatch")
    return normalize(x + (x @ a) @ b)


def validate_dataset(manifest):
    if manifest.get("kind") != "meta.public-abo-retrieval" or manifest.get("license") != "CC-BY-4.0":
        raise ValueError("unexpected_dataset")
    families, image_hashes, ids = {}, {}, set()
    categories = set(manifest["ood_categories"])
    counts = Counter()
    for r in manifest["records"]:
        if r["product_id"] in ids:
            raise ValueError("duplicate_product")
        ids.add(r["product_id"])
        split = r["split"]
        if split not in {"train", "dev", "cal", "test", "ood"}:
            raise ValueError("invalid_split")
        if r["category"] in categories and split != "ood":
            raise ValueError("ood_category_leak")
        if r["family_id"] in families and families[r["family_id"]] != split:
            raise ValueError("family_split_leak")
        families[r["family_id"]] = split
        if len(r["views"]) != 2 or r["views"][0]["sha256"] == r["views"][1]["sha256"]:
            raise ValueError("independent_catalog_views_required")
        for view in r["views"]:
            digest = view["sha256"]
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("invalid_image_sha256")
            if digest in image_hashes and image_hashes[digest] != split:
                raise ValueError("image_split_leak")
            image_hashes[digest] = split
        counts[split] += 1
    if dict(counts) != manifest["counts"]:
        raise ValueError("split_count_mismatch")
    if min(counts.get(s, 0) for s in ("train", "dev", "cal", "test", "ood")) < 20:
        raise ValueError("insufficient_split")
    return {"products": len(ids), "families": len(families), "unique_images": len(image_hashes), "counts": dict(counts)}


def tokenize(text):
    return re.findall(r"\w+", text.casefold(), flags=re.UNICODE)


def bm25_scores(queries, documents, k1=1.5, b=0.75):
    docs = [Counter(tokenize(d)) for d in documents]
    lengths = np.asarray([sum(d.values()) for d in docs], dtype=np.float32)
    average = max(float(lengths.mean()), 1.0)
    vocabulary = set(t for d in docs for t in d)
    frequencies = {t: sum(t in d for d in docs) for t in vocabulary}
    postings = {t: [(i, d[t]) for i, d in enumerate(docs) if t in d] for t in vocabulary}
    result = np.zeros((len(queries), len(docs)), dtype=np.float32)
    for qi, query in enumerate(queries):
        for token in set(tokenize(query)):
            if token not in frequencies:
                continue
            df = frequencies[token]
            idf = math.log(1.0 + (len(docs) - df + 0.5) / (df + 0.5))
            for di, tf in postings[token]:
                result[qi, di] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * lengths[di] / average))
    return result


def rank_normalize(scores):
    order = np.argsort(-scores, axis=1, kind="stable")
    ranks = np.empty_like(order)
    np.put_along_axis(ranks, order, np.arange(scores.shape[1])[None, :], axis=1)
    return 1.0 / (ranks.astype(np.float32) + 1.0)


def retrieval_metrics(scores, families=None):
    scores = np.asarray(scores)
    if scores.ndim != 2 or scores.shape[0] != scores.shape[1] or not np.isfinite(scores).all():
        raise ValueError("finite_square_scores_required")
    order = np.argsort(-scores, axis=1, kind="stable")
    ranks = (order == np.arange(len(scores))[:, None]).argmax(axis=1) + 1
    result = {"queries": len(scores), "recall_at_1": float(np.mean(ranks <= 1)), "recall_at_5": float(np.mean(ranks <= 5)), "recall_at_10": float(np.mean(ranks <= 10)), "mrr": float(np.mean(1 / ranks)), "ndcg_at_10": float(np.mean(np.where(ranks <= 10, 1 / np.log2(ranks + 1), 0))), "gallery_products": scores.shape[1]}
    if families is not None:
        f = np.asarray(families)
        result["family_recall_at_1"] = float(np.mean(f[order[:, 0]] == f))
    return result


def confidence(scores):
    scores = np.asarray(scores, dtype=np.float32)
    if scores.ndim != 2 or scores.shape[1] < 2 or np.isnan(scores).any():
        raise ValueError("invalid_scores")
    order = np.argsort(-scores, axis=1, kind="stable")[:, :2]
    top = np.take_along_axis(scores, order, axis=1)
    if not np.isfinite(top).all():
        raise ValueError("two_finite_candidates_required")
    # A score used only for thresholding. It is NOT a calibrated probability.
    return top[:, 0] + (top[:, 0] - top[:, 1]), order[:, 0]


def family_max(values, families):
    """Aggregate all variants; no ordering-dependent representative selection."""
    values = np.asarray(values)
    groups = {}
    for value, family in zip(values, families):
        groups[family] = max(groups.get(family, -np.inf), float(value))
    return np.asarray([groups[key] for key in sorted(groups)], dtype=np.float64)


def absent_family_scores(scores, families):
    f = np.asarray(families)
    result = scores.copy()
    result[f[:, None] == f[None, :]] = -np.inf
    return result


def upper_false_accept_bound(errors, n, alpha=0.05):
    if n <= 0:
        return 1.0
    if errors == 0:
        # Exact one-sided binomial upper bound at zero events.
        return 1.0 - alpha ** (1.0 / n)
    # One-sided Wilson approximation for nonzero counts; labelled in report.
    z = 1.6448536269514722
    p = errors / n
    return (p + z*z / (2*n) + z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))) / (1 + z*z/n)


def calibrate_threshold(scores, families, risk_target=0.01):
    if not 0 < risk_target < 1:
        raise ValueError("invalid_risk_target")
    positive, predicted = confidence(scores)
    negative_all, _ = confidence(absent_family_scores(scores, families))
    negative = family_max(negative_all, families)
    correct = predicted == np.arange(len(positive))
    # Present errors cover ALL query rows. The absent event is ANY acceptance
    # within each family, avoiding the same first-variant/argmax tie selection.
    # Calibration is a selection set; final claims require sealed evaluation.
    candidates = np.unique(np.concatenate((positive, negative)))
    best = None
    above_max = np.nextafter(np.float32(candidates.max()), np.float32(np.inf))
    for threshold in np.concatenate((candidates, [above_max])):
        accepted = positive >= threshold
        false_absent = int(np.sum(negative >= threshold))
        wrong_present = int(np.sum(accepted & ~correct))
        bound = upper_false_accept_bound(false_absent, len(negative))
        if bound <= risk_target and wrong_present == 0:
            candidate = {"threshold": float(threshold), "status": "calibrated_candidate_policy", "calibration_queries": len(positive), "calibration_families": len(negative), "calibration_coverage": float(accepted.mean()), "calibration_absent_families_with_any_false_accept": false_absent, "calibration_absent_family_upper95": bound, "calibration_wrong_present_all_queries": wrong_present, "absent_family_false_accept_rate_target": risk_target}
            if best is None or candidate["calibration_coverage"] > best["calibration_coverage"]:
                best = candidate
    if best is None:
        best = {"threshold": None, "status": "always_abstain_insufficient_calibration", "calibration_queries": len(positive), "calibration_families": len(negative), "calibration_coverage": 0.0, "absent_family_false_accept_rate_target": risk_target, "zero_error_upper95": upper_false_accept_bound(0, len(negative))}
    best["confidence_is_probability"] = False
    best["bound_method"] = "family_any_absent_accept; exact_zero_event_binomial_else_one_sided_Wilson95; final_test_required"
    best["conditional_accepted_error_certified"] = False
    return best


def policy_metrics(scores, families, policy):
    c, predicted = confidence(scores)
    negative, _ = confidence(absent_family_scores(scores, families))
    threshold = policy["threshold"]
    accepted = np.zeros(len(c), dtype=bool) if threshold is None else c >= threshold
    absent_accepted = np.zeros(len(c), dtype=bool) if threshold is None else negative >= threshold
    correct = predicted == np.arange(len(c))
    wrong_present = accepted & ~correct
    family_wrong = family_max(wrong_present, families) > 0
    family_absent = family_max(absent_accepted, families) > 0
    n = len(family_absent)
    errors = int(np.sum(family_absent))
    present_family_errors = int(np.sum(family_wrong))
    return {"queries": len(c), "families": n, "coverage": float(accepted.mean()), "abstention": float(1-accepted.mean()), "accepted": int(accepted.sum()), "correct_accepted": int(np.sum(accepted & correct)), "wrong_present_accepted": int(wrong_present.sum()), "accepted_precision": float(np.sum(accepted & correct)/accepted.sum()) if accepted.any() else None, "present_families_with_any_accepted_error": present_family_errors, "present_family_error_rate": present_family_errors/n, "present_family_error_upper95": upper_false_accept_bound(present_family_errors,n), "absent_query_false_accepts": int(absent_accepted.sum()), "absent_query_false_accept_rate": float(absent_accepted.mean()), "absent_family_false_accepts": errors, "absent_family_false_accept_rate": errors/n, "absent_family_upper95": upper_false_accept_bound(errors, n), "bound_method": "any_error_within_family; exact_zero_event_binomial_else_one_sided_Wilson95", "bound_assumption": "independent_connected_families; source_correlations_not_eliminated", "conditional_accepted_error_certified": False, "candidate_only": True, "identity_verified": False, "action_authorized": False}


def candidate_proposal(scores, product_ids, policy):
    values, top = confidence(np.asarray(scores, dtype=np.float32).reshape(1, -1))
    threshold = policy.get("threshold")
    accepted = threshold is not None and float(values[0]) >= threshold
    return {"decision": "candidate" if accepted else "abstain", "product_id": product_ids[int(top[0])] if accepted else None, "confidence_score": float(values[0]), "confidence_is_probability": False, "identity_verified": False, "action_authorized": False, "evidence_domain": "public_catalog_retrieval"}


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
