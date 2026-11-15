#!/usr/bin/env python3
"""Audit original GitHub ZIPs, source receipts, group splits and reported metrics.

This does not unpickle or rerun fitted models and is not provider attestation.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import zipfile

import numpy as np
from sklearn.model_selection import GroupKFold

SOURCE = "76138f0c27fca50694aef7b6016af65478df65e4"
INDEX_SHA = "1ddd091d63168af573e1593c49d4084b74f277aa972420dce253ade68e6829f9"
RUN = 43672442214
LINES = ("v2d", "g1", "robo")
METHODS = ("ridge", "trees", "mlp")


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def numeric(a, b):
    return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-12)


def read_zip(path, record):
    raw = path.read_bytes()
    require(len(raw) == record["size_in_bytes"] and
            "sha256:" + digest(raw) == record["digest"], "OUTER_ARTIFACT_DIGEST")
    archive = zipfile.ZipFile(io.BytesIO(raw))
    names = archive.namelist()
    require(len(names) == len(set(names)) and all(
        not name.startswith("/") and ".." not in PurePosixPath(name).parts
        for name in names), "UNSAFE_ARTIFACT_PATHS")
    return archive


def verify_receipt(archive):
    manifest_raw = archive.read("manifest.json")
    manifest = json.loads(manifest_raw)
    receipt = json.loads(archive.read("receipt.json"))
    command = json.loads(archive.read("command.json"))
    binding = receipt["binding"]
    require(receipt["status"] == "succeeded" and receipt["sourceVerified"] is True
            and receipt["harnessVerified"] is True and manifest["complete"] is True
            and receipt["manifest"]["sha256"] == digest(manifest_raw)
            and binding["sourceSha"] == binding["harnessSha"] == SOURCE
            and binding["workload"] == "hf-open3d-ml"
            and command["state"] == "completed" and command["exitCode"] == 0
            and command["wrapperExitCode"] == 0, "RECEIPT_OR_SOURCE_MISMATCH")
    for item in manifest["files"]:
        data = archive.read(item["path"])
        require(len(data) == item["bytes"] and digest(data) == item["sha256"],
                "INNER_ARTIFACT_DIGEST")
    return receipt


def audit(root, index_path, local_features):
    index_raw = index_path.read_bytes()
    require(digest(index_raw) == INDEX_SHA, "ARTIFACT_INDEX_DIGEST")
    index = json.loads(index_raw)
    require(len(index) == 48 and len({x["id"] for x in index}) == 48,
            "ARTIFACT_COUNT")
    rows, features, prep, summary, plan = {}, {}, None, None, None
    receipts = 0
    provider_verified = False
    actual_cost_known = False
    for record in index:
        require(record["expired"] is False, "ARCHIVE_REPORTED_EXPIRED")
        name = record["name"]
        path = root / (str(record["id"]) + ".zip")
        with read_zip(path, record) as archive:
            if name.startswith("craci-plan-"):
                plan = json.loads(archive.read("plan.json"))
                continue
            receipt = verify_receipt(archive)
            receipts += 1
            provider_verified |= receipt["providerAttestationVerified"] is True
            actual_cost_known |= receipt["cost"]["actual"] is not None
            prefix = "artifacts/hf-open3d/"
            if name.startswith("hf-open3d-prepared-"):
                require(prep is None, "DUPLICATE_PREPARATION")
                prep = json.loads(archive.read(prefix + "preparation.json"))
                for line in LINES:
                    with zipfile.ZipFile(io.BytesIO(archive.read(prefix + line + ".zip"))) as inner:
                        require(inner.namelist() == [line + ".npz"], "FEATURE_ARCHIVE_CONTENT")
                        raw = inner.read(line + ".npz")
                    entry = prep["lines"][line]
                    require(len(raw) == entry["bytes"] and digest(raw) == entry["sha256"],
                            "FEATURE_DIGEST")
                    if local_features:
                        require(digest((local_features / (line + ".npz")).read_bytes()) == entry["sha256"],
                                "LOCAL_FEATURE_DIGEST")
                    with np.load(io.BytesIO(raw), allow_pickle=False) as data:
                        features[line] = {key: data[key] for key in ("Y", "baseline", "groups")}
            elif name.startswith("hf-open3d-summary-"):
                require(summary is None, "DUPLICATE_SUMMARY")
                summary = json.loads(archive.read(prefix + "summary.json"))
            elif name.startswith("hf-open3d-cell-"):
                result = json.loads(archive.read(prefix + "result.json"))
                key = (result["line"], result["fold"], result["method"])
                require(key not in rows and result["promotion_authorized"] is False,
                        "DUPLICATE_OR_PROMOTED_CELL")
                model_hash = hashlib.sha256()
                for part in result["trained_model"]["parts"]:
                    packed = archive.read(prefix + part["file"])
                    require(digest(packed) == part["archive_sha256"], "MODEL_ARCHIVE_DIGEST")
                    with zipfile.ZipFile(io.BytesIO(packed)) as inner:
                        require(inner.namelist() == [part["entry"]], "MODEL_PART_CONTENT")
                        raw = inner.read(part["entry"])
                    require(len(raw) == part["bytes"] and digest(raw) == part["sha256"],
                            "MODEL_PART_DIGEST")
                    model_hash.update(raw)
                require(model_hash.hexdigest() == result["trained_model"]["sha256"],
                        "MODEL_DIGEST")
                rows[key] = result
            else:
                raise ValueError("UNKNOWN_ARTIFACT")
    require(receipts == 47 and plan and plan["harnessSha"] == SOURCE
            and plan["workload"] == "hf-open3d-ml" and plan["jobCount"] == 47
            and plan["maxParallel"] == 6 and len(plan["matrix"]["include"]) == 42,
            "PLAN_OR_RECEIPT_COUNT")
    require(prep and prep["verified_files"] == 112 and summary and summary["cells"] == 45,
            "PREPARATION_OR_SUMMARY_MISSING")
    expected = {(line, fold, method) for line in LINES for fold in range(5) for method in METHODS}
    require(set(rows) == expected and not provider_verified and not actual_cost_known,
            "CELL_SET_OR_CLAIM_MISMATCH")
    limits = {"v2d": 0.002, "g1": 0.02, "robo": 0.005}
    recomputed = {}
    for line in LINES:
        arrays = features[line]
        y, baseline, groups = arrays["Y"], arrays["baseline"], arrays["groups"]
        splits = list(GroupKFold(n_splits=5).split(np.zeros((len(y), 1)), y, groups))
        recomputed[line] = {}
        for method in METHODS:
            group_rows, total_squares, n = [], 0.0, 0
            for fold, (fit, held) in enumerate(splits):
                row = rows[(line, fold, method)]
                fit_groups = set(groups[fit].tolist())
                held_groups = set(groups[held].tolist())
                require(not fit_groups.intersection(held_groups)
                        and row["group_overlap"] == 0
                        and row["feature_sha256"] == prep["lines"][line]["sha256"]
                        and row["fit_examples"] == len(fit)
                        and row["heldout_examples"] == len(held)
                        and set(x["group"] for x in row["heldout_group_metrics"]) == held_groups,
                        "GROUP_SPLIT_MISMATCH")
                for group in row["heldout_group_metrics"]:
                    selected = held[groups[held] == group["group"]]
                    measured_zero = float(np.sqrt(np.mean(y[selected].astype(np.float64) ** 2)))
                    measured_velocity = float(np.sqrt(np.mean(
                        (y[selected].astype(np.float64) - baseline[selected]) ** 2)))
                    require(group["examples"] == len(selected)
                            and numeric(group["persistence"]["rmse"], measured_zero)
                            and numeric(group["constant_velocity"]["rmse"], measured_velocity),
                            "GROUP_BASELINE_MISMATCH")
                    group_rows.append(group)
                moving = np.sqrt(np.mean(y[held].astype(np.float64) ** 2, axis=1)) > limits[line]
                require(row["moving_examples"] == int(moving.sum()), "MOVING_COUNT_MISMATCH")
                n += len(held)
                total_squares += row["model"]["rmse"] ** 2 * len(held)
            require(len({g["group"] for g in group_rows}) == len(group_rows)
                    == prep["lines"][line]["groups"], "REPEATED_TEST_GROUP")
            macro = sum(g["model"]["rmse"] for g in group_rows) / len(group_rows)
            baseline_macro = sum(g["constant_velocity"]["rmse"] for g in group_rows) / len(group_rows)
            better = sum(g["model"]["rmse"] < g["constant_velocity"]["rmse"] for g in group_rows)
            expected_row = summary["lines"][line][method]
            require(n == expected_row["heldout_examples"]
                    and numeric(macro, expected_row["macro_group_rmse"])
                    and numeric(baseline_macro, expected_row["macro_group_constant_velocity_rmse"])
                    and numeric(math.sqrt(total_squares / n), expected_row["pooled_rmse"])
                    and better == expected_row["groups_better_than_constant_velocity"],
                    "SUMMARY_MISMATCH")
            recomputed[line][method] = {
                "macro_group_rmse": macro, "baseline": baseline_macro,
                "groups_better": better, "groups": len(group_rows),
                "mlp_not_converged_before_limit": sum(
                    rows[(line, fold, method)]["converged_before_limit"] is False
                    for fold in range(5)) if method == "mlp" else None,
            }
    return {
        "run": RUN, "source_sha": SOURCE, "github_artifacts": len(index),
        "verified_receipts": receipts, "verified_model_cells": len(rows),
        "prepared_source_files_reported": prep["verified_files"],
        "features_match_separately_downloaded_local_data": bool(local_features),
        "artifact_index_sha256": digest(index_raw),
        "provider_attestation_verified": provider_verified,
        "actual_cost_known": actual_cost_known,
        "model_predictions_independently_replayed": False,
        "group_split_and_baselines_recomputed": True,
        "results": recomputed,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--local-features", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.artifacts, args.index, args.local_features)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2, sort_keys=True)
        output.write("\n")
    print(json.dumps(result, sort_keys=True))
