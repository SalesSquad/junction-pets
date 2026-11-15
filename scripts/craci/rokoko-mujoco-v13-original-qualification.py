#!/usr/bin/env python3
"""CRACI V13 honest fresh-TRAIN MuJoCo pilot: 512 public starts, 48x4 episodes.

This is an EXPERIMENT, not a promotion. Source-bound original V8 physics, V5
baseline, frozen V12 supported-action policy and UNTRAINED RIGHT4 bursts 2/4.
Run V5 FIRST, then V12, then burst2, then burst4 per selected world. On any observed
unsafe or V5-goal regression STOP immediately and retain SHA-bound INCOMPLETE
raw evidence; never fish/retry affected seeds or pretend full qualification.

Full 192-episode originals remain private until a completely independent
true-MuJoCo, policy, seven-mask, contact+250tick replay verifies EVERY option.
The versioned V13 packer publishes only 6MiB lossless parts under the original
CRACI 20MiB/file and 63MiB total collector caps. DEV/CAL/TEST/OOD unopened.
"""
from __future__ import annotations

import argparse
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


PRODUCT = Path("solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v13_right_dwell_exploration")
PHYSICS = PRODUCT.parent
V12_PRODUCT = PHYSICS / "v12_learning"
MODEL = V12_PRODUCT / "frozen-real-train-v10-v11-final/model.json"
OLD_PLAN = V12_PRODUCT / "frozen-real-train-v10-v11-final/next-train-plan.json"
MODEL_SHA = "82cfa42ba2240aff6d00ec3e2b15c06d78386d3c0682986a23e478977f2dbf9e"
OLD_PLAN_SHA = "8074f8f8978e2e55bdf201eeb9713888e44befe1d93856da44c1830bb86cfc48"
V10_SHA = "9cc583d3f0f24484b79c1929ba875c7a3b667806"
V10_WEIGHTS_SHA = "3a926fdd80bc5bfe069ba4ab50792aaed760d81480eb68a80b6e087beec71f3d"
V8_WEIGHTS_SHA = "07823dcc52ea85b64e18767e1b1af29e63e3236613598cb349610a6b4fd37dc1"
V8_RECEIPT_SHA = "dc22f5538f19ef346d6b9965e7b28beed15e813b4b149ae5711d7dfae1771e73"
SCHEMA = "junction.rokoko.v13.fresh-519024-sustained-right.v1"
PREFLIGHT_SHA = "099d8cc69d0d11bca1e21d0fe2b4c7c397b3f094a352d80ea3fcc52a2fddad29"
# Pinned, source-derived aggregate over all 512 pre-registered resets. It
# binds public observations/masks and 12-decimal scenario fingerprints from
# the original ARM64 reference; native world hashes are retained separately.
PORTABLE_PREFLIGHT_SHA = "c9a64e3b1582543ee1c96ad2c67a042fe106ca82aed1a09fdf0b61f26f57cc3e"
CUTOFF = 1794762000  # 2026-11-15T17:00:00Z
REVIEWED_PLAN_SHA = "93013025c9e19d94911f249f4dbf0cc034c767da23dca0273d8808323c0b173c"
OBSERVED_PRODUCT_HEAD = "faec266d6d3a44af3a564f46e0778209c1dc3af1"
PLAN_SHA = None  # Mandatory caller pin; never inferred from product bytes.
FIRST = 519024
SCAN = 512
EXPECTED = 192
ARMS = ("frozen_v5", "v12_phase_dwell_supported_actions",
        "train_only_right4_burst2", "train_only_right4_burst4")
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
    require(path.is_file() and not path.is_symlink(), "V13_SOURCE_MODULE_MISSING")
    spec = importlib.util.spec_from_file_location(unique, path)
    require(spec is not None and spec.loader is not None,
            "V13_EXACT_SOURCE_MODULE_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git_head_clean(root, expected, product=True):
    require(SHA40.fullmatch(expected) is not None and
            subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                    text=True).strip() == expected and
            subprocess.check_output(["git", "-C", str(root), "status", "--porcelain=v1"],
                                    text=True).strip() == "",
            "V13_CLEAN_SOURCE_EXACT_FULL_HEAD_REQUIRED")
    if product:
        # The product must descend from the original frozen sources. A
        # separately pinned harness can legitimately have squash-merged
        # history; its identity and clean bytes are checked above instead.
        require(subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor",
                                V10_SHA, "HEAD"], capture_output=True).returncode == 0,
                "V13_FROZEN_V10_SOURCE_ANCESTOR_REQUIRED")
        require(subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor",
                                "c77158f9ae80acc2b1eafaf9284c4397426799b2", "HEAD"],
                               capture_output=True).returncode == 0,
                "V13_KNOWN_PRODUCT_PARENT_REQUIRED")


def stage_frozen_models(source_root, private):
    require(not private.exists(), "V13_PRIVATE_MODEL_STAGING_MUST_BE_FRESH")
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
                sha(source) == expected, "V13_REVIEWED_FROZEN_SOURCE_MODEL_CHANGED")
        shutil.copyfile(source, dest)
        require(sha(dest) == expected and
                not dest.resolve().is_relative_to(source_root),
                "V13_PRIVATE_FROZEN_MODEL_COPY_NOT_EXACT_OR_OUTSIDE_SOURCE")
        staged[name] = dest
    return staged


def near(a, b, tol=1e-5):
    return len(a) == len(b) == 18 and all(
        abs(float(x) - float(y)) <= tol for x, y in zip(a, b))


def original_plan_and_model(source_root, policy, protocol, plan_path, plan_sha):
    model = source_root / MODEL
    require(sha(model) == MODEL_SHA and sha(source_root / OLD_PLAN) == OLD_PLAN_SHA,
            "V13_FROZEN_V12_MODEL_OR_PLAN_CHANGED")
    require(re.fullmatch(r"[0-9a-f]{64}", plan_sha or "") and
            plan_path.resolve().is_relative_to((source_root / PRODUCT).resolve()) and
            not plan_path.is_symlink() and sha(plan_path) == plan_sha,
            "V13_NEW_PLAN_EXPLICIT_SHA_AND_OWNED_PATH_REQUIRED")
    require(callable(getattr(policy, "right_burst_factory", None)) and
            all(callable(getattr(protocol, n, None)) for n in
                ("load_plan", "derive_cohort", "paired_physical_goal_readout")),
            "V13_EXACT_PRODUCT_API_MISMATCH")
    require(plan_sha == REVIEWED_PLAN_SHA, "V13_UNREVIEWED_NEW_PLAN_REFUSED")
    plan = protocol.load_plan(plan_path)
    validate_plan_contract(plan)
    return model, plan


def validate_plan_contract(plan):
    require(plan["strategies"] == list(ARMS) and plan["expectedTrials"] == EXPECTED and
            plan["trainSeedRangeInclusive"] == [FIRST, FIRST + SCAN - 1] and
            plan["modelPromotionAuthorized"] is False and
            plan["devCalTestOodOpened"] is False and
            set(plan["trialFields"]) == set(PROTOCOL_FIELDS),
            "V13_PRODUCT_PLAN_CONTRACT_MISMATCH")
    require(plan["contactGoal"]["minimumActualContactDwellTicks"] == 250,
            "V13_ORIGINAL_V7_GOAL_MINIMUM_250_TICKS_REQUIRED")


PROTOCOL_FIELDS = ("seed", "world_hash", "strategy", "success", "unsafe", "abstained",
                   "contact_dwell_ticks", "contacts", "final_error_m")


def protocol_trials(trials):
    # Explicit compact product ABI. Lossless original rows remain unmodified.
    return [{**{key: r[key] for key in PROTOCOL_FIELDS[:6]},
             "contact_dwell_ticks": r["terminal_dwell_ticks"],
             "contacts": r["contacts"], "final_error_m": r["final_error"]}
            for r in trials]


def original_factories(source_root, stage, v13_policy):
    original = load_module(source_root / PHYSICS / "v10_prospective/run.py",
                           "v13_verified_frozen_v10_prospective_source")
    original.verify_historical_source(source_root)
    v7, Env = original.v8.import_v7_and_physics()
    frozen_v8, _, _ = original.v8.verify_frozen_model(
        stage["weights.json"], stage["training-receipt.json"],
        original.v8.FROZEN_WEIGHTS_SHA256)
    frozen_v5 = original.policy_factory(
        "frozen_v5", stage["candidate-weights.json"], frozen_v8, frozen_v7=v7)
    require(sha(source_root / V12_PRODUCT / "policy.py") ==
            "bd748f604dafbc6e0d3d59e0a5b7e08dab5e9e8ed010a13053f1417a32fd6fc6",
            "V13_FROZEN_V12_POLICY_SHA_CHANGED")
    v12_policy = load_module(source_root / V12_PRODUCT / "policy.py",
                             "v13_frozen_v12_policy")
    model = source_root / MODEL
    return ({ARMS[0]: frozen_v5,
             ARMS[1]: v12_policy.policy_factory(frozen_v5, model),
             ARMS[2]: v13_policy.right_burst_factory(frozen_v5, model, burst_length=2),
             ARMS[3]: v13_policy.right_burst_factory(frozen_v5, model, burst_length=4)},
            original.v8, v7, Env, v7.v6.v5.v4.v3.v2.v1._world_signature)


def verify_preflight(path):
    require(Path(path).is_file() and not Path(path).is_symlink() and
            sha(path) == PREFLIGHT_SHA, "V13_KNOWN_PREFLIGHT_SHA_REQUIRED")
    doc = json.loads(Path(path).read_text())
    require(doc["new_training_range"] == [FIRST, FIRST + SCAN - 1] and
            doc["near_count"] == 178 and doc["clear_count"] == 334 and
            doc["engine"] == "mujoco3.3.7" and doc["input_dim"] == 18 and
            doc["public_mask_count"] == 7 and
            doc["distinct_512_world_signatures"] == 512 and
            doc["model_promotion_authorized"] is False and
            doc["no_dev_cal_test_ood"] is True,
            "V13_PREFLIGHT_CONTRACT_CHANGED")
    return doc


def verify_public_preflight(scans, cohort, survey):
    require(len({w["world_hash"] for w in scans}) == SCAN and
            sum(abs(w["observation"][7]) < .122 for w in scans) == 178 and
            [{"seed": w["seed"], "near": w["observed_corridor"]} for w in cohort] ==
            [{"seed": w["seed"], "near": w["near"]}
             for w in survey["selected_first40_near8_clear"]] and
            portable_scan_digest(scans) == PORTABLE_PREFLIGHT_SHA,
            "V13_FRESH_PUBLIC_WORLDS_DIFFER_FROM_KNOWN_PREFLIGHT")


def portable_scenario_digest(env):
    """Compare latent reset identity at 12 decimal places, never policy input."""
    def rounded(value):
        value = float(value)
        require(np.isfinite(value), "V13_NONFINITE_PORTABLE_SCENARIO")
        return round(value, 12)

    def integer(value):
        result = int(value)
        require(not isinstance(value, (bool, np.bool_)) and result == value,
                "V13_NONINTEGER_PORTABLE_SCENARIO")
        return result

    return digest({"initial_x": rounded(env.data.qpos[0]),
                   "initial_y": rounded(env.data.qpos[1]),
                   "mass": rounded(env.model.body_mass[env.obj]),
                   "friction": rounded(env.model.geom_friction[env.og, 0]),
                   "obstacle_y": rounded(env.model.geom_pos[env.bg, 1]),
                   "amplitude": rounded(env.amplitude),
                   "frequency": rounded(env.frequency),
                   "phase": rounded(env.phase),
                   "drop_start": integer(env.drop_start),
                   "drop_len": integer(env.drop_len),
                   "deadman_release": integer(env.release)})


def portable_scan_digest(scans):
    """Bind ordered seeds, near labels, scenario digests and full public ABI."""
    return digest([{"seed": row["seed"],
                    "near": bool(abs(float(row["observation"][7])) < .122),
                    "portable_scenario_sha256": row["portable_scenario_sha256"],
                    "public_state_sha256": digest({"observation": row["observation"],
                                                   "mask": row["mask"]})}
                   for row in scans])


def scan_real_public_starts(env, signature):
    result = []
    for seed in range(FIRST, FIRST + SCAN):
        obs = env.reset(seed=seed, ood=False)
        mask = env.mask(obs)
        require(np.asarray(obs).shape == (18,) and
                np.asarray(mask).shape == (7,) and
                np.all(np.isfinite(obs)), "V13_ONLY_REAL_FINITE_PUBLIC_18D_AND_SEVEN_MASK")
        result.append({"seed": seed, "world_hash": str(signature(env)),
                       "portable_scenario_sha256": portable_scenario_digest(env),
                       "observation": np.asarray(obs).tolist(),
                       "mask": np.asarray(mask, dtype=int).tolist()})
    return result


def independent_first_public_cohort(scans, cohort):
    """Defend even if a future product protocol accidentally accepts a forged plan."""
    require(len(scans) == SCAN and
            [row["seed"] for row in scans] == list(range(FIRST, FIRST + SCAN)),
            "V13_INDEPENDENT_ONLY_CANONICAL_519024_512_PUBLIC_SEEDS")
    near, clear = [], []
    for row in scans:
        obs = row["observation"]
        mask = row["mask"]
        require(len(obs) == 18 and len(mask) == 7 and
                all(type(x) in (int, float) and np.isfinite(x) for x in obs) and
                all(type(bit) is int and bit in (0, 1) for bit in mask) and
                any(mask) and re.fullmatch(r"[0-9a-f]{64}", row["world_hash"]) is not None,
                "V13_INDEPENDENT_FINITE_PUBLIC_18D_7MASK_SHA_WORLD_REQUIRED")
        record = {"seed": row["seed"], "world_hash": row["world_hash"],
                  "initial_public_obstacle_y": obs[7], "initial_mask": mask,
                  "observed_corridor": abs(obs[7]) < .122}
        if record["observed_corridor"] and len(near) < 40:
            near.append(record)
        elif not record["observed_corridor"] and len(clear) < 8:
            clear.append(record)
    require(len(near) == 40 and len(clear) == 8 and
            cohort == sorted([*near, *clear], key=lambda row: row["seed"]),
            "V13_INDEPENDENT_FIRST40_NEAR8_CLEAR_CANNOT_BE_FORGED")
    return True


def save_json_fresh(path, value):
    with path.open("xb") as out:
        out.write(canonical(value) + b"\n")


def safe_goal(row):
    return bool(row["success"] is True and row["unsafe"] is False and
                row["abstained"] is False and row.get("contacts", 0) > 0 and
                0 <= row.get("final_error", float("inf")) < .02 and
                row.get("terminal_dwell_ticks", 0) >= 250)



def validate_returned_episode(row, trace, world, arm, scan):
    """Reject invalid producer terminal evidence before selecting next episode."""
    # Fail on NaN/Infinity or unsupported JSON values anywhere in evidence.
    canonical({"row": row, "transitions": trace})
    require(type(row) is dict and type(trace) is list and len(trace) > 0 and
            row.get("seed") == world["seed"] and row.get("strategy") == arm and
            row.get("world_hash") == world["world_hash"] and
            near(trace[0]["observation"], scan[world["seed"] - FIRST]["observation"]),
            "V13_PAIRED_ACTUAL_REAL_PUBLIC_WORLD_SOURCE_CHANGED")
    require(all(type(row.get(k)) is bool for k in ("success", "unsafe", "abstained")) and
            all(type(row.get(k)) is int and row[k] >= 0 for k in
                ("contacts", "dwell_ticks_final", "option_steps", "full_transition_count")) and
            type(row.get("final_error")) in (int, float) and np.isfinite(row["final_error"]) and
            row["final_error"] >= 0 and
            row["option_steps"] == row["full_transition_count"] == len(trace) and
            row.get("full_transition_sha256") == digest(trace),
            "V13_INVALID_TERMINAL_ROW")
    last = trace[-1]
    require(type(last) is dict and last.get("done") is True and
            type(last.get("dwell_ticks_current")) is int and
            last["dwell_ticks_current"] == row["dwell_ticks_final"] and
            type(last.get("contacts_cumulative")) is int and
            last["contacts_cumulative"] == row["contacts"] and
            type(last.get("success_info")) is bool and
            last["success_info"] == row["success"],
            "V13_TERMINAL_TRACE_ROW_MISMATCH")
    physical = (row["contacts"] > 0 and row["dwell_ticks_final"] >= 250 and
                row["final_error"] < .02 and not row["unsafe"] and not row["abstained"])
    require(row["success"] == physical, "V13_CONTRADICTORY_TRUE_GOAL")
    require(all(type(t) is dict and type(t.get("mask")) is list and len(t["mask"]) == 7 and
                all(type(bit) is int and bit in (0, 1) for bit in t["mask"]) and
                type(t.get("action")) is int and 0 <= t["action"] < 7 and
                t["mask"][t["action"]] == 1 and
                type(t.get("cost")) is int and t["cost"] >= 0 for t in trace),
            "V13_ORIGINAL_ILLEGAL_ACTION_STOP")
    require(not any(t["cost"] > 0 for t in trace) or row["unsafe"],
            "V13_UNSAFE_FLAG_COST_CONTRADICTION")


def save_quarantine(private, seed, arm, row, trace):
    """Retain the rejected producer result including non-finite float spellings."""
    value = {"schema": SCHEMA + ".quarantine", "expected_seed": seed,
             "expected_strategy": arm, "returned_row": row, "returned_trace": trace}
    # No canonical JSON: NaN and Infinity must remain observable on rejection.
    # This is forensic data only and is never accepted as a scientific trial.
    with (private / "quarantine.json").open("x", encoding="utf8") as out:
        json.dump(value, out, sort_keys=True, allow_nan=True, default=repr)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())


def source_bound_burst_right4_instances(seed, strategy, trace, modes):
    """Only policy-active RIGHT4 bursts count, never incidental frozen-V5 action4.

    Modes are execution-controller provenance, never a model input. Every
    producer mode is reproduced by an independent source-pinned policy replay
    against the full original public 18D observations and seven-action masks.
    """
    require(strategy in ARMS[2:] and type(modes) is list and
            len(modes) == len(trace) and len(trace) > 0,
            "V13_BURST_MODE_HISTORY_MISSING_OR_INCOMPLETE")
    observed = []
    for index, (step, mode) in enumerate(zip(trace, modes)):
        require(type(mode) is str and
                mode in ("frozen_v5", "UNTRAINED_RIGHT4_EXPLORATION_ONLY") and
                type(step) is dict and type(step.get("action")) is int and
                type(step.get("mask")) is list and len(step["mask"]) == 7 and
                all(type(x) is int and x in (0, 1) for x in step["mask"]) and
                0 <= step["action"] < 7 and step["mask"][step["action"]] == 1,
                "V13_BURST_MODE_OR_ORIGINAL_PUBLIC_SEVEN_MASK_INVALID")
        if mode == "UNTRAINED_RIGHT4_EXPLORATION_ONLY":
            require(step["action"] == 4 and step["mask"][4] == 1,
                    "V13_BURST_MODE_REQUIRES_ACTUALLY_EXECUTED_LEGAL_ACTION4")
            observed.append({"seed": seed, "strategy": strategy,
                             "option_index": index,
                             "original_seven_mask": list(step["mask"])})
    return observed


def stop_after(row, baseline):
    if row["unsafe"]:
        return "OBSERVED_UNSAFE_ACTUAL_MUJOCO_COST"
    if row["strategy"] != ARMS[0] and baseline is not None and safe_goal(baseline) and not safe_goal(row):
        return "NONBASELINE_LOST_ACTUAL_FROZEN_V5_GOAL"
    return None


def independent_science_gate(rows, original_burst_right4_instances):
    """A real burst action4 must occur in the SAME arm/world as a novel goal."""
    losses = [r["seed"] for r in rows.values() if
              r["strategy"] != ARMS[0] and safe_goal(rows[r["seed"], ARMS[0]]) and
              not safe_goal(r)]
    unsafe = [r["seed"] for r in rows.values() if r["unsafe"]]
    burst_novel = {(r["seed"], r["strategy"]) for r in rows.values() if
                   r["strategy"] in ARMS[2:] and safe_goal(r) and
                   not safe_goal(rows[r["seed"], ARMS[0]])}
    require(type(original_burst_right4_instances) is list and
            all(type(item) is dict and
                (item.get("seed"), item.get("strategy")) in rows and
                item.get("strategy") in ARMS[2:] and
                type(item.get("option_index")) is int and
                item["option_index"] >= 0 and
                type(item.get("original_seven_mask")) is list and
                len(item["original_seven_mask"]) == 7 and
                all(type(x) is int and x in (0, 1) for x in item["original_seven_mask"]) and
                item["original_seven_mask"][4] == 1
                for item in original_burst_right4_instances),
            "V13_UNTRUSTED_BURST_RIGHT4_SCIENCE_GATE_INSTANCES")
    burst_observed = {(item["seed"], item["strategy"])
                      for item in original_burst_right4_instances}
    return ("STOP_UNSAFE_LOST_ZERO_NOVEL_OR_NO_ACTUAL_RIGHT4_DATA"
            if losses or unsafe or not (burst_novel & burst_observed)
            else "TRAIN_ONLY_SCIENCE_HYPOTHESIS_REQUIRES_NEW_REVIEW")


def run_pilot_originals(source_root, private, model, plan, policy, protocol,
                        factories, v8, v7, Env, signature, source_sha,
                        seconds=900, survey=None):
    """Original producer: completed rows only, immutable full raw stream."""
    require(not private.exists(), "V13_PRIVATE_ORIGINAL_OUTPUT_ALREADY_EXISTS")
    private.mkdir(mode=0o700, parents=True, exist_ok=False)
    env = Env(max_options=v8.MAX_OPTIONS)
    scan = scan_real_public_starts(env, signature)
    cohort = protocol.derive_cohort(scan, plan)
    independent_first_public_cohort(scan, cohort)
    verify_public_preflight(scan, cohort, survey)
    require(len(cohort) == 48 and sum(w["observed_corridor"] for w in cohort) == 40 and
            len({w["seed"] for w in cohort}) == 48,
            "V13_PUBLIC_FIRST_40_NEAR_8_CLEAR_COHORT_DRIFT")
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
                        # V8 constructs one controller via factory() per episode.
                        # Capture that exact controller only for burst-mode audit.
                        burst_controller = factories[arm]() if arm in ARMS[2:] else None
                        episode_factory = ((lambda controller=burst_controller: controller)
                                           if burst_controller is not None else factories[arm])
                        row, trace = v8.run_real_episode(
                            env, world["seed"], arm, episode_factory,
                            signature, deadline, v7)
                    except TimeoutError:
                        stop_reason = "TIME_BUDGET_EXCEEDED_DURING_EPISODE"
                        break
                    try:
                        validate_returned_episode(row, trace, world, arm, scan)
                        if arm in ARMS[2:]:
                            modes = getattr(burst_controller, "mode_history", None)
                            burst_instances = source_bound_burst_right4_instances(
                                world["seed"], arm, trace, modes)
                            row["source_policy_mode_history"] = list(modes)
                        else:
                            burst_instances = []
                    except Exception:
                        save_quarantine(private, world["seed"], arm, row, trace)
                        raise
                    # Only fully validated source rows enter the canonical trial stream.
                    row.update(terminal_dwell_ticks=trace[-1]["dwell_ticks_current"],
                               observed_corridor=world["observed_corridor"],
                               initial_observed_obstacle_y=world["initial_public_obstacle_y"])
                    trials.append(row)
                    gz.write(canonical({"seed": world["seed"], "strategy": arm,
                                        "transitions": trace}).decode() + "\n")
                    gz.flush()
                    if arm == ARMS[0]:
                        baseline = row
                    stop_reason = stop_after(row, baseline)
                    if any(t["cost"] > 0 for t in trace):
                        stop_reason = "OBSERVED_UNSAFE_ACTUAL_MUJOCO_COST"
                    if arm in ARMS[2:]:
                        right4.extend(burst_instances)
                    if stop_reason:
                        break
                if stop_reason:
                    break
    except Exception as exc:
        # A fatal runtime exception cannot be treated as scientific success.
        # The class-only failure code (no private error payload) is retained
        # alongside completed raw traces and a nonzero INCOMPLETE job status.
        stop_reason = "SOURCE_OR_PHYSICS_EXCEPTION_UNQUALIFIED_" + type(exc).__name__
    if not stop_reason:
        try:
            require(len(trials) == EXPECTED, "V13_MISSING_REAL_EPISODES")
            readout = protocol.paired_physical_goal_readout(
                protocol_trials(trials), cohort, all_512_initial_public_worlds=scan, plan=plan)
        except Exception as exc:
            stop_reason = "SOURCE_READOUT_EXCEPTION_UNQUALIFIED_" + type(exc).__name__
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
            "plan_sha256": PLAN_SHA, "preflight_sha256": PREFLIGHT_SHA, "training_only": True,
            "raw_sha256": {
                name: sha(private / name)
                for name in (("partial_training.json", "full_transitions.jsonl.gz") +
                             (("quarantine.json",) if (private / "quarantine.json").exists() else ()))},
            "promotion_authorized": False, "dev_cal_test_ood_opened": False})
        return {"complete": False, "reason": stop_reason,
                "completed_episodes": len(trials)}
    training = {"schema": SCHEMA + ".training", "executed_head": source_sha,
                "training_only": True, "actual_physics_engine": "mujoco-3.3.7",
                "all_512_public_initial_scans": scan, "cohort": cohort,
                "strategies": list(ARMS), "trials": trials,
                "actual_trials": len(trials),
                "actual_option_transitions": sum(r["full_transition_count"] for r in trials),
                "model_sha256": MODEL_SHA, "plan_sha256": PLAN_SHA, "preflight_sha256": PREFLIGHT_SHA,
                "observed_exploration_action4_executions": len(right4),
                "observed_exploration_action4_instances": right4,
                "no_dev_test_ood": True, "model_promotion_authorized": False}
    save_json_fresh(private / "training.json", training)
    save_json_fresh(private / "paired-readout.json", readout)
    manifest = {"schema": SCHEMA + ".manifest", "executed_head": source_sha,
                "training_only": True, "model_sha256": MODEL_SHA,
                "plan_sha256": PLAN_SHA, "preflight_sha256": PREFLIGHT_SHA, "actual_trials": len(trials),
                "actual_option_transitions": training["actual_option_transitions"],
                "original_v10_source_sha": V10_SHA, "promotion_authorized": False,
                "dev_cal_test_ood_opened": False,
                "file_sha256": {name: sha(private / name) for name in (
                    "training.json", "full_transitions.jsonl.gz", "paired-readout.json")}}
    save_json_fresh(private / "manifest.json", manifest)
    return {"complete": True, "right4_executions": len(right4),
            "source_preliminary_readout": readout}


def verify_full_originals(private, source_sha, protocol, plan, v7, survey):
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
            training["preflight_sha256"] == manifest["preflight_sha256"] == PREFLIGHT_SHA and
            set(manifest["file_sha256"]) ==
            {"training.json", "full_transitions.jsonl.gz", "paired-readout.json"},
            "V13_EXACT_COMPLETE_ORIGINAL_REAL_PILOT_SCHEMA_MISMATCH")
    for name, expected in manifest["file_sha256"].items():
        require((private / name).is_file() and not (private / name).is_symlink()
                and (private / name).stat().st_size <= 32 * 1024 * 1024
                and sha(private / name) == expected,
                "V13_THREE_COMPLETE_ORIGINAL_FILE_SHA_MISMATCH")
    scans = training["all_512_public_initial_scans"]
    cohort = protocol.derive_cohort(scans, plan)
    independent_first_public_cohort(scans, cohort)
    verify_public_preflight(scans, cohort, survey)
    require(training["cohort"] == cohort and len(cohort) == 48 and
            sum(w["observed_corridor"] for w in cohort) == 40,
            "V13_PUBLIC_512_FIRST40_NEAR8_CLEAR_SELECTION_NOT_REPRODUCIBLE")
    require([(r["seed"], r["strategy"]) for r in training["trials"]] ==
            [(w["seed"], a) for w in cohort for a in ARMS],
            "V13_BASELINE_FIRST_EXACT_PAIRED_ORDER_REQUIRED")
    rows = {(r["seed"], r["strategy"]): r for r in training["trials"]}
    require(len(rows) == EXPECTED and
            set(rows) == {(world["seed"], arm) for world in cohort for arm in ARMS},
            "V13_ORIGINAL_192_COMPLETE_PAIRED_WORLD_STRATEGIES_MISSING")
    for world in cohort:
        baseline = rows[world["seed"], ARMS[0]]
        require(all(stop_after(rows[world["seed"], arm], baseline) is None for arm in ARMS),
                "V13_COMPLETE_RUN_IGNORED_IMMEDIATE_STOP")
    original_readout = protocol.paired_physical_goal_readout(
        protocol_trials(training["trials"]), cohort,
        all_512_initial_public_worlds=scans, plan=plan)
    require(readout == original_readout and
            training["actual_option_transitions"] ==
            manifest["actual_option_transitions"] ==
            sum(r["full_transition_count"] for r in training["trials"]),
            "V13_ORIGINAL_GOAL250_PAIRED_SCIENCE_OR_TRANSITION_COUNTS_DRIFT")
    return training, manifest, readout, rows


def independent_true_physics_replay(private, training, rows, factories, v7,
                                    Env, signature):
    """Replay ALL 192 completed episodes, every legal action and every step."""
    env = Env(max_options=60)
    for frame in training["all_512_public_initial_scans"]:
        obs = env.reset(seed=frame["seed"], ood=False)
        require(near(obs, frame["observation"]) and
                [int(bit) for bit in env.mask(obs)] == frame["mask"] and
                signature(env) == frame["world_hash"] and
                portable_scenario_digest(env) == frame["portable_scenario_sha256"],
                "V13_INDEPENDENT_MUJOCO_ALL512_INITIAL_PUBLIC_WORLDS_NOT_REPRODUCED")
    seen = set()
    ordered = iter((w["seed"], a) for w in training["cohort"] for a in ARMS)
    action4 = []
    replay_near, replay_clear = 0, 0
    physics_options = 0
    with gzip.open(private / "full_transitions.jsonl.gz", "rt",
                   encoding="utf8") as source:
        for line in source:
            require(len(line) < 2 * 1024 * 1024 and len(seen) < EXPECTED,
                    "V13_FULL_RAW_OPTION_TRACE_MISSING_OR_OVERSIZED")
            doc = json.loads(line)
            key = (doc["seed"], doc["strategy"])
            require(key == next(ordered) and key in rows and key not in seen,
                    "V13_UNREGISTERED_OR_DUPLICATE_REAL_RAW_STRATEGY_ROW")
            seen.add(key)
            row, transitions = rows[key], doc["transitions"]
            require(len(transitions) == row["option_steps"] ==
                    row["full_transition_count"] and
                    digest(transitions) == row["full_transition_sha256"] and
                    [transitions[i] for i in v7.sparse_indices(len(transitions))] ==
                    row["transitions"],
                    "V13_FULL_RAW_SPARSE_AND_SHA_ORIGINALS_INCONSISTENT")
            observation = env.reset(seed=doc["seed"], ood=False)
            require(signature(env) == row["world_hash"] and
                    near(observation, transitions[0]["observation"]),
                    "V13_INDEPENDENT_INITIAL_PAIRED_MUJOCO_WORLD_DRIFT")
            controller = factories[key[1]]()
            max_dwell = 0
            last = None
            for index, t in enumerate(transitions):
                v7.validate_transition(t)
                require(near(observation, t["observation"]),
                        "V13_INDEPENDENT_PHYSICS_18D_PRESTATE_NOT_REPRODUCED")
                mask = env.mask(observation)
                require([int(x) for x in mask] == t["mask"] and
                        mask[t["action"]] and
                        len(mask) == 7,
                        "V13_INDEPENDENT_ALL_SEVEN_ACTION_MASKS_NOT_ORIGINAL")
                action = controller(observation.copy(), mask.copy())
                require(type(action) is int and action == t["action"],
                        "V13_SOURCE_FROZEN_POLICY_ACTION_NOT_REPRODUCED")
                observation, reward, done, info = env.step(action)
                max_dwell = max(max_dwell, int(env.dwell))
                require(near(observation, t["next_observation"]) and
                        abs(float(reward) - float(t["reward"])) < 1e-5 and
                        int(info["cost"]) == t["cost"] == 0 and
                        int(info["contacts"]) == t["contacts_cumulative"] and
                        bool(info["success"]) == t["success_info"] and
                        bool(done) == t["done"] and
                        max_dwell == t["dwell_ticks_cumulative"] and
                        int(env.dwell) == t["dwell_ticks_current"] and
                        (not done or index == len(transitions) - 1),
                        "V13_INDEPENDENT_EVERY_REAL_PHYSICS_TRANSITION_DIVERGED")
                last = info
                physics_options += 1
            if key[1] in ARMS[2:]:
                replay_modes = getattr(controller, "mode_history", None)
                require(type(replay_modes) is list and
                        replay_modes == row.get("source_policy_mode_history"),
                        "V13_INDEPENDENT_SOURCE_POLICY_BURST_MODE_HISTORY_NOT_REPRODUCED")
                action4.extend(source_bound_burst_right4_instances(
                    doc["seed"], key[1], transitions, replay_modes))
            else:
                require("source_policy_mode_history" not in row,
                        "V13_NONBURST_CANNOT_CLAIM_BURST_MODE_HISTORY")
            require(last is not None and env.done and
                    int(env.dwell) == row["terminal_dwell_ticks"] and
                    bool(last["success"]) == row["success"] and
                    bool(last["unsafe"]) == row["unsafe"] and
                    bool(last["abstained"]) == row["abstained"] and
                    int(env.steps) == row["option_steps"] and
                    int(env.physics_steps) == row["physics_steps"] and
                    int(env.contacts) == row["contacts"] and
                    abs(float(last["error"]) - float(row["final_error"])) < 1e-5 and
                    (not row["success"] or
                     (int(env.dwell) >= 250 and int(env.contacts) > 0 and
                      float(last["error"]) < .02 and
                      not row["unsafe"] and not row["abstained"])),
                    "V13_INDEPENDENT_COMPLETE_TERMINAL_MUJOCO_250TICK_GOAL_DRIFT")
            if safe_goal(row):
                if row["observed_corridor"]:
                    replay_near += 1
                else:
                    replay_clear += 1
    require(len(seen) == EXPECTED and seen == set(rows) and
            physics_options == training["actual_option_transitions"] and
            action4 == training["observed_exploration_action4_instances"] and
            len(action4) == training["observed_exploration_action4_executions"],
            "V13_INDEPENDENT_192_PHYSICS_OR_ORIGINAL_RIGHT4_PROBE_TRACE_MISSING")
    return {"schema": SCHEMA + ".independent-physics",
            "exact_real_full_options_replayed": physics_options,
            "all_512_public_initial_worlds_replayed": True,
            "all_192_complete_real_episodes_replayed": True,
            "real_safe_near_goal_trajectories_replayed": replay_near,
            "real_safe_clear_goal_trajectories_replayed": replay_clear,
            "untrained_right4_actual_legal_executions": len(action4),
            "untrained_right4_actual_legal_instances": action4,
            "original_exploration_option4_instances_sha256": digest(action4),
            "claim_verified": True, "training_only": True,
            "promotion_authorized": False, "dev_cal_test_ood_opened": False}


def admission(env, now, stage="full"):
    # The job has a hard 60-minute timeout. Reserve two hours before starting
    # originals so the separate qualifier can still satisfy its unchanged
    # one-hour admission gate even if originals occupy the entire job window.
    require(stage in ("full", "original", "qualify"), "V13_INVALID_STAGE")
    reserve = 3600 if stage == "qualify" else 7200
    require(env.get("CRACI_WORKLOAD") == "rokoko-mujoco-v13-pilot" and
            env.get("CRACI_CREDIT_WINDOW_OPEN") == "true" and
            float(env.get("CRACI_CREDIT_REMAINING_SECONDS", "0")) >= reserve and
            now + reserve <= CUTOFF and
            env.get("CRACI_MANUAL_SOURCE_REVIEWED") == "true",
            "V13_MANUAL_REVIEW_CREDIT_CUTOFF_STAGE_RESERVE_REQUIRED")


def main():
    global PLAN_SHA
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("full", "original", "qualify"), default="full")
    args = parser.parse_args()
    admission(os.environ, time.time(), args.stage)
    source_root = Path(os.environ["CRACI_SOURCE_ROOT"]).resolve(strict=True)
    harness_root = Path(os.environ["CRACI_HARNESS_ROOT"]).resolve(strict=True)
    receipt = Path(os.environ["CRACI_RECEIPT_DIR"]).resolve(strict=True)
    expected = os.environ["CRACI_SOURCE_SHA"]
    harness_sha = os.environ["CRACI_HARNESS_SHA"]
    git_head_clean(source_root, expected)
    git_head_clean(harness_root, harness_sha, product=False)
    require(Path(__file__).resolve() == (harness_root / "scripts/craci/rokoko-mujoco-v13-original-qualification.py").resolve(),
            "V13_RUNNING_SCRIPT_MUST_BE_PINNED_HARNESS_BYTES")
    PLAN_SHA = os.environ["CRACI_V13_PLAN_SHA256"]
    survey = verify_preflight(Path(os.environ["CRACI_V13_PREFLIGHT_PATH"]))
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    require(all(not path.is_relative_to(repo) and not repo.is_relative_to(path)
                for path in (runner_temp, receipt) for repo in (source_root, harness_root)),
            "V13_PRIVATE_RAW_AND_COLLECTOR_MUST_BE_OUTSIDE_SOURCE_CHECKOUTS")
    py = runner_temp / "mujoco-venv/bin/python"
    require(py.is_file(), "V13_PINNED_NORMAL_PYTHON_VENV_SYMLINK_SUPPORTED")
    import mujoco
    require(mujoco.__version__ == "3.3.7" and np.__version__ == "2.3.4" and
            sys.prefix != sys.base_prefix, "V13_ACTIVE_INTERPRETER_VERSION_REQUIRED")
    subprocess.run([str(py), "-B", "-c",
                    "import mujoco,numpy,sys;"
                    "assert mujoco.__version__=='3.3.7';"
                    "assert numpy.__version__=='2.3.4';"
                    "assert sys.prefix!=sys.base_prefix"],
                   cwd=source_root, check=True)
    product = source_root / PRODUCT
    policy = load_module(product / "policy.py", "v13_product_policy_unique")
    protocol = load_module(product / "protocol.py", "v13_product_protocol_unique")
    model, plan = original_plan_and_model(
        source_root, policy, protocol,
        source_root / os.environ["CRACI_V13_PLAN_PATH"], PLAN_SHA)
    stage = stage_frozen_models(
        source_root, runner_temp / ("v13-" + args.stage + "-private-frozen-models"))
    factories, v8, v7source, Env, signature = original_factories(
        source_root, stage, policy)
    private = runner_temp / "v13-pilot-519024-private-originals"
    packer = load_module(
        harness_root / "scripts/craci/rokoko-mujoco-v13-original-retain-evidence.py",
        "v13_lossless_private_packer")
    collector = receipt / "artifacts" / "rokoko-mujoco-v13-original"
    if args.stage != "qualify":
        result = run_pilot_originals(
            source_root, private, model, plan, policy, protocol,
            factories, v8, v7source, Env, signature, expected, survey=survey)
        if not result["complete"]:
            try:
                packer.publish_early_stop(private, collector)
            except Exception as exc:
                save_json_fresh(private / "failure.json", {
                    "schema": SCHEMA + ".qualification-failure", "executed_head": expected,
                    "harness_head": harness_sha, "reason": type(exc).__name__,
                    "promotion_authorized": False})
                packer.publish_failure(private, collector)
            return 3
        if args.stage == "original":
            print(json.dumps({"status": "ORIGINALS_ONLY_UNQUALIFIED", "promotion_authorized": False}))
            return 0
        # Separate interpreter reloads exact source and private originals; no producer booleans qualify it.
        code = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()),
                               "--stage", "qualify"], cwd=source_root).returncode
        if code and not collector.exists():
            if not (private / "failure.json").exists():
                save_json_fresh(private / "failure.json", {
                    "schema": SCHEMA + ".qualification-failure", "executed_head": expected,
                    "harness_head": harness_sha, "reason": "QUALIFIER_PROCESS_FAILED",
                    "promotion_authorized": False})
            packer.publish_failure(private, collector)
        return code
    v7 = load_module(
        harness_root / "scripts/craci/rokoko-mujoco-v7-feasibility-qualification.py",
        "v13_original_v7_unmodified_real_trace_validator")
    try:
        training, manifest, readout, rows = verify_full_originals(
            private, expected, protocol, plan, v7, survey)
        replay = independent_true_physics_replay(
            private, training, rows, factories, v7, Env, signature)
        git_head_clean(source_root, expected)
        git_head_clean(harness_root, harness_sha, product=False)
    except Exception as exc:
        save_json_fresh(private / "failure.json", {
            "schema": SCHEMA + ".qualification-failure", "executed_head": expected,
            "harness_head": harness_sha, "reason": type(exc).__name__,
            "promotion_authorized": False})
        packer.publish_failure(private, collector)
        return 4
    # RIGHT4 must be actually emitted under the *original* mask. The probe
    # never trains a right4 transition model and never permits promotion.
    # Compute science independently from terminal physics, never producer scores.
    science = independent_science_gate(rows, replay["untrained_right4_actual_legal_instances"])
    qualified = {"schema": SCHEMA + ".independent-qualification",
                 "executed_head": expected, "harness_head": harness_sha,
                 "experiment_complete": True, "actual_trials": EXPECTED,
                 "actual_option_transitions": training["actual_option_transitions"],
                 "model_sha256": MODEL_SHA, "plan_sha256": PLAN_SHA, "preflight_sha256": PREFLIGHT_SHA,
                 "original_sha256": manifest["file_sha256"],
                 "full_192_real_episode_physics_replay": replay,
                 "science_gate": science, "new_model_promotion_authorized": False,
                 "dev_cal_test_ood_opened": False,
                 "right4_exploration_is_untrained": True}
    save_json_fresh(private / "independent-qualification.json", qualified)
    packed = packer.publish_qualified(private, collector)
    require(packed["original_sha256"] == manifest["file_sha256"] and
            packed["exact_source_sha"] == expected,
            "V13_LOSSLESS_THREE_ORIGINAL_SOURCES_NOT_RETAINED")
    print(json.dumps({"status": "COMPLETE_TRAIN_ONLY", "science": science,
                      "real_episodes": EXPECTED,
                      "real_physics_options_replayed": replay["exact_real_full_options_replayed"],
                      "observed_legal_right4_actions": replay["untrained_right4_actual_legal_executions"],
                      "safe_v5_goals": sum(safe_goal(r) for r in rows.values() if r["strategy"] == ARMS[0]),
                      "safe_v12_goals": sum(safe_goal(r) for r in rows.values() if r["strategy"] == ARMS[1]),
                      "lossless_collector_bytes": packed["collector_bytes"],
                      "promotion_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
