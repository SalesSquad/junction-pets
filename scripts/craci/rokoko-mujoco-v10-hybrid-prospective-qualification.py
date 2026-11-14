#!/usr/bin/env python3
"""Source-locked CRACI qualification of the V10 hybrid on fresh TRAIN worlds.

The product computes the four-arm MuJoCo experiment; this independent harness
rechecks the *entire* public-observation world scan, each original option trace,
seven-action shield, goal dwell, placebo and same-world regret before a signed-
away evidence archive is admitted. A successful job is never model promotion.
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

import numpy as np


PRODUCT_HEAD = "39f48031f7bff3970516a3c055efe47603e78be5"
V8_TRAINER_HEAD = "4b91c64bc1a79bf630b1da6d12bea28e87c2990a"
V8_WEIGHTS_SHA = "07823dcc52ea85b64e18767e1b1af29e63e3236613598cb349610a6b4fd37dc1"
V8_RECEIPT_SHA = "dc22f5538f19ef346d6b9965e7b28beed15e813b4b149ae5711d7dfae1771e73"
V8_MODEL_SHA = "9dd1011cd267899da4b9205fb73bdd2f5a8453719b1003351a24a82a2743e0ea"
PRODUCT = Path("solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco")
HYBRID = PRODUCT / "v10_hybrid"
V8 = PRODUCT / "v8_learning"
NAME = "rokoko-mujoco-v10-hybrid-prospective"
SCHEMA = "junction.rokoko.mujoco-v10-hybrid-prospective.v1"
FIRST = 516000
LAST = 516511
NEAR = 128
CLEAR = 32
STRATEGIES = ("frozen_v5", "v8_hierarchical", "near-early-side-mask-rescue",
              "rescue_off_v5")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
ORIGINAL_FILES = ("training.json", "full_transitions.jsonl.gz", "paired-readout.json")


def require(condition, reason):
    if not condition:
        raise AssertionError(reason)


def digest_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path, limit=32 * 1024 * 1024):
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= limit, "HYBRID_EVIDENCE_FILE_MISSING_OR_UNBOUNDED")
    return json.loads(path.read_text(encoding="utf8"))


def import_source(path: Path, module_name: str):
    require(path.is_file() and not path.is_symlink(), "HYBRID_VERIFIER_SOURCE_MISSING")
    spec = importlib.util.spec_from_file_location(module_name, path)
    require(spec is not None and spec.loader is not None,
            "HYBRID_VERIFIER_MODULE_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_goal(row):
    require(type(row.get("success")) is bool and type(row.get("unsafe")) is bool
            and type(row.get("dwell_ticks_final")) is int and
            row["dwell_ticks_final"] >= 0, "HYBRID_UNQUALIFIED_PHYSICAL_GOAL")
    return row["success"] and not row["unsafe"] and row["dwell_ticks_final"] >= 250


def independent_paired_science(training: dict, readout: dict):
    """Recompute *all* four-arm outcomes; never accept producer subset or label."""
    require(training.get("schema") == SCHEMA + ".training" and
            training.get("strategies") == list(STRATEGIES) and
            training.get("train_first_seed") == FIRST and
            training.get("selection_seed_limit") == LAST - FIRST + 1 and
            training.get("selected_near_count") == NEAR and
            training.get("selected_clear_count") == CLEAR and
            training.get("actual_trials") == 640 and
            training.get("dev_cal_test_ood_opened") is False and
            training.get("no_dev_evaluation") is True and
            training.get("model_promotion_authorized") is False,
            "HYBRID_UNREVIEWED_COHORT_OR_PROVENANCE")
    rows = training.get("trials")
    require(isinstance(rows, list) and len(rows) == 640,
            "HYBRID_INCOMPLETE_OR_EXTRA_TRIALS")
    groups = {}
    for row in rows:
        seed, strategy = row.get("seed"), row.get("strategy")
        require(type(seed) is int and FIRST <= seed <= LAST and
                strategy in STRATEGIES and type(row.get("observed_corridor")) is bool and
                SHA64.fullmatch(row.get("full_transition_sha256", "")) is not None,
                "HYBRID_UNKNOWN_WORLD_OR_UNBOUND_RAW")
        group = groups.setdefault(seed, {})
        require(strategy not in group, "HYBRID_DUPLICATE_STRATEGY_IN_WORLD")
        group[strategy] = row
    require(len(groups) == NEAR + CLEAR and all(set(g) == set(STRATEGIES)
            for g in groups.values()), "HYBRID_MISSING_PAIRED_WORLD_OR_ARM")
    near = sorted(seed for seed, g in groups.items()
                  if g["frozen_v5"]["observed_corridor"])
    clear = sorted(seed for seed, g in groups.items()
                   if not g["frozen_v5"]["observed_corridor"])
    require(len(near) == NEAR and len(clear) == CLEAR and
            near == training.get("near_seeds") and clear == training.get("clear_seeds"),
            "HYBRID_CHERRY_PICKED_OR_UNOBSERVED_WORLD_SET")
    require(readout.get("schema") == SCHEMA + ".readout" and
            readout.get("strict_original_v5_placebo_raw_trace_identical") is True and
            readout.get("cohort") == {"near": near, "clear": clear} and
            readout.get("dev_cal_test_ood_opened") is False and
            readout.get("promotion_authorized") is False,
            "HYBRID_UNTRUSTED_ADVISORY_READOUT")

    for seed, group in groups.items():
        original, placebo = group["frozen_v5"], group["rescue_off_v5"]
        require(original["full_transition_sha256"] == placebo["full_transition_sha256"] and
                all(original[k] == placebo[k] for k in (
                    "success", "unsafe", "abstained", "physics_steps")),
                f"HYBRID_PLACEBO_CHANGED_FROZEN_CONTROL_WORLD_{seed}")
        require(len({row["world_hash"] for row in group.values()}) == 1 and
                len({row["observed_corridor"] for row in group.values()}) == 1,
                "HYBRID_UNPAIRED_REAL_WORLD_OR_PUBLIC_CORRIDOR")

    stats = {}
    for name in STRATEGIES:
        arm = [g[name] for g in groups.values()]
        stats[name] = {
            "real_trials": len(arm),
            "safe_near_goals": sum(bool(safe_goal(r) and r["observed_corridor"]) for r in arm),
            "safe_clear_goals": sum(bool(safe_goal(r) and not r["observed_corridor"]) for r in arm),
            "unsafe": sum(bool(r["unsafe"]) for r in arm),
            "abstained": sum(bool(r["abstained"]) for r in arm),
            "timeouts": sum(not (r["success"] or r["unsafe"] or r["abstained"])
                            for r in arm),
            "forward_reopened_after_side": sum(r["forward_reopened_after_side"] for r in arm),
            "real_option_steps": sum(r["full_transition_count"] for r in arm),
        }
    require(readout.get("strategies") == stats,
            "HYBRID_PRODUCER_ARM_STATISTICS_NOT_INDEPENDENTLY_REPRODUCIBLE")
    novel, lost, shared, new_unsafe = [], [], [], []
    for seed, group in sorted(groups.items()):
        original, candidate = group["frozen_v5"], group["near-early-side-mask-rescue"]
        before, after = safe_goal(original), safe_goal(candidate)
        if after and not before:
            novel.append(seed)
        elif before and not after:
            lost.append(seed)
        elif before and after:
            shared.append(seed)
        if candidate["unsafe"] and not original["unsafe"]:
            new_unsafe.append(seed)
    require(readout.get("novel_hybrid_safe_goal_seeds_vs_v5") == novel and
            readout.get("lost_v5_safe_goal_seeds_under_hybrid") == lost and
            readout.get("shared_v5_hybrid_safe_goal_seeds") == shared and
            readout.get("hybrid_new_unsafe_seeds_vs_v5") == new_unsafe,
            "HYBRID_CHERRY_PICKED_PAIRED_REGRESSION_READOUT")
    verdict = ("NO_GO_ANY_CANDIDATE_UNSAFE" if stats["near-early-side-mask-rescue"]["unsafe"] else
               "NO_GO_FROZEN_GOAL_REGRESSION" if lost else
               "NO_GO_NO_NOVEL_GOAL" if not novel else
               "TRAIN_ONLY_NOVEL_GOAL_UNPROMOTED")
    return {"verdict": verdict, "novel_goals": len(novel),
            "lost_frozen_v5_goals": len(lost), "shared_goals": len(shared),
            "new_unsafe": len(new_unsafe), "strategies": stats,
            "near_seeds": near, "clear_seeds": clear}


def bind_terminal_dwell_and_timeout(training: dict, raw_gzip: Path):
    """Close the V7 historical verifier's row-vs-raw terminal dwell gap."""
    row_by_key = {(r["seed"], r["strategy"]): r for r in training["trials"]}
    require(len(row_by_key) == len(training["trials"]),
            "HYBRID_DUPLICATE_RAW_TERMINAL_IDENTITY")
    seen = set()
    with gzip.open(raw_gzip, "rt", encoding="utf8") as stream:
        for line in stream:
            doc = json.loads(line)
            key = (doc.get("seed"), doc.get("strategy"))
            require(key in row_by_key and key not in seen,
                    "HYBRID_UNKNOWN_OR_DUPLICATE_RAW_TERMINAL")
            transitions = doc.get("transitions")
            require(isinstance(transitions, list) and transitions,
                    "HYBRID_MISSING_RAW_TERMINAL_EVENT")
            last = transitions[-1]
            row = row_by_key[key]
            require(type(last.get("dwell_ticks_current")) is int and
                    type(row.get("dwell_ticks_final")) is int and
                    last["dwell_ticks_current"] == row["dwell_ticks_final"] and
                    type(row.get("safe_goal_dwell250")) is bool and
                    row["safe_goal_dwell250"] == safe_goal(row) and
                    type(row.get("timeout")) is bool and
                    row["timeout"] == (not (row["success"] or row["unsafe"] or
                                            row["abstained"])),
                    "HYBRID_FORGED_TERMINAL_DWELL_OR_TIMEOUT")
            seen.add(key)
    require(seen == set(row_by_key), "HYBRID_RAW_TERMINAL_COVERAGE_INCOMPLETE")
    return len(seen)


def all_goals_plus_original_positive(row, original_selector):
    """Strict superset of V7 positive replay; includes clear-world goals too."""
    require(type(row.get("success")) is bool, "HYBRID_INVALID_GOAL_REPLAY_LABEL")
    return bool(original_selector(row) or row["success"])


def main():
    source_root = Path(os.environ["CRACI_SOURCE_ROOT"]).resolve(strict=True)
    harness_root = Path(os.environ["CRACI_HARNESS_ROOT"]).resolve(strict=True)
    evidence_root = Path(os.environ["CRACI_RECEIPT_DIR"]).resolve(strict=True)
    requested_source = os.environ.get("CRACI_SOURCE_SHA", "")
    requested_harness = os.environ.get("CRACI_HARNESS_SHA", "")
    require(requested_source == PRODUCT_HEAD and SHA40.fullmatch(requested_source)
            and SHA40.fullmatch(requested_harness) is not None and
            os.environ.get("CRACI_WORKLOAD") == NAME,
            "HYBRID_UNREVIEWED_PRODUCT_OR_HARNESS_SOURCE")
    for folder, requested in ((source_root, requested_source),
                              (harness_root, requested_harness)):
        actual = subprocess.check_output(["git", "-C", str(folder), "rev-parse", "HEAD"],
                                         text=True).strip()
        require(actual == requested and not subprocess.check_output(
            ["git", "-C", str(folder), "status", "--porcelain=v1"],
            text=True).strip(), "HYBRID_EXECUTED_SOURCE_OR_HARNESS_DIRTY")
    require(subprocess.run(["git", "-C", str(source_root), "merge-base",
                            "--is-ancestor", V8_TRAINER_HEAD, requested_source],
                           capture_output=True).returncode == 0,
            "HYBRID_FROZEN_TRAINER_NOT_IN_SOURCE_LINEAGE")
    python = Path(os.environ["RUNNER_TEMP"]) / "mujoco-venv/bin/python"
    require(python.is_file() and not python.is_symlink(),
            "HYBRID_PINNED_MUJOCO_ENV_MISSING")
    subprocess.run([str(python), "-c",
                    "import mujoco,numpy;assert mujoco.__version__=='3.3.7'"],
                   check=True, cwd=source_root)

    original = source_root / V8 / "checkpoints"
    weights_in = original / "weights.json"
    receipt_in = original / "training-receipt.json"
    require(digest_file(weights_in) == V8_WEIGHTS_SHA and
            digest_file(receipt_in) == V8_RECEIPT_SHA,
            "HYBRID_UNREVIEWED_FROZEN_CHECKPOINT_FILES")
    private_model = Path(os.environ["RUNNER_TEMP"]) / "v10-hybrid-original-v8-pinned"
    require(not private_model.exists(), "HYBRID_PREEXISTING_MODEL_STAGING")
    private_model.mkdir(mode=0o700)
    weights = private_model / "weights.json"
    receipt = private_model / "training-receipt.json"
    shutil.copyfile(weights_in, weights)
    shutil.copyfile(receipt_in, receipt)
    require(digest_file(weights) == V8_WEIGHTS_SHA and
            digest_file(receipt) == V8_RECEIPT_SHA,
            "HYBRID_PRIVATE_CHECKPOINT_MISMATCH")
    hybrid_path = source_root / HYBRID
    subprocess.run([str(python), "-m", "unittest", "discover", "-q", "-s",
                    str(hybrid_path), "-p", "test_*.py"],
                   check=True, cwd=source_root)
    destination = evidence_root / "artifacts" / NAME
    require(not destination.exists(), "HYBRID_EVIDENCE_OUTPUT_ALREADY_EXISTS")
    result = subprocess.run([str(python), str(hybrid_path / "prospective_train.py"),
                             "--mode", "prospective-train", "--require-git",
                             "--expected-head", requested_source,
                             "--expected-harness-head", requested_harness,
                             "--reviewed-weights-sha256", V8_MODEL_SHA,
                             "--frozen-weights", str(weights),
                             "--frozen-training-receipt", str(receipt),
                             "--output-dir", str(destination),
                             "--time-budget-seconds", "1800"],
                            cwd=source_root, check=False)
    # Preserve every source file and the original partial state on nonzero.
    require(result.returncode == 0, "HYBRID_PROSPECTIVE_INCOMPLETE_REAL_PHYSICS_RUN")

    training = read_json(destination / "training.json", 19 * 1024 * 1024)
    manifest = read_json(destination / "manifest.json")
    readout = read_json(destination / "paired-readout.json", 19 * 1024 * 1024)
    parts_plan = read_json(destination / "evidence-parts-plan.json")
    require(manifest.get("schema") == SCHEMA + ".manifest" and
            manifest.get("executed_head") == requested_source and
            manifest.get("harness_expected_head") == requested_harness and
            manifest.get("training_only") is True and
            manifest.get("dev_cal_test_ood_opened") is False and
            manifest.get("promotion_authorized") is False and
            set(manifest.get("file_sha256", {})) == set(ORIGINAL_FILES) and
            training.get("harness_expected_head") == requested_harness and
            readout.get("executed_head") == requested_source and
            readout.get("harness_expected_head") == requested_harness and
            manifest.get("dataset_sha256") == training.get("dataset_sha256") ==
            readout.get("dataset_sha256"),
            "HYBRID_SOURCE_OR_EVIDENCE_MANIFEST_INCOMPLETE")
    for name, expected in manifest["file_sha256"].items():
        require(SHA64.fullmatch(expected) and
                digest_file(destination / name) == expected,
                "HYBRID_ORIGINAL_RAW_SHA_MISMATCH_" + name)
    require(parts_plan.get("schema") ==
            "junction.rokoko.mujoco-v10-hybrid-evidence-parts.v1" and
            parts_plan.get("archive_created_by_this_runner") is False and
            parts_plan.get("manifest_sha256") == digest_file(destination / "manifest.json") and
            sorted(p.get("name") for p in parts_plan.get(
                "part_files_for_independent_external_packager", [])) == sorted(ORIGINAL_FILES),
            "HYBRID_EVIDENCE_PLAN_CANNOT_REPLACE_ACTUAL_ARCHIVE")
    for declaration in parts_plan["part_files_for_independent_external_packager"]:
        name = declaration["name"]
        require(declaration["sha256"] == manifest["file_sha256"][name] and
                declaration["bytes"] == (destination / name).stat().st_size,
                "HYBRID_PACK_PLAN_ORIGINAL_BYTE_DRIFT")

    # Original V7 validator independently derives the exact first 128 near +
    # first 32 clear public-world scan, every row, source digest, every 18D
    # observation, legal seven-option shield and *all* gzip transitions.
    verifier = import_source(harness_root / "scripts/craci/rokoko-mujoco-v7-feasibility-qualification.py",
                             "hybrid_v7_original_raw_validator")
    verifier.TRAIN_FIRST = FIRST
    verifier.MIN_STRATEGIES = len(STRATEGIES)
    # The producer's third preserved file is separately verified above; V7
    # has a narrow historical two-file contract and is not weakened here.
    original_two_file_manifest = dict(manifest)
    original_two_file_manifest["file_sha256"] = {
        name: manifest["file_sha256"][name]
        for name in ("training.json", "full_transitions.jsonl.gz")}
    raw_check = verifier.verify_training(training, original_two_file_manifest,
                                         requested_source, destination)
    require(raw_check["trials"] == 640 and
            raw_check["selected_near_worlds"] == NEAR and
            raw_check["selected_clear_worlds"] == CLEAR and
            raw_check["strategies"] == {name: NEAR + CLEAR for name in STRATEGIES},
            "HYBRID_INCOMPLETE_INDEPENDENT_PUBLIC_OBS_COHORT")
    require(bind_terminal_dwell_and_timeout(
        training, destination / "full_transitions.jsonl.gz") == 640,
        "HYBRID_INCOMPLETE_INDEPENDENT_TERMINAL_BINDING")
    require(manifest.get("actual_real_mujoco_trials") == 640 and
            manifest.get("actual_real_option_transitions") ==
            raw_check["actual_real_option_transitions"],
            "HYBRID_MANIFEST_COUNT_OMITTED_NEGATIVE_TRIALS")
    science = independent_paired_science(training, readout)

    v8shim = import_source(harness_root / "scripts/craci/rokoko-mujoco-v8-prospective-qualification.py",
                           "hybrid_public_mask_reopening_validator")
    v8shim.STRATEGIES = STRATEGIES
    sys.path.insert(0, str(source_root / PRODUCT))
    hybrid_module = import_source(hybrid_path / "hybrid_policy.py",
                                  "hybrid_original_frozen_model_factory")
    runner, _, v5_factory, v8_factory = hybrid_module.verified_original_bundle(weights, receipt)
    _, Env = runner.import_v7_and_physics()
    reopens = v8shim.independently_verify_all_masks_and_reopening(
        destination, training, lambda: Env(max_options=60))
    for name in STRATEGIES:
        require(reopens[name] <= NEAR and reopens[name] >= 0,
                "HYBRID_INDEPENDENT_MASK_REOPENING_UNBOUNDED")

    replayer = import_source(harness_root / "scripts/craci/rokoko-mujoco-v7-positive-replay.py",
                             "hybrid_original_true_physics_replayer")
    # Original V7 positive replay historically selects near-corridor goals
    # only. This four-arm prospective qualification MUST additionally replay
    # every clear-world success, not merely inherit the old narrower selector.
    historical_selector = replayer.positive_candidate
    replayer.positive_candidate = lambda row: all_goals_plus_original_positive(
        row, historical_selector)
    factory = {
        "frozen_v5": v5_factory,
        "v8_hierarchical": v8_factory,
        "near-early-side-mask-rescue": hybrid_module.policy_factory(
            "near-early-side-mask-rescue", weights, receipt),
        "rescue_off_v5": v5_factory,
    }
    replay = replayer.replay_positive(
        destination, lambda: Env(max_options=60), lambda name: factory[name],
        runner.v7.v6.v5.v4.v3.v2.v1._world_signature)
    all_goal_seeds = {row["seed"] for row in training["trials"]
                      if row["success"] and not row["unsafe"]}
    require(replay["claim_verified"] is True and
            replay["selection_scan_replayed"] >= NEAR + CLEAR and
            replay["verified_near_corridor_success_worlds"] == len(all_goal_seeds),
            "HYBRID_FROZEN_POLICY_OR_REAL_PHYSICS_REPLAY_FAILED")
    result_doc = {
        "schema": SCHEMA + ".independent-qualification", "source_head": requested_source,
        "harness_head": requested_harness, "experiment_complete": True,
        "status": "qualified_train_only", "real_original_mujoco_episodes": 640,
        "real_original_option_transitions": raw_check["actual_real_option_transitions"],
        "all_original_full_traces_and_masks_verified": True,
        "independent_true_physics_positive_replay": True,
        "independent_true_physics_all_goal_worlds_replayed": len(all_goal_seeds),
        "original_v7_positive_selector_strengthened_to_all_goal_worlds": True,
        "independent_public_mask_reopen_worlds": reopens,
        "strict_frozen_v5_placebo_identical": True,
        "science": science, "candidate_verdict": science["verdict"],
        "model_improvement_certified": False, "promotion_authorized": False,
        "dev_cal_test_ood_opened": False,
        "source_reported_execution_not_external_provider_attestation": True,
    }
    with (destination / "independent-qualification.json").open("x", encoding="utf8") as f:
        json.dump(result_doc, f, sort_keys=True, indent=2)
        f.write("\n")
    with (destination / "independent-positive-replay.json").open("x", encoding="utf8") as f:
        json.dump(replay, f, sort_keys=True, indent=2)
        f.write("\n")
    print(json.dumps({"science": science["verdict"], "real_trials": 640,
                      "real_option_transitions": raw_check["actual_real_option_transitions"],
                      "original_full_traces": True, "no_promotion": True},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
