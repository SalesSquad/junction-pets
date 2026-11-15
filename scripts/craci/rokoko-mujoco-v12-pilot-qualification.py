#!/usr/bin/env python3
"""CRACI V12 honest fresh-TRAIN MuJoCo pilot: 512 public starts, 48x3 episodes.

This is an EXPERIMENT, not a promotion. Source-bound original V8 physics, V5
baseline, V12 supported-action hypothesis and distinct UNTRAINED right4 probe.
Run V5 FIRST, then hypothesis, then probe per selected world. On any observed
unsafe or V5-goal regression STOP immediately and retain SHA-bound INCOMPLETE
raw evidence; never fish/retry affected seeds or pretend full qualification.

Full 144-episode originals remain private until a completely independent
true-MuJoCo, policy, seven-mask, contact+250tick replay verifies EVERY option.
The versioned V12 packer publishes only 6MiB lossless parts under the original
CRACI 20MiB/file and 63MiB total collector caps. DEV/CAL/TEST/OOD unopened.
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import numpy as np


PRODUCT = Path("solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v12_learning")
PHYSICS = PRODUCT.parent
MODEL = PRODUCT / "frozen-real-train-v10-v11-final/model.json"
PLAN = PRODUCT / "frozen-real-train-v10-v11-final/next-train-plan.json"
MODEL_SHA = "82cfa42ba2240aff6d00ec3e2b15c06d78386d3c0682986a23e478977f2dbf9e"
PLAN_SHA = "8074f8f8978e2e55bdf201eeb9713888e44befe1d93856da44c1830bb86cfc48"
V10_SHA = "9cc583d3f0f24484b79c1929ba875c7a3b667806"
V10_WEIGHTS_SHA = "3a926fdd80bc5bfe069ba4ab50792aaed760d81480eb68a80b6e087beec71f3d"
V8_WEIGHTS_SHA = "07823dcc52ea85b64e18767e1b1af29e63e3236613598cb349610a6b4fd37dc1"
V8_RECEIPT_SHA = "dc22f5538f19ef346d6b9965e7b28beed15e813b4b149ae5711d7dfae1771e73"
SCHEMA = "junction.rokoko.v12.fresh-518000-pilot.v1"
FIRST = 518000
SCAN = 512
EXPECTED = 144
ARMS = ("frozen_v5", "v12_phase_dwell_supported_actions",
        "v12_right_side_action4_exploration_train_only")
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def require(ok, why):
    if not ok:
        raise AssertionError(why)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def load_module(path, unique):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "V12_SOURCE_MODULE_MISSING")
    spec = importlib.util.spec_from_file_location(unique, path)
    require(spec is not None and spec.loader is not None,
            "V12_EXACT_SOURCE_MODULE_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git_head_clean(root, expected):
    require(SHA40.fullmatch(expected) is not None and
            subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                    text=True).strip() == expected and
            subprocess.check_output(["git", "-C", str(root), "status", "--porcelain=v1"],
                                    text=True).strip() == "",
            "V12_CLEAN_SOURCE_EXACT_FULL_HEAD_REQUIRED")
    require(subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor",
                            V10_SHA, "HEAD"], capture_output=True).returncode == 0,
            "V12_FROZEN_V10_SOURCE_ANCESTOR_REQUIRED")


def stage_frozen_models(source_root, private):
    require(not private.exists(), "V12_PRIVATE_MODEL_STAGING_MUST_BE_FRESH")
    private.mkdir(mode=0o700, parents=True, exist_ok=False)
    sources = {
        "candidate-weights.json": (PHYSICS / "v10_learning/checkpoints/candidate-weights.json",
                                   V10_WEIGHTS_SHA),
        "weights.json": (PHYSICS / "v8_learning/checkpoints/weights.json",
                         V8_WEIGHTS_SHA),
        "training-receipt.json": (PHYSICS / "v8_learning/checkpoints/training-receipt.json",
                                  V8_RECEIPT_SHA),
    }
    staged = {}
    for name, (relative, expected) in sources.items():
        source = source_root / relative
        dest = private / name
        require(source.is_file() and not source.is_symlink() and
                sha(source) == expected, "V12_REVIEWED_FROZEN_SOURCE_MODEL_CHANGED")
        shutil.copyfile(source, dest)
        require(sha(dest) == expected and
                not dest.resolve().is_relative_to(source_root),
                "V12_PRIVATE_FROZEN_MODEL_COPY_NOT_EXACT_OR_OUTSIDE_SOURCE")
        staged[name] = dest
    return staged


def near(a, b, tol=1e-5):
    return len(a) == len(b) == 18 and all(
        abs(float(x) - float(y)) <= tol for x, y in zip(a, b))


def original_plan_and_model(product_root, policy, protocol):
    model = product_root / "frozen-real-train-v10-v11-final/model.json"
    plan = product_root / "frozen-real-train-v10-v11-final/next-train-plan.json"
    require(sha(model) == MODEL_SHA and sha(plan) == PLAN_SHA,
            "V12_REVIEWED_FROZEN_MODEL_OR_PLAN_SHA_CHANGED")
    policy.load_frozen_model(model)
    protocol.verified_plan(plan)
    require(protocol.PILOT_ARMS == ARMS,
            "V12_ORIGINAL_THREE_ARM_PILOT_PROTOCOL_CHANGED")
    return model, protocol.verified_plan(plan)


def original_factories(source_root, stage, v12_policy):
    source = source_root / PHYSICS / "v10_prospective/run.py"
    original = load_module(source, "v12_verified_frozen_v10_prospective_source")
    original.verify_historical_source(source_root)
    v7, Env = original.v8.import_v7_and_physics()
    frozen_v8, _, _ = original.v8.verify_frozen_model(
        stage["weights.json"], stage["training-receipt.json"],
        original.v8.FROZEN_WEIGHTS_SHA256)
    frozen_v5 = original.policy_factory(
        "frozen_v5", stage["candidate-weights.json"],
        frozen_v8, frozen_v7=v7)
    model = source_root / MODEL
    return ({
        ARMS[0]: frozen_v5,
        ARMS[1]: v12_policy.policy_factory(frozen_v5, model),
        ARMS[2]: v12_policy.right4_train_only_factory(frozen_v5, model),
    }, original.v8, v7, Env, v7.v6.v5.v4.v3.v2.v1._world_signature)


def scan_real_public_starts(env, signature):
    result = []
    for seed in range(FIRST, FIRST + SCAN):
        obs = env.reset(seed=seed, ood=False)
        mask = env.mask(obs)
        require(np.asarray(obs).shape == (18,) and
                np.asarray(mask).shape == (7,) and
                np.all(np.isfinite(obs)), "V12_ONLY_REAL_FINITE_PUBLIC_18D_AND_SEVEN_MASK")
        result.append({"seed": seed, "world_hash": str(signature(env)),
                       "observation": np.asarray(obs).tolist(),
                       "mask": np.asarray(mask, dtype=int).tolist()})
    return result


def independent_first_public_cohort(scans, cohort):
    """Defend even if a future product protocol accidentally accepts a forged plan."""
    require(len(scans) == SCAN and
            [row["seed"] for row in scans] == list(range(FIRST, FIRST + SCAN)),
            "V12_INDEPENDENT_ONLY_CANONICAL_518000_512_PUBLIC_SEEDS")
    near, clear = [], []
    for row in scans:
        obs = row["observation"]
        mask = row["mask"]
        require(len(obs) == 18 and len(mask) == 7 and
                all(type(x) in (int, float) and np.isfinite(x) for x in obs) and
                all(type(bit) is int and bit in (0, 1) for bit in mask) and
                any(mask) and len(row["world_hash"]) == 64,
                "V12_INDEPENDENT_FINITE_PUBLIC_18D_7MASK_SHA_WORLD_REQUIRED")
        record = {"seed": row["seed"], "world_hash": row["world_hash"],
                  "initial_public_obstacle_y": obs[7], "initial_mask": mask,
                  "observed_corridor": abs(obs[7]) < .122}
        if record["observed_corridor"] and len(near) < 40:
            near.append(record)
        elif not record["observed_corridor"] and len(clear) < 8:
            clear.append(record)
    require(len(near) == 40 and len(clear) == 8 and
            cohort == sorted([*near, *clear], key=lambda row: row["seed"]),
            "V12_INDEPENDENT_FIRST40_NEAR8_CLEAR_CANNOT_BE_FORGED")
    return True


def save_json_fresh(path, value):
    with path.open("xb") as out:
        out.write(canonical(value) + b"\n")


def safe_goal(row):
    return bool(row["success"] and not row["unsafe"] and not row["abstained"])


def run_pilot_originals(source_root, private, model, plan, policy, protocol,
                        factories, v8, v7, Env, signature, source_sha,
                        seconds=900):
    """Original producer: completed rows only, immutable full raw stream."""
    require(not private.exists(), "V12_PRIVATE_ORIGINAL_OUTPUT_ALREADY_EXISTS")
    private.mkdir(mode=0o700, parents=True, exist_ok=False)
    env = Env(max_options=v8.MAX_OPTIONS)
    scan = scan_real_public_starts(env, signature)
    cohort = protocol.derive_cohort(scan, plan, "pilot")
    independent_first_public_cohort(scan, cohort)
    require(len(cohort) == 48 and sum(w["observed_corridor"] for w in cohort) == 40 and
            len({w["seed"] for w in cohort}) == 48,
            "V12_PUBLIC_FIRST_40_NEAR_8_CLEAR_COHORT_DRIFT")
    deadline = time.monotonic() + seconds
    trials = []
    right4 = []
    stop_reason = None
    try:
        with gzip.open(private / "full_transitions.jsonl.gz", "xt",
                       encoding="utf8", newline="\n", compresslevel=6) as gz:
            for world in cohort:
                baseline = None
                for arm in ARMS:
                    if time.monotonic() >= deadline:
                        stop_reason = "TIME_BUDGET_EXCEEDED_BEFORE_NEXT_EPISODE"
                        break
                    try:
                        row, trace = v8.run_real_episode(
                            env, world["seed"], arm, factories[arm],
                            signature, deadline, v7)
                    except TimeoutError:
                        stop_reason = "TIME_BUDGET_EXCEEDED_DURING_EPISODE"
                        break
                    require(row["world_hash"] == world["world_hash"] and
                            near(trace[0]["observation"], scan[world["seed"] - FIRST]["observation"]),
                            "V12_PAIRED_ACTUAL_REAL_PUBLIC_WORLD_SOURCE_CHANGED")
                    row.update(observed_corridor=world["observed_corridor"],
                               initial_observed_obstacle_y=world["initial_public_obstacle_y"])
                    # Complete raw row must be retained *before* any STOP decision.
                    trials.append(row)
                    gz.write(canonical({"seed": world["seed"], "strategy": arm,
                                        "transitions": trace}).decode() + "\n")
                    if arm == ARMS[0]:
                        baseline = row
                    elif arm == ARMS[1] and baseline is not None and safe_goal(baseline) and not safe_goal(row):
                        stop_reason = "CANDIDATE_LOST_ACTUAL_FROZEN_V5_GOAL"
                    if row["unsafe"]:
                        stop_reason = "OBSERVED_UNSAFE_ACTUAL_MUJOCO_COST"
                    if arm == ARMS[2]:
                        right4.extend((world["seed"], i, step["mask"])
                                      for i, step in enumerate(trace)
                                      if step["action"] == 4)
                    if stop_reason:
                        break
                if stop_reason:
                    break
    except Exception as exc:
        # A fatal runtime exception cannot be treated as scientific success.
        # The class-only failure code (no private error payload) is retained
        # alongside completed raw traces and a nonzero INCOMPLETE job status.
        stop_reason = "SOURCE_OR_PHYSICS_EXCEPTION_UNQUALIFIED_" + type(exc).__name__
    if stop_reason:
        partial = {"schema": SCHEMA + ".incomplete",
                   "executed_head": source_sha, "training_only": True,
                   "status": "INCOMPLETE_STOP",
                   "stop_reason": stop_reason,
                   "real_completed_episodes": len(trials),
                   "raw_real_option_transitions": sum(
                       r["full_transition_count"] for r in trials),
                   "all_512_public_initial_scans": scan, "cohort": cohort,
                   "complete_real_trial_rows": trials,
                   "promotion_authorized": False,
                   "dev_cal_test_ood_opened": False,
                   "no_automatic_retry_or_seed_fishing": True}
        save_json_fresh(private / "partial_training.json", partial)
        save_json_fresh(private / "early_stop.json", {
            "schema": SCHEMA + ".early-stop",
            "status": "INCOMPLETE_STOP", "executed_head": source_sha,
            "reason": stop_reason, "completed_episodes": len(trials),
            "expected_episodes": EXPECTED, "model_sha256": MODEL_SHA,
            "plan_sha256": PLAN_SHA, "training_only": True,
            "raw_sha256": {
                name: sha(private / name)
                for name in ("partial_training.json", "full_transitions.jsonl.gz")},
            "promotion_authorized": False, "dev_cal_test_ood_opened": False})
        return {"complete": False, "reason": stop_reason,
                "completed_episodes": len(trials)}
    require(len(trials) == EXPECTED, "V12_PILOT_MISSING_REAL_EPISODES")
    readout = protocol.paired_physical_goal_readout(
        trials, cohort, "pilot", all_512_initial_public_worlds=scan,
        plan=plan)
    training = {"schema": SCHEMA + ".training", "executed_head": source_sha,
                "training_only": True, "actual_physics_engine": "mujoco-3.3.7",
                "all_512_public_initial_scans": scan, "cohort": cohort,
                "strategies": list(ARMS), "trials": trials,
                "actual_trials": len(trials),
                "actual_option_transitions": sum(r["full_transition_count"] for r in trials),
                "model_sha256": MODEL_SHA, "plan_sha256": PLAN_SHA,
                "observed_exploration_action4_executions": len(right4),
                "observed_exploration_action4_instances": [
                    {"seed": s, "option_index": i, "original_seven_mask": m}
                    for s, i, m in right4],
                "no_dev_test_ood": True, "model_promotion_authorized": False}
    save_json_fresh(private / "training.json", training)
    save_json_fresh(private / "paired-readout.json", readout)
    manifest = {"schema": SCHEMA + ".manifest", "executed_head": source_sha,
                "training_only": True, "model_sha256": MODEL_SHA,
                "plan_sha256": PLAN_SHA, "actual_trials": len(trials),
                "actual_option_transitions": training["actual_option_transitions"],
                "original_v10_source_sha": V10_SHA, "promotion_authorized": False,
                "dev_cal_test_ood_opened": False,
                "file_sha256": {name: sha(private / name) for name in (
                    "training.json", "full_transitions.jsonl.gz", "paired-readout.json")}}
    save_json_fresh(private / "manifest.json", manifest)
    return {"complete": True, "right4_executions": len(right4),
            "source_preliminary_readout": readout}


def verify_full_originals(private, source_sha, protocol, plan, v7):
    training = v7.read_json(private / "training.json")  # frozen 32MiB cap
    manifest = v7.read_json(private / "manifest.json", max_bytes=1024 * 1024)
    readout = v7.read_json(private / "paired-readout.json", max_bytes=1024 * 1024)
    require(training.get("schema") == SCHEMA + ".training" and
            manifest.get("schema") == SCHEMA + ".manifest" and
            training["executed_head"] == manifest["executed_head"] == source_sha and
            training["actual_physics_engine"] == "mujoco-3.3.7" and
            training["no_dev_test_ood"] is True and
            training["model_promotion_authorized"] is False and
            manifest["promotion_authorized"] is False and
            manifest["dev_cal_test_ood_opened"] is False and
            training["strategies"] == list(ARMS) and
            training["actual_trials"] == manifest["actual_trials"] == EXPECTED and
            len(training["trials"]) == EXPECTED and
            training["model_sha256"] == manifest["model_sha256"] == MODEL_SHA and
            training["plan_sha256"] == manifest["plan_sha256"] == PLAN_SHA and
            set(manifest["file_sha256"]) ==
            {"training.json", "full_transitions.jsonl.gz", "paired-readout.json"},
            "V12_EXACT_COMPLETE_ORIGINAL_REAL_PILOT_SCHEMA_MISMATCH")
    for name, expected in manifest["file_sha256"].items():
        require((private / name).is_file() and not (private / name).is_symlink()
                and (private / name).stat().st_size <= 32 * 1024 * 1024
                and sha(private / name) == expected,
                "V12_THREE_COMPLETE_ORIGINAL_FILE_SHA_MISMATCH")
    scans = training["all_512_public_initial_scans"]
    cohort = protocol.derive_cohort(scans, plan, "pilot")
    independent_first_public_cohort(scans, cohort)
    require(training["cohort"] == cohort and len(cohort) == 48 and
            sum(w["observed_corridor"] for w in cohort) == 40,
            "V12_PUBLIC_512_FIRST40_NEAR8_CLEAR_SELECTION_NOT_REPRODUCIBLE")
    rows = {(r["seed"], r["strategy"]): r for r in training["trials"]}
    require(len(rows) == EXPECTED and
            set(rows) == {(world["seed"], arm) for world in cohort for arm in ARMS},
            "V12_ORIGINAL_144_COMPLETE_PAIRED_WORLD_STRATEGIES_MISSING")
    original_readout = protocol.paired_physical_goal_readout(
        training["trials"], cohort, "pilot",
        all_512_initial_public_worlds=scans, plan=plan)
    require(readout == original_readout and
            training["actual_option_transitions"] ==
            manifest["actual_option_transitions"] ==
            sum(r["full_transition_count"] for r in training["trials"]),
            "V12_ORIGINAL_GOAL250_PAIRED_SCIENCE_OR_TRANSITION_COUNTS_DRIFT")
    return training, manifest, readout, rows


def independent_true_physics_replay(private, training, rows, factories, v7,
                                    Env, signature):
    """Replay ALL 144 completed episodes, every legal action and every step."""
    env = Env(max_options=60)
    for frame in training["all_512_public_initial_scans"]:
        obs = env.reset(seed=frame["seed"], ood=False)
        require(near(obs, frame["observation"]) and
                [int(bit) for bit in env.mask(obs)] == frame["mask"] and
                signature(env) == frame["world_hash"],
                "V12_INDEPENDENT_MUJOCO_ALL512_INITIAL_PUBLIC_WORLDS_NOT_REPRODUCED")
    seen = set()
    action4 = []
    replay_near, replay_clear = 0, 0
    physics_options = 0
    with gzip.open(private / "full_transitions.jsonl.gz", "rt",
                   encoding="utf8") as source:
        for line in source:
            require(len(line) < 2 * 1024 * 1024 and len(seen) < EXPECTED,
                    "V12_FULL_RAW_OPTION_TRACE_MISSING_OR_OVERSIZED")
            doc = json.loads(line)
            key = (doc["seed"], doc["strategy"])
            require(key in rows and key not in seen,
                    "V12_UNREGISTERED_OR_DUPLICATE_REAL_RAW_STRATEGY_ROW")
            seen.add(key)
            row, transitions = rows[key], doc["transitions"]
            require(len(transitions) == row["option_steps"] ==
                    row["full_transition_count"] and
                    digest(transitions) == row["full_transition_sha256"] and
                    [transitions[i] for i in v7.sparse_indices(len(transitions))] ==
                    row["transitions"],
                    "V12_FULL_RAW_SPARSE_AND_SHA_ORIGINALS_INCONSISTENT")
            observation = env.reset(seed=doc["seed"], ood=False)
            require(signature(env) == row["world_hash"] and
                    near(observation, transitions[0]["observation"]),
                    "V12_INDEPENDENT_INITIAL_PAIRED_MUJOCO_WORLD_DRIFT")
            controller = factories[key[1]]()
            max_dwell = 0
            last = None
            for index, t in enumerate(transitions):
                v7.validate_transition(t)
                require(near(observation, t["observation"]),
                        "V12_INDEPENDENT_PHYSICS_18D_PRESTATE_NOT_REPRODUCED")
                mask = env.mask(observation)
                require([int(x) for x in mask] == t["mask"] and
                        mask[t["action"]] and
                        len(mask) == 7,
                        "V12_INDEPENDENT_ALL_SEVEN_ACTION_MASKS_NOT_ORIGINAL")
                action = controller(observation.copy(), mask.copy())
                require(type(action) is int and action == t["action"],
                        "V12_SOURCE_FROZEN_POLICY_ACTION_NOT_REPRODUCED")
                if key[1] == ARMS[2] and action == 4:
                    action4.append({"seed": doc["seed"], "option_index": index,
                                    "original_seven_mask": [int(x) for x in mask]})
                observation, reward, done, info = env.step(action)
                max_dwell = max(max_dwell, int(env.dwell))
                require(near(observation, t["next_observation"]) and
                        abs(float(reward) - float(t["reward"])) < 1e-5 and
                        int(info["cost"]) == t["cost"] and
                        int(info["contacts"]) == t["contacts_cumulative"] and
                        bool(info["success"]) == t["success_info"] and
                        bool(done) == t["done"] and
                        max_dwell == t["dwell_ticks_cumulative"] and
                        int(env.dwell) == t["dwell_ticks_current"] and
                        (not done or index == len(transitions) - 1),
                        "V12_INDEPENDENT_EVERY_REAL_PHYSICS_TRANSITION_DIVERGED")
                last = info
                physics_options += 1
            require(last is not None and env.done and
                    bool(last["success"]) == row["success"] and
                    bool(last["unsafe"]) == row["unsafe"] and
                    bool(last["abstained"]) == row["abstained"] and
                    int(env.steps) == row["option_steps"] and
                    int(env.physics_steps) == row["physics_steps"] and
                    int(env.contacts) == row["contacts"] and
                    abs(float(last["error"]) - float(row["final_error"])) < 1e-5 and
                    (not row["success"] or
                     (int(env.dwell) >= 250 and int(env.contacts) > 0 and
                      not row["unsafe"] and not row["abstained"])),
                    "V12_INDEPENDENT_COMPLETE_TERMINAL_MUJOCO_250TICK_GOAL_DRIFT")
            if safe_goal(row):
                if row["observed_corridor"]:
                    replay_near += 1
                else:
                    replay_clear += 1
    require(len(seen) == EXPECTED and seen == set(rows) and
            physics_options == training["actual_option_transitions"] and
            action4 == training["observed_exploration_action4_instances"] and
            len(action4) == training["observed_exploration_action4_executions"],
            "V12_INDEPENDENT_144_PHYSICS_OR_ORIGINAL_RIGHT4_PROBE_TRACE_MISSING")
    return {"schema": SCHEMA + ".independent-physics",
            "exact_real_full_options_replayed": physics_options,
            "all_512_public_initial_worlds_replayed": True,
            "all_144_complete_real_episodes_replayed": True,
            "real_safe_near_goal_trajectories_replayed": replay_near,
            "real_safe_clear_goal_trajectories_replayed": replay_clear,
            "untrained_right4_actual_legal_executions": len(action4),
            "original_exploration_option4_instances_sha256": digest(action4),
            "claim_verified": True, "training_only": True,
            "promotion_authorized": False, "dev_cal_test_ood_opened": False}


def main():
    source_root = Path(os.environ["CRACI_SOURCE_ROOT"]).resolve(strict=True)
    harness_root = Path(os.environ["CRACI_HARNESS_ROOT"]).resolve(strict=True)
    receipt = Path(os.environ["CRACI_RECEIPT_DIR"]).resolve(strict=True)
    expected = os.environ["CRACI_SOURCE_SHA"]
    harness_sha = os.environ["CRACI_HARNESS_SHA"]
    git_head_clean(source_root, expected)
    require(SHA40.fullmatch(harness_sha) is not None and
            subprocess.check_output(["git", "-C", str(harness_root), "rev-parse",
                                     "HEAD"], text=True).strip() == harness_sha,
            "V12_SEPARATE_PINNED_EXECUTION_HARNESS_SHA_REQUIRED")
    require(os.environ.get("CRACI_WORKLOAD") == "rokoko-mujoco-v12-pilot" and
            os.environ.get("CRACI_CREDIT_WINDOW_OPEN") == "true" and
            float(os.environ.get("CRACI_CREDIT_REMAINING_SECONDS", "0")) >= 3600,
            "V12_CREDIT_3600S_ADMISSION_OR_WORKLOAD_NOT_AUTHORIZED")
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    py = runner_temp / "mujoco-venv/bin/python"
    require(py.is_file(), "V12_PINNED_NORMAL_PYTHON_VENV_SYMLINK_SUPPORTED")
    subprocess.run([str(py), "-B", "-c",
                    "import mujoco,numpy,sys;"
                    "assert mujoco.__version__=='3.3.7';"
                    "assert numpy.__version__=='2.3.4';"
                    "assert sys.prefix!=sys.base_prefix"],
                   cwd=source_root, check=True)
    subprocess.run([str(py), "-B", "-m", "unittest", "discover", "-q",
                    "-s", str(source_root / PRODUCT), "-p", "test_learning.py"],
                   cwd=source_root, check=True)
    product = source_root / PRODUCT
    policy = load_module(product / "policy.py", "v12_product_policy_unique")
    protocol = load_module(product / "protocol.py", "v12_product_protocol_unique")
    model, plan = original_plan_and_model(product, policy, protocol)
    stage = stage_frozen_models(
        source_root, runner_temp / "v12-pilot-private-frozen-models")
    factories, v8, v7source, Env, signature = original_factories(
        source_root, stage, policy)
    private = runner_temp / "v12-pilot-518000-private-originals"
    result = run_pilot_originals(
        source_root, private, model, plan, policy, protocol,
        factories, v8, v7source, Env, signature, expected)
    # Even a scientific STOP must retain original *partial* completed episodes
    # and the explicit INCOMPLETE status. Never misreport a 144-row dataset.
    packer = load_module(
        harness_root / "scripts/craci/rokoko-mujoco-v12-retain-evidence.py",
        "v12_reviewed_lossless_private_pilot_packer")
    collector = receipt / "artifacts" / "rokoko-mujoco-v12-pilot"
    if not result["complete"]:
        packed = packer.publish_early_stop(private, collector)
        print(json.dumps({"status": "INCOMPLETE_STOP", "reason": result["reason"],
                          "completed_real_episodes": result["completed_episodes"],
                          "partial_original_sha256": packed["original_sha256"],
                          "promotion_authorized": False}, sort_keys=True))
        return 3
    v7 = load_module(
        harness_root / "scripts/craci/rokoko-mujoco-v7-feasibility-qualification.py",
        "v12_original_v7_unmodified_real_trace_validator")
    training, manifest, readout, rows = verify_full_originals(
        private, expected, protocol, plan, v7)
    replay = independent_true_physics_replay(
        private, training, rows, factories, v7, Env, signature)
    # RIGHT4 must be actually emitted under the *original* mask. The probe
    # never trains a right4 transition model and never permits promotion.
    lost = readout["candidateLostV5GoalWorldSeeds"]
    unsafe = (readout["candidateUnsafeWorldSeeds"] +
              readout["explorationOnlyUnsafeWorldSeeds"])
    novel = readout["candidateNovelSafeGoalWorldSeeds"]
    stop = bool(lost or unsafe or not novel or
                replay["untrained_right4_actual_legal_executions"] == 0)
    science = ("STOP_UNSAFE_LOST_ZERO_NOVEL_OR_NO_ACTUAL_RIGHT4_DATA" if stop else
               "TRAIN_ONLY_SCIENCE_HYPOTHESIS_REQUIRES_NEW_REVIEW")
    qualified = {"schema": SCHEMA + ".independent-qualification",
                 "executed_head": expected, "harness_head": harness_sha,
                 "experiment_complete": True, "actual_trials": EXPECTED,
                 "actual_option_transitions": training["actual_option_transitions"],
                 "model_sha256": MODEL_SHA, "plan_sha256": PLAN_SHA,
                 "original_sha256": manifest["file_sha256"],
                 "full_144_real_episode_physics_replay": replay,
                 "science_gate": science, "new_model_promotion_authorized": False,
                 "dev_cal_test_ood_opened": False,
                 "right4_exploration_is_untrained": True}
    save_json_fresh(private / "independent-qualification.json", qualified)
    packed = packer.publish_qualified(private, collector)
    require(packed["original_sha256"] == manifest["file_sha256"] and
            packed["exact_source_sha"] == expected,
            "V12_LOSSLESS_THREE_ORIGINAL_SOURCES_NOT_RETAINED")
    print(json.dumps({"status": "COMPLETE_TRAIN_ONLY", "science": science,
                      "real_episodes": EXPECTED,
                      "real_physics_options_replayed": replay["exact_real_full_options_replayed"],
                      "observed_legal_right4_actions": replay["untrained_right4_actual_legal_executions"],
                      "safe_v5_goals": readout["frozenV5SafeGoals"],
                      "safe_v12_goals": readout["candidateSafeGoals"],
                      "lossless_collector_bytes": packed["collector_bytes"],
                      "promotion_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
