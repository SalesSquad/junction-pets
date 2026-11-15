#!/usr/bin/env python3
"""Turn independently qualified V7 TRAIN traces into a source-bound learning brief.

This script neither learns weights nor dispatches work. It mines the *actual*
raw MuJoCo traces into an observational stage funnel and a registered next-
experiment proposal. All explored sub-25mm bins are labelled post-hoc; the
predeclared V7 >=25mm feasibility gate is never rewritten.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path

SOURCE_SCHEMA = "junction.rokoko.mujoco-v7-stage-learning.v1"
STRATEGIES = ("frozen_v5", "frozen_v6", "repeat_left", "repeat_right",
              "align_left", "align_right", "retreat_left", "observed_branch")
NEAR = 128
CLEAR = 32


def require(ok, code):
    if not ok:
        raise AssertionError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf8")).hexdigest()


def file_digest(path: Path):
    out = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            out.update(chunk)
    return out.hexdigest()


def quantile(samples, q):
    if not samples:
        return None
    order = sorted(samples)
    scaled = q * (len(order) - 1)
    lo = math.floor(scaled)
    hi = math.ceil(scaled)
    return round(order[lo] * (hi - scaled) + order[hi] * (scaled - lo), 8) if lo != hi else round(order[lo], 8)


def readout(training_path: Path, raw_path: Path, artifact_dir: Path, receipt_path: Path):
    training = json.loads(training_path.read_text(encoding="utf8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf8"))
    product = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf8"))
    qualified = json.loads((artifact_dir / "independent-qualification.json").read_text(encoding="utf8"))
    replay = json.loads((artifact_dir / "independent-positive-replay.json").read_text(encoding="utf8"))
    require(training.get("no_dev_evaluation") is True and
            qualified.get("experiment_complete") is True and
            qualified.get("dev_cal_test_ood_opened") is False and
            qualified.get("promotion_authorized") is False and
            replay.get("claim_verified") is True and
            replay.get("no_dev_cal_test_ood") is True,
            "TRAIN_ONLY_INDEPENDENT_QUALIFICATION_REQUIRED")
    require(receipt.get("status") == "succeeded" and
            receipt.get("sourceVerified") is True and
            receipt.get("harnessVerified") is True and
            receipt.get("issues") == [] and
            receipt.get("binding", {}).get("workload") ==
            "rokoko-mujoco-v7-feasibility" and
            receipt.get("binding", {}).get("sourceSha") ==
            training.get("executed_head"),
            "COMPLETE_EXACT_SOURCE_CRACI_RECEIPT_REQUIRED")
    require(training.get("executed_head") == product.get("executed_head") ==
            qualified.get("exact_source_sha"), "SOURCE_HEAD_MISMATCH")
    require(file_digest(training_path) == product["file_sha256"]["training.json"] and
            file_digest(raw_path) == product["file_sha256"]["full_transitions.jsonl.gz"] ==
            qualified["full_transition_archive_sha256"],
            "RESTORED_RAW_BYTES_NOT_SOURCE_MANIFEST")
    require(digest(training["trials"]) == training["dataset_sha256"] ==
            qualified["dataset_sha256"], "DATASET_ROWS_NOT_QUALIFIED")
    rows = training["trials"]
    by_key = {(r["seed"], r["strategy"]): r for r in rows}
    require(len(rows) == len(by_key) == 1280 and
            set(training["strategies"]) == set(STRATEGIES) and
            training["selected_near_count"] == NEAR and
            training["selected_clear_count"] == CLEAR,
            "PAIRED_160_BY_8_CONTRACT")
    scan = training["selection_scan"]
    require(len(scan) == replay["selection_scan_replayed"],
            "PREOUTCOME_SELECTION_REPLAY_MISMATCH")
    # Stream and verify *all* full traces; never infer stage performance from
    # a sparse telemetry subset. This is a digest integrity check, not a
    # second physical validation (that is the frozen CRACI independent replay).
    visited = set()
    transitions = 0
    with gzip.open(raw_path, "rt", encoding="utf8") as archive:
        for line in archive:
            doc = json.loads(line)
            key = (doc["seed"], doc["strategy"])
            require(key in by_key and key not in visited,
                    "FULL_TRACE_DUPLICATE_OR_UNREGISTERED")
            full = doc["transitions"]
            require(len(full) == by_key[key]["full_transition_count"] and
                    digest(full) == by_key[key]["full_transition_sha256"],
                    "FULL_TRACE_CONTENT_NOT_QUALIFIED")
            transitions += len(full)
            visited.add(key)
    require(len(visited) == len(rows) and transitions ==
            training["actual_transition_count"] ==
            qualified["actual_real_option_transitions"],
            "FULL_TRACE_COVERAGE_MISMATCH")

    paired = defaultdict(dict)
    per_strategy = {}
    for r in rows:
        paired[r["seed"]][r["strategy"]] = r
    near_seeds = sorted({r["seed"] for r in rows if r["observed_corridor"]})
    clear_seeds = sorted({r["seed"] for r in rows if not r["observed_corridor"]})
    require(len(near_seeds) == NEAR and len(clear_seeds) == CLEAR and
            all(set(paired[s]) == set(STRATEGIES) for s in paired),
            "PAIRING_NOT_BALANCED")
    for name in STRATEGIES:
        samples = [paired[s][name] for s in near_seeds]
        signed = [float(r["lateral_displacement"]) for r in samples]
        require(all(math.isfinite(x) for x in signed),
                "NONFINITE_LATERAL_PROGRESS")
        safe = [r for r in samples if not r["unsafe"]]
        per_strategy[name] = {
            "hard_worlds": NEAR,
            "safe_completed_goal_worlds": sum(bool(r["success"]) for r in safe),
            "unsafe_worlds": len(samples) - len(safe),
            "abstained_worlds": sum(bool(r["abstained"]) for r in samples),
            "contact_worlds": sum(r["contacts"] > 0 for r in samples),
            "safe_forward_reopen_worlds": sum(bool(r["forward_reopened_after_side"]) for r in safe),
            "safe_forward_reopen_events": sum(int(r["forward_reopened_after_side"]) for r in safe),
            "safe_side_contact_worlds": sum(bool(r["side_contact_option_steps"]) for r in safe),
            "safe_signed_away_mm_p50": round(1000 * quantile([float(r["lateral_displacement"]) for r in safe], .50), 4),
            "safe_signed_away_mm_p90": round(1000 * quantile([float(r["lateral_displacement"]) for r in safe], .90), 4),
            "safe_signed_away_mm_p95": round(1000 * quantile([float(r["lateral_displacement"]) for r in safe], .95), 4),
            "safe_signed_away_mm_max": round(1000 * max(float(r["lateral_displacement"]) for r in safe), 4),
            "predeclared_safe_away_ge_25mm_worlds": sum(
                float(r["lateral_displacement"]) >= .025 for r in safe),
            "exploratory_posthoc_safe_away_worlds": {
                f"ge_{mm}mm": sum(float(r["lateral_displacement"]) >= mm / 1000
                                  for r in safe) for mm in (5, 10, 15, 20)},
        }
    require(len({s for s in near_seeds if any(
        paired[s][p]["success"] and not paired[s][p]["unsafe"] for p in STRATEGIES)}) ==
        qualified["worlds_safe_corridor_success"] and
        len({s for s in near_seeds if any(
            paired[s][p]["lateral_displacement"] >= .025 and
            not paired[s][p]["unsafe"] for p in STRATEGIES)}) ==
            qualified["worlds_safe_lateral_displacement_ge_25mm"],
            "INDEPENDENT_POSITIVE_QUALIFICATION_MISMATCH")
    worlds = sorted({(r["seed"], r["world_hash"]) for r in rows})
    sample_sha = digest([{"seed": seed, "world_hash": h} for seed, h in worlds])
    frozen_best = max(per_strategy[p]["safe_completed_goal_worlds"]
                      for p in ("frozen_v5", "frozen_v6"))
    novel_best = max(per_strategy[p]["safe_completed_goal_worlds"]
                     for p in STRATEGIES if not p.startswith("frozen_"))
    next_stage = ("observation_mask_stage_policy_training" if
                  per_strategy["repeat_left"]["predeclared_safe_away_ge_25mm_worlds"] > 0
                  else "train_only_masked_option_sequence_search")
    return {
        "schema": SOURCE_SCHEMA,
        "craci_run_id": receipt["runId"],
        "craci_receipt_sha256": file_digest(receipt_path),
        "craci_harness_sha": receipt["binding"]["harnessSha"],
        "source_sha": training["executed_head"],
        "dataset_sha256": training["dataset_sha256"],
        "full_transition_archive_sha256": file_digest(raw_path),
        "sample_set_sha256": sample_sha,
        "train_worlds": len(worlds), "hard_worlds": NEAR,
        "actual_option_transitions": transitions,
        "independent_true_physics_positive_traces": replay["fully_replayed_positive_train_trials"],
        "frozen_best_safe_hard_wins": frozen_best,
        "new_macro_best_safe_hard_wins": novel_best,
        "model_improvement_demonstrated": False,
        "per_strategy": per_strategy,
        "next_train_seed_start": 513000,
        "proposed_next_stage": next_stage,
        "requires_frozen_new_dev": True,
        "new_dev_seed_start": 129330,
        "auto_training_or_dispatch": False,
        "model_promotion_authorized": False,
        "limitations": [
            "Actual MuJoCo TRAIN cohort only; no independent generalization conclusion",
            "Sub-25mm exploratory bins are post-hoc descriptive, not changed pass criteria",
            "No physical robot validation or provider billing attestation"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--qualified-artifacts", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = readout(args.training, args.raw, args.qualified_artifacts, args.receipt)
    text = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf8") as stream:
            stream.write(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
