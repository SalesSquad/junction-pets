#!/usr/bin/env python3
"""Prospective paired TRAIN-only MuJoCo rollout for a separately frozen V8 policy.

This is NOT model training, development-set evaluation, a safety certificate,
or an auto-promotion gate. Source, prior V7 evidence and frozen-model SHA must
be bound before a fresh 513000+ rollout. No simulator mocks are permitted.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np


HERE = Path(__file__).resolve().parent
MUJOCO_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import run as v8  # noqa: E402; production provenance is checked before simulation


SCHEMA = "junction.rokoko.mujoco-v8.prospective-train.v1"
TRAINER_HEAD = "4b91c64bc1a79bf630b1da6d12bea28e87c2990a"
# The real offline source-verified fit was frozen on this historical HEAD.
# Prospective runner code is a later reviewed descendant and MUST NOT mutate
# or relabel these immutable prior trained weights or training receipt.
FROZEN_WEIGHTS_SHA256 = "9dd1011cd267899da4b9205fb73bdd2f5a8453719b1003351a24a82a2743e0ea"
FROZEN_WEIGHTS_FILE_SHA256 = "07823dcc52ea85b64e18767e1b1af29e63e3236613598cb349610a6b4fd37dc1"
FROZEN_RECEIPT_FILE_SHA256 = "dc22f5538f19ef346d6b9965e7b28beed15e813b4b149ae5711d7dfae1771e73"
TRAIN_FIRST_SEED = 513_000
SELECTION_MAX_SEEDS = 512
TRAIN_LAST_SCAN_SEED = TRAIN_FIRST_SEED + SELECTION_MAX_SEEDS - 1
NEAR_TARGET = 128
CLEAR_TARGET = 32
NEAR_OBSERVED_Y_THRESHOLD = .122
STRATEGIES = ("frozen_v5", "frozen_v6", "repeat_left", "v8_hierarchical")
FROZEN_V7_RUN_FILE_SHA256 = "88b403e5246d2e496cf48a1e405708e6f86e1107d89185ebb615cf6af069f144"
MAX_OPTIONS = 60
MIN_SAFE_LATERAL = .025
MIN_SUCCESS_DWELL_TICKS = 250
EXPECTED_TRIALS = (NEAR_TARGET + CLEAR_TARGET) * len(STRATEGIES)
MAX_CAPTURED_JSON_BYTES = 19 * 1024 * 1024


def validate_train_bounds():
    v8.require(v8.NEXT_TRAIN_SEED_MIN == TRAIN_FIRST_SEED and
               TRAIN_LAST_SCAN_SEED < 520_000 and
               TRAIN_FIRST_SEED > v8.TRAIN_SEED_MAX and
               len(STRATEGIES) == len(set(STRATEGIES)) == 4,
               "V8_PROSPECTIVE_TRAIN_PRE_REGISTRATION_INVALID")


def sha_file(path):
    return v8.file_sha256(path)


def verify_frozen_model(weights_path, receipt_path, reviewed_sha):
    """Production pins real reviewed model AND receipt bytes from trainer HEAD.

    The explicit reviewed_sha MUST additionally agree with immutable code pin.
    No fallback, CLI bypass, retraining or model selection based on new worlds.
    """
    v8.require(reviewed_sha == FROZEN_WEIGHTS_SHA256,
               "V8_REVIEWED_FROZEN_WEIGHTS_SHA_MISMATCH")
    return _frozen_model_contract(weights_path, receipt_path,
                                  TRAINER_HEAD, reviewed_sha,
                                  FROZEN_WEIGHTS_FILE_SHA256,
                                  FROZEN_RECEIPT_FILE_SHA256)


def _frozen_model_contract(weights_path, receipt_path, trainer_head, reviewed_sha,
                           weight_file_sha, receipt_file_sha):
    """Unit-test-only fixture seam. main() uses immutable production digest pins."""
    v8.require(len(reviewed_sha) == 64 and
               all(c in "0123456789abcdef" for c in reviewed_sha),
               "V8_REVIEWED_FROZEN_WEIGHTS_SHA_REQUIRED")
    v8.require(sha_file(weights_path) == weight_file_sha and
               sha_file(receipt_path) == receipt_file_sha,
               "V8_IMMUTABLE_FROZEN_MODEL_OR_RECEIPT_FILE_SHA_MISMATCH")
    frozen = v8.read_json(weights_path)
    receipt = v8.read_json(receipt_path)
    checksum = v8.digest(frozen)
    v8.require(checksum == reviewed_sha == receipt.get("model_weights_sha256") and
               frozen.get("schema") == v8.SCHEMA + ".weights" and
               frozen.get("source_head") == trainer_head and
               receipt.get("executed_head") == trainer_head and
               receipt.get("schema") == v8.SCHEMA + ".receipt" and
               frozen.get("v7_source_head") == v8.V7_SOURCE_SHA and
               frozen.get("v7_training_sha256") == v8.V7_PINNED_FILES["training.json"] and
               frozen.get("v7_full_transitions_sha256") ==
               v8.V7_PINNED_FILES["full_transitions.jsonl.gz"] and
               receipt.get("v7_evidence_dataset_sha256") == v8.V7_DATASET_SHA256 and
               receipt.get("actual_v7_raw_train_transitions") == 68_568 and
               receipt.get("model_weights_frozen") is True and
               receipt.get("dev_cal_test_ood_opened") is False and
               receipt.get("independent_science_qualification") is False and
               receipt.get("deployment_authorized") is False and
               receipt.get("next_fresh_train_seed") == TRAIN_FIRST_SEED and
               frozen.get("model_type") ==
               "four-stage masked-observation linear softmax" and
               frozen.get("feature_count") == v8.FEATURE_COUNT and
               frozen.get("stages") == v8.STAGE_COUNT and
               frozen.get("actions") == v8.ACTION_COUNT and
               frozen.get("seed") == v8.RANDOM_SEED and
               receipt.get("gradient_epochs_per_stage") == v8.EPOCHS,
               "V8_FROZEN_PRIOR_TRAIN_EVIDENCE_MISMATCH")
    weights = np.asarray(frozen["weights"], dtype=np.float64)
    v8.require(weights.shape == (v8.STAGE_COUNT, v8.FEATURE_COUNT, v8.ACTION_COUNT)
               and np.all(np.isfinite(weights)) and np.any(np.abs(weights) > 1e-12),
               "V8_FROZEN_POLICY_SHAPE_OR_ZERO_WEIGHTS")
    return weights, receipt, checksum


def validate_historical_trainer_source(checkout):
    root = str(checkout)
    ancestor = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor",
                               TRAINER_HEAD, "HEAD"], capture_output=True, timeout=15)
    v8.require(ancestor.returncode == 0,
               "V8_PROSPECTIVE_NOT_DESCENDED_FROM_REAL_FROZEN_TRAINER")
    trainer = str((HERE / "run.py").relative_to(checkout))
    original_unchanged = subprocess.run(
        ["git", "-C", root, "diff", "--quiet", TRAINER_HEAD, "HEAD", "--", trainer],
        capture_output=True, timeout=15)
    v8.require(original_unchanged.returncode == 0,
               "V8_PROSPECTIVE_HISTORICAL_TRAINER_BYTES_CHANGED")


def select_train_worlds(env, signature):
    """Deterministic ascending first 128 near/32 clear, solely public first obs.

    Selection cannot observe any result, hidden obstacle, learned model output,
    contact, success or reward. All four policies use the exact same seeds.
    """
    near, clear, scan = [], [], []
    for seed in range(TRAIN_FIRST_SEED, TRAIN_FIRST_SEED + SELECTION_MAX_SEEDS):
        obs = np.asarray(env.reset(seed=seed, ood=False), dtype=np.float64)
        v8.require(obs.shape == (v8.OBSERVATION_COUNT,) and np.all(np.isfinite(obs)),
                   "V8_WORLD_SELECTION_PUBLIC_OBS_INVALID")
        row = {"seed": seed, "world_hash": str(signature(env)),
               "initial_observed_obstacle_y": float(obs[7]),
               "observed_corridor": abs(float(obs[7])) < NEAR_OBSERVED_Y_THRESHOLD}
        scan.append({"seed": seed, "world_hash": row["world_hash"],
                     "initial_observed_obstacle_y": row["initial_observed_obstacle_y"]})
        if row["observed_corridor"] and len(near) < NEAR_TARGET:
            near.append(row)
        elif not row["observed_corridor"] and len(clear) < CLEAR_TARGET:
            clear.append(row)
        if len(near) == NEAR_TARGET and len(clear) == CLEAR_TARGET:
            break
    v8.require(len(near) == NEAR_TARGET and len(clear) == CLEAR_TARGET,
               "V8_FRESH_TRAIN_COHORT_INCOMPLETE")
    return sorted([*near, *clear], key=lambda row: row["seed"]), scan


def paired_plan(cohort):
    v8.require(len(cohort) == NEAR_TARGET + CLEAR_TARGET and
               len({r["seed"] for r in cohort}) == len(cohort) and
               all(TRAIN_FIRST_SEED <= r["seed"] <= TRAIN_LAST_SCAN_SEED
                   for r in cohort), "V8_FRESH_PAIRED_PLAN_BAD_COHORT")
    return [(row, strategy) for row in cohort for strategy in STRATEGIES]


def signed_away(first, last):
    a, b = np.asarray(first, dtype=np.float64), np.asarray(last, dtype=np.float64)
    v8.require(a.shape == b.shape == (v8.OBSERVATION_COUNT,),
               "V8_SIGNED_PUBLIC_LATERAL_ABI")
    sign = -1. if float(a[7]) >= float(a[1]) else 1.
    return (float(b[1]) - float(a[1])) * sign


def direct_side_reopened_forward(mask_before, mask_after, action):
    """A *side option* actually reopens a previously masked forward option."""
    return bool(action in (3, 4) and
                not(mask_before[1] or mask_before[2]) and
                (mask_after[1] or mask_after[2]))


def stage_funnel(transitions, forward_reopen_option_steps=()):
    """Chronological public-observation stage milestones, no latent state.

    The forward-reopen event must follow BOTH first contact and signed >=25 mm
    public lateral progress, and arise after a side option when forwards were
    previously masked. Report raw unsequenced progress independently too.
    """
    v8.require(bool(transitions), "V8_STAGE_FUNNEL_EMPTY_REAL_TRACE")
    reopen_options = set(forward_reopen_option_steps)
    contact = lateral = reopen = None
    any_lateral = False
    any_reopen = False
    for i, transition in enumerate(transitions):
        if contact is None and transition["contacts_cumulative"] > 0:
            contact = i
        is_lateral = signed_away(transitions[0]["observation"],
                                 transition["next_observation"]) >= MIN_SAFE_LATERAL
        any_lateral |= is_lateral
        if contact is not None and lateral is None and is_lateral and i >= contact:
            lateral = i
        did_reopen = (i + 1) in reopen_options
        any_reopen |= did_reopen
        if lateral is not None and reopen is None and did_reopen and i >= lateral:
            reopen = i
    terminal = transitions[-1]
    safe_goal = bool(terminal["success_info"] and terminal["dwell_ticks_current"] >=
                     MIN_SUCCESS_DWELL_TICKS and terminal["cost"] == 0)
    return {"contact": contact is not None,
            "any_signed_lateral25": any_lateral,
            "signed_lateral25_after_contact": lateral is not None,
            "any_forward_reopen_after_side": any_reopen,
            "forward_reopen_after_lateral25": reopen is not None,
            "full_contact_lateral_reopen_goal_dwell": bool(reopen is not None and safe_goal),
            "contact_first_option": None if contact is None else contact + 1,
            "lateral25_first_option": None if lateral is None else lateral + 1,
            "reopen_first_option": None if reopen is None else reopen + 1}


def run_real_episode(env, seed, strategy, factory, signature, deadline, v7):
    controller = factory()
    observed = np.asarray(env.reset(seed=seed, ood=False), dtype=np.float64)
    first_observation = observed.copy()
    world_hash = str(signature(env))
    transitions = []
    last = None
    side_reopens = 0
    last_contacts = 0
    max_dwell = 0
    side_contact_options = []
    forward_reopen_options = []
    side_proposals = 0
    for option in range(MAX_OPTIONS):
        if time.monotonic() >= deadline:
            raise TimeoutError("V8_PROSPECTIVE_REAL_PHYSICS_DEADLINE")
        raw_mask = env.mask(observed)
        # V8's strict mask ABI is applied to ALL policies, not merely itself.
        _, _, allowed = v8.PublicMemory().features(observed, raw_mask)
        action = controller(observed.copy(), allowed.copy())
        v8.require(type(action) is int and 0 <= action < v8.ACTION_COUNT and allowed[action],
                   "V8_PROSPECTIVE_ACTION_VIOLATED_ORIGINAL_SEVEN_SHIELD")
        before = observed.copy()
        observed, reward, done, last = env.step(action)
        observed = np.asarray(observed, dtype=np.float64)
        next_mask = env.mask(observed)
        _, _, next_legal = v8.PublicMemory().features(observed, next_mask)
        reopened = direct_side_reopened_forward(allowed, next_legal, action)
        side_reopens += int(reopened)
        if action in (3, 4):
            side_proposals += 1
            if int(last["contacts"]) > last_contacts:
                side_contact_options.append(option + 1)
        last_contacts = int(last["contacts"])
        max_dwell = max(max_dwell, int(env.dwell))
        if reopened:
            forward_reopen_options.append(option + 1)
        transitions.append({"observation": before.tolist(),
                            "mask": allowed.astype(int).tolist(),
                            "action": action, "reward": float(reward),
                            "cost": int(last["cost"]), "done": bool(done),
                            "contacts_cumulative": last_contacts,
                            "dwell_ticks_current": int(env.dwell),
                            "dwell_ticks_cumulative": max_dwell,
                            "success_info": bool(last["success"]),
                            "next_observation": observed.tolist()})
        if done:
            break
    v8.require(bool(transitions) and last is not None,
               "V8_PROSPECTIVE_NO_REAL_PHYSICS")
    v7.verify_contact_trace(transitions, env.contacts)
    lateral = round(signed_away(first_observation, observed), 8)
    sparse_indices = v7.sparse_indices(len(transitions))
    result = {"seed": seed, "world_hash": world_hash, "strategy": strategy,
              "success": bool(last["success"]), "unsafe": bool(last["unsafe"]),
              "abstained": bool(last["abstained"]),
              "zero_physics_abstain": int(env.physics_steps) == 0,
              "physics_steps": int(env.physics_steps),
              "option_steps": int(env.steps), "contacts": int(env.contacts),
              "side_contact_option_steps": side_contact_options,
              "dwell_ticks_final": int(env.dwell),
              "lateral_displacement": lateral,
              "away_lateral_displacement": round(max(0., lateral), 8),
              "final_error": float(last["error"]),
              "total_reward": round(sum(t["reward"] for t in transitions), 8),
              "side_proposals": side_proposals,
              "forward_reopened_after_side": side_reopens,
              "forward_reopen_option_steps": forward_reopen_options,
              "contact_to_forward_to_dwell": bool(
                  side_contact_options and forward_reopen_options and
                  int(env.dwell) >= MIN_SUCCESS_DWELL_TICKS and bool(last["success"])),
              "full_transition_count": len(transitions),
              "full_transition_sha256": v8.digest(transitions),
              "sparse_trace": True,
              "sparse_transition_indices": sparse_indices,
              "transitions": [transitions[i] for i in sparse_indices],
              "stage_funnel": stage_funnel(transitions, forward_reopen_options)}
    v7.verify_terminal_success(transitions, result)
    v8.require(result["physics_steps"] > 0 or
               (result["abstained"] and not result["unsafe"] and
                not result["success"] and len(transitions) == 1 and
                transitions[0]["action"] == 6),
               "V8_PROSPECTIVE_UNACCOUNTED_ZERO_PHYSICS")
    return result, transitions


def paired_readout(trials):
    by_seed = {}
    for row in trials:
        key = row["seed"]
        item = by_seed.setdefault(key, {})
        v8.require(row["strategy"] in STRATEGIES and row["strategy"] not in item,
                   "V8_PROSPECTIVE_DUPLICATE_OR_UNKNOWN_STRATEGY")
        item[row["strategy"]] = row
    v8.require(len(by_seed) == NEAR_TARGET + CLEAR_TARGET and
               all(set(pairs) == set(STRATEGIES) and
                   len({x["world_hash"] for x in pairs.values()}) == 1 and
                   len({x["observed_corridor"] for x in pairs.values()}) == 1
                   for pairs in by_seed.values()),
               "V8_PROSPECTIVE_UNPAIRED_REAL_WORLDS")
    cohort = {"near": sorted(seed for seed, pairs in by_seed.items()
                             if pairs["v8_hierarchical"]["observed_corridor"]),
              "clear": sorted(seed for seed, pairs in by_seed.items()
                              if not pairs["v8_hierarchical"]["observed_corridor"])}
    v8.require(len(cohort["near"]) == NEAR_TARGET and
               len(cohort["clear"]) == CLEAR_TARGET,
               "V8_PROSPECTIVE_WRONG_NEAR_CLEAR_COHORT")
    stats = {}
    for strategy in STRATEGIES:
        rows = [pairs[strategy] for pairs in by_seed.values()]
        safe = [r for r in rows if not r["unsafe"] and not r["abstained"]]
        near = [r for r in safe if r["observed_corridor"]]
        stats[strategy] = {"real_trials": len(rows), "unsafe": sum(r["unsafe"] for r in rows),
                           "abstained": sum(r["abstained"] for r in rows),
                           "safe_near_goals": sum(r["success"] for r in near),
                           "safe_near_signed_lateral25": sum(
                               r["stage_funnel"]["any_signed_lateral25"] for r in near),
                           "safe_near_chronological_contact_lateral25": sum(
                               r["stage_funnel"]["signed_lateral25_after_contact"]
                               for r in near),
                           "safe_near_chronological_forward_reopen": sum(
                               r["stage_funnel"]["forward_reopen_after_lateral25"]
                               for r in near),
                           "safe_near_full_stage_dwell": sum(
                               r["stage_funnel"]["full_contact_lateral_reopen_goal_dwell"]
                               for r in near)}
    lost, novel, new_unsafe = [], [], []
    for seed in cohort["near"]:
        pairs = by_seed[seed]
        v8row = pairs["v8_hierarchical"]
        baseline_goal = any(pairs[p]["success"] and not pairs[p]["unsafe"]
                            for p in ("frozen_v5", "frozen_v6"))
        v8_goal = v8row["success"] and not v8row["unsafe"]
        if baseline_goal and not v8_goal:
            lost.append(seed)
        if v8_goal and not baseline_goal:
            novel.append(seed)
        if v8row["unsafe"] and not any(pairs[p]["unsafe"]
                                       for p in ("frozen_v5", "frozen_v6", "repeat_left")):
            new_unsafe.append(seed)
    return {"strategies": stats, "cohort": cohort,
            "lost_frozen_v5_v6_safe_near_goal_seeds": lost,
            "novel_v8_safe_near_goal_seeds": novel,
            "v8_new_unsafe_vs_all_three_baselines_near_seeds": new_unsafe,
            "science_gate": "INDEPENDENT_REVIEW_REQUIRED_NO_PROMOTION",
            "prospective_train_only": True,
            "dev_cal_test_ood_opened": False,
            "model_promotion_authorized": False}


def import_v7_and_physics():
    # Import original verified V7 source, NOT a reconstructed environment.
    if str(MUJOCO_ROOT) not in sys.path:
        sys.path.insert(0, str(MUJOCO_ROOT))
    path = MUJOCO_ROOT / "v7_feasibility" / "run.py"
    v8.require(path.is_file(), "V8_ORIGINAL_V7_REAL_ROLLOUT_MISSING")
    v8.require(sha_file(path) == FROZEN_V7_RUN_FILE_SHA256,
               "V8_FROZEN_V7_REAL_ROLLOUT_SOURCE_SHA_MISMATCH")
    spec = importlib.util.spec_from_file_location("v8_frozen_v7_source", path)
    v8.require(spec is not None and spec.loader is not None,
               "V8_FROZEN_V7_IMPORT_UNAVAILABLE")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        import mujoco
        from physics import MovingContactEnv
    except ImportError as exc:
        raise RuntimeError("V8_REAL_MUJOCO_REQUIRED_NO_EMULATION") from exc
    v8.require(mujoco.__version__ == "3.3.7", "V8_MUJOCO_3_3_7_REQUIRED")
    return mod, MovingContactEnv


_CACHED_V7_SOURCE = None


class _LazyV7Source:
    """Read-only compatibility shim for independent V7 replay world-signature API."""
    def __getattr__(self, attribute):
        global _CACHED_V7_SOURCE
        if _CACHED_V7_SOURCE is None:
            _CACHED_V7_SOURCE, _ = import_v7_and_physics()
        return getattr(_CACHED_V7_SOURCE, attribute)


v7 = _LazyV7Source()


def policy_factory(name, frozen_weights, *, frozen_v7=None):
    """Stable policy factory for independent physics replay of every strategy.

    Signature intentionally matches V7 `policy_factory`, with the immutable
    V8 weights supplied explicitly. Every policy gets only (obs, original
    shield mask), and every episode gets its own fresh controller state.
    """
    v8.require(name in STRATEGIES, "V8_UNREGISTERED_PROSPECTIVE_POLICY")
    if name == "v8_hierarchical":
        # An independent physics replayer may pass an immutable checkpoint
        # Path rather than already verified NumPy arrays. In that case the
        # exact reviewed original model + receipt SHA is checked again.
        if isinstance(frozen_weights, (str, Path)):
            path = Path(frozen_weights).resolve(strict=True)
            weights, _, _ = verify_frozen_model(
                path, path.with_name("training-receipt.json"), FROZEN_WEIGHTS_SHA256)
        else:
            weights = np.asarray(frozen_weights, dtype=np.float64)
        v8.require(weights.shape == (4, 41, 7) and np.all(np.isfinite(weights)),
                   "V8_INDEPENDENT_REPLAY_MODEL_WEIGHTS_INVALID")
        return lambda: v8.HierarchicalPolicy(weights.copy())
    global _CACHED_V7_SOURCE
    if frozen_v7 is None:
        if _CACHED_V7_SOURCE is None:
            _CACHED_V7_SOURCE, _ = import_v7_and_physics()
        frozen_v7 = _CACHED_V7_SOURCE
    return frozen_v7.policy_factory(name)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("prospective-train",), required=True)
    p.add_argument("--require-git", action="store_true")
    p.add_argument("--expected-head", required=True)
    p.add_argument("--reviewed-weights-sha256", required=True)
    p.add_argument("--frozen-weights", type=Path, required=True)
    p.add_argument("--frozen-training-receipt", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--time-budget-seconds", type=int, default=1200)
    args = p.parse_args(argv)
    v8.require(args.require_git and 60 <= args.time_budget_seconds <= 3600,
               "V8_PROSPECTIVE_SOURCE_OR_TIME_BOUND_INVALID")
    validate_train_bounds()
    head, checkout = v8.source_identity(args.expected_head)
    validate_historical_trainer_source(checkout)
    weights_path = args.frozen_weights.resolve(strict=True)
    receipt_path = args.frozen_training_receipt.resolve(strict=True)
    output = args.output_dir.resolve()
    v8.require(not weights_path.is_relative_to(checkout) and
               not receipt_path.is_relative_to(checkout) and
               not output.is_relative_to(checkout) and
               output != weights_path.parent and output != receipt_path.parent,
               "V8_PROSPECTIVE_PRIVATE_ARTIFACT_PATHS_REQUIRED")
    weights, prior_receipt, frozen_sha = verify_frozen_model(
        weights_path, receipt_path, args.reviewed_weights_sha256)
    v7, Env = import_v7_and_physics()
    deadline = time.monotonic() + args.time_budget_seconds
    env = Env(max_options=MAX_OPTIONS)
    signature = v7.v6.v5.v4.v3.v2.v1._world_signature
    cohort, selection_scan = select_train_worlds(env, signature)
    schedule = paired_plan(cohort)
    v8.require(len(schedule) == EXPECTED_TRIALS,
               "V8_PROSPECTIVE_COMPLETE_PAIRED_SCHEDULE_REQUIRED")
    # Never adapt, early-stop by score, retry favorable worlds, or sample a
    # second cohort after seeing any outcome.
    factories = {s: policy_factory(s, weights, frozen_v7=v7) for s in STRATEGIES}
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    trials = []
    raw_path = output / "full_transitions.jsonl.gz"
    with gzip.open(raw_path, "xt", encoding="utf8", newline="\n", compresslevel=6) as stream:
        for definition, strategy in schedule:
            if time.monotonic() >= deadline:
                raise TimeoutError("V8_PROSPECTIVE_PAIRED_COHORT_DEADLINE")
            row, transitions = run_real_episode(
                env, definition["seed"], strategy, factories[strategy], signature,
                deadline, v7)
            v8.require(row["world_hash"] == definition["world_hash"],
                       "V8_PROSPECTIVE_STRATEGY_WORLD_HASH_DRIFT")
            row.update(observed_corridor=definition["observed_corridor"],
                       initial_observed_obstacle_y=definition["initial_observed_obstacle_y"])
            trials.append(row)
            stream.write(v8.canonical_bytes({"seed": row["seed"],
                                             "strategy": strategy,
                                             "transitions": transitions}).decode("utf8") + "\n")
    readout = paired_readout(trials)
    dataset_sha = v8.digest(trials)
    training = {"schema": SCHEMA + ".training", "executed_head": head,
                "actual_physics_engine": "mujoco-3.3.7", "training_only": True,
                "train_first_seed": TRAIN_FIRST_SEED,
                "selection_seed_limit": SELECTION_MAX_SEEDS,
                "selection_max_seeds": SELECTION_MAX_SEEDS,
                "selected_near_count": NEAR_TARGET,
                "selected_clear_count": CLEAR_TARGET,
                "selection_scan": selection_scan,
                "near_seeds": [r["seed"] for r in cohort if r["observed_corridor"]],
                "clear_seeds": [r["seed"] for r in cohort if not r["observed_corridor"]],
                "strategies": list(STRATEGIES), "cohort": cohort,
                "allocation": "all four frozen strategies on identical 160 fresh training worlds",
                "actual_trials": len(trials),
                "actual_transition_count": sum(r["full_transition_count"] for r in trials),
                "full_option_transitions": sum(r["full_transition_count"] for r in trials),
                "frozen_weights_sha256": frozen_sha,
                "historical_frozen_trainer_head": TRAINER_HEAD,
                "frozen_training_receipt_sha256": sha_file(receipt_path),
                "parent_v7_source_sha": v8.V7_SOURCE_SHA,
                "v7_training_dataset_sha256": v8.V7_DATASET_SHA256,
                "no_dev_evaluation": True,
                "dev_cal_test_ood_opened": False,
                "model_promotion_authorized": False,
                "no_provider_billing_assertion": True,
                "source_sha256": {"rollout_train.py": sha_file(HERE / "rollout_train.py"),
                                  "run.py": sha_file(HERE / "run.py")},
                "trials": trials, "dataset_sha256": dataset_sha}
    v8.write_new(output / "training.json", training)
    v8.require((output / "training.json").stat().st_size <= MAX_CAPTURED_JSON_BYTES,
               "V8_TRAIN_SUMMARY_EXCEEDS_CRACI_CAPTURE_LIMIT")
    readout.update(schema=SCHEMA + ".readout", executed_head=head,
                   frozen_weights_sha256=frozen_sha,
                   dataset_sha256=dataset_sha)
    v8.write_new(output / "paired-readout.json", readout)
    v8.require((output / "paired-readout.json").stat().st_size <= MAX_CAPTURED_JSON_BYTES,
               "V8_READOUT_EXCEEDS_CRACI_CAPTURE_LIMIT")
    manifest = {"schema": SCHEMA + ".manifest", "executed_head": head,
                "produced_at": datetime.now(timezone.utc).isoformat(),
                "immutable_source_v7_head": v8.V7_SOURCE_SHA,
                "frozen_weights_sha256": frozen_sha,
                "historical_frozen_trainer_head": TRAINER_HEAD,
                "file_sha256": {p.name: sha_file(p) for p in
                                (raw_path, output / "training.json", output / "paired-readout.json")},
                "source_sha256": training["source_sha256"],
                "auxiliary_file_sha256": {"paired-readout.json": sha_file(
                    output / "paired-readout.json")},
                "actual_trials": len(trials), "train_only": True,
                "dev_cal_test_ood_opened": False, "promotion_authorized": False}
    v8.write_new(output / "manifest.json", manifest)
    print(json.dumps({"executed_head": head, "train_only_real_trials": len(trials),
                      "model_weights_sha256": frozen_sha,
                      "dataset_sha256": dataset_sha,
            "v8_safe_near_goals": readout["strategies"]["v8_hierarchical"]["safe_near_goals"],
                      "promotion_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
