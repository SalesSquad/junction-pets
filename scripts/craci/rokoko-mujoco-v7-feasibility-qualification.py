#!/usr/bin/env python3
"""CRACI train-only v7 physics feasibility audit; NEVER opens dev/cal/test/OOD.

Execution completeness and discovery of a useful contact route are separate
outcomes. Zero discovered successes is a valid negative experiment, not a
reason to falsify the science or repeat the same frozen experiment.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess


PRODUCT = Path("solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v7_feasibility")
TRAIN_FIRST = 512000
SEED_LIMIT = 512
OBS_CORRIDOR_LIMIT = .122
MIN_NEAR = 128
MIN_CLEAR = 32
MIN_STRATEGIES = 8
ANCESTOR_V6 = "0fcf7fe87e6169aa383807ec8616cc6f98694aca"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf8")).hexdigest()


def read_json(path, max_bytes=32 * 1024 * 1024):
    require(path.is_file() and not path.is_symlink(), f"MISSING_EVIDENCE_{path.name}")
    require(0 < path.stat().st_size <= max_bytes, f"OVERSIZED_OR_EMPTY_{path.name}")
    with path.open(encoding="utf8") as handle:
        return json.load(handle)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def vector(value, length):
    return isinstance(value, list) and len(value) == length and all(map(finite, value))


def sparse_indices(n):
    return sorted(set(range(min(12, n))) | set(range(max(0, n - 8), n)) |
                  set(range(0, n, 5)))


def validate_transition(t):
    require(isinstance(t, dict) and vector(t.get("observation"), 18) and
            vector(t.get("next_observation"), 18),
            "MISSING_REAL_18D_OBSERVATION")
    mask = t.get("mask")
    action = t.get("action")
    require(isinstance(mask, list) and len(mask) == 7 and
            all(type(v) in (int, bool) and v in (0, 1) for v in mask) and
            type(action) is int and 0 <= action < 7 and bool(mask[action]),
            "OPTION_BYPASSED_FROZEN_SEVEN_ACTION_SHIELD")
    require(finite(t.get("reward")) and
            type(t.get("cost")) is int and t["cost"] in (0, 1) and
            type(t.get("done")) is bool, "INVALID_REWARD_COST_OR_TERMINAL_FLAG")
    require(type(t.get("contacts_cumulative")) is int and
            t["contacts_cumulative"] >= 0,
            "UNVERIFIED_ACTUAL_MUJOCO_CONTACT_COUNTER")
    require(type(t.get("success_info")) is bool and
            type(t.get("dwell_ticks_cumulative")) is int and
            t["dwell_ticks_cumulative"] >= 0,
            "MISSING_TRUE_MUJOCO_GOAL_DWELL_OUTCOME")


def verify_training(training, manifest, source, evidence_dir):
    require(SHA40.fullmatch(source) is not None, "INVALID_EXACT_SOURCE")
    require(training.get("executed_head") == source, "TRAINING_EXACT_SOURCE_MISMATCH")
    require(training.get("actual_physics_engine") == "mujoco-3.3.7",
            "NO_PINNED_REAL_PHYSICS")
    require(training.get("train_first_seed") == TRAIN_FIRST,
            "TRAINING_WRONG_SEED_RESERVATION")
    limit = training.get("selection_seed_limit")
    require(type(limit) is int and 160 <= limit <= SEED_LIMIT,
            "INVALID_TRAIN_ONLY_SELECTION_LIMIT")
    require(training.get("no_dev_evaluation") is True,
            "DEVELOPMENT_OR_HELDOUT_COULD_BE_OPENED")
    strategies = training.get("strategies")
    require(isinstance(strategies, list) and len(strategies) >= MIN_STRATEGIES and
            all(isinstance(name, str) and 1 <= len(name) <= 80 for name in strategies) and
            len(set(strategies)) == len(strategies), "INVALID_FROZEN_STRATEGY_CATALOG")
    trials = training.get("trials")
    require(isinstance(trials, list) and len(trials) == 160 * len(strategies)
            and len(trials) <= 1600,
            "INCOMPLETE_OR_UNBOUNDED_FEASIBILITY_TRIALS")
    scan = training.get("selection_scan")
    require(isinstance(scan, list) and 160 <= len(scan) <= limit,
            "MISSING_COMPLETE_PREOUTCOME_PUBLIC_SCENARIO_SCAN")
    expected_near, expected_clear = [], []
    scan_hash, scan_observed = {}, {}
    for offset, frame in enumerate(scan):
        require(isinstance(frame, dict) and frame.get("seed") == TRAIN_FIRST + offset
                and finite(frame.get("initial_observed_obstacle_y")) and
                SHA64.fullmatch(frame.get("world_hash", "")) is not None,
                "NONCONSECUTIVE_OR_PRIVILEGED_WORLD_SELECTION_SCAN")
        seed = frame["seed"]
        scan_hash[seed] = frame["world_hash"]
        scan_observed[seed] = frame["initial_observed_obstacle_y"]
        if abs(frame["initial_observed_obstacle_y"]) < OBS_CORRIDOR_LIMIT:
            if len(expected_near) < MIN_NEAR:
                expected_near.append(seed)
        elif len(expected_clear) < MIN_CLEAR:
            expected_clear.append(seed)
        if len(expected_near) == MIN_NEAR and len(expected_clear) == MIN_CLEAR:
            require(offset == len(scan) - 1,
                    "POSTSELECTION_SCAN_MAY_HIDE_CHERRY_PICKING")
    require(len(expected_near) == MIN_NEAR and len(expected_clear) == MIN_CLEAR,
            "INSUFFICIENT_FIRST_DISTINCT_PUBLIC_SCENARIOS")
    require(SHA64.fullmatch(training.get("dataset_sha256", "")) is not None and
            training["dataset_sha256"] == canonical_sha(trials),
            "FORGED_OR_MISSING_TRAIN_ONLY_DATASET_DIGEST")
    require(manifest.get("executed_head") == source,
            "MANIFEST_SOURCE_MISMATCH")
    fh = manifest.get("file_sha256")
    require(isinstance(fh, dict) and
            set(fh) == {"training.json", "full_transitions.jsonl.gz"},
            "INCOMPLETE_EXACT_RAW_EVIDENCE_MANIFEST")
    for name, checksum in fh.items():
        path = evidence_dir / name
        require(SHA64.fullmatch(checksum) is not None and path.is_file() and
                not path.is_symlink() and
                0 < path.stat().st_size <= 32 * 1024 * 1024 and
                hashlib.sha256(path.read_bytes()).hexdigest() == checksum,
                f"RAW_ARTIFACT_BYTES_MISMATCH_{name}")
    require(not any((evidence_dir / x).exists()
                    for x in ("dev.json", "cal.json", "test.json", "ood.json")),
            "HELDOUT_OR_DEVELOPMENT_ARTIFACT_PROHIBITED")

    row_map = {}
    seed_hash = {}
    near_seeds = set()
    clear_seeds = set()
    strategy_usage = {name: 0 for name in strategies}
    trial_transition_sum = 0
    for row in trials:
        require(isinstance(row, dict) and type(row.get("seed")) is int and
                TRAIN_FIRST <= row["seed"] < TRAIN_FIRST + limit,
                "TRIAL_USES_EXPOSED_OR_UNRESERVED_SEED")
        seed = row["seed"]
        strategy = row.get("strategy")
        require(strategy in strategy_usage and (seed, strategy) not in row_map,
                "UNREGISTERED_OR_DUPLICATE_STRATEGY_TRIAL")
        wh = row.get("world_hash")
        require(isinstance(wh, str) and SHA64.fullmatch(wh) is not None,
                "UNHASHED_REAL_WORLD")
        if seed in seed_hash:
            require(seed_hash[seed] == wh, "STRATEGY_ARMS_NOT_SAME_INITIAL_WORLD")
        else:
            seed_hash[seed] = wh
        require(scan_hash.get(seed) == wh,
                "TRIAL_NOT_FROM_PRESELECTED_PUBLIC_INITIAL_WORLD")
        observed_y = row.get("initial_observed_obstacle_y")
        require(finite(observed_y), "CORRIDOR_LABEL_NOT_PUBLIC_OBSERVATION")
        require(abs(observed_y - scan_observed[seed]) < 1e-5,
                "SCENARIO_LABEL_DIFFERS_ACROSS_PAIRED_ARMS")
        near = abs(observed_y) < OBS_CORRIDOR_LIMIT
        require(type(row.get("observed_corridor")) is bool and
                near == row["observed_corridor"],
                "FORGED_OBSERVED_CORRIDOR_LABEL")
        (near_seeds if near else clear_seeds).add(seed)
        strategy_usage[strategy] += 1
        for flag in ("success", "unsafe", "abstained"):
            require(type(row.get(flag)) is bool, "UNQUALIFIED_PHYSICS_OUTCOME")
        require(not (row["success"] and (row["unsafe"] or row["abstained"])),
                "UNSAFE_OR_ABORTED_SUCCESS_FORGERY")
        require(type(row.get("physics_steps")) is int and row["physics_steps"] >= 0 and
                type(row.get("option_steps")) is int and 1 <= row["option_steps"] <= 60,
                "INVALID_REAL_OPTION_PHYSICS_COUNTS")
        if row["physics_steps"] == 0:
            require(row["abstained"] and not row["success"] and not row["unsafe"]
                    and row["option_steps"] == 1, "INVENTED_ZERO_STEP_PHYSICS")
        else:
            require(row["physics_steps"] <= row["option_steps"] * 100,
                    "IMPOSSIBLE_MUJOCO_STEP_COUNT")
        require(row["success"] or row["unsafe"] or row["abstained"] or
                row["option_steps"] == 60,
                "NONTERMINAL_OPTION_SEQUENCE_CANNOT_END_EPISODE")
        require(type(row.get("contacts")) is int and row["contacts"] >= 0 and
                finite(row.get("lateral_displacement")) and
                finite(row.get("final_error")) and row["final_error"] >= 0 and
                finite(row.get("total_reward")), "NONPHYSICAL_CONTACT_PROGRESS_RECORD")
        n = row.get("full_transition_count")
        require(type(n) is int and n == row["option_steps"] and 1 <= n <= 60 and
                isinstance(row.get("transitions"), list) and row["transitions"] and
                SHA64.fullmatch(row.get("full_transition_sha256", "")) is not None and
                row.get("sparse_trace") is True,
                "INCOMPLETE_FULL_VS_SPARSE_TRANSITION_BINDING")
        require(row.get("sparse_transition_indices") == sparse_indices(n),
                "UNBOUND_SPARSE_TRANSITION_INDICES")
        row_map[(seed, strategy)] = row
        trial_transition_sum += n
    require(near_seeds == set(expected_near) and clear_seeds == set(expected_clear) and
            set(row_map) == {(seed, name)
                             for seed in (*expected_near, *expected_clear)
                             for name in strategies},
            "NOT_ALL_FROZEN_STRATEGIES_ON_EXACT_FIRST_160_TRAIN_WORLDS")
    require(training.get("selected_near_count") == len(near_seeds) and
            training.get("selected_clear_count") == len(clear_seeds),
            "SELECTED_TRAIN_WORLD_COUNTS_NOT_REPRODUCIBLE")
    require(all(count == MIN_NEAR + MIN_CLEAR for count in strategy_usage.values()),
            "STRATEGY_CATALOG_CONTAINS_UNEXECUTED_ARMS")
    require(training.get("actual_transition_count") == trial_transition_sum,
            "TRAIN_TRANSITION_COUNT_NOT_BOUND_TO_TRIALS")

    raw_path = evidence_dir / "full_transitions.jsonl.gz"
    seen = set()
    raw_actual = 0
    with gzip.open(raw_path, "rt", encoding="utf8") as source_stream:
        for line in source_stream:
            require(len(line) <= 2 * 1024 * 1024 and len(seen) < len(trials),
                    "UNBOUNDED_OR_EXTRA_FULL_TRANSITION_LINE")
            doc = json.loads(line)
            require(isinstance(doc, dict) and
                    type(doc.get("seed")) is int and
                    isinstance(doc.get("strategy"), str),
                    "INVALID_FULL_TRANSITION_IDENTITY")
            key = (doc["seed"], doc["strategy"])
            require(key in row_map and key not in seen, "UNKNOWN_OR_DUPLICATE_FULL_TRACE")
            row = row_map[key]
            full = doc.get("transitions")
            require(isinstance(full, list) and len(full) == row["full_transition_count"],
                    "MISSING_FULL_REAL_TRANSITIONS")
            require(canonical_sha(full) == row["full_transition_sha256"],
                    "FORGED_FULL_ACTION_DATASET_SHA")
            for t in full:
                validate_transition(t)
            contact_trace = [t["contacts_cumulative"] for t in full]
            require(contact_trace == sorted(contact_trace) and
                    contact_trace[-1] == row["contacts"],
                    "FORGED_CONTACT_COUNT_NOT_BOUND_TO_REAL_STEP_INFO")
            require(row["success"] == full[-1]["success_info"],
                    "FORGED_SUCCESS_NOT_BOUND_TO_TRUE_TERMINAL_INFO")
            if row["success"]:
                last = full[-1]
                obs = last["next_observation"]
                require(row["physics_steps"] > 0 and not row["unsafe"] and
                        not row["abstained"] and last["action"] != 6 and
                        last["contacts_cumulative"] > 0 and
                        last["dwell_ticks_cumulative"] >= 250 and
                        math.hypot(obs[0] - obs[16], obs[1] - obs[17]) < .025,
                        "UNPHYSICAL_DWELL_OR_CONTACT_SUCCESS")
            if row["abstained"]:
                require(full[-1]["action"] == 6,
                        "ABSTAIN_EPISODE_WITHOUT_TERMINAL_ABSTAIN_OPTION")
            require(abs(float(full[0]["observation"][7]) -
                        row["initial_observed_obstacle_y"]) < 1e-5,
                    "SCENARIO_LABEL_CANNOT_BE_RECONSTRUCTED_FROM_PUBLIC_INPUT")
            first_obj_y = float(full[0]["observation"][1])
            final_obj_y = float(full[-1]["next_observation"][1])
            away_sign = (-1. if float(full[0]["observation"][7]) >= first_obj_y
                         else 1.)
            observed_away_displacement = (final_obj_y - first_obj_y) * away_sign
            require(abs(observed_away_displacement - row["lateral_displacement"]) < 1e-5,
                    "FORGED_OBSTACLE_AWAY_LATERAL_DISPLACEMENT")
            require([full[i] for i in sparse_indices(len(full))] ==
                    row["transitions"], "SPARSE_TRACE_DOES_NOT_MATCH_TRUE_FULL_TRACE")
            require(abs(sum(t["reward"] for t in full) - row["total_reward"]) < 1e-4,
                    "REWARD_RECEIPT_NOT_DERIVED_FROM_REAL_OPTIONS")
            require(bool(any(t["cost"] for t in full)) == row["unsafe"],
                    "UNSAFE_OUTCOME_NOT_DERIVED_FROM_COST")
            require(full[-1]["done"] is True,
                    "UNFINISHED_PHYSICS_ROLLOUT_CLAIMED_COMPLETE")
            if row["physics_steps"] == 0:
                require(full[0]["action"] == 6, "ZERO_STEP_NONABSTAIN_ACTION")
                require(all(abs(float(full[0]["observation"][i]) -
                                float(full[0]["next_observation"][i])) < 1e-6
                            for i in range(4)),
                        "ZERO_PHYSICS_CANNOT_MOVE_OBJECT_OR_PUSHER")
            seen.add(key)
            raw_actual += len(full)
    require(seen == set(row_map) and raw_actual == trial_transition_sum,
            "INCOMPLETE_RAW_TRANSITION_COVERAGE")

    safe_corridor_successes = {
        seed for (seed, _), row in row_map.items()
        if row["observed_corridor"] and row["success"] and not row["unsafe"]
    }
    corridor_displacement = {
        seed for (seed, _), row in row_map.items()
        if row["observed_corridor"] and not row["unsafe"] and
        row["lateral_displacement"] >= .025
    }
    result = {
        "schema": "junction.rokoko.mujoco-v7-feasibility.craci.train.v1",
        "exact_source_sha": source,
        "experiment_complete": True,
        "mechanism_positive": bool(safe_corridor_successes),
        "train_only_seed_start": TRAIN_FIRST,
        "selected_near_worlds": len(near_seeds),
        "selected_clear_worlds": len(clear_seeds),
        "strategies": strategy_usage,
        "worlds_safe_corridor_success": len(safe_corridor_successes),
        "worlds_safe_lateral_displacement_ge_25mm": len(corridor_displacement),
        "actual_real_option_transitions": raw_actual,
        "trials": len(trials),
        "dataset_sha256": training["dataset_sha256"],
        "full_transition_archive_sha256": fh["full_transitions.jsonl.gz"],
        "promotion_authorized": False,
        "dev_cal_test_ood_opened": False,
        "dispatch_authorized": False,
        "next_experiment_advisory": {
            "new_train_seed_start": 513000,
            "new_dev_seed_start": 129330,
            "next_step": ("new_source_holdout_after_independent_review"
                          if safe_corridor_successes else
                          "examine_action_primitive_feasibility_without_changing_frozen_task"),
            "note": "No discovery among tested strategies is not an impossibility theorem",
        },
        "limits": "Real MuJoCo train-only probe; no test qualification or physical robot safety certificate",
    }
    return result


def main():
    src = Path(os.environ["CRACI_SOURCE_ROOT"]).resolve()
    receipt = Path(os.environ["CRACI_RECEIPT_DIR"]).resolve()
    dest = receipt / "artifacts" / "rokoko-mujoco-v7-feasibility"
    require(not dest.exists(), "NO_OVERWRITE_V7_EVIDENCE")
    dest.mkdir(parents=True)
    requested = os.environ["CRACI_SOURCE_SHA"]
    require(SHA40.fullmatch(requested) is not None, "EXACT_SOURCE_SHA_REQUIRED")
    head = subprocess.check_output(["git", "-C", str(src), "rev-parse", "HEAD"],
                                   text=True).strip()
    require(head == requested, "SOURCE_GIT_HEAD_MISMATCH")
    require(subprocess.run(["git", "-C", str(src), "status", "--porcelain"],
                           capture_output=True, text=True, check=True).stdout == "",
            "NONCLEAN_PRODUCT_SOURCE")
    require(subprocess.run(["git", "-C", str(src), "merge-base", "--is-ancestor",
                            ANCESTOR_V6, requested], check=False).returncode == 0,
            "V7_NOT_DESCENDED_FROM_REVIEWED_V6")
    py = Path(os.environ["RUNNER_TEMP"]) / "mujoco-venv/bin/python"
    require(py.is_file(), "PINNED_MUJOCO_PYTHON_MISSING")
    module = src / PRODUCT
    subprocess.run([str(py), "-m", "unittest", "discover", "-v", "-s",
                    str(module), "-p", "test_contract.py"], cwd=src, check=True)
    subprocess.run([str(py), "-c",
        "import sys;sys.path.insert(0,sys.argv[1]);"
        f"from physics import MovingContactEnv; o=MovingContactEnv(max_options=60).reset(seed={TRAIN_FIRST},ood=False);"
        "assert len(o)==18, 'REAL_18D_MUJOCO_SMOKE_FAILURE'",
        str(src / PRODUCT.parent)], cwd=src, check=True)
    process = subprocess.run([
        str(py), str(module / "run.py"), "--mode", "train-feasibility",
        "--require-git", "--expected-head", requested,
        "--output-dir", str(dest), "--max-seeds", str(SEED_LIMIT),
        "--time-budget-seconds", "1200",
    ], cwd=src, check=False)
    training = read_json(dest / "training.json")
    manifest = read_json(dest / "manifest.json")
    result = verify_training(training, manifest, requested, dest)
    # Producer flags, even when self-consistent with its JSON, cannot certify
    # a new contact capability. Re-run every CLAIMED positive TRAIN trace on
    # the reviewed MuJoCo physics with the exact seed and action sequence.
    # This deliberately spends extra CPU instead of trusting copied flags.
    replay_script = Path(__file__).with_name("rokoko-mujoco-v7-positive-replay.py")
    require(replay_script.is_file(), "INDEPENDENT_POSITIVE_REPLAY_MISSING")
    subprocess.run([
        str(py), str(replay_script), "--evidence-dir", str(dest),
        "--physics-dir", str(src / PRODUCT.parent),
    ], cwd=src, check=True)
    replay = read_json(dest / "independent-positive-replay.json", max_bytes=1024 * 1024)
    require(replay.get("claim_verified") is True and
            replay.get("verified_near_corridor_success_worlds") ==
            result["worlds_safe_corridor_success"] and
            replay.get("verified_obstacle_away_displacement_worlds") ==
            result["worlds_safe_lateral_displacement_ge_25mm"],
            "MECHANISM_NOT_INDEPENDENTLY_REPLAYED_ON_REAL_MUJOCO")
    result["independent_true_physics_positive_replay"] = replay
    result["producer_exit_code"] = process.returncode
    result["experiment_complete"] &= process.returncode == 0
    result["decision"] = ("valid_train_only_feasibility_evidence" if
                          result["experiment_complete"] else "producer_nonzero")
    path = dest / "independent-qualification.json"
    with path.open("x", encoding="utf8") as f:
        json.dump(result, f, sort_keys=True, indent=2)
        f.write("\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["experiment_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
