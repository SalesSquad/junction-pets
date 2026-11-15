#!/usr/bin/env python3
"""Train one fixed model on one group-disjoint open-data fold."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time
import zipfile

import joblib
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

LINES = ("v2d", "g1", "robo")
METHODS = ("ridge", "trees", "mlp")
THRESHOLDS = {"v2d": 0.002, "g1": 0.02, "robo": 0.005}
UNITS = {"v2d": "metres", "g1": "radians", "robo": "metres"}
CHUNK_BYTES = 6 * 1024 * 1024
MAX_MODEL_BYTES = 50 * 1024 * 1024


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        while part := source.read(1024 * 1024):
            h.update(part)
    return h.hexdigest()


def metrics(y, predicted, moving):
    error = np.asarray(y, dtype=np.float64) - np.asarray(predicted, dtype=np.float64)
    if not np.isfinite(error).all():
        raise ValueError("non-finite predictions")
    return {
        "rmse": float(np.sqrt(np.mean(error * error))),
        "mae": float(np.mean(np.abs(error))),
        "moving_rmse": (float(np.sqrt(np.mean(error[moving] ** 2)))
                        if moving.any() else None),
    }


def train(features, output, line, fold, method, threads=32):
    if line not in LINES or method not in METHODS or fold not in range(5):
        raise ValueError("unregistered experiment cell")
    if not 1 <= threads <= 32:
        raise ValueError("invalid thread count")
    report = json.loads((features / "preparation.json").read_text(encoding="utf-8"))
    path = features / (line + ".npz")
    expected = report["lines"][line]
    if path.is_symlink() or sha(path) != expected["sha256"]:
        raise ValueError("prepared feature digest changed")
    with np.load(path, allow_pickle=False) as data:
        X = np.asarray(data["X"], dtype=np.float32)
        Y = np.asarray(data["Y"], dtype=np.float32)
        baseline = np.asarray(data["baseline"], dtype=np.float32)
        groups = np.asarray(data["groups"], dtype=np.int32)
    if (X.ndim != 2 or Y.ndim != 2 or baseline.shape != Y.shape
            or not (len(X) == len(Y) == len(groups) == expected["examples"])
            or not np.isfinite(X).all() or not np.isfinite(Y).all()
            or len(np.unique(groups)) != expected["groups"]
            or len(np.unique(groups)) < 5):
        raise ValueError("invalid prepared examples")
    splits = list(GroupKFold(n_splits=5).split(X, Y, groups))
    fit_idx, hold_idx = splits[fold]
    fit_groups = set(groups[fit_idx].tolist())
    hold_groups = set(groups[hold_idx].tolist())
    if fit_groups & hold_groups or len(fit_idx) < 50 or len(hold_idx) < 10:
        raise ValueError("group-disjoint split invalid")

    start = time.monotonic()
    scaler = StandardScaler().fit(X[fit_idx])
    fit_x = scaler.transform(X[fit_idx])
    hold_x = scaler.transform(X[hold_idx])
    target_scaler = None
    if method == "ridge":
        model = Ridge(alpha=10.0, solver="lsqr")
        fit_y = Y[fit_idx]
    elif method == "trees":
        model = ExtraTreesRegressor(
            n_estimators=32, max_depth=16, min_samples_leaf=8,
            max_features=0.5, n_jobs=threads, random_state=1701 + fold,
        )
        fit_y = Y[fit_idx]
    else:
        target_scaler = StandardScaler().fit(Y[fit_idx])
        fit_y = target_scaler.transform(Y[fit_idx])
        model = MLPRegressor(
            hidden_layer_sizes=(128, 64), activation="relu", alpha=0.001,
            batch_size=256, learning_rate_init=0.001, max_iter=60,
            early_stopping=False, random_state=1701 + fold,
        )
    model.fit(fit_x, fit_y)
    prediction = model.predict(hold_x)
    if target_scaler is not None:
        prediction = target_scaler.inverse_transform(prediction)
    elapsed = time.monotonic() - start
    y = Y[hold_idx]
    moving = np.sqrt(np.mean(y.astype(np.float64) ** 2, axis=1)) > THRESHOLDS[line]
    heldout_group_ids = groups[hold_idx]
    group_metrics = []
    for group in sorted(hold_groups):
        mask = heldout_group_ids == group
        group_metrics.append({
            "group": group, "examples": int(mask.sum()),
            "model": metrics(y[mask], prediction[mask], moving[mask]),
            "persistence": metrics(y[mask], np.zeros_like(y[mask]), moving[mask]),
            "constant_velocity": metrics(y[mask], baseline[hold_idx][mask], moving[mask]),
        })
    result = {
        "schema": "junction.open3d.grouped-forecast.v1",
        "line": line, "fold": fold, "method": method,
        "fit_examples": len(fit_idx), "heldout_examples": len(hold_idx),
        "fit_groups": len(fit_groups), "heldout_groups": len(hold_groups),
        "group_overlap": 0, "moving_examples": int(moving.sum()),
        "moving_threshold_rms": THRESHOLDS[line], "units": UNITS[line],
        "feature_sha256": expected["sha256"], "datasets": report["datasets"],
        "seconds": elapsed,
        "model": metrics(y, prediction, moving),
        "persistence": metrics(y, np.zeros_like(y), moving),
        "constant_velocity": metrics(y, baseline[hold_idx], moving),
        "heldout_group_metrics": group_metrics,
        "iterations": int(model.n_iter_) if method == "mlp" else None,
        "converged_before_limit": bool(model.n_iter_ < model.max_iter) if method == "mlp" else None,
        "promotion_authorized": False,
        "scope": "group-held-out offline research; not a robot controller or safety result",
    }
    if not all(math.isfinite(result["model"][key]) for key in ("rmse", "mae")):
        raise ValueError("non-finite metrics")
    output.mkdir(parents=True, exist_ok=False)
    model_path = output / "trained-model.joblib"
    joblib.dump({"model": model, "x_scaler": scaler, "y_scaler": target_scaler,
                 "line": line, "fold": fold, "method": method}, model_path, compress=3)
    if model_path.stat().st_size > MAX_MODEL_BYTES:
        raise ValueError("trained model exceeds archive bound")
    model_sha = sha(model_path)
    parts = []
    with model_path.open("rb") as source:
        index = 0
        while chunk := source.read(CHUNK_BYTES):
            entry = f"model.part{index:03d}"
            part = output / f"{entry}.zip"
            with zipfile.ZipFile(part, "x", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr(entry, chunk)
            parts.append({"file": part.name, "entry": entry, "bytes": len(chunk),
                          "sha256": hashlib.sha256(chunk).hexdigest(),
                          "archive_sha256": sha(part)})
            index += 1
    model_path.unlink()
    result["trained_model"] = {"sha256": model_sha, "parts": parts,
                               "note": "joblib/pickle: load only as trusted code"}
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--line", required=True, choices=LINES)
    parser.add_argument("--fold", required=True, type=int, choices=range(5))
    parser.add_argument("--method", required=True, choices=METHODS)
    parser.add_argument("--threads", type=int, default=32)
    args = parser.parse_args()
    print(json.dumps(train(args.features, args.out, args.line, args.fold, args.method, args.threads),
                     sort_keys=True))
