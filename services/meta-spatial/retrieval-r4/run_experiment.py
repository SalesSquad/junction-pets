#!/usr/bin/env python3
"""Bounded, source-bound R4 export, actual R fit, and cross-language verification."""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from runtime import FEATURE_NAMES, ResearchReranker

ROOT = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def source_binding(commit):
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != commit:
        raise ValueError("execution_head_mismatch")
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"],
                                    cwd=ROOT, text=True)
    if dirty:
        raise ValueError("execution_requires_clean_worktree")
    return {p.name: digest(p) for p in ROOT.iterdir() if p.is_file()}


def verify_scores(candidates, training):
    """Compare every candidate score and every query with independent Python runtime."""
    model_path = training / "model.json"
    model = ResearchReranker.from_file(model_path, expected_sha256=digest(model_path))
    with (training / "query_metrics.csv").open(newline="") as handle:
        query_metrics = {(r["split"], r["query_id"]): r for r in csv.DictReader(handle)}
    rows = queries = 0
    max_score_error = max_confidence_error = 0.0
    with candidates.open(newline="") as source, (training / "predictions.csv").open(newline="") as fitted:
        predictions = iter(csv.DictReader(fitted))
        groups = itertools.groupby(csv.DictReader(source), key=lambda r: (r["split"], r["query_id"]))
        for key, group in groups:
            batch = list(group)
            result = model.rank([{"candidate_id": r["candidate_id"],
                                  **{f: float(r[f]) for f in FEATURE_NAMES}} for r in batch], limit=100)
            scores = {r["candidate_id"]: r["rank_score"] for r in result["candidates"]}
            for row in batch:
                predicted = next(predictions)
                for field in ("split", "query_id", "candidate_id"):
                    if predicted[field] != row[field]:
                        raise ValueError("prediction_row_identity_mismatch")
                actual, expected = scores[row["candidate_id"]], float(predicted["rank_score"])
                max_score_error = max(max_score_error, abs(actual - expected))
                if not math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10):
                    raise ValueError("r_python_score_mismatch")
                rows += 1
            reference = query_metrics.pop(key)
            if result["candidates"][0]["candidate_id"] != reference["candidate_id"]:
                raise ValueError("r_python_top_candidate_mismatch")
            if len(batch) >= 2:
                error = abs(result["confidence"] - float(reference["confidence"]))
                max_confidence_error = max(max_confidence_error, error)
                if error > 1e-10:
                    raise ValueError("r_python_confidence_mismatch")
            # Runtime deliberately abstains on a singleton; the R table is descriptive.
            if result["accepted"] or result["action_authorized"] or result["physical_identity_verified"]:
                raise ValueError("research_runtime_authorized_action")
            queries += 1
        if next(predictions, None) is not None or query_metrics:
            raise ValueError("unexpected_extra_prediction_or_query")
    return {"status": "PASS", "candidate_rows": rows, "queries": queries,
            "max_absolute_score_difference": max_score_error,
            "max_absolute_confidence_difference": max_confidence_error,
            "all_runtime_results_abstain": True,
            "singleton_runtime": "no confidence; no diagnostic acceptance",
            "qualification": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("prior-data", "prior-features", "fresh-data", "fresh-features", "training", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--rscript", required=True)
    args = parser.parse_args()
    sources = source_binding(args.source_commit)
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    receipt = {"schema_version": 1, "work_id": "META-LENS-R4-COVERAGE93-20261114",
               "source_commit": args.source_commit, "source_sha256": sources,
               "started_at_unix": started, "python": sys.version,
               "new_cloud_instances": 0, "new_pixel_inference": False,
               "qualification": False, "stages": []}
    env = dict(os.environ, OPENBLAS_NUM_THREADS="2", OMP_NUM_THREADS="2", VECLIB_MAXIMUM_THREADS="2")
    candidates = args.output / "candidates"
    training = args.output / "training"
    export = [sys.executable, str(ROOT / "prepare_candidates.py"), "--source-commit", args.source_commit,
              "--output", str(candidates)]
    for name in ("prior-data", "prior-features", "fresh-data", "fresh-features", "training"):
        export.extend(["--" + name, str(getattr(args, name.replace("-", "_")))])
    fit = [args.rscript, str(ROOT / "train_reranker.R"), "--input", str(candidates / "candidates.csv"),
           "--manifest", str(candidates / "data_manifest.json"), "--output", str(training),
           "--source-commit", args.source_commit]
    try:
        for name, command in (("export", export), ("fit", fit)):
            at = time.monotonic()
            print(json.dumps({"stage": name, "status": "STARTED"}), flush=True)
            log = args.output / (name + ".log")
            with log.open("xb") as handle:
                process = subprocess.run(command, cwd=ROOT, env=env, stdout=handle,
                                         stderr=subprocess.STDOUT, timeout=900)
            receipt["stages"].append({"name": name, "exit_code": process.returncode,
                                      "elapsed_seconds": time.monotonic() - at, "log_sha256": digest(log)})
            if process.returncode:
                raise RuntimeError(name + "_failed_see_preserved_log")
            print(json.dumps(receipt["stages"][-1]), flush=True)
        parity = verify_scores(candidates / "candidates.csv", training)
        write_json(args.output / "runtime_parity.json", parity)
        if source_binding(args.source_commit) != sources:
            raise ValueError("source_changed_during_experiment")
        receipt["status"] = "TRAINED_AND_VERIFIED_RESEARCH_ONLY"
        receipt["runtime_parity"] = parity
        receipt["artifacts"] = [{"path": str(p.relative_to(args.output)), "bytes": p.stat().st_size,
                                  "sha256": digest(p)} for p in sorted(args.output.rglob("*")) if p.is_file()]
    except BaseException as error:
        receipt["status"] = "FAILED"
        receipt["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        receipt["elapsed_seconds"] = time.time() - started
        write_json(args.output / "execution.json", receipt)
        print(json.dumps({"status": receipt["status"], "elapsed_seconds": receipt["elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
