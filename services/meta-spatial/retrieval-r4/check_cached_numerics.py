#!/usr/bin/env python3
"""Bounded independent arithmetic check of the actual R4 exported scores.

Sixteen evenly spaced query indices per split; the smallest/largest retained
baseline ranks select two candidates each, without consulting truth labels.
Scalar math.fsum and float64 unoptimized einsum do not repeat the BLAS matmuls
whose runtime warnings prompted this check. Passing does not diagnose a backend.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time

import numpy as np

from prepare_candidates import ROOT, SOURCE_PINS, WORK_ID, load_inputs, sha256
from features import FEATURE_NAMES

TOLERANCE = 1e-5
SPLITS = ("train", "dev", "cal", "test")
SCORE_FIELDS = ("f_visual", "f_text", "f_adapted")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict_json(path):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate_manifest_field")
            result[key] = value
        return result
    def bad_constant(value):
        raise ValueError("nonfinite_manifest_constant")
    return json.loads(Path(path).read_bytes(), object_pairs_hook=object_pairs, parse_constant=bad_constant)


def scalar_dot(left, right):
    left, right = np.asarray(left, dtype=np.float64), np.asarray(right, dtype=np.float64)
    require(left.ndim == right.ndim == 1 and left.shape == right.shape, "scalar_dot_shape_mismatch")
    require(np.isfinite(left).all() and np.isfinite(right).all(), "nonfinite_reference_input")
    result = math.fsum(float(a) * float(b) for a, b in zip(left, right))
    require(math.isfinite(result), "nonfinite_reference_dot")
    return result


def reference_projection(vector, weights):
    x = np.asarray(vector, dtype=np.float64)
    require(x.ndim == 1 and np.isfinite(x).all(), "nonfinite_reference_projection_input")
    if weights is None:
        # Match the explicitly selected identity path, without renormalization.
        return x
    a, b = np.asarray(weights["a"], dtype=np.float64), np.asarray(weights["b"], dtype=np.float64)
    require(a.ndim == b.ndim == 2 and a.shape[0] == len(x) and b.shape == (a.shape[1], len(x)),
            "reference_adapter_shape_mismatch")
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        latent = np.einsum("d,dr->r", x, a, optimize=False)
        residual = np.einsum("r,rd->d", latent, b, optimize=False)
        projected = x + residual
    require(np.isfinite(projected).all(), "nonfinite_reference_projection")
    norm = math.sqrt(math.fsum(float(value) * float(value) for value in projected))
    require(math.isfinite(norm) and norm > 1e-12, "invalid_reference_projection_norm")
    result = projected / norm
    require(np.isfinite(result).all(), "nonfinite_normalized_reference")
    return result


def sampled_rows(path, manifest, partitions):
    wanted, indices, samples = {}, {}, {}
    for split in SPLITS:
        records = partitions[split]["records"]
        chosen = np.linspace(0, len(records) - 1, min(16, len(records)), dtype=np.int64)
        require(len(set(chosen.tolist())) == len(chosen), "duplicate_sample_query_index")
        indices[split] = {r["product_id"]: i for i, r in enumerate(records)}
        wanted[split] = {records[int(i)]["product_id"] for i in chosen}
        for qi in chosen:
            samples[(split, records[int(qi)]["product_id"])] = []
    counts = Counter()
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == manifest.get("columns"), "csv_header_manifest_mismatch")
        for row in reader:
            split = row.get("split")
            require(split in SPLITS, "unexpected_csv_split")
            counts[split] += 1
            if row.get("query_id") not in wanted[split]:
                continue
            require(row.get("candidate_id") in indices[split], "candidate_not_in_bound_split")
            try:
                rank = int(row["baseline_rank"])
            except (TypeError, ValueError) as error:
                raise ValueError("invalid_sample_baseline_rank") from error
            require(rank >= 1, "invalid_sample_baseline_rank")
            # Selection is independent of label, query title, and family fields.
            item = {"candidate_id": row["candidate_id"], "baseline_rank": rank,
                    **{name: float(row[name]) for name in SCORE_FIELDS}}
            require(all(math.isfinite(item[name]) for name in SCORE_FIELDS), "nonfinite_exported_sample_score")
            selected = samples[(split, row["query_id"])]
            if not selected:
                selected.extend([item, item])
            else:
                if (rank, item["candidate_id"]) < (selected[0]["baseline_rank"], selected[0]["candidate_id"]):
                    selected[0] = item
                if (rank, item["candidate_id"]) > (selected[1]["baseline_rank"], selected[1]["candidate_id"]):
                    selected[1] = item
    for split in SPLITS:
        require(counts[split] == manifest["partitions"][split]["rows"], "csv_partition_row_count_mismatch")
    for selected in samples.values():
        require(len(selected) == 2 and selected[0]["candidate_id"] != selected[1]["candidate_id"],
                "two_distinct_sample_candidates_required")
    return indices, samples


def run(args):
    manifest_sha = sha256(args.manifest)
    csv_sha = sha256(args.candidates)
    manifest = strict_json(args.manifest)
    require(manifest.get("schema_version") == 1 and manifest.get("kind") == "meta.r4.actual_candidate_features"
            and manifest.get("work_id") == WORK_ID, "unexpected_candidate_manifest")
    require(manifest.get("input_sha256") == csv_sha, "candidate_csv_hash_mismatch")
    require(manifest.get("feature_names") == list(FEATURE_NAMES), "feature_contract_mismatch")
    require(manifest.get("admission", {}).get("family_disjoint") is True
            and manifest.get("admission", {}).get("image_hash_disjoint") is True, "dataset_not_admitted")
    expected_sources = {"features.py", "prepare_candidates.py", "contract.json", *SOURCE_PINS}
    require(set(manifest.get("source_hashes", {})) == expected_sources, "unexpected_export_source_set")
    sources = {name: sha256(ROOT / name) for name in sorted(expected_sources)}
    require(sources == manifest["source_hashes"], "export_source_hash_mismatch")
    partitions, weights, _, admission, binding = load_inputs(
        args.prior_data, args.prior_features, args.fresh_data, args.fresh_features, args.training)
    require(binding == manifest.get("binding"), "original_input_binding_mismatch")
    require(admission == manifest.get("admission"), "original_admission_mismatch")
    require({s: len(partitions[s]["records"]) for s in SPLITS} == manifest.get("counts"),
            "original_partition_count_mismatch")
    indices, sample = sampled_rows(args.candidates, manifest, partitions)
    pairs, maxima = [], {field: 0.0 for field in SCORE_FIELDS}
    for (split, query_id), selected in sample.items():
        qi = indices[split][query_id]
        arrays = partitions[split]["arrays"]
        query = arrays["query"][qi]
        projected_query = reference_projection(query, weights)
        for role, row in zip(("minimum_retained_baseline_rank", "maximum_retained_baseline_rank"), selected):
            gi = indices[split][row["candidate_id"]]
            gallery, text = arrays["gallery"][gi], arrays["text"][gi]
            reference = {"f_visual": scalar_dot(query, gallery), "f_text": scalar_dot(query, text),
                         "f_adapted": scalar_dot(projected_query, reference_projection(gallery, weights))}
            errors = {field: abs(row[field] - reference[field]) for field in SCORE_FIELDS}
            require(all(math.isfinite(v) for v in errors.values()), "nonfinite_comparison_error")
            for field, value in errors.items():
                maxima[field] = max(maxima[field], value)
            pairs.append({"split": split, "query_id": query_id, "query_index": qi,
                          "candidate_id": row["candidate_id"], "candidate_index": gi,
                          "selection": role, "baseline_rank": row["baseline_rank"],
                          "exported": {field: row[field] for field in SCORE_FIELDS},
                          "reference": reference, "absolute_error": errors,
                          "pass": all(v <= TOLERANCE for v in errors.values())})
    require(len(pairs) == 128, "expected_128_predeclared_sample_pairs")
    require(sha256(args.candidates) == csv_sha and sha256(args.manifest) == manifest_sha,
            "input_changed_during_numeric_check")
    require({name: sha256(ROOT / name) for name in sources} == sources, "export_source_changed_during_numeric_check")
    return {"schema_version": 1, "kind": "meta.r4.sampled_independent_numeric_check", "work_id": WORK_ID,
            "status": "PASS" if all(pair["pass"] for pair in pairs) else "FAIL",
            "checker_source_commit": args.source_commit, "export_source_commit": manifest.get("source_commit"),
            "checker_sha256": sha256(Path(__file__)), "export_source_hashes": sources,
            "candidate_csv_sha256": csv_sha, "manifest_sha256": manifest_sha, "input_binding": binding,
            "pairs_checked": len(pairs), "tolerance_absolute": TOLERANCE, "maximum_absolute_errors": maxima,
            "selection_protocol": "16 evenly spaced query indices per split; min/max retained baseline rank; no labels read",
            "reference_method": "math.fsum scalar dots; float64 numpy.einsum optimize=False residual projections; scalar norm",
            "samples": pairs, "original_warnings_preserved": True, "backend_warning_cause_diagnosed": False,
            "limitations": ["Sampled numerical parity only, not exhaustive score or ranking verification",
                            "Reverse ranks, density and gap features are not recomputed by this check",
                            "Original NumPy/Accelerate warning cause remains unresolved; no suppression or source mutation",
                            "Historical public catalog data only; no fresh model qualification"],
            "qualification": False, "action_authorized": False, "physical_identity_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("prior-data", "prior-features", "fresh-data", "fresh-features", "training", "candidates", "manifest", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    if re.fullmatch(r"[0-9a-f]{40}", args.source_commit) is None:
        parser.error("exact checker source commit required")
    if args.output.exists() or args.output.is_symlink():
        parser.error("new numeric-check output required; preserve previous evidence")
    started = time.monotonic()
    checker_before = sha256(Path(__file__))
    try:
        result = run(args)
        require(sha256(Path(__file__)) == checker_before, "checker_source_changed_during_execution")
    except Exception as error:
        result = {"schema_version": 1, "kind": "meta.r4.sampled_independent_numeric_check", "work_id": WORK_ID,
                  "status": "FAIL", "error_type": type(error).__name__, "error": str(error),
                  "checker_source_commit": args.source_commit, "checker_sha256": checker_before,
                  "qualification": False, "action_authorized": False,
                  "backend_warning_cause_diagnosed": False, "original_warnings_preserved": True}
    result["seconds"] = time.monotonic() - started
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"status": result["status"], "pairs_checked": result.get("pairs_checked"),
                      "maximum_absolute_errors": result.get("maximum_absolute_errors"),
                      "error": result.get("error"), "backend_warning_cause_diagnosed": False}), flush=True)
    if result["status"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
