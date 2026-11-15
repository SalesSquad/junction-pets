#!/usr/bin/env python3
"""Validate and summarize exactly 45 fixed open-data training cells."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import zipfile

LINES = ("v2d", "g1", "robo")
METHODS = ("ridge", "trees", "mlp")
EXPECTED = {(line, fold, method) for line in LINES for fold in range(5) for method in METHODS}


def summarize(artifacts, output):
    found = {}
    for path in artifacts.rglob("result.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        key = row["line"], row["fold"], row["method"]
        if key not in EXPECTED or key in found or row["promotion_authorized"] is not False:
            raise ValueError("unexpected or duplicate result cell")
        digest = hashlib.sha256()
        for part in row["trained_model"]["parts"]:
            name = part["file"]
            if Path(name).name != name:
                raise ValueError("unsafe model part path")
            archive_path = path.parent / name
            if hashlib.sha256(archive_path.read_bytes()).hexdigest() != part["archive_sha256"]:
                raise ValueError("model archive mismatch")
            with zipfile.ZipFile(archive_path) as archive:
                if archive.namelist() != [part["entry"]]:
                    raise ValueError("unexpected model archive member")
                data = archive.read(part["entry"])
            if len(data) != part["bytes"] or hashlib.sha256(data).hexdigest() != part["sha256"]:
                raise ValueError("model part mismatch")
            digest.update(data)
        if digest.hexdigest() != row["trained_model"]["sha256"]:
            raise ValueError("model reassembly mismatch")
        if row["group_overlap"] != 0 or row["fit_groups"] < 1 or row["heldout_groups"] < 1:
            raise ValueError("group leakage")
        found[key] = row
    if set(found) != EXPECTED:
        raise ValueError(f"expected 45 unique cells, got {len(found)}")
    summary = {}
    for line in LINES:
        hashes = {row["feature_sha256"] for key, row in found.items() if key[0] == line}
        if len(hashes) != 1:
            raise ValueError("source feature hashes disagree")
        for fold in range(5):
            rows = [found[(line, fold, method)] for method in METHODS]
            fields = ("fit_examples", "heldout_examples", "fit_groups", "heldout_groups",
                      "moving_examples", "persistence", "constant_velocity")
            if any(any(row[field] != rows[0][field] for field in fields) for row in rows[1:]):
                raise ValueError("paired-fold denominators or baselines disagree")
            reference = [(g["group"], g["examples"], g["persistence"], g["constant_velocity"])
                         for g in rows[0]["heldout_group_metrics"]]
            for row in rows[1:]:
                other = [(g["group"], g["examples"], g["persistence"], g["constant_velocity"])
                         for g in row["heldout_group_metrics"]]
                if other != reference:
                    raise ValueError("paired groups or group baselines disagree")
        summary[line] = {}
        for method in METHODS:
            rows = [found[(line, fold, method)] for fold in range(5)]
            count = sum(row["heldout_examples"] for row in rows)
            groups = [group for row in rows for group in row["heldout_group_metrics"]]
            if len({group["group"] for group in groups}) != len(groups):
                raise ValueError("a held-out group appeared in multiple folds")
            summary[line][method] = {
                "heldout_examples": count,
                "heldout_groups": len(groups),
                "macro_group_rmse": sum(g["model"]["rmse"] for g in groups) / len(groups),
                "macro_group_persistence_rmse": sum(g["persistence"]["rmse"] for g in groups) / len(groups),
                "macro_group_constant_velocity_rmse": sum(g["constant_velocity"]["rmse"] for g in groups) / len(groups),
                "groups_better_than_constant_velocity": sum(
                    g["model"]["rmse"] < g["constant_velocity"]["rmse"] for g in groups),
                "pooled_rmse": math.sqrt(sum(row["model"]["rmse"] ** 2
                                              * row["heldout_examples"] for row in rows) / count),
                "persistence_rmse": math.sqrt(sum(row["persistence"]["rmse"] ** 2
                                                   * row["heldout_examples"] for row in rows) / count),
                "constant_velocity_rmse": math.sqrt(sum(row["constant_velocity"]["rmse"] ** 2
                                                         * row["heldout_examples"] for row in rows) / count),
                "units": rows[0]["units"], "folds": len(rows),
            }
    result = {
        "schema": "junction.open3d.grouped-forecast-summary.v1",
        "cells": len(found), "lines": summary,
        "note": "Cross-validation on selected public datasets. It is not an untouched final evaluation, a robot policy, or evidence of physical safety.",
        "promotion_authorized": False,
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(summarize(args.artifacts, args.out), sort_keys=True))
