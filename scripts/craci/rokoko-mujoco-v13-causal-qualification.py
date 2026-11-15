#!/usr/bin/env python3
"""Source-bound V13 retrospective TRAIN-only original-MuJoCo causal diagnostic.

V12's 48 *already seen* worlds are a diagnostic, never a prospective or
promotion cohort. No network download, credential permission changes, automatic
dispatch, or DEV/CAL/TEST/OOD access. All original executed branches and even
incomplete STOP evidence are retained privately before bounded publication.
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time


SOURCE_PRODUCT = Path("solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco")
V13 = SOURCE_PRODUCT / "v13_causal_reachability"
INDEX = Path("docs/craci/learning/rokoko-mujoco-v12-43657058944/trajectory-sha256.json")
INDEX_SHA = "24460b2ed49635b33db66233dd854f84593e6f65484cde229ee17ec483dd0245"
V12_SOURCE_SHA = "78f1b9de566dedf9ba3800ebee60fffa8ed0cc4f"
V12_HARNESS_SHA = "4874d15dd68d3a809aaf7d769d6b5bef85d378bd"
# Provisional source pin from draft PR#241. The integrator MUST require an
# independent final byte-exact review of this HEAD before any hosted dispatch.
PINNED_V13_PRODUCT_SHA = "0751d78b93855bf70820b03b0a543e123d218baf"
SCHEMA = "junction.rokoko.v13.actual-physics-causal-diagnostic.v1"
MAX_BRANCHES = 720
MAX_OPTIONS = 60
MAX_OPTION_EVENTS = MAX_BRANCHES * MAX_OPTIONS
MAX_TOTAL_SECONDS = 3000
DIAGNOSTIC_SECONDS = 1200
REGENERATE_SECONDS = 1000
INDEPENDENT_REPLAY_SECONDS = 800
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def require(ok, code):
    if not ok:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            result.update(block)
    return result.hexdigest()


def save_new(path, data):
    with Path(path).open("xb") as stream:
        stream.write(canonical(data) + b"\n")


def load_unique(path, label):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "V13_MODULE_SOURCE_MISSING_OR_LINK")
    spec = importlib.util.spec_from_file_location(label, path)
    require(spec is not None and spec.loader is not None, "V13_UNIQUE_SOURCE_IMPORT_FAILED")
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def import_v13_product(product_dir):
    """`causal.py` imports `forensic`; bind its exact reviewed module, no collision."""
    forensic = load_unique(product_dir / "forensic.py", "v13_exact_forensic_source")
    sentinel = object()
    prior = sys.modules.get("forensic", sentinel)
    sys.modules["forensic"] = forensic
    try:
        causal = load_unique(product_dir / "causal.py", "v13_exact_causal_source")
    finally:
        if prior is sentinel:
            del sys.modules["forensic"]
        else:
            sys.modules["forensic"] = prior
    require(causal.forensic is forensic and forensic.SOURCE_HEAD == V12_SOURCE_SHA and
            forensic.HARNESS_HEAD == V12_HARNESS_SHA and
            causal.MAX_DEPTH == 3 and causal.BEAM_WIDTH == 2 and
            causal.MAX_WORLD_BRANCHES == 20 and causal.MAX_TOTAL_BRANCHES == MAX_BRANCHES and
            causal.MAX_RUNTIME_SECONDS == DIAGNOSTIC_SECONDS,
            "V13_PRODUCT_ABI_SOURCE_OR_BUDGET_CHANGED")
    return forensic, causal


def pinned_git(root, expected, code, clean=True):
    require(bool(SHA40.fullmatch(expected)), "V13_FULL_40_CHAR_HEAD_REQUIRED")
    actual = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                     text=True).strip()
    require(actual == expected, code)
    if clean:
        require(not subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain=v1"],
            text=True).strip(), "V13_SOURCE_CHECKOUT_DIRTY_STOP")


def original_physics(source_root):
    """Reuse original V8->V7->V1 original MuJoCo, no substitute simulator."""
    original = load_unique(source_root / SOURCE_PRODUCT / "v10_prospective/run.py",
                           "v13_original_v10_unique_run_not_top_level_run")
    original.verify_historical_source(source_root)
    v7, Env = original.v8.import_v7_and_physics()
    return Env, v7.v6.v5.v4.v3.v2.v1._world_signature


def verified_trajectory_index(path, forensic):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and
            path.stat().st_size < 128 * 1024 and sha(path) == INDEX_SHA,
            "V13_AUDITED_TRAJECTORY_INDEX_SHA_OR_SIZE_STOP")
    data = json.loads(path.read_text(encoding="utf8"))
    require(data.get("schema") == "craci.rokoko.mujoco.v12.public-trajectory-index.v1" and
            data.get("executed_harness_head") == V12_HARNESS_SHA and
            data.get("executed_product_head") == V12_SOURCE_SHA and
            data.get("hosted_run") == 43657058944 and
            data.get("train_only") is True and
            data.get("contains_original_18d_observations") is False and
            data.get("contains_original_mask_or_action_history") is False,
            "V13_TRAJECTORY_INDEX_ORIGIN_OR_PRIVACY_MISMATCH")
    worlds = data["worlds"]
    trials = data["trajectories"]
    w = {row["seed"]: row["world_hash"] for row in worlds}
    t = {(row["seed"], row["strategy"]): row["full_transition_sha256"]
         for row in trials}
    require(len(w) == len(worlds) == 48 and len(t) == len(trials) == 144 and
            set(t) == {(seed, arm) for seed in w for arm in forensic.ARMS} and
            all(type(seed) is int and 518000 <= seed <= 518511 and
                type(h) is str and len(h) == 64 and
                all(c in "0123456789abcdef" for c in h) for seed, h in w.items()) and
            all(type(h) is str and len(h) == 64 and
                all(c in "0123456789abcdef" for c in h) for h in t.values()),
            "V13_TRAJECTORY_INDEX_NOT_COMPLETE_48x3_OR_SHA_UNSAFE")
    return w, t


def regenerate_verified_v12(source_root, harness_root, forensic, Env, signature,
                            stage_root, deadline):
    """Optional no-new-permissions source; every 1/144 original SHA must match.

    This *regenerates* 144 already-seen TRAIN episodes; it never says the
    newly generated gzip has the original historic aggregate gzip checksum.
    The reviewed original SHA is retained only as provenance, with all 144
    separately SHA-pinned full option histories replayed in original MuJoCo.
    """
    expected_worlds, expected_traces = verified_trajectory_index(
        harness_root / INDEX, forensic)
    v12_harness = load_unique(
        harness_root / "scripts/craci/rokoko-mujoco-v12-pilot-qualification.py",
        "v13_exact_v12_legacy_runner_not_generic_run")
    product = source_root / SOURCE_PRODUCT / "v12_learning"
    v12_policy = load_unique(product / "policy.py", "v13_exact_v12_policy_unique")
    protocol = load_unique(product / "protocol.py", "v13_exact_v12_protocol_unique")
    model, plan = v12_harness.original_plan_and_model(product, v12_policy, protocol)
    stage = v12_harness.stage_frozen_models(source_root, stage_root)
    factories, v8, v7, original_env, original_signature = v12_harness.original_factories(
        source_root, stage, v12_policy)
    require(original_signature is not None and callable(original_signature),
            "V13_ORIGINAL_REAL_SIGNATURE_NOT_LOADABLE")
    env = original_env(max_options=MAX_OPTIONS)
    scans = v12_harness.scan_real_public_starts(env, original_signature)
    cohort = protocol.derive_cohort(scans, plan, "pilot")
    v12_harness.independent_first_public_cohort(scans, cohort)
    require(len(cohort) == 48 and
            {row["seed"]: row["world_hash"] for row in cohort} == expected_worlds,
            "V13_REGENERATED_FIRST40_NEAR8_CLEAR_WORLD_HASH_SOURCE_MISMATCH")
    rows, traces = {}, {}
    options = 0
    for world in cohort:
        for arm in forensic.ARMS:
            require(time.monotonic() < deadline,
                    "V13_REGENERATE_144_EXACT_SOURCE_EPISODES_BUDGET_EXHAUSTED")
            row, trace = v8.run_real_episode(
                env, world["seed"], arm, factories[arm], original_signature,
                deadline, v7)
            key = (world["seed"], arm)
            require(key not in rows and row["world_hash"] == expected_worlds[key[0]] and
                    row["full_transition_sha256"] == expected_traces[key] and
                    digest(trace) == expected_traces[key] and
                    row["full_transition_count"] == len(trace) and
                    all(step["mask"][step["action"]] == 1 and
                        len(step["observation"]) == 18 and len(step["mask"]) == 7
                        for step in trace),
                    "V13_REGENERATED_REAL_FULL_TRACE_DOES_NOT_MATCH_AUDITED_144_PIN")
            row.update(observed_corridor=world["observed_corridor"],
                       initial_observed_obstacle_y=world["initial_public_obstacle_y"])
            rows[key] = row
            traces[key] = trace
            options += len(trace)
    require(len(rows) == len(traces) == 144 and options == 4228,
            "V13_REGENERATED_144_SOURCE_REAL_OPTION_COUNT_MISMATCH")
    source = {"rows": rows, "traces": traces, "sourceSha": V12_SOURCE_SHA,
              "harnessSha": V12_HARNESS_SHA,
              "fullTransitionsSha256": forensic.RAW_SHAS["full_transitions.jsonl.gz"],
              "independentReplayQualified": True, "newPhysicsPerformed": True,
              "v12RegeneratedAgainstAuditedPerTracePins": True}
    forensic.source_failure_diagnosis(source)
    return source


def validate_raw_branch(branch, forensic, original_source, max_count=MAX_OPTIONS):
    # The product library can run with an injected toy environment. Its marker
    # is deliberately UNATTESTED; only this pinned hosted V8/MuJoCo runner and
    # its independent replay may qualify actual physical execution.
    require(type(branch) is dict and branch.get("sourceOnlyUnattestedExecution") is True and
            branch.get("newRealMuJoCoExecuted") is False and
            branch.get("trainingOnly") is True and
            branch.get("modelPromotionAuthorized") is False and
            type(branch.get("seed")) is int and
            (branch["seed"], forensic.ARM_V5) in original_source["rows"] and
            branch["sourceWorldHash"] == original_source["rows"][
                branch["seed"], forensic.ARM_V5]["world_hash"],
            "V13_RAW_BRANCH_NOT_BOUND_TO_VERIFIED_ORIGINAL_TRAIN_WORLD")
    trace = branch["trace"]
    actions = branch["actions"]
    fork = branch["forkOptionIndexZeroBased"]
    require(branch.get("branchId") ==
            f'v13-seen-train-{branch["seed"]}-{int(branch["branchId"].rsplit("-", 1)[1]):02d}'
            if type(branch.get("branchId")) is str and
            branch["branchId"].rsplit("-", 1)[-1].isdigit() else False,
            "V13_UNREGISTERED_OR_MALFORMED_SOURCE_BRANCH_ID")
    require(type(fork) is int and 0 <= fork < len(original_source["traces"][
                branch["seed"], forensic.ARM_V5]) and
            type(trace) is list and 0 < len(trace) <= max_count and
            type(actions) is list and len(actions) == len(trace) ==
            branch["actualOptionSteps"] and
            branch["traceSha256"] == digest(trace) and
            [t["action"] for t in trace] == actions and
            trace[:fork] == original_source["traces"][
                branch["seed"], forensic.ARM_V5][:fork],
            "V13_RAW_BRANCH_SOURCE_PREFIX_OR_FULL_SHA_INVALID")
    for row in trace:
        forensic.public(row["observation"], row["mask"])
        require(type(row["action"]) is int and 0 <= row["action"] < 7 and
                row["mask"][row["action"]] == 1 and
                len(row["next_observation"]) == 18 and
                all(type(v) in (int, float) and math.isfinite(v)
                    for v in row["next_observation"]),
                "V13_RAW_BRANCH_ILLEGAL_SEVEN_MASK_OR_PRIVATE_VALUE")
    require(branch["decisionPublic18D"] == original_source["traces"][
                branch["seed"], forensic.ARM_V5][fork]["observation"] and
            branch["decisionOriginalMask7"] == original_source["traces"][
                branch["seed"], forensic.ARM_V5][fork]["mask"] and
            branch["exactOriginalPrefixReplayed"] is True,
            "V13_BRANCH_FORK_NOT_EXACT_OBSERVED_ORIGINAL_PUBLIC_DECISION")


def independent_branch_replay(branch, forensic, original_source, Env, signature,
                              deadline):
    """Fresh independent MuJoCo replay of *every* physical option and shield."""
    validate_raw_branch(branch, forensic, original_source)
    env = Env(max_options=MAX_OPTIONS)
    observation = env.reset(seed=branch["seed"], ood=False)
    require(str(signature(env)) == branch["sourceWorldHash"],
            "V13_REPLAY_ORIGINAL_WORLD_HASH_CHANGED")
    last_info = None
    last_done = False
    max_dwell = 0
    for step in branch["trace"]:
        require(time.monotonic() < deadline, "V13_INDEPENDENT_PHYSICS_REPLAY_TIMEOUT")
        obs = [float(v) for v in observation]
        mask = [int(v) for v in env.mask(observation)]
        require(obs == step["observation"] and mask == step["mask"] and
                mask[step["action"]] == 1 and
                (obs[10] or step["action"] == 6),
                "V13_REPLAY_PUBLIC_OBS7_SHIELD_OR_DEADMAN_DRIFT")
        observation, reward, done, info = env.step(step["action"])
        max_dwell = max(max_dwell, int(env.dwell))
        require([float(v) for v in observation] == step["next_observation"] and
                float(reward) == step["reward"] and
                bool(done) == step["done"] and
                int(info["cost"]) == step["cost"] and
                int(info["contacts"]) == step["contacts_cumulative"] and
                int(env.dwell) == step["dwell_ticks_current"] and
                max_dwell == step["dwell_ticks_cumulative"] and
                bool(info["success"]) == step["success_info"],
                "V13_INDEPENDENT_ALL_REAL_OPTION_PHYSICS_DIVERGED")
        last_info = info
        last_done = done
    expected_success = bool(last_info and last_info["success"] and
                            not last_info["unsafe"] and env.dwell >= 250 and
                            env.contacts > 0 and last_done)
    require(expected_success == branch["actualGoalSuccess250Tick"] and
            bool(last_info and last_info["unsafe"]) == branch["actualUnsafe"] and
            int(env.physics_steps) == branch["actualPhysicsSteps"] and
            int(env.contacts) == branch["actualContacts"] and
            int(env.dwell) == branch["actualDwellTicks"] and
            [float(v) for v in observation] == branch["lastPublicObservation18D"] and
            [int(v) for v in env.mask(observation)] == branch["lastOriginalMask7"],
            "V13_REPLAY_TERMINAL_250TICK_CONTACT_UNSAFE_OR_STATS_DRIFT")
    return len(branch["trace"]), expected_success


def preserve_diagnostic(private, source_sha, harness_sha, original_source,
                        result, recorded, exception_code=None, option_events=None):
    """Publisher schema; full traces already journaled via on_branch callback."""
    option_events = option_events if option_events is not None else sum(
        b["actualOptionSteps"] for b in recorded)
    require(len(recorded) <= MAX_BRANCHES and
            sum(b["actualOptionSteps"] for b in recorded) <= option_events <= MAX_OPTION_EVENTS and
            isinstance(result, dict), "V13_PRIVATE_RESULT_TYPE_OR_BRANCH_BOUND")
    full = bool(exception_code is None and result.get("allWorldsComplete") is True and
                result.get("status") == "TRAIN_ONLY_DIAGNOSTIC_COMPLETE" and
                result.get("hardStopReason") is None and
                len(result.get("worldResults", [])) == 36)
    reason = exception_code or result.get("hardStopReason") or (
        "V13_INCOMPLETE_SOURCE_OUTPUT" if not full else None)
    small = {k: v for k, v in result.items() if k != "rawBranches"}
    small.update({"schema": SCHEMA + (".training" if full else ".incomplete"),
                  "executed_head": source_sha, "harness_head": harness_sha,
                  "source_v12_head": V12_SOURCE_SHA,
                  "source_v12_original_sha256": original_source["fullTransitionsSha256"],
                  "source_mode": "REGENERATED_ALL144_AUDITED_TRACE_PINS" if
                      original_source.get("v12RegeneratedAgainstAuditedPerTracePins") else
                      "PINNED_PRESTAGED_ORIGINAL_V12_ARCHIVE",
                  "status": "COMPLETE_TRAIN_DIAGNOSTIC_ONLY" if full else "INCOMPLETE_STOP",
                  "recorded_branches": len(recorded),
                  "recorded_real_options": sum(b["actualOptionSteps"] for b in recorded),
                  "durably_journaled_all_executed_option_events": option_events,
                  "new_real_mujoco_performed": option_events > 0,
                  "training_only": True, "dev_cal_test_ood_opened": False,
                  "model_promotion_authorized": False,
                  "novel_prospective_goal_claim": False,
                  "no_automatic_retry_or_seed_fishing": True})
    training_name = "training.json" if full else "partial_training.json"
    save_new(private / training_name, small)
    if full:
        save_new(private / "diagnostic-readout.json", {
            "schema": SCHEMA + ".readout", "executed_head": source_sha,
            "status": small["status"], "world_results": small["worldResults"],
            "source_only_seen_train": True, "prospective_goal_improvement": False,
            "model_promotion_authorized": False, "raw_branch_count": len(recorded)})
        save_new(private / "manifest.json", {
            "schema": SCHEMA + ".manifest", "executed_head": source_sha,
            "harness_head": harness_sha,
            "source_v12_head": V12_SOURCE_SHA,
            "source_v12_original_sha256": original_source["fullTransitionsSha256"],
            "actual_branch_episodes": len(recorded),
            "actual_option_transitions": small["recorded_real_options"],
            "complete_36_failed_seen_train_worlds": True,
            "no_prospective_goal_promotion": True,
            "file_sha256": {name: sha(private / name) for name in
                            (training_name, "full_transitions.jsonl.gz",
                             "option_journal.jsonl.gz",
                             "diagnostic-readout.json")}})
    else:
        save_new(private / "early_stop.json", {
            "schema": SCHEMA + ".early-stop", "executed_head": source_sha,
            "harness_head": harness_sha, "status": "INCOMPLETE_STOP",
            "reason": reason, "recorded_branches": len(recorded),
            "expected_max_branches": MAX_BRANCHES,
            "recorded_real_options": small["recorded_real_options"],
            "durably_journaled_all_executed_option_events": option_events,
            "model_promotion_authorized": False,
            "raw_sha256": {name: sha(private / name) for name in
                           (training_name, "full_transitions.jsonl.gz",
                            "option_journal.jsonl.gz")}})
    return full


def run_diagnostic(source_root, harness_root, forensic, causal,
                   original_source, Env, signature, private, source_sha, harness_sha,
                   deadline):
    require(not private.exists(), "V13_PRIVATE_OUTPUT_MUST_BE_FRESH")
    private.mkdir(parents=True, mode=0o700, exist_ok=False)
    recorded = []
    steps = {}
    events = []
    def fsync_stream(stream):
        stream.flush()
        stream.buffer.fileobj.flush()
        os.fsync(stream.buffer.fileobj.fileno())
    def journal_step(event):
        require(type(event) is dict and
                event.get("schema") == causal.SCHEMA + ".option-journal.v1" and
                event.get("sourceOnlyUnattestedExecution") is True and
                event.get("physicsQualificationPending") is True and
                type(event.get("seed")) is int and
                (event["seed"], forensic.ARM_V5) in original_source["rows"] and
                event["sourceWorldHash"] == original_source["rows"][
                    event["seed"], forensic.ARM_V5]["world_hash"] and
                type(event.get("branchId")) is str and
                event["branchId"].startswith(f'v13-seen-train-{event["seed"]}-') and
                type(event.get("optionIndexZeroBased")) is int and
                event["optionIndexZeroBased"] >= 0 and
                event["phase"] in ("ORIGINAL_PREFIX", "COUNTERFACTUAL") and
                event["transitionSha256"] == digest(event["transition"]) and
                len(events) < MAX_OPTION_EVENTS,
                "V13_ON_STEP_ORIGINAL_PHYSICS_EVENT_SHA_OR_SOURCE_STOP")
        history = steps.setdefault(event["branchId"], [])
        require(event["optionIndexZeroBased"] == len(history) and
                len(history) < MAX_OPTIONS,
                "V13_ON_STEP_REORDER_DUPLICATE_OR_OVER_60_OPTIONS")
        t = event["transition"]
        forensic.public(t["observation"], t["mask"])
        require(type(t["action"]) is int and 0 <= t["action"] < 7 and
                t["mask"][t["action"]] == 1,
                "V13_ON_STEP_ORIGINAL_SEVEN_SHIELD_ILLEGAL")
        history.append(event["transitionSha256"])
        events.append(event)
        step_stream.write(canonical(event).decode() + "\n")
        fsync_stream(step_stream)
    def journal(branch):
        require(len(recorded) < MAX_BRANCHES, "V13_ON_BRANCH_EXCEEDS_FINITE_BUDGET")
        validate_raw_branch(branch, forensic, original_source)
        require(branch["branchId"] in steps and
                steps[branch["branchId"]] == [digest(t) for t in branch["trace"]] and
                branch["branchId"] not in {b["branchId"] for b in recorded},
                "V13_COMPLETED_BRANCH_NOT_LOSSLESSLY_ON_STEP_JOURNALED")
        recorded.append(branch)
        document = {"seed": branch["seed"], "branch_id": len(recorded) - 1,
                    "source_prefix": branch["forkOptionIndexZeroBased"],
                    "actions": branch["actions"], "transitions": branch["trace"]}
        stream.write(canonical(document).decode() + "\n")
        fsync_stream(stream)
    result = {}
    error = None
    with gzip.open(private / "full_transitions.jsonl.gz", "xt",
                   encoding="utf8", compresslevel=6, newline="\n") as stream, \
         gzip.open(private / "option_journal.jsonl.gz", "xt",
                   encoding="utf8", compresslevel=6, newline="\n") as step_stream:
        try:
            result = causal.run_budgeted_diagnostic(
                original_source, Env, signature, max_depth=3, beam_width=2,
                max_world_branches=20, deadline=min(deadline, time.monotonic() +
                                                    DIAGNOSTIC_SECONDS),
                on_branch=journal, on_step=journal_step)
        except Exception as exc:
            error = "V13_SOURCE_OR_PHYSICS_EXCEPTION_" + type(exc).__name__
    if error is None:
        try:
            require([b["traceSha256"] for b in result["rawBranches"]] ==
                    [b["traceSha256"] for b in recorded] and
                    sum(w["executedBudgetBranches"] for w in result["worldResults"]) ==
                    len(recorded) and
                    len(events) == sum(b["actualOptionSteps"] for b in recorded),
                    "V13_CALLBACK_JOURNAL_OR_WORLD_COUNT_LOSS_STOP")
        except Exception as exc:
            error = "V13_SOURCE_OR_PHYSICS_EXCEPTION_" + type(exc).__name__
    return result, recorded, error, len(events)


def independent_qualification(private, original_source, forensic, Env,
                              signature, recorded, result, deadline):
    require(result.get("allWorldsComplete") is True and
            len(result["worldResults"]) == 36 and
            len(recorded) == sum(w["executedBudgetBranches"]
                                 for w in result["worldResults"]) and
            36 <= len(recorded) <= MAX_BRANCHES,
            "V13_ALL36_SEEN_FAILURES_OR_BRANCH_COUNT_MISSING")
    seen_seeds = sorted(set(b["seed"] for b in recorded))
    diag = forensic.source_failure_diagnosis(original_source)
    require(seen_seeds == sorted(diag["v5FailedWorlds"]) and
            sorted(w["seed"] for w in result["worldResults"]) == seen_seeds and
            not any(b["actualUnsafe"] for b in recorded),
            "V13_SEED_FISHING_OMISSION_OR_REAL_UNSAFE_HARD_STOP")
    reconstructed = []
    with gzip.open(private / "full_transitions.jsonl.gz", "rt", encoding="utf8") as gz:
        for line in gz:
            require(len(line) < 2 * 1024 * 1024 and len(reconstructed) < MAX_BRANCHES,
                    "V13_ORIGINAL_RAW_BRANCH_OVERSIZED_OR_OMITTED")
            record = json.loads(line)
            b = recorded[len(reconstructed)]
            require(record == {"seed": b["seed"], "branch_id": len(reconstructed),
                               "source_prefix": b["forkOptionIndexZeroBased"],
                               "actions": b["actions"], "transitions": b["trace"]},
                    "V13_JOURNALED_REAL_BRANCH_MISSING_OR_TAMPERED")
            reconstructed.append(record)
    require(len(reconstructed) == len(recorded), "V13_GZIP_RAW_BRANCH_COUNT_MISSING")
    event_rows = 0
    by_branch = {}
    with gzip.open(private / "option_journal.jsonl.gz", "rt", encoding="utf8") as gz:
        for line in gz:
            require(len(line) < 2 * 1024 * 1024 and event_rows < MAX_OPTION_EVENTS,
                    "V13_OPTION_JOURNAL_OVERSIZE_OR_EXTRA_ORIGINAL_STEP")
            event = json.loads(line)
            history = by_branch.setdefault(event["branchId"], [])
            require(event["optionIndexZeroBased"] == len(history) and
                    event["transitionSha256"] == digest(event["transition"]),
                    "V13_OPTION_EVENT_SHA_OR_ORDER_NOT_INDEPENDENT")
            history.append(event["transitionSha256"])
            event_rows += 1
    require(event_rows == sum(b["actualOptionSteps"] for b in recorded) and
            set(by_branch) == {b["branchId"] for b in recorded} and
            all(by_branch[b["branchId"]] == [digest(t) for t in b["trace"]]
                for b in recorded), "V13_ON_STEP_SOURCE_BRANCH_EXACT_MATCH_STOP")
    options = 0
    goals = 0
    for branch in recorded:
        count, success = independent_branch_replay(
            branch, forensic, original_source, Env, signature, deadline)
        options += count
        goals += int(success)
    require(options == sum(b["actualOptionSteps"] for b in recorded) and
            all(w["status"] in ("WITNESS", "NONE_REACHABLE_WITHIN_FINITE_BUDGET")
                for w in result["worldResults"]) and
            all((w["actual250TickWitnessTraceSha256"] is None) ==
                (w["status"] != "WITNESS") for w in result["worldResults"]),
            "V13_FULL_ACTUAL_GOAL_WITNESS_ORIGINAL_OPTION_REPLAY_DRIFT")
    branch_by_seed_sha = {(b["seed"], b["traceSha256"]): b for b in recorded}
    require(len(branch_by_seed_sha) == len(recorded) and
            all((w["seed"], w["actual250TickWitnessTraceSha256"]) in
                branch_by_seed_sha and branch_by_seed_sha[
                    w["seed"], w["actual250TickWitnessTraceSha256"]][
                        "actualGoalSuccess250Tick"] is True
                if w["status"] == "WITNESS" else
                not any(b["seed"] == w["seed"] and b["actualGoalSuccess250Tick"]
                        for b in recorded)
                for w in result["worldResults"]),
            "V13_WITNESS_CANNOT_BE_MODEL_PROXY_OR_ANOTHER_WORLD_TRACE_SHA")
    return {"schema": SCHEMA + ".independent-qualification",
            "source_original_v12_head": V12_SOURCE_SHA,
            "source_original_v12_harness_head": V12_HARNESS_SHA,
            "all_36_seen_train_failure_worlds_physically_replayed": True,
            "all_raw_branches_independently_replayed": len(recorded),
            "all_raw_original_physics_option_steps_replayed": options,
            "all_source_step_journal_events_matched_exact": event_rows,
            "verified_goal250_branch_rollouts": goals,
            "any_unsafe_actual_cost": False,
            "no_new_fresh_worlds_opened": True,
            "train_only": True, "model_promotion_authorized": False}


def main():
    source_root = Path(os.environ["CRACI_SOURCE_ROOT"]).resolve(strict=True)
    harness_root = Path(os.environ["CRACI_HARNESS_ROOT"]).resolve(strict=True)
    receipt = Path(os.environ["CRACI_RECEIPT_DIR"]).resolve(strict=True)
    source_sha = os.environ["CRACI_SOURCE_SHA"]
    harness_sha = os.environ["CRACI_HARNESS_SHA"]
    require(source_sha == PINNED_V13_PRODUCT_SHA and
            os.environ.get("CRACI_WORKLOAD") == "rokoko-mujoco-v13-causal" and
            os.environ.get("CRACI_CREDIT_WINDOW_OPEN") == "true" and
            float(os.environ.get("CRACI_CREDIT_REMAINING_SECONDS", "0")) >= 3600,
            "V13_REVIEWED_SOURCE_CREDIT_3600S_ADMISSION_OR_WORKLOAD_STOP")
    pinned_git(source_root, source_sha, "V13_EXACT_REVIEWED_PRODUCT_GIT_HEAD_REQUIRED")
    pinned_git(harness_root, harness_sha, "V13_EXACT_EXECUTION_HARNESS_HEAD_REQUIRED")
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    pinned_python = runner_temp / "mujoco-venv/bin/python"
    require(pinned_python.is_file(), "V13_ORIGINAL_MUJOCO_VENV_REQUIRED")
    subprocess.run([str(pinned_python), "-B", "-c",
                    "import mujoco,numpy,sys;"
                    "assert mujoco.__version__=='3.3.7';"
                    "assert numpy.__version__=='2.3.4';"
                    "assert sys.prefix!=sys.base_prefix"],
                   cwd=source_root, check=True)
    start = time.monotonic()
    final_deadline = start + MAX_TOTAL_SECONDS
    forensic, causal = import_v13_product(source_root / V13)
    Env, signature = original_physics(source_root)
    mode = os.environ.get("CRACI_V13_ORIGINAL_MODE")
    if mode == "prestaged-immutable-v12-artifact":
        archive = Path(os.environ["CRACI_V12_ORIGINAL_ARCHIVE_DIR"]).resolve(strict=True)
        source_receipt = Path(os.environ["CRACI_V12_ORIGINAL_RECEIPT_PATH"]).resolve(strict=True)
        require(not archive.is_relative_to(source_root) and
                not archive.is_relative_to(harness_root) and
                not source_receipt.is_relative_to(source_root) and
                not source_receipt.is_relative_to(harness_root),
                "V13_PRIVATE_ORIGINAL_NOT_OUTSIDE_REVIEWED_SOURCE_CHECKOUTS")
        original_source = forensic.load_original_v12(archive, source_receipt)
    elif mode == "regenerate-144-audited-trace-pins":
        original_source = regenerate_verified_v12(
            source_root, harness_root, forensic, Env, signature,
            runner_temp / "v13-private-model-staging",
            min(start + REGENERATE_SECONDS, final_deadline))
    else:
        raise ValueError("V13_EXPLICIT_AUTHORIZED_ORIGINAL_ARTIFACT_MODE_REQUIRED")
    private = runner_temp / "v13-causal-seen-train-private-originals"
    result, recorded, error, option_events = run_diagnostic(
        source_root, harness_root, forensic, causal, original_source, Env,
        signature, private, source_sha, harness_sha, final_deadline)
    if error is None and result.get("allWorldsComplete") is True:
        try:
            independent = independent_qualification(
                private, original_source, forensic, Env, signature, recorded,
                result, min(time.monotonic() + INDEPENDENT_REPLAY_SECONDS,
                            final_deadline))
            # Packer considers qualification only after the full private
            # original source is independently physics-replayed.
            save_new(private / "independent-qualification.json", independent)
        except Exception as exc:
            error = "V13_INDEPENDENT_PHYSICS_NOT_QUALIFIED_" + type(exc).__name__
    complete = preserve_diagnostic(
        private, source_sha, harness_sha, original_source, result, recorded,
        exception_code=error, option_events=option_events)
    packer = load_unique(harness_root /
        "scripts/craci/rokoko-mujoco-v13-retain-evidence.py",
        "v13_exact_lossless_private_retention")
    collector = receipt / "artifacts" / "rokoko-mujoco-v13-causal"
    packed = packer.publish(private, collector, complete=complete)
    require(packed["exact_source_sha"] == source_sha,
            "V13_LOSSLESS_COLLECTOR_NOT_BOUND_TO_PRODUCT_SOURCE")
    print(json.dumps({"status": "COMPLETE_TRAIN_DIAGNOSTIC_ONLY" if complete
                      else "INCOMPLETE_STOP", "real_branch_episodes": len(recorded),
                      "real_original_options": sum(b["actualOptionSteps"] for b in recorded),
                      "original_option_events_durably_retained": option_events,
                      "source_mode": mode, "collector_bytes": packed["collector_bytes"],
                      "prospective_promotion": False}, sort_keys=True))
    return 0 if complete else 3


if __name__ == "__main__":
    raise SystemExit(main())
