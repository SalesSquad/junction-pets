#!/usr/bin/env python3
"""Preregistered, fresh TRAIN-only physics comparison of the unpromoted V10.

This reuses the ORIGINAL MuJoCo 3.3.7 world, seven-action shield, V5/V6
baselines, repeat-left and V8 frozen runner.  It never trains on or chooses
actions from the new cohort's outcomes.  Success is a physical goal/dwell,
not imitation accuracy.  All 800 full option traces are retained losslessly.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
V8_DIR = ROOT / "v8_learning"
V10_DIR = ROOT / "v10_learning"
V10_TRAIN_HEAD = "58c972e58575f022f2e97f09612f7c7fb244d4cb"
V8_TRAINED_HEAD = "4b91c64bc1a79bf630b1da6d12bea28e87c2990a"
V10_WEIGHTS_FILE_SHA256 = "3a926fdd80bc5bfe069ba4ab50792aaed760d81480eb68a80b6e087beec71f3d"
V8_WEIGHTS_FILE_SHA256 = "07823dcc52ea85b64e18767e1b1af29e63e3236613598cb349610a6b4fd37dc1"
SCHEMA = "junction.rokoko.mujoco-v10.prospective-train.v1"
FIRST_SEED = 515_000
MAX_SCAN = 512
NEAR = 128
CLEAR = 32
STRATEGIES = ("frozen_v5", "frozen_v6", "repeat_left", "frozen_v8",
              "v10_loss_informed")
EXPECTED_TRIALS = (NEAR + CLEAR) * len(STRATEGIES)
MAX_SUMMARY_BYTES = 32 * 1024 * 1024  # Original 32-MiB V7 qualifier limit.


def load_module(path: Path, name: str):
    if not path.is_file() or path.is_symlink():
        raise ValueError("V10_PROSPECTIVE_REVIEWED_SOURCE_NOT_FOUND")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("V10_PROSPECTIVE_MODULE_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.dont_write_bytecode = True
# Historical V8 rollout imports the generic name `run`. A Python host may
# already have cached an unrelated `run` from V10 or another agent. Never
# silently bind that module to an original-physics safety verifier.
generic_run = sys.modules.get("run")
if generic_run is not None and (Path(getattr(generic_run, "__file__", "")).resolve() !=
                                (V8_DIR / "run.py").resolve()):
    raise ValueError("V10_PROSPECTIVE_GENERIC_RUN_MODULE_COLLISION")
v8 = load_module(V8_DIR / "rollout_train.py", "rokoko_v8_original_prospective")
require = v8.v8.require
require(Path(v8.v8.__file__).resolve() == (V8_DIR / "run.py").resolve(),
        "V10_PROSPECTIVE_V8_VERIFIER_MODULE_IDENTITY_MISMATCH")
v10 = load_module(V10_DIR / "run.py", "rokoko_v10_original_frozen_policy")


def validate_pre_registration():
    require(FIRST_SEED == v10.NEXT_TRAIN_FIRST_SEED and
            FIRST_SEED + MAX_SCAN - 1 == v10.NEXT_TRAIN_LAST_SELECTION_SEED and
            NEAR == v10.NEXT_NEAR and CLEAR == v10.NEXT_CLEAR and
            STRATEGIES == v10.NEXT_COMPARATORS and
            FIRST_SEED > v8.TRAIN_LAST_SCAN_SEED and
            len(STRATEGIES) == len(set(STRATEGIES)) == 5 and
            EXPECTED_TRIALS == 800,
            "V10_PROSPECTIVE_PRE_REGISTERED_TRAIN_COHORT_CHANGED")


def verify_historical_source(checkout: Path):
    """Only a descendant of the *frozen V10* may evaluate the reviewed model.

    No descendant may modify V10 training, historical physics, existing V8
    runner or baselines as part of this prospective comparison.
    """
    for ancestor in (V10_TRAIN_HEAD, V8_TRAINED_HEAD):
        result = subprocess.run(["git", "-C", str(checkout), "merge-base",
                                 "--is-ancestor", ancestor, "HEAD"],
                                capture_output=True, timeout=15)
        require(result.returncode == 0, "V10_PROSPECTIVE_NOT_FROM_FROZEN_LINEAGE")
    immutable = [
        "solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/" + name
        for name in ("physics.py", "moving_scene.xml", "v7_feasibility/run.py",
                     "v5_learning/run.py", "v5_learning/policy.py",
                     "v6_learning/run.py", "v6_learning/corridor_policy.py",
                     "v8_learning/run.py", "v8_learning/rollout_train.py",
                     "v8_learning/checkpoints/weights.json",
                     "v8_learning/checkpoints/training-receipt.json")]
    for name in immutable:
        outcome = subprocess.run(["git", "-C", str(checkout), "diff", "--quiet",
                                  V10_TRAIN_HEAD, "HEAD", "--", name],
                                 capture_output=True, timeout=15)
        require(outcome.returncode == 0, "V10_PROSPECTIVE_FROZEN_BASELINE_DRIFT")
    unchanged_v10 = subprocess.run(["git", "-C", str(checkout), "diff", "--quiet",
                                    V10_TRAIN_HEAD, "HEAD", "--",
                                    str(V10_DIR.relative_to(checkout))],
                                   capture_output=True, timeout=15)
    require(unchanged_v10.returncode == 0,
            "V10_PROSPECTIVE_TRAINED_MODEL_OR_CODE_CHANGED")
    v8.validate_historical_trainer_source(checkout)


def select_public_train_worlds(env, world_signature):
    """Cohort selection uses only initial public 18-D observation, never reward."""
    near, clear, scan = [], [], []
    for seed in range(FIRST_SEED, FIRST_SEED + MAX_SCAN):
        observed = np.asarray(env.reset(seed=seed, ood=False), dtype=np.float64)
        require(observed.shape == (18,) and np.all(np.isfinite(observed)),
                "V10_PRE_OUTCOME_PUBLIC_OBSERVATION_INVALID")
        obstacle_y = float(observed[7])
        row = {"seed": seed, "world_hash": str(world_signature(env)),
               "initial_observed_obstacle_y": obstacle_y,
               "observed_corridor": abs(obstacle_y) < v8.NEAR_OBSERVED_Y_THRESHOLD}
        scan.append({k: row[k] for k in ("seed", "world_hash",
                                            "initial_observed_obstacle_y")})
        if row["observed_corridor"] and len(near) < NEAR:
            near.append(row)
        elif not row["observed_corridor"] and len(clear) < CLEAR:
            clear.append(row)
        if len(near) == NEAR and len(clear) == CLEAR:
            break
    require(len(near) == NEAR and len(clear) == CLEAR,
            "V10_PROSPECTIVE_FRESH_COHORT_INCOMPLETE")
    return sorted([*near, *clear], key=lambda row: row["seed"]), scan


def paired_schedule(cohort):
    require(len(cohort) == NEAR + CLEAR and
            len({row["seed"] for row in cohort}) == len(cohort) and
            all(FIRST_SEED <= row["seed"] < FIRST_SEED + MAX_SCAN for row in cohort),
            "V10_PROSPECTIVE_COHORT_OUT_OF_BOUNDS")
    schedule = [(row, name) for row in cohort for name in STRATEGIES]
    require(len(schedule) == EXPECTED_TRIALS,
            "V10_PROSPECTIVE_INCOMPLETE_PAIRED_SCHEDULE")
    return schedule


def policy_factory(name: str, candidate_weights: Path, frozen_v8_weights,
                   *, frozen_v7=None):
    """Each episode gets its own PUBLIC (observation, legal-mask) controller."""
    require(name in STRATEGIES, "V10_PROSPECTIVE_UNREGISTERED_STRATEGY")
    if name == "v10_loss_informed":
        return v10.policy_factory(candidate_weights)
    if name == "frozen_v8":
        return v8.policy_factory("v8_hierarchical", frozen_v8_weights,
                                 frozen_v7=frozen_v7)
    return v8.policy_factory(name, frozen_v8_weights, frozen_v7=frozen_v7)


def paired_readout(trials):
    by_world = {}
    for row in trials:
        seed, name = row["seed"], row["strategy"]
        require(name in STRATEGIES, "V10_PROSPECTIVE_UNKNOWN_STRATEGY")
        pair = by_world.setdefault(seed, {})
        require(name not in pair, "V10_PROSPECTIVE_DUPLICATE_PAIRED_ARM")
        pair[name] = row
    require(len(by_world) == NEAR + CLEAR and
            all(set(p) == set(STRATEGIES) and
                len({r["world_hash"] for r in p.values()}) == 1 and
                len({r["observed_corridor"] for r in p.values()}) == 1
                for p in by_world.values()),
            "V10_PROSPECTIVE_NOT_ALL_FIVE_ON_IDENTICAL_WORLDS")
    near_seeds = sorted(s for s, p in by_world.items()
                        if p["v10_loss_informed"]["observed_corridor"])
    clear_seeds = sorted(s for s in by_world if s not in near_seeds)
    require(len(near_seeds) == NEAR and len(clear_seeds) == CLEAR,
            "V10_PROSPECTIVE_NEAR_CLEAR_GROUP_CHANGED")
    stats = {}
    for name in STRATEGIES:
        rows = [by_world[seed][name] for seed in sorted(by_world)]
        safe = [row for row in rows if not row["unsafe"] and not row["abstained"]]
        near = [row for row in safe if row["observed_corridor"]]
        clear = [row for row in safe if not row["observed_corridor"]]
        stats[name] = {
            "paired_trials": len(rows),
            "unsafe": sum(row["unsafe"] for row in rows),
            "abstained": sum(row["abstained"] for row in rows),
            "safe_goals_all": sum(row["success"] for row in safe),
            "safe_goals_near": sum(row["success"] for row in near),
            "safe_goals_clear": sum(row["success"] for row in clear),
            "safe_near_lateral25_after_contact": sum(
                row["stage_funnel"]["signed_lateral25_after_contact"] for row in near),
            "safe_near_forward_reopen_after_lateral": sum(
                row["stage_funnel"]["forward_reopen_after_lateral25"] for row in near),
            "safe_near_dwell_after_reopen": sum(
                row["stage_funnel"]["full_contact_lateral_reopen_goal_dwell"]
                for row in near),
        }
    losses, new_goals, new_unsafe = [], [], []
    for seed in near_seeds:
        p = by_world[seed]
        v10row = p["v10_loss_informed"]
        candidate_goal = v10row["success"] and not v10row["unsafe"]
        old_goal = any(p[name]["success"] and not p[name]["unsafe"]
                       for name in ("frozen_v5", "frozen_v6"))
        if old_goal and not candidate_goal:
            losses.append(seed)
        if candidate_goal and not old_goal:
            new_goals.append(seed)
        if v10row["unsafe"] and not any(p[name]["unsafe"]
                                       for name in STRATEGIES if name != "v10_loss_informed"):
            new_unsafe.append(seed)
    return {"schema": SCHEMA + ".readout", "strategies": stats,
            "near_seeds": near_seeds, "clear_seeds": clear_seeds,
            "lost_baseline_safe_near_goal_seeds": losses,
            "novel_v10_safe_near_goal_seeds": new_goals,
            "v10_new_unsafe_vs_frozen_controls": new_unsafe,
            "science_gate": "TRAIN_ONLY_INDEPENDENT_REVIEW_REQUIRED_NO_PROMOTION",
            "dev_cal_test_ood_opened": False,
            "model_promotion_authorized": False}


def write_original_summary(path, payload):
    encoded = v8.v8.canonical_bytes(payload) + b"\n"
    # Unlike the previous V8 failure, the private original may exceed the
    # collector's 20 MiB *file* limit; it MUST be losslessly chunk-packaged
    # after qualification, never truncated or sampled to make collection green.
    require(0 < len(encoded) <= MAX_SUMMARY_BYTES,
            "V10_ORIGINAL_TRAIN_JSON_EXCEEDS_UNCHANGED_32M_QUALIFIER_CAP")
    with path.open("xb") as stream:
        stream.write(encoded)
    return len(encoded)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("prospective-train",), required=True)
    parser.add_argument("--require-git", action="store_true")
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--v10-weights", type=Path, required=True)
    parser.add_argument("--v8-weights", type=Path, required=True)
    parser.add_argument("--v8-training-receipt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--time-budget-seconds", type=int, default=1800)
    args = parser.parse_args(argv)
    require(args.require_git and 60 <= args.time_budget_seconds <= 3600,
            "V10_PROSPECTIVE_GIT_AND_FINITE_TIME_REQUIRED")
    validate_pre_registration()
    head, checkout = v8.v8.source_identity(args.expected_head)
    verify_historical_source(checkout)
    paths = [p.resolve(strict=True) for p in (args.v10_weights, args.v8_weights,
                                               args.v8_training_receipt)]
    output = args.output_dir.resolve()
    require(all(not p.is_relative_to(checkout) for p in paths) and
            not output.is_relative_to(checkout) and
            output not in {p.parent for p in paths} and
            len(set(paths)) == 3,
            "V10_PROSPECTIVE_PRIVATE_UNMUTATED_CHECKPOINT_REQUIRED")
    require(v8.v8.file_sha256(paths[0]) == V10_WEIGHTS_FILE_SHA256 and
            v8.v8.file_sha256(paths[1]) == V8_WEIGHTS_FILE_SHA256,
            "V10_PROSPECTIVE_FROZEN_REVIEWED_WEIGHTS_HASH_MISMATCH")
    prior_v8, _, prior_sha = v8.verify_frozen_model(
        paths[1], paths[2], v8.FROZEN_WEIGHTS_SHA256)
    require(callable(v10.policy_factory(paths[0])),
            "V10_PROSPECTIVE_NEW_POLICY_FACTORY_NOT_REVIEWED")
    original_v7, Env = v8.import_v7_and_physics()
    env = Env(max_options=v8.MAX_OPTIONS)
    signature = original_v7.v6.v5.v4.v3.v2.v1._world_signature
    cohort, selection_scan = select_public_train_worlds(env, signature)
    schedule = paired_schedule(cohort)
    factories = {name: policy_factory(name, paths[0], prior_v8,
                                      frozen_v7=original_v7) for name in STRATEGIES}
    deadline = time.monotonic() + args.time_budget_seconds
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    trials = []
    raw_file = output / "full_transitions.jsonl.gz"
    with gzip.open(raw_file, "xt", encoding="utf8", newline="\n", compresslevel=6) as raw:
        for world, name in schedule:
            require(time.monotonic() < deadline,
                    "V10_PROSPECTIVE_REAL_PHYSICS_DEADLINE")
            result, transitions = v8.run_real_episode(
                env, world["seed"], name, factories[name], signature,
                deadline, original_v7)
            require(result["world_hash"] == world["world_hash"],
                    "V10_PROSPECTIVE_SAME_WORLD_DRIFT")
            result.update(
                observed_corridor=world["observed_corridor"],
                initial_observed_obstacle_y=world["initial_observed_obstacle_y"],
                allocation_phase="all_five_frozen_paired_fresh_train")
            trials.append(result)
            raw.write(v8.v8.canonical_bytes({"seed": result["seed"],
                                             "strategy": name,
                                             "transitions": transitions}).decode("utf8") + "\n")
    readout = paired_readout(trials)
    dataset_sha = v8.v8.digest(trials)
    training = {"schema": SCHEMA + ".training", "executed_head": head,
                "produced_at": datetime.now(timezone.utc).isoformat(),
                "actual_physics_engine": "mujoco-3.3.7", "training_only": True,
                "train_first_seed": FIRST_SEED,
                "selection_seed_limit": MAX_SCAN,
                "selection_scan": selection_scan,
                "selected_near_count": NEAR, "selected_clear_count": CLEAR,
                "strategies": list(STRATEGIES), "cohort": cohort,
                "near_seeds": readout["near_seeds"],
                "clear_seeds": readout["clear_seeds"],
                "allocation": "all five unmodified policies on identical 160 fresh TRAIN worlds",
                "actual_trials": len(trials),
                "actual_transition_count": sum(r["full_transition_count"] for r in trials),
                "candidate_v10_weights_file_sha256": V10_WEIGHTS_FILE_SHA256,
                "historical_v10_trainer_head": V10_TRAIN_HEAD,
                "frozen_v8_weights_sha256": prior_sha,
                "historical_v8_trainer_head": V8_TRAINED_HEAD,
                "frozen_v8_receipt_sha256": v8.v8.file_sha256(paths[2]),
                "original_v7_source_sha": v8.v8.V7_SOURCE_SHA,
                "no_dev_evaluation": True, "dev_cal_test_ood_opened": False,
                "model_promotion_authorized": False,
                "no_provider_billing_assertion": True,
                "source_sha256": {"run.py": v8.v8.file_sha256(HERE / "run.py"),
                                  "v10_learning/run.py": v8.v8.file_sha256(V10_DIR / "run.py"),
                                  "v8_learning/rollout_train.py":
                                  v8.v8.file_sha256(V8_DIR / "rollout_train.py")},
                "trials": trials, "dataset_sha256": dataset_sha}
    original_bytes = write_original_summary(output / "training.json", training)
    readout.update(executed_head=head, dataset_sha256=dataset_sha,
                   candidate_v10_weights_file_sha256=V10_WEIGHTS_FILE_SHA256)
    v8.v8.write_new(output / "paired-readout.json", readout)
    require((output / "paired-readout.json").stat().st_size < v8.MAX_CAPTURED_JSON_BYTES,
            "V10_PROSPECTIVE_PAIRED_READOUT_TOO_LARGE")
    manifest = {"schema": SCHEMA + ".manifest", "executed_head": head,
                "produced_at": datetime.now(timezone.utc).isoformat(),
                "immutable_v10_training_head": V10_TRAIN_HEAD,
                "candidate_v10_weights_file_sha256": V10_WEIGHTS_FILE_SHA256,
                "frozen_v8_weights_sha256": prior_sha,
                "file_sha256": {name: v8.v8.file_sha256(output / name)
                                for name in ("training.json", "full_transitions.jsonl.gz")},
                "source_sha256": training["source_sha256"],
                "auxiliary_file_sha256": {
                    "paired-readout.json": v8.v8.file_sha256(output / "paired-readout.json")},
                "actual_trials": len(trials), "train_only": True,
                "dev_cal_test_ood_opened": False, "promotion_authorized": False}
    v8.v8.write_new(output / "manifest.json", manifest)
    print(json.dumps({"executed_head": head, "train_only_real_trials": len(trials),
                      "option_transitions": training["actual_transition_count"],
                      "original_training_json_bytes": original_bytes,
                      "v10_safe_near_goals": readout["strategies"]["v10_loss_informed"]["safe_goals_near"],
                      "frozen_v5_safe_near_goals": readout["strategies"]["frozen_v5"]["safe_goals_near"],
                      "model_promotion_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
