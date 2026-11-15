#!/usr/bin/env python3
"""Read-only, byte-bound V8 TRAIN-world opportunity analysis for V5-first rescue.

This does not execute hybrid physics or claim counterfactual success. The
trusted source is the original hosted CRACI success receipt and two recovered
raw MuJoCo files, not a self-rehashed manifest or an agent narrative.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from collections import Counter
from pathlib import Path


RECEIPT_SHA = "59e200ce7570157f643174b9f0d8dce8a9c47fdf99aa5080afaab8b7da337e6f"
TRAINING_SHA = "af84ec8c6552383e29b8a8dd18ef237c8e3dfd3080729b16f445239618327965"
RAW_SHA = "cbaeacd5a7a2a46a30e6b63afeb12614552da032b68e78a6a90fa7d75c49101a"
MANIFEST_SHA = "08915667f14bdbeed191b457cb3576fde55180aaedc1499614f9f81db41238c5"
QUALIFICATION_SHA = "1215cbbaf9807830121c396f8348065b7c6451ee5436e697b2258d0622e24f59"
POSITIVE_REPLAY_SHA = "af11a65aa2599973830df743b02ab6838622e7c1ee0ff26061f3ca305fbd95bf"
PRODUCT_SHA = "87c91de52cef5c3e745115f737abc4ab8d654a32"
HARNESS_SHA = "251f003b56b9eea1aff79568ad351f615acaee20"
RUN_ID = "craci.43645486985.1.0627c4e23e4a1296"
DATASET_SHA = "217bf81618cb6641dd106540b5dbc9f2ae7bd89d232684b7675d59479bc7ad4c"
STRATEGIES = {"frozen_v5", "frozen_v6", "repeat_left", "v8_hierarchical"}
EARLY_PUBLIC_NEAR_Y = .122
EARLY_PUBLIC_GOAL_DISTANCE = .035


def require(yes, code):
    if not yes:
        raise ValueError(code)


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True,
                        separators=(",", ":"), ensure_ascii=False,
                        allow_nan=False).encode("utf8")).hexdigest()


def exact(path: Path, sha: str):
    import hashlib
    require(path.is_file() and not path.is_symlink(), "HYBRID_ORIGINAL_EVIDENCE_MISSING")
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    require(h.hexdigest() == sha, "HYBRID_ORIGINAL_EVIDENCE_SHA_MISMATCH")
    return path


def load(path: Path, sha: str):
    return json.loads(exact(path, sha).read_text(encoding="utf8"))


def diagnose(raw_dir: Path, artifact_dir: Path, receipt_path: Path):
    receipt = load(receipt_path, RECEIPT_SHA)
    binding = receipt.get("command", {}).get("binding", {})
    require(receipt.get("runId") == RUN_ID and
            receipt.get("status") == "succeeded" and
            receipt.get("stageOutcome") == "success" and
            receipt.get("command", {}).get("exitCode") == 0 and
            binding.get("sourceSha") == PRODUCT_SHA and
            binding.get("harnessSha") == HARNESS_SHA and
            binding.get("workload") == "rokoko-mujoco-v8-prospective",
            "HYBRID_HOSTED_CRACI_COMPLETION_NOT_PROVEN")
    training = load(raw_dir / "training.json", TRAINING_SHA)
    exact(raw_dir / "full_transitions.jsonl.gz", RAW_SHA)
    manifest = load(artifact_dir / "manifest.json", MANIFEST_SHA)
    qualification = load(artifact_dir / "independent-qualification.json", QUALIFICATION_SHA)
    replay = load(artifact_dir / "independent-positive-replay.json", POSITIVE_REPLAY_SHA)
    require(manifest.get("executed_head") == PRODUCT_SHA and
            manifest.get("file_sha256") == {
                "training.json": TRAINING_SHA,
                "full_transitions.jsonl.gz": RAW_SHA} and
            manifest.get("actual_trials") == 640 and
            training.get("dataset_sha256") == DATASET_SHA and
            digest(training.get("trials")) == DATASET_SHA and
            training.get("train_first_seed") == 513000 and
            training.get("strategies") == ["frozen_v5", "frozen_v6", "repeat_left", "v8_hierarchical"],
            "HYBRID_FROZEN_RAW_TRAIN_BINDING_INVALID")
    require(qualification.get("experiment_complete") is True and
            qualification.get("decision") == "valid_prospective_train_only_evidence" and
            qualification.get("independent_full_trace_public_mask_replay") is True and
            qualification.get("promotion_authorized") is False and
            qualification.get("independentHoldout") is False and
            qualification.get("trials") == 640 and
            qualification.get("actual_real_option_transitions") == 29923 and
            replay.get("claim_verified") is True and
            replay.get("fully_replayed_positive_train_trials") == 202 and
            replay.get("selection_scan_replayed") == 365,
            "HYBRID_HOSTED_INDEPENDENT_TRAIN_QUALIFICATION_MISSING")
    rows = {}
    for trial in training["trials"]:
        key = (trial["seed"], trial["strategy"])
        require(key not in rows and trial["strategy"] in STRATEGIES,
                "HYBRID_DUPLICATE_OR_UNKNOWN_REAL_TRIAL")
        rows[key] = trial
    worlds = {seed for seed, _ in rows}
    require(len(worlds) == 160 and len(rows) == 640 and
            all({name for seed, name in rows if seed == world} == STRATEGIES
                for world in worlds), "HYBRID_UNPAIRED_OR_PARTIAL_REAL_WORLDS")
    for seed in worlds:
        group = [rows[seed, name] for name in STRATEGIES]
        require(len({row["world_hash"] for row in group}) == 1 and
                len({row["observed_corridor"] for row in group}) == 1,
                "HYBRID_PAIRED_WORLD_PROVENANCE_MISMATCH")
    trace_rows = set()
    eligible_v5_early_gate = {}
    options = 0
    with gzip.open(raw_dir / "full_transitions.jsonl.gz", "rt", encoding="utf8") as stream:
        for line in stream:
            doc = json.loads(line)
            key = (doc["seed"], doc["strategy"])
            require(key in rows and key not in trace_rows,
                    "HYBRID_FULL_TRACE_IDENTITY_INVALID")
            trace_rows.add(key)
            transitions = doc["transitions"]
            require(len(transitions) == rows[key]["full_transition_count"] and
                    digest(transitions) == rows[key]["full_transition_sha256"],
                    "HYBRID_FULL_TRACE_SHA_OR_COUNT_MISMATCH")
            if doc["strategy"] == "frozen_v5":
                all_world = 0
                near_world = 0
                for transition in transitions:
                    observation, mask = transition["observation"], transition["mask"]
                    require(len(observation) == 18 and len(mask) == 7,
                            "HYBRID_REAL_PUBLIC_ABI_DRIFT")
                    far = math.hypot(float(observation[16] - observation[0]),
                                     float(observation[17] - observation[1])) > EARLY_PUBLIC_GOAL_DISTANCE
                    gate = (far and not (mask[1] or mask[2]) and bool(mask[3] or mask[4]))
                    all_world += int(gate)
                    near_world += int(gate and abs(float(observation[7])) < EARLY_PUBLIC_NEAR_Y)
                eligible_v5_early_gate[doc["seed"]] = {
                    "early-side-mask-rescue": all_world,
                    "near-early-side-mask-rescue": near_world}
            options += len(transitions)
    require(trace_rows == set(rows) and options == 29923,
            "HYBRID_REAL_OPTION_TRACE_COVERAGE_INCOMPLETE")
    successes = Counter()
    opportunities = Counter()
    early_gate = Counter()
    for seed in sorted(worlds):
        row_v5 = rows[seed, "frozen_v5"]
        row_v8 = rows[seed, "v8_hierarchical"]
        bucket = "near" if row_v5["observed_corridor"] else "clear"
        for name in STRATEGIES:
            row = rows[seed, name]
            successes[(name, bucket)] += int(row["success"] and not row["unsafe"])
        if row_v5["abstained"]:
            opportunities[("v5_abstained", bucket)] += 1
            if row_v8["forward_reopened_after_side"] > 0 and not row_v8["unsafe"]:
                opportunities[("v5_abstain_v8_reopens", bucket)] += 1
        for mode in ("early-side-mask-rescue", "near-early-side-mask-rescue"):
            if eligible_v5_early_gate[seed][mode]:
                outcome = "v5_won" if row_v5["success"] and not row_v5["unsafe"] else "v5_did_not_win"
                early_gate[(mode, outcome, bucket)] += 1
                if row_v8["forward_reopened_after_side"] and not row_v8["unsafe"]:
                    early_gate[(mode, "v8_separately_reopened", bucket)] += 1
    require(successes[("frozen_v5", "near")] == 9 and
            successes[("frozen_v5", "clear")] == 20 and
            successes[("v8_hierarchical", "near")] == 0 and
            successes[("v8_hierarchical", "clear")] == 1,
            "HYBRID_BENCHMARK_METRIC_SOURCE_DRIFT")
    return {
        "schema": "junction.rokoko.v10-hybrid.source-bound-train-diagnostic.v1",
        "craci_run_id": RUN_ID,
        "source_sha": PRODUCT_SHA, "harness_sha": HARNESS_SHA,
        "real_paired_train_worlds": 160, "real_train_options": options,
        "trained_candidate_executed_in_physics": False,
        "hybrid_success_is_known": False,
        "new_prospective_train_qualification": False,
        "successes_from_original_paired_controls": {
            name: {bucket: successes[(name, bucket)] for bucket in ("near", "clear")}
            for name in sorted(STRATEGIES)},
        "counterfactual_rescue_opportunity_only": {
            key: {bucket: opportunities[(key, bucket)] for bucket in ("near", "clear")}
            for key in ("v5_abstained", "v5_abstain_v8_reopens")},
        "source_observed_preemptive_mask_gate_only": {
            mode: {
                outcome: {bucket: early_gate[(mode, outcome, bucket)]
                          for bucket in ("near", "clear")}
                for outcome in ("v5_won", "v5_did_not_win", "v8_separately_reopened")}
            for mode in ("early-side-mask-rescue", "near-early-side-mask-rescue")},
        "no_dev_cal_test_ood": True,
        "no_promotion_authorized": True,
        "remaining_uncertainty": "Hybrid switching alters future states; these paired single-policy traces cannot prove hybrid success or safety."
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--restored-raw", type=Path, required=True)
    p.add_argument("--retained-artifacts", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(diagnose(a.restored_raw, a.retained_artifacts, a.receipt),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
