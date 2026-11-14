"""Predeclared fresh-cohort evaluation; no model/threshold changes on test."""
from __future__ import annotations

import argparse
from functools import lru_cache
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

R2 = Path(__file__).resolve().parent.parent / "retrieval-r2"
sys.path.insert(0, str(R2))
from retrieval import (absent_family_scores, confidence, family_max, file_sha256,
                       retrieval_metrics, write_json)
from train_retrieval import encode, load_features, verify_images


@lru_cache(maxsize=8192)
def exact_upper(errors: int, n: int, alpha: float = 0.05) -> float:
    """One-sided Clopper-Pearson bound, including nonzero error counts."""
    if not isinstance(errors, (int, np.integer)) or not isinstance(n, (int, np.integer)):
        raise ValueError("integer_counts_required")
    if n <= 0 or errors < 0 or errors > n or not 0 < alpha < 1:
        raise ValueError("invalid_binomial_counts")
    if errors == n:
        return 1.0
    if errors == 0:
        return -math.expm1(math.log(alpha) / n)
    k = np.arange(errors + 1, dtype=np.float64)
    log_comb = np.asarray([math.lgamma(n+1)-math.lgamma(int(j)+1)-math.lgamma(n-int(j)+1) for j in k])
    low, high = errors/n, 1.0
    for _ in range(70):
        p = (low + high) / 2
        log_pmf = log_comb + k*math.log(p) + (n-k)*math.log1p(-p)
        maximum = float(log_pmf.max())
        cdf = math.exp(maximum)*float(np.exp(log_pmf-maximum).sum())
        if cdf > alpha:
            low = p
        else:
            high = p
    return high


def policy_inputs(scores, families):
    scores = np.asarray(scores, dtype=np.float32)
    if scores.shape != (len(families), len(families)) or not np.isfinite(scores).all():
        raise ValueError("finite_square_scores_required")
    positive, predicted = confidence(scores)
    negative, _ = confidence(absent_family_scores(scores, families))
    return positive, predicted == np.arange(len(scores)), negative


def measure_policy(scores, families, threshold):
    positive, correct, negative = policy_inputs(scores, families)
    accepted = np.zeros(len(positive), dtype=bool) if threshold is None else positive >= threshold
    absent_accepted = np.zeros(len(negative), dtype=bool) if threshold is None else negative >= threshold
    wrong = accepted & ~correct
    present_family = family_max(wrong, families) > 0
    absent_family = family_max(absent_accepted, families) > 0
    combined = present_family | absent_family
    n, errors = len(combined), int(combined.sum())
    return {"queries": len(positive), "families": n, "accepted": int(accepted.sum()),
            "coverage": float(accepted.mean()), "wrong_present_accepted": int(wrong.sum()),
            "correct_accepted": int((accepted & correct).sum()),
            "accepted_precision": float(correct[accepted].mean()) if accepted.any() else None,
            "present_families_with_any_error": int(present_family.sum()),
            "absent_queries_accepted": int(absent_accepted.sum()),
            "absent_families_with_any_error": int(absent_family.sum()),
            "combined_families_with_any_error": errors,
            "combined_family_error_rate": errors/n,
            "combined_family_error_upper95": exact_upper(errors, n),
            "bound": "exact_one_sided_Clopper_Pearson_95",
            "risk_event": "any_present_wrong_OR_any_absent_accept_within_family",
            "denominator": "all_eligible_families",
            "independence_assumption": "connected_source_families; other correlations unknown",
            "conditional_accepted_error_certified": False,
            "physical_identity_verified": False, "action_authorized": False}


def calibrate_policy(scores, families, risk_target=0.01):
    positive, correct, negative = policy_inputs(scores, families)
    # Wrong-present confidence and absent confidence are aggregated with the
    # SAME sorted family order, so a family counts once for their union.
    bad_present = np.where(correct, -np.inf, positive)
    bad_family = family_max(np.maximum(bad_present, negative), families)
    candidates = np.unique(np.concatenate((positive, bad_family)))
    candidates = np.r_[candidates, np.nextafter(np.float32(candidates.max()), np.float32(np.inf))]
    best = None
    for threshold in candidates:
        accepted = positive >= threshold
        errors = int((bad_family >= threshold).sum())
        if np.any(accepted & ~correct) or exact_upper(errors, len(bad_family)) > risk_target:
            continue
        count = int(accepted.sum())
        if best is None or count > best[0]:
            best = (count, float(threshold))
    threshold = None if best is None else best[1]
    return {"threshold": threshold, "risk_target": risk_target,
            "confidence_is_probability": False,
            "status": "always_abstain_insufficient_calibration" if best is None else "calibration_selected_not_test_certified",
            "calibration": measure_policy(scores, families, threshold)}


def paired_family_bootstrap(candidate, baseline, families, resamples=2000, seed=14683):
    difference = (np.argmax(candidate, axis=1) == np.arange(len(candidate))).astype(float)
    difference -= (np.argmax(baseline, axis=1) == np.arange(len(baseline)))
    unique = sorted(set(families))
    f = np.asarray(families)
    sums = np.asarray([difference[f == family].sum() for family in unique])
    sizes = np.asarray([(f == family).sum() for family in unique])
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, len(unique), size=(resamples, len(unique)))
    values = sums[samples].sum(axis=1) / sizes[samples].sum(axis=1)
    interval = np.quantile(values, [0.025, 0.975])
    return {"recall_at_1_difference": float(difference.mean()), "interval95": interval.tolist(),
            "superiority_supported_by_interval": bool(interval[0] > 0),
            "method": "paired_family_cluster_percentile_bootstrap_query_weighted",
            "resamples": resamples, "seed": seed, "families": len(unique),
            "not_a_field_or_pretraining_independence_guarantee": True}


def validate_fresh(manifest, prior):
    from prepare_holdout import collision_proof, PRIOR_DATASET_SHA256
    if manifest.get("kind") != "meta.public-abo-fresh-r3-holdout" or manifest.get("prior_dataset_sha256") != PRIOR_DATASET_SHA256:
        raise ValueError("unexpected_fresh_dataset")
    records = manifest["records"]
    if set(r["split"] for r in records) != {"cal", "test"}:
        raise ValueError("unexpected_fresh_splits")
    proof = collision_proof(records, prior["records"])
    for split in ("cal", "test"):
        subset = [r for r in records if r["split"] == split]
        families = len(set(r["family_id"] for r in subset))
        if families < 400 or families != manifest["family_counts"][split] or len(subset) != manifest["counts"][split]:
            raise ValueError("fresh_partition_count_mismatch")
    return proof


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--prior-data", type=Path, required=True)
    p.add_argument("--training", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cache", type=Path)
    p.add_argument("--features", type=Path)
    p.add_argument("--source-commit", required=True)
    p.add_argument("--device", default="cuda")
    p.add_argument("--max-seconds", type=int, default=1200)
    a = p.parse_args()
    if a.output.exists() and any(a.output.iterdir()):
        p.error("fresh_evaluation_output_must_be_empty")
    a.output.mkdir(parents=True, exist_ok=True)
    from visual_adapter import load_selected, load_ablation, project_features
    started = time.monotonic()
    protocol_path = Path(__file__).with_name("protocol.json")
    protocol = json.loads(protocol_path.read_text())
    selection_path = a.training / "selection.json"
    selection = json.loads(selection_path.read_text())
    from train_visual import PROTOCOL as TRAIN_PROTOCOL, canonical, sha_bytes
    if selection.get("protocol_sha256") != sha_bytes(canonical(TRAIN_PROTOCOL)):
        raise ValueError("training_protocol_changed_since_selection")
    expected_sources = {name: file_sha256(Path(__file__).with_name(name))
                        for name in ("visual_adapter.py", "train_visual.py", "test_visual_adapter.py")}
    expected_sources["../retrieval-r2/retrieval.py"] = file_sha256(R2/"retrieval.py")
    if selection.get("source_hashes") != expected_sources:
        raise ValueError("training_core_changed_since_selection")
    prior_path, dataset_path = a.prior_data/"dataset.json", a.data/"dataset.json"
    if file_sha256(prior_path) != protocol["prior_dataset_sha256"]:
        raise ValueError("prior_dataset_hash_mismatch")
    manifest, prior = json.loads(dataset_path.read_text()), json.loads(prior_path.read_text())
    validate_fresh(manifest, prior)
    records, dataset_sha = manifest["records"], file_sha256(dataset_path)
    if (a.data/"dataset.sha256").read_text().strip() != dataset_sha:
        raise ValueError("fresh_dataset_seal_mismatch")
    if selection["dataset_sha256"] != protocol["prior_dataset_sha256"] or selection["feature_sha256"] != protocol["prior_feature_sha256"]:
        raise ValueError("training_input_binding_mismatch")
    if selection["confirmation_candidate"] != selection["primary"]:
        raise ValueError("confirmation_candidate_changed")
    primary_weights = load_selected(selection, a.training)
    ablation_weights = load_ablation(selection, a.training)
    # Immutable binding written BEFORE any fresh pixel/model inference/scoring.
    freeze = {"schema_version": 1, "source_commit": a.source_commit,
              "protocol_sha256": file_sha256(protocol_path), "selection_sha256": file_sha256(selection_path),
              "dataset_sha256": dataset_sha, "confirmation_candidate": selection["primary"],
              "ablation_candidate": selection["ablation"], "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "fresh_scores_observed": False,
              "source_hashes": {x.name: file_sha256(x) for x in Path(__file__).parent.glob("*.py")}}
    write_json(a.output/"evaluation-freeze.json", freeze)
    verified_images = verify_images(a.data, records)
    if a.features:
        features, feature_receipt = load_features(a.features, records, dataset_sha)
    else:
        features, feature_receipt = encode(a.data, records, a.output, a.device, 128, a.cache, started+a.max_seconds, dataset_sha)
    policies, partitions, matrices = {}, {}, {}
    for split in ("cal", "test"):
        indices = np.asarray([i for i,r in enumerate(records) if r["split"] == split])
        families = [records[i]["family_id"] for i in indices]
        q, g, t = (features[k][indices] for k in ("query", "gallery", "text"))
        frozen = q @ g.T
        scores = {"frozen_image_image": frozen,
                  "frozen_hybrid_text_weight_0.25": 0.75*frozen + 0.25*(q@t.T),
                  "primary_visual": frozen if primary_weights is None else project_features(q, primary_weights) @ project_features(g, primary_weights).T,
                  "cosine_preservation_ablation": frozen if ablation_weights is None else project_features(q, ablation_weights) @ project_features(g, ablation_weights).T}
        if split == "cal":
            policies = {name: calibrate_policy(s, families) for name,s in scores.items()}
            write_json(a.output/"frozen-policies.json", {"selection_sha256": freeze["selection_sha256"], "policies": policies,
                                                       "fresh_test_scores_observed": False})
        partitions[split] = {name: {"retrieval": retrieval_metrics(s, families),
                                    "policy": measure_policy(s, families, policies[name]["threshold"])} for name,s in scores.items()}
        matrices.update({split+"__"+name: s for name,s in scores.items()})
        if split == "test":
            paired = paired_family_bootstrap(scores["primary_visual"], frozen, families)
    np.savez_compressed(a.output/"scores.npz", **matrices)
    primary = partitions["test"]["primary_visual"]
    policy = primary["policy"]
    checks = {
        "recall_at_least_fixed_hybrid": primary["retrieval"]["recall_at_1"] >= partitions["test"]["frozen_hybrid_text_weight_0.25"]["retrieval"]["recall_at_1"],
        "coverage_at_least_20_percent": policy["coverage"] >= 0.20,
        "zero_wrong_present_accepted": policy["wrong_present_accepted"] == 0,
        "combined_family_upper95_at_most_1_percent": policy["combined_family_error_upper95"] <= 0.01,
    }
    report = {"schema_version": 1, "kind": "meta.visual_adapter.r3.fresh_evaluation", "source_commit": a.source_commit,
              "protocol_sha256": freeze["protocol_sha256"], "selection_sha256": freeze["selection_sha256"],
              "dataset_sha256": dataset_sha, "verified_unique_images": verified_images,
              "feature_sha256": feature_receipt["feature_sha256"], "scores_sha256": file_sha256(a.output/"scores.npz"),
              "counts": manifest["counts"], "family_counts": manifest["family_counts"],
              "partitions": partitions, "paired_primary_vs_frozen": paired, "policies": policies,
              "product_gate": {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks},
              "selection": selection["primary"], "ablation_selection": selection["ablation"],
              "production_activation": False, "physical_identity_verified": False,
              "seconds": time.monotonic()-started, "limitations": protocol["limitations"]}
    write_json(a.output/"report.json", report)
    print(json.dumps({"stage": "FRESH_EVALUATION_COMPLETE", "product_gate": report["product_gate"],
                      "paired": paired, "primary_recall": primary["retrieval"]["recall_at_1"]}), flush=True)


if __name__ == "__main__":
    main()
