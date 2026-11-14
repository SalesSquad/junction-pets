#!/usr/bin/env python3
"""Independent bounded float64 audit; never trains, tunes or changes evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import zipfile

import numpy as np

TOLERANCE = 1e-5
MAX_SAMPLE_ROWS = 32
MAX_SECONDS = 120
METHODS = ("frozen_image_image", "frozen_hybrid_text_weight_0.25",
           "primary_visual", "cosine_preservation_ablation")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text())


def deadline(started):
    require(time.monotonic() - started <= MAX_SECONDS, "diagnostic_deadline_exceeded")


def normalize64(x):
    x = np.asarray(x, dtype=np.float64)
    norm = np.sqrt(np.einsum("ij,ij->i", x, x, optimize=False))
    require(np.isfinite(norm).all() and np.all(norm > 1e-12), "invalid_reference_norm")
    result = x / norm[:, None]
    require(np.isfinite(result).all(), "nonfinite_reference_normalization")
    return result


def project64(x, weights):
    x = np.asarray(x, dtype=np.float64)
    if weights is not None:
        low = np.einsum("nd,dr->nr", x, weights["a"], optimize=False)
        x = x + np.einsum("nr,rd->nd", low, weights["b"], optimize=False)
    return normalize64(x)


def dot64(q, g):
    result = np.einsum("id,jd->ij", q, g, optimize=False)
    require(np.isfinite(result).all(), "nonfinite_reference_scores")
    return result


def checked_npz(path, expected_sha, keys, rows, report, label, started, features=False):
    deadline(started)
    actual_sha = sha(path)
    report["artifacts"][label] = {"path": str(path), "sha256": actual_sha, "arrays": {}}
    require(actual_sha == expected_sha, "artifact_hash_mismatch:" + label)
    with zipfile.ZipFile(path) as archive:
        require(sum(item.file_size for item in archive.infolist()) <= 512 * 1024**2,
                "npz_uncompressed_size_limit:" + label)
    result = {}
    with np.load(path, allow_pickle=False) as archive:
        require(set(archive.files) == set(keys), "unexpected_npz_keys:" + label)
        for key in keys:
            deadline(started)
            value = archive[key]
            n = rows if isinstance(rows, int) else rows[key]
            expected_shape = (n, 768) if features else (n, n)
            require(value.dtype == np.float32 and value.shape == expected_shape,
                    "array_dtype_or_shape_mismatch:" + label + ":" + key)
            finite = bool(np.isfinite(value).all())
            report["artifacts"][label]["arrays"][key] = {
                "shape": list(value.shape), "dtype": str(value.dtype),
                "elements_checked": int(value.size), "all_finite": finite}
            require(finite, "nonfinite_cached_array:" + label + ":" + key)
            result[key] = value
    return result


def checked_weights(node, training, report, label):
    require(node["kind"] in ("identity", "adapter"), "invalid_checkpoint_kind")
    if node["kind"] == "identity":
        require(node["epoch"] == 0 and node["checkpoint"] is None and node["checkpoint_sha256"] is None,
                "invalid_identity_checkpoint")
        report["checkpoints"][label] = {"kind": "identity", "sha256": None}
        return None
    relative = Path(node["checkpoint"])
    path = training / relative
    require(node["epoch"] >= 1 and not relative.is_absolute() and ".." not in relative.parts
            and not path.is_symlink() and path.resolve().is_relative_to(training),
            "checkpoint_path_or_epoch_invalid")
    digest = sha(path)
    require(digest == node["checkpoint_sha256"], "checkpoint_hash_mismatch:" + label)
    from safetensors.numpy import load_file
    weights = load_file(str(path))
    require(set(weights) == {"a", "b"}, "unexpected_checkpoint_keys")
    require(weights["a"].shape == (768, 64) and weights["b"].shape == (64, 768),
            "checkpoint_shape_mismatch")
    require(all(w.dtype == np.float32 and np.isfinite(w).all() for w in weights.values()),
            "checkpoint_dtype_or_finiteness_failure")
    report["checkpoints"][label] = {"kind": "adapter", "sha256": digest,
                                   "path": str(path), "all_weights_finite": True}
    return {key: value.astype(np.float64) for key, value in weights.items()}


def audit(campaign, report, started):
    training, evaluation = campaign / "training", campaign / "evaluation"
    paths = {"selection": training / "selection.json", "evaluation_report": evaluation / "report.json",
             "freeze": evaluation / "evaluation-freeze.json", "feature_receipt": evaluation / "features.json",
             "dataset": campaign / "fresh-data/dataset.json", "campaign_start": campaign / "campaign-start.json",
             "train_receipt": campaign / "logs/train-visual.json"}
    docs = {key: read_json(path) for key, path in paths.items()}
    report["document_sha256"] = {key: sha(path) for key, path in paths.items()}
    selection, fresh, freeze = docs["selection"], docs["evaluation_report"], docs["freeze"]
    dataset, receipt, start = docs["dataset"], docs["feature_receipt"], docs["campaign_start"]
    require(selection["confirmation_candidate"] == selection["primary"], "confirmation_candidate_changed")
    require(selection["ablation"]["recipe"] == "cosine_preservation_ablation"
            and selection["ablation"]["preservation"] == 0.05, "unexpected_ablation_recipe")
    require(freeze["confirmation_candidate"] == selection["primary"]
            and freeze["ablation_candidate"] == selection["ablation"], "freeze_selection_mismatch")
    require(fresh["selection"] == selection["primary"] and fresh["ablation_selection"] == selection["ablation"],
            "report_selection_mismatch")
    require(fresh["source_commit"] == freeze["source_commit"] == start["source_commit"], "source_commit_mismatch")
    require(fresh["selection_sha256"] == freeze["selection_sha256"] == report["document_sha256"]["selection"],
            "selection_document_hash_mismatch")
    data_sha = report["document_sha256"]["dataset"]
    require(data_sha == fresh["dataset_sha256"] == freeze["dataset_sha256"] == receipt["dataset_sha256"]
            == (campaign / "fresh-data/dataset.sha256").read_text().strip(), "dataset_hash_mismatch")
    records = dataset["records"]
    require(1 <= len(records) <= 2400 and set(r["split"] for r in records) == {"cal", "test"},
            "fresh_dataset_bound_or_partition_mismatch")
    require(receipt["product_order"] == [r["product_id"] for r in records], "feature_order_mismatch")
    report["executed_source"] = {"commit": fresh["source_commit"], "evaluation_files": freeze["source_hashes"],
                                 "training_files": selection["source_hashes"],
                                 "training_protocol_sha256": selection["protocol_sha256"],
                                 "evaluation_protocol_sha256": fresh["protocol_sha256"]}
    require(receipt["feature_sha256"] == fresh["feature_sha256"], "feature_receipt_hash_mismatch")
    feature_keys = ("gallery", "query", "text", "hint")
    features = checked_npz(evaluation / "features.npz", fresh["feature_sha256"], feature_keys,
                           len(records), report, "fresh_features", started, features=True)
    # The campaign preserves the external R2 cache path in its exact argv receipt.
    command = docs["train_receipt"]["command"]
    require(command.count("--features") == 1 and docs["train_receipt"]["exit_code"] == 0,
            "training_feature_receipt_invalid")
    prior_path = Path(command[command.index("--features") + 1])
    require(prior_path.is_absolute(), "prior_feature_receipt_path_not_absolute")
    prior_data = read_json(campaign / "prior-data/dataset.json")
    require(sha(campaign / "prior-data/dataset.json") == selection["dataset_sha256"], "prior_dataset_hash_mismatch")
    prior_rows = len(prior_data["records"])
    require(1 <= prior_rows <= 6000 and selection["feature_sha256"] == start["prior_features_sha256"],
            "prior_cache_binding_mismatch")
    checked_npz(prior_path, selection["feature_sha256"], feature_keys, prior_rows,
                report, "prior_features", started, features=True)
    indices = {split: np.asarray([i for i, r in enumerate(records) if r["split"] == split], dtype=np.int64)
               for split in ("cal", "test")}
    shapes = {split + "__" + method: len(index) for split, index in indices.items() for method in METHODS}
    scores = checked_npz(evaluation / "scores.npz", fresh["scores_sha256"], shapes, shapes,
                         report, "fresh_scores", started)
    weights = {"primary_visual": checked_weights(selection["primary"], training, report, "primary"),
               "cosine_preservation_ablation": checked_weights(selection["ablation"], training, report, "ablation")}
    failed = []
    for split, index in indices.items():
        deadline(started)
        n = len(index)
        require(n > 0, "empty_partition")
        sample = np.linspace(0, n - 1, min(MAX_SAMPLE_ROWS, n), dtype=np.int64)
        require(len(np.unique(sample)) == len(sample), "duplicate_sample_index")
        q, g, t = (features[key][index].astype(np.float64) for key in ("query", "gallery", "text"))
        frozen = dot64(normalize64(q[sample]), normalize64(g))
        references = {"frozen_image_image": frozen,
                      "frozen_hybrid_text_weight_0.25": 0.75 * frozen + 0.25 * dot64(normalize64(q[sample]), normalize64(t))}
        for method, adapter in weights.items():
            references[method] = frozen if adapter is None else dot64(project64(q[sample], adapter), project64(g, adapter))
        for method in METHODS:
            deadline(started)
            key = split + "__" + method
            stored = scores[key][sample].astype(np.float64)
            difference = np.abs(stored - references[method])
            maximum = float(difference.max())
            passed = bool(np.isfinite(difference).all() and maximum <= TOLERANCE)
            report["comparisons"][key] = {"sample_row_indices": sample.tolist(),
                "sample_dataset_indices": index[sample].tolist(), "sample_rows": len(sample),
                "gallery_columns": n, "elements_compared": int(difference.size),
                "max_absolute_difference": maximum, "mean_absolute_difference": float(difference.mean()),
                "row_max_absolute_difference": difference.max(axis=1).tolist(),
                "elements_above_tolerance": int(np.sum(difference > TOLERANCE)), "passed": passed}
            if not passed:
                failed.append(key)
    require(not failed, "score_reference_tolerance_failure:" + ",".join(failed))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("new_diagnostic_output_required; historical outputs are preserved")
    started = time.monotonic()
    report = {"schema_version": 1, "kind": "meta.r3.independent_numerical_diagnostic", "status": "FAIL",
              "diagnostic_source_sha256": sha(Path(__file__)), "numpy": np.__version__, "python": platform.python_version(),
              "reference": "float64 np.einsum(optimize=False), explicit L2 normalization; no BLAS matmul",
              "absolute_tolerance": TOLERANCE, "max_sample_rows_per_partition_method": MAX_SAMPLE_ROWS,
              "sample_selection": "evenly spaced partition row indices; independent of observed scores",
              "bounded_seconds": MAX_SECONDS, "warnings_suppressed": False,
              "artifacts": {}, "checkpoints": {}, "comparisons": {},
              "scope": "All values in recorded prior/fresh feature caches and fresh score matrices are checked for finiteness; numerical references sample query rows only.",
              "training_or_threshold_changes": False, "new_field_performance_claim": False,
              "original_evidence_modified": False, "production_activation": False}
    try:
        audit(args.campaign.resolve(), report, started)
        report["status"] = "PASS"
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
    report["seconds"] = time.monotonic() - started
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "output": str(args.output),
                      "comparisons": len(report["comparisons"]), "error": report.get("error")}), flush=True)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
