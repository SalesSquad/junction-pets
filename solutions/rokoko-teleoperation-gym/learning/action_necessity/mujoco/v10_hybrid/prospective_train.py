#!/usr/bin/env python3
"""Fresh TRAIN-only four-arm V10 hybrid MuJoCo physical qualification producer.

This is a SOURCE-BOUND EXPERIMENT RUNNER, not a claim that any run happened.
The original V8 real MuJoCo 3.3.7 run_real_episode is reused without edits;
no contact oracle, hidden simulator state or world seed enters a policy. All
worlds are selected before outcomes, only from original public first obs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import re
import time

import numpy as np

import hybrid_policy as hybrid


HERE = Path(__file__).resolve().parent
REPO_FILE = Path("solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v10_hybrid/prospective_train.py")
SCHEMA = "junction.rokoko.mujoco-v10-hybrid-prospective.v1"
EVIDENCE_PARTS_SCHEMA = "junction.rokoko.mujoco-v10-hybrid-evidence-parts.v1"
FIRST_TRAIN_SEED = 516_000
MAX_SCANNED = 512
LAST_SCANNED_SEED = FIRST_TRAIN_SEED + MAX_SCANNED - 1
NEAR_N = 128
CLEAR_N = 32
OBSERVED_CORRIDOR_Y = .122
ORIGINAL_OBS_D = 18
ORIGINAL_MASK_N = 7
MAX_OPTIONS = 60
MIN_SUCCESS_DWELL_TICKS = 250
MAX_SUMMARY_BYTES = 19 * 1024 * 1024
STRATEGIES = ("frozen_v5", "v8_hierarchical",
              "near-early-side-mask-rescue", "rescue_off_v5")
EXPECTED_TRIALS = (NEAR_N + CLEAR_N) * len(STRATEGIES)


def require(condition: bool, code: str):
    if not condition:
        raise ValueError(code)


def public_selection(observation):
    obs = np.asarray(observation, dtype=np.float64)
    require(obs.shape == (ORIGINAL_OBS_D,) and np.all(np.isfinite(obs)),
            "HYBRID_PROSPECTIVE_ORIGINAL_18D_PUBLIC_OBSERVATION_REQUIRED")
    return float(obs[7]), abs(float(obs[7])) < OBSERVED_CORRIDOR_Y


def select_fresh_train_worlds(env, signature):
    """Strict 516000+ ascending public-obs-only cohort, no policy outcomes."""
    near, clear, scan = [], [], []
    for seed in range(FIRST_TRAIN_SEED, FIRST_TRAIN_SEED + MAX_SCANNED):
        obs_y, is_near = public_selection(env.reset(seed=seed, ood=False))
        # World hash is provenance metadata ONLY, never selection/learning.
        world_hash = str(signature(env))
        scan.append({"seed": seed, "world_hash": world_hash,
                     "initial_observed_obstacle_y": obs_y})
        candidate = {"seed": seed, "world_hash": world_hash,
                     "initial_observed_obstacle_y": obs_y,
                     "observed_corridor": is_near}
        if is_near and len(near) < NEAR_N:
            near.append(candidate)
        elif not is_near and len(clear) < CLEAR_N:
            clear.append(candidate)
        if len(near) == NEAR_N and len(clear) == CLEAR_N:
            break
    require(len(near) == NEAR_N and len(clear) == CLEAR_N,
            "HYBRID_PROSPECTIVE_FRESH_PAIRED_COHORT_INCOMPLETE")
    return sorted([*near, *clear], key=lambda x: x["seed"]), scan


def paired_schedule(cohort):
    require(len(cohort) == NEAR_N + CLEAR_N and
            len({x["seed"] for x in cohort}) == NEAR_N + CLEAR_N and
            all(FIRST_TRAIN_SEED <= x["seed"] <= LAST_SCANNED_SEED
                for x in cohort), "HYBRID_PROSPECTIVE_COHORT_DRIFT")
    return [(definition, arm) for definition in cohort for arm in STRATEGIES]


def safe_goal(row):
    return bool(row["success"] and not row["unsafe"] and
                row["dwell_ticks_final"] >= MIN_SUCCESS_DWELL_TICKS)


def paired_readout(trials):
    by_world = {}
    for row in trials:
        group = by_world.setdefault(row["seed"], {})
        require(row["strategy"] in STRATEGIES and row["strategy"] not in group,
                "HYBRID_PROSPECTIVE_DUPLICATE_OR_UNKNOWN_PAIRED_ARM")
        group[row["strategy"]] = row
    require(len(by_world) == NEAR_N + CLEAR_N and all(
        set(group) == set(STRATEGIES) and
        len({row["world_hash"] for row in group.values()}) == 1 and
        len({row["observed_corridor"] for row in group.values()}) == 1
        for group in by_world.values()),
        "HYBRID_PROSPECTIVE_MISSING_OR_UNPAIRED_WORLD")
    cohort = {"near": sorted(s for s, r in by_world.items()
                             if r["frozen_v5"]["observed_corridor"]),
              "clear": sorted(s for s, r in by_world.items()
                              if not r["frozen_v5"]["observed_corridor"])}
    require(len(cohort["near"]) == NEAR_N and len(cohort["clear"]) == CLEAR_N,
            "HYBRID_PROSPECTIVE_ORIGINAL_NEAR_CLEAR_COUNT_DRIFT")
    # Crucial paired placebo check: if deterministic unchanged V5 gives a
    # different raw trace, the experiment CANNOT claim a policy effect.
    for seed, group in by_world.items():
        original, placebo = group["frozen_v5"], group["rescue_off_v5"]
        require(original["full_transition_sha256"] == placebo["full_transition_sha256"] and
                original["success"] == placebo["success"] and
                original["unsafe"] == placebo["unsafe"] and
                original["abstained"] == placebo["abstained"] and
                original["physics_steps"] == placebo["physics_steps"],
                f"HYBRID_PROSPECTIVE_PLACEBO_TRACE_MISMATCH_SEED_{seed}")
    stats = {}
    for strategy in STRATEGIES:
        rows = [g[strategy] for g in by_world.values()]
        stats[strategy] = {
            "real_trials": len(rows),
            "safe_near_goals": sum(safe_goal(r) and r["observed_corridor"] for r in rows),
            "safe_clear_goals": sum(safe_goal(r) and not r["observed_corridor"] for r in rows),
            "unsafe": sum(bool(r["unsafe"]) for r in rows),
            "abstained": sum(bool(r["abstained"]) for r in rows),
            "timeouts": sum(not (r["success"] or r["unsafe"] or r["abstained"])
                            for r in rows),
            "forward_reopened_after_side": sum(r["forward_reopened_after_side"] for r in rows),
            "real_option_steps": sum(r["full_transition_count"] for r in rows)}
    novel, lost, new_unsafe, shared = [], [], [], []
    for seed, group in sorted(by_world.items()):
        baseline, candidate = group["frozen_v5"], group["near-early-side-mask-rescue"]
        if safe_goal(candidate) and not safe_goal(baseline):
            novel.append(seed)
        elif safe_goal(baseline) and not safe_goal(candidate):
            lost.append(seed)
        elif safe_goal(baseline) and safe_goal(candidate):
            shared.append(seed)
        if candidate["unsafe"] and not baseline["unsafe"]:
            new_unsafe.append(seed)
    return {"schema": SCHEMA + ".readout",
            "strict_original_v5_placebo_raw_trace_identical": True,
            "strategies": stats, "cohort": cohort,
            "novel_hybrid_safe_goal_seeds_vs_v5": novel,
            "lost_v5_safe_goal_seeds_under_hybrid": lost,
            "shared_v5_hybrid_safe_goal_seeds": shared,
            "hybrid_new_unsafe_seeds_vs_v5": new_unsafe,
            "scientific_status": "UNPROMOTED_TRAIN_EVIDENCE_REQUIRES_INDEPENDENT_REPLAY",
            "dev_cal_test_ood_opened": False,
            "promotion_authorized": False}


def write_compact_json(path, object_, canonical):
    encoded = canonical(object_) + b"\n"
    require(len(encoded) <= MAX_SUMMARY_BYTES,
            "HYBRID_PROSPECTIVE_LOSSLESS_TRAIN_SUMMARY_TOO_LARGE_FOR_CAPTURE")
    with path.open("xb") as stream:
        stream.write(encoded)
    return len(encoded)


def validate_git_and_paths(runner, args):
    require(args.require_git and re.fullmatch(r"[0-9a-f]{40}", args.expected_head) and
            re.fullmatch(r"[0-9a-f]{40}", args.expected_harness_head) and
            60 <= args.time_budget_seconds <= 3600,
            "HYBRID_PROSPECTIVE_SOURCE_HARNESS_OR_BUDGET_PIN_MISSING")
    head, checkout = runner.v8.source_identity(args.expected_head)
    require((checkout / REPO_FILE).resolve() == HERE.joinpath("prospective_train.py").resolve(),
            "HYBRID_PROSPECTIVE_UNEXPECTED_EXECUTED_RUNNER_PATH")
    runner.validate_historical_trainer_source(checkout)
    weights = args.frozen_weights.resolve(strict=True)
    receipt = args.frozen_training_receipt.resolve(strict=True)
    output = args.output_dir.resolve()
    require(not weights.is_relative_to(checkout) and
            not receipt.is_relative_to(checkout) and
            not output.is_relative_to(checkout) and
            output != weights.parent and output != receipt.parent,
            "HYBRID_PROSPECTIVE_PRIVATE_ARTIFACT_PATHS_REQUIRED")
    return head, checkout, output


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("prospective-train",), required=True)
    p.add_argument("--require-git", action="store_true")
    p.add_argument("--expected-head", required=True)
    p.add_argument("--expected-harness-head", required=True)
    p.add_argument("--reviewed-weights-sha256", required=True)
    p.add_argument("--frozen-weights", type=Path, required=True)
    p.add_argument("--frozen-training-receipt", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--time-budget-seconds", type=int, default=1200)
    args = p.parse_args(argv)
    require(args.reviewed_weights_sha256 == hybrid.V8_CANONICAL_MODEL_SHA256,
            "HYBRID_PROSPECTIVE_UNREVIEWED_FROZEN_MODEL")
    # Code identity is re-bound independently, not a cached generic `run`.
    runner, weights, v5_factory, v8_factory = hybrid.verified_original_bundle(
        args.frozen_weights, args.frozen_training_receipt)
    head, _, output = validate_git_and_paths(runner, args)
    v7, Env = runner.import_v7_and_physics()
    env = Env(max_options=MAX_OPTIONS)
    signature = v7.v6.v5.v4.v3.v2.v1._world_signature
    deadline = time.monotonic() + args.time_budget_seconds
    cohort, scan = select_fresh_train_worlds(env, signature)
    schedule = paired_schedule(cohort)
    require(len(schedule) == EXPECTED_TRIALS,
            "HYBRID_PROSPECTIVE_FULL_FOUR_ARM_PLAN_REQUIRED")
    factories = {
        "frozen_v5": v5_factory,
        "v8_hierarchical": v8_factory,
        "near-early-side-mask-rescue": hybrid.policy_factory(
            "near-early-side-mask-rescue", args.frozen_weights,
            args.frozen_training_receipt),
        "rescue_off_v5": v5_factory,
    }
    # Output is created only after all source/model/world cohort checks.
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    trials = []
    with gzip.open(output / "full_transitions.jsonl.gz", "xt", encoding="utf8",
                   newline="\n", compresslevel=6) as raw:
        for definition, strategy in schedule:
            require(time.monotonic() < deadline,
                    "HYBRID_PROSPECTIVE_COMPLETE_PAIRED_TRIAL_DEADLINE")
            trial, transitions = runner.run_real_episode(
                env, definition["seed"], strategy, factories[strategy],
                signature, deadline, v7)
            require(trial["world_hash"] == definition["world_hash"],
                    "HYBRID_PROSPECTIVE_SAME_WORLD_HASH_DRIFT")
            trial.update(observed_corridor=definition["observed_corridor"],
                         initial_observed_obstacle_y=definition["initial_observed_obstacle_y"],
                         allocation_phase="all_four_paired_fresh_hybrid_train",
                         safe_goal_dwell250=safe_goal(trial),
                         timeout=not (trial["success"] or trial["unsafe"] or
                                      trial["abstained"]))
            trials.append(trial)
            raw.write(runner.v8.canonical_bytes({"seed": trial["seed"],
                                                  "strategy": strategy,
                                                  "transitions": transitions}).decode("utf8") + "\n")
    readout = paired_readout(trials)
    dataset_sha = runner.v8.digest(trials)
    training = {
        "schema": SCHEMA + ".training", "executed_head": head,
        "harness_expected_head": args.expected_harness_head,
        "actual_physics_engine": "mujoco-3.3.7",
        "original_public_observation_count": ORIGINAL_OBS_D,
        "original_seven_action_mask": ORIGINAL_MASK_N,
        "training_only": True, "train_first_seed": FIRST_TRAIN_SEED,
        "selection_seed_limit": MAX_SCANNED, "selection_scan": scan,
        "selected_near_count": NEAR_N, "selected_clear_count": CLEAR_N,
        "near_seeds": readout["cohort"]["near"],
        "clear_seeds": readout["cohort"]["clear"],
        "strategies": list(STRATEGIES), "cohort": cohort,
        "allocation": "all four frozen candidate and control policies on identical fresh TRAIN worlds",
        "actual_trials": len(trials),
        "actual_transition_count": sum(r["full_transition_count"] for r in trials),
        "full_option_transitions": sum(r["full_transition_count"] for r in trials),
        "frozen_weights_sha256": hybrid.V8_CANONICAL_MODEL_SHA256,
        "frozen_weights_file_sha256": hybrid.V8_WEIGHTS_FILE_SHA256,
        "historical_frozen_trainer_head": runner.TRAINER_HEAD,
        "frozen_training_receipt_sha256": hybrid.V8_RECEIPT_FILE_SHA256,
        "parent_v7_source_sha": runner.v8.V7_SOURCE_SHA,
        "v7_training_dataset_sha256": runner.v8.V7_DATASET_SHA256,
        "no_dev_evaluation": True, "dev_cal_test_ood_opened": False,
        "model_promotion_authorized": False,
        "source_sha256": {
            "prospective_train.py": hybrid.sha256_file(HERE / "prospective_train.py"),
            "hybrid_policy.py": hybrid.sha256_file(HERE / "hybrid_policy.py"),
            "v8_rollout_train.py": hybrid.V8_RUNNER_SHA256,
            "v8_run.py": hybrid.V8_TRAINER_SHA256},
        "trials": trials, "dataset_sha256": dataset_sha}
    summary_bytes = write_compact_json(output / "training.json", training,
                                       runner.v8.canonical_bytes)
    readout.update(executed_head=head, harness_expected_head=args.expected_harness_head,
                   dataset_sha256=dataset_sha)
    runner.v8.write_new(output / "paired-readout.json", readout)
    require((output / "paired-readout.json").stat().st_size <= MAX_SUMMARY_BYTES,
            "HYBRID_PROSPECTIVE_READOUT_EXCEEDS_CAPTURE_LIMIT")
    core_files = ("training.json", "full_transitions.jsonl.gz", "paired-readout.json")
    file_sha = {name: hybrid.sha256_file(output / name) for name in core_files}
    source_manifest = {"schema": SCHEMA + ".manifest", "executed_head": head,
                       "harness_expected_head": args.expected_harness_head,
                       "produced_at": datetime.now(timezone.utc).isoformat(),
                       "actual_real_mujoco_trials": len(trials),
                       "actual_real_option_transitions": training["actual_transition_count"],
                       "selected_train_worlds": len(cohort),
                       "dataset_sha256": dataset_sha,
                       "file_sha256": file_sha,
                       "source_sha256": training["source_sha256"],
                       "training_only": True, "dev_cal_test_ood_opened": False,
                       "promotion_authorized": False}
    runner.v8.write_new(output / "manifest.json", source_manifest)
    evidence_parts = {"schema": EVIDENCE_PARTS_SCHEMA, "executed_head": head,
                      "harness_expected_head": args.expected_harness_head,
                      "archive_created_by_this_runner": False,
                      "part_files_for_independent_external_packager": [
                          {"name": name, "sha256": file_sha[name],
                           "bytes": (output / name).stat().st_size}
                          for name in core_files],
                      "manifest_sha256": hybrid.sha256_file(output / "manifest.json"),
                      "no_dev_cal_test_ood": True,
                      "promotion_authorized": False}
    runner.v8.write_new(output / "evidence-parts-plan.json", evidence_parts)
    print(json.dumps({"schema": SCHEMA + ".terminal", "executed_head": head,
                      "harness_expected_head": args.expected_harness_head,
                      "real_paired_worlds": len(cohort), "real_trials": len(trials),
                      "real_option_transitions": training["actual_transition_count"],
                      "training_json_bytes": summary_bytes,
                      "frozen_v5_safe_near_goals": readout["strategies"]["frozen_v5"]["safe_near_goals"],
                      "hybrid_safe_near_goals": readout["strategies"]["near-early-side-mask-rescue"]["safe_near_goals"],
                      "novel_hybrid_goals": len(readout["novel_hybrid_safe_goal_seeds_vs_v5"]),
                      "lost_v5_goals": len(readout["lost_v5_safe_goal_seeds_under_hybrid"]),
                      "hybrid_new_unsafe": len(readout["hybrid_new_unsafe_seeds_vs_v5"]),
                      "promotion_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
