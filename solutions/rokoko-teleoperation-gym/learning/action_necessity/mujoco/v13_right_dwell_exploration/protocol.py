"""Strict preliminary TRAIN evidence accounting; no physics or replay attestation."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("rokoko_v13_burst_policy_protocol", HERE / "policy.py")
if _spec is None or _spec.loader is None:
    raise ImportError("V13_UNIQUE_POLICY_REQUIRED")
_policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_policy)
require, public_abi = _policy.v12.require, _policy.v12.public_abi
PLAN_SHA256 = "93013025c9e19d94911f249f4dbf0cc034c767da23dca0273d8808323c0b173c"
ARMS = ("frozen_v5", "v12_phase_dwell_supported_actions",
        "train_only_right4_burst2", "train_only_right4_burst4")


def _bound_plan(plan):
    require(type(plan) is dict, "V13_PLAN_OBJECT_REQUIRED")
    raw = (json.dumps(plan, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    require(hashlib.sha256(raw).hexdigest() == PLAN_SHA256, "V13_PLAN_SOURCE_CHANGED")
    return plan


def load_plan(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1,
            "V13_PLAN_MISSING_OR_UNSAFE")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == PLAN_SHA256, "V13_PLAN_BYTES_CHANGED")
    plan = _bound_plan(json.loads(raw))
    original = HERE.parent / "v12_learning"
    for filename, key in (("policy.py", "originalV12PolicySha256"),
                          ("frozen-real-train-v10-v11-final/model.json", "originalV12ModelSha256"),
                          ("frozen-real-train-v10-v11-final/next-train-plan.json", "originalV12PlanSha256")):
        require(hashlib.sha256((original / filename).read_bytes()).hexdigest() == plan[key],
                "V13_ORIGINAL_V12_SOURCE_CHANGED")
    return plan


def derive_cohort(all512, plan):
    plan = _bound_plan(plan)
    require(len(all512) == 512 and
            all(type(w["seed"]) is int for w in all512) and
            [w["seed"] for w in all512] == list(range(519024, 519536)),
            "V13_FULL_ORDERED_NEW_TRAIN_SCAN_REQUIRED")
    near, clear, hashes, signatures = [], [], set(), set()
    for world in all512:
        obs, mask = public_abi(world["observation"], world["mask"])
        world_hash = world["world_hash"]
        require(type(world_hash) is str and len(world_hash) == 64 and
                all(c in "0123456789abcdef" for c in world_hash) and world_hash not in hashes,
                "V13_DUPLICATE_OR_INVALID_WORLD_HASH")
        signature = (obs, mask)
        require(signature not in signatures, "V13_REPEATED_PUBLIC_WORLD")
        hashes.add(world_hash)
        signatures.add(signature)
        is_near = abs(obs[7]) < plan["cohort"]["nearAbsPublicObservation7Lt"]
        selected, limit = (near, 40) if is_near else (clear, 8)
        if len(selected) < limit:
            selected.append({"seed": world["seed"], "world_hash": world_hash,
                             "initial_public_obstacle_y": obs[7],
                             "initial_mask": list(mask), "observed_corridor": is_near})
    require(len(near) == 40 and len(clear) == 8, "V13_COHORT_UNDERFILLED")
    return sorted(near + clear, key=lambda w: w["seed"])


def _safe_goal(row):
    require(all(type(row[k]) is bool for k in ("success", "unsafe", "abstained")),
            "V13_BOOLEAN_OUTCOMES_REQUIRED")
    require(type(row["contact_dwell_ticks"]) is int and row["contact_dwell_ticks"] >= 0 and
            type(row["contacts"]) is int and row["contacts"] >= 0 and
            type(row["final_error_m"]) in (float, int) and
            math.isfinite(row["final_error_m"]) and row["final_error_m"] >= 0,
            "V13_ACTUAL_CONTACT_TICK_ERROR_EVIDENCE_REQUIRED")
    safe = (row["contact_dwell_ticks"] >= 250 and row["contacts"] > 0 and
            row["final_error_m"] < .02 and not row["unsafe"] and not row["abstained"])
    require(row["success"] == safe, "V13_FORGED_OR_INCONSISTENT_SUCCESS_FLAG")
    return safe


def paired_physical_goal_readout(trials, cohort, all_512_initial_public_worlds, plan):
    plan = _bound_plan(plan)
    require(cohort == derive_cohort(all_512_initial_public_worlds, plan),
            "V13_COHORT_NOT_INDEPENDENTLY_REDERIVED")
    expected = [(w["seed"], arm, w["world_hash"]) for w in cohort for arm in ARMS]
    require(len(trials) == 192 and
            [(r["seed"], r["strategy"], r["world_hash"]) for r in trials] == expected,
            "V13_ORDERED_V5_FIRST_192_UNIQUE_PAIRED_TRIALS_REQUIRED")
    safe = []
    for row in trials:
        require(set(row) == set(plan["trialFields"]) and type(row["seed"]) is int,
                "V13_TRIAL_SCHEMA_CHANGED")
        safe.append(_safe_goal(row))
    counts = {arm: 0 for arm in ARMS}
    lost = {arm: [] for arm in ARMS[1:]}
    novel = {arm: [] for arm in ARMS[1:]}
    unsafe = {arm: [] for arm in ARMS}
    for i, world in enumerate(cohort):
        offset = i * 4
        for j, arm in enumerate(ARMS):
            row, goal = trials[offset+j], safe[offset+j]
            counts[arm] += int(goal)
            if row["unsafe"]:
                unsafe[arm].append(world["seed"])
            if j:
                if safe[offset] and not goal:
                    lost[arm].append(world["seed"])
                if goal and not safe[offset]:
                    novel[arm].append(world["seed"])
    burst_novel = sorted(set(novel[ARMS[2]] + novel[ARMS[3]]))
    stop = any(lost.values()) or any(unsafe.values()) or not burst_novel
    return {"schema": plan["protocolSchema"], "totalEpisodes": 192,
            "safeGoalsByStrategy": counts, "lostV5GoalsByStrategy": lost,
            "novelSafeGoalsByStrategy": novel, "unsafeByStrategy": unsafe,
            "novelBurstGoalSeeds": burst_novel,
            "hardStopNoFurtherPhysics": bool(stop),
            "scienceDecision": "STOP" if stop else "REVIEW_PRELIMINARY_TRAIN_ONLY",
            "trainingOnly": True, "modelPromotionAuthorized": False,
            "devCalTestOodOpened": False, "independentPhysicsReplayQualified": False,
            "deviceSafeOperationQualified": False}
