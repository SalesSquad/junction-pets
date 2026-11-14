#!/usr/bin/env python3
"""Independently qualify a frozen V8 model on *fresh TRAIN-only* real MuJoCo worlds.

Reuses the V7 source-bound 18D/7-mask full-trace verifier and action-proposal
physics replayer. A successful CRACI job is NOT a model promotion, locked-test
qualification, development-set evaluation, or real robot safety certificate.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


V8_PRODUCT = Path("solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v8_learning")
V7_PHYSICS = V8_PRODUCT.parent
HISTORICAL_TRAINER_SHA = "4b91c64bc1a79bf630b1da6d12bea28e87c2990a"
FROZEN_MODEL_SHA256 = "9dd1011cd267899da4b9205fb73bdd2f5a8453719b1003351a24a82a2743e0ea"
WEIGHTS_FILE_SHA256 = "07823dcc52ea85b64e18767e1b1af29e63e3236613598cb349610a6b4fd37dc1"
TRAIN_RECEIPT_FILE_SHA256 = "dc22f5538f19ef346d6b9965e7b28beed15e813b4b149ae5711d7dfae1771e73"
EXPECTED_COHORT = 160
EXPECTED_TRIALS = 640
NEW_TRAIN_FIRST = 513_000
STRATEGIES = ("frozen_v5", "frozen_v6", "repeat_left", "v8_hierarchical")
SHA40 = re.compile("^[0-9a-f]{40}$")


def require(ok, reason):
    if not ok:
        raise AssertionError(reason)


def sha_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path):
    require(path.is_file() and not path.is_symlink(), "V8_CHECKPOINT_FILE_MISSING")
    return json.loads(path.read_text(encoding="utf8"))


def verify_checkpoint(weights_path: Path, receipt_path: Path):
    require(sha_file(weights_path) == WEIGHTS_FILE_SHA256 and
            sha_file(receipt_path) == TRAIN_RECEIPT_FILE_SHA256,
            "V8_FROZEN_CHECKPOINT_BYTES_MISMATCH")
    weights = load_json(weights_path)
    receipt = load_json(receipt_path)
    require(weights.get("source_head") == HISTORICAL_TRAINER_SHA and
            weights.get("v7_source_head") ==
            "127ceb9be4374ba46908cd398ced6b740275a434" and
            receipt.get("executed_head") == HISTORICAL_TRAINER_SHA and
            receipt.get("model_weights_sha256") == FROZEN_MODEL_SHA256 and
            receipt.get("dev_cal_test_ood_opened") is False and
            receipt.get("deployment_authorized") is False and
            receipt.get("model_weights_frozen") is True,
            "V8_HISTORICAL_CHECKPOINT_PROVENANCE_INVALID")
    return weights, receipt


def import_verified_module(path: Path, module_name: str):
    require(path.is_file() and not path.is_symlink(),
            "V8_INDEPENDENT_VERIFIER_MODULE_MISSING")
    spec = importlib.util.spec_from_file_location(module_name, path)
    require(spec is not None and spec.loader is not None,
            "V8_VERIFIER_IMPORT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_paired_train_result(training, manifest, source_head, evidence_dir,
                               v7_qualifier):
    require(training.get("schema") ==
            "junction.rokoko.mujoco-v8.prospective-train.v1.training",
            "V8_TRAIN_SCHEMA_INVALID")
    require(training.get("train_first_seed") == NEW_TRAIN_FIRST and
            training.get("strategies") == list(STRATEGIES) and
            len(training.get("trials", [])) == EXPECTED_TRIALS and
            training.get("selected_near_count") == 128 and
            training.get("selected_clear_count") == 32,
            "V8_PROSPECTIVE_COHORT_CHANGED")
    # Specialize only the known V7 TRAIN-only proof checker; NEVER weaken its
    # contact/goal/mask/seed-scan/full-transition requirements.
    v7_qualifier.TRAIN_FIRST = NEW_TRAIN_FIRST
    v7_qualifier.MIN_STRATEGIES = len(STRATEGIES)
    check = v7_qualifier.verify_training(training, manifest, source_head,
                                         evidence_dir)
    require(check["trials"] == EXPECTED_TRIALS and
            check["selected_near_worlds"] == 128 and
            check["selected_clear_worlds"] == 32 and
            set(check["strategies"]) == set(STRATEGIES) and
            all(n == EXPECTED_COHORT for n in check["strategies"].values()),
            "V8_PROSPECTIVE_NOT_FULLY_PAIRED")
    check["schema"] = "junction.rokoko.mujoco-v8-prospective.craci.train.v1"
    check["independentHoldout"] = False
    by_name = {}
    for name in STRATEGIES:
        rows = [row for row in training["trials"]
                if row["strategy"] == name and row["observed_corridor"]]
        require(len(rows) == 128, "V8_INCOMPLETE_CANDIDATE_NEAR_WORLD_COMPARISON")
        by_name[name] = {
            "safe_near_goals": sum(int(row["success"] and not row["unsafe"])
                                   for row in rows),
            "unsafe_near": sum(int(row["unsafe"]) for row in rows),
            "safe_lateral_ge_25mm": sum(int(not row["unsafe"] and
                                           row["away_lateral_displacement"] >= .025)
                                      for row in rows),
            "forward_reopen_worlds": sum(int(row["forward_reopened_after_side"] > 0)
                                         for row in rows),
        }
    check["prospective_train_only_paired_candidate_and_controls"] = by_name
    check["candidate_v8_safe_goal_difference_vs_best_frozen_baseline"] = (
        by_name["v8_hierarchical"]["safe_near_goals"] -
        max(by_name["frozen_v5"]["safe_near_goals"],
            by_name["frozen_v6"]["safe_near_goals"]))
    check["model_improvement_independently_verified"] = False
    check["next_experiment_advisory"] = {
        "new_train_seed_start": 514_000,
        "next_step": "scientific_review_then_independent_new_train_cohort",
        "note": "No promotion based on TRAIN-only difference; no locked dev/test authorization"}
    return check


def main():
    source_root = Path(os.environ["CRACI_SOURCE_ROOT"]).resolve(strict=True)
    harness_root = Path(os.environ["CRACI_HARNESS_ROOT"]).resolve(strict=True)
    receipt_root = Path(os.environ["CRACI_RECEIPT_DIR"]).resolve(strict=True)
    actual_head = subprocess.check_output(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True).strip()
    requested_head = os.environ["CRACI_SOURCE_SHA"]
    require(SHA40.fullmatch(requested_head) is not None and
            actual_head == requested_head, "V8_EXACT_PRODUCT_HEAD_REQUIRED")
    require(subprocess.check_output(
        ["git", "-C", str(source_root), "status", "--porcelain=v1"],
        text=True).strip() == "", "V8_DIRTY_SOURCE_OR_UNTRACKED_FILES")
    require(subprocess.run(
        ["git", "-C", str(source_root), "merge-base", "--is-ancestor",
         HISTORICAL_TRAINER_SHA, requested_head],
        capture_output=True).returncode == 0, "V8_SOURCE_NOT_DESCENDED_FROM_TRAINER")
    require(os.environ.get("CRACI_WORKLOAD") == "rokoko-mujoco-v8-prospective",
            "V8_WRONG_CRACI_WORKLOAD")

    python = Path(os.environ["RUNNER_TEMP"]) / "mujoco-venv/bin/python"
    require(python.is_file(), "V8_PINNED_MUJOCO_PYTHON_MISSING")
    product = source_root / V8_PRODUCT
    model_dir = product / "checkpoints"
    source_weights_path = model_dir / "weights.json"
    source_receipt_path = model_dir / "training-receipt.json"
    verify_checkpoint(source_weights_path, source_receipt_path)
    # Keep immutable reviewed source CHECKOUT CLEAN during training/evaluation.
    # The product intentionally disallows private checkpoint paths inside
    # checkout, so copy the byte-exact pinned checkpoint to private runner temp.
    private_model = Path(os.environ["RUNNER_TEMP"]) / "v8-private-checkpoint"
    require(not private_model.exists(), "V8_CHECKPOINT_STAGING_MUST_BE_NEW")
    private_model.mkdir(mode=0o700)
    weights_path = private_model / "weights.json"
    receipt_path = private_model / "training-receipt.json"
    shutil.copyfile(source_weights_path, weights_path)
    shutil.copyfile(source_receipt_path, receipt_path)
    verify_checkpoint(weights_path, receipt_path)
    subprocess.run([str(python), "-c",
                    "import mujoco,numpy;assert mujoco.__version__=='3.3.7'"],
                   check=True, cwd=source_root)
    subprocess.run([str(python), "-m", "unittest", "discover", "-q",
                    "-s", str(product), "-p", "test_rollout_contract.py"],
                   check=True, cwd=source_root)

    output = receipt_root / "artifacts" / "rokoko-mujoco-v8-prospective"
    require(not output.exists(), "V8_EVIDENCE_OUTPUT_MUST_BE_NEW")
    result = subprocess.run([
        str(python), str(product / "rollout_train.py"),
        "--mode", "prospective-train",
        "--require-git",
        "--expected-head", requested_head,
        "--reviewed-weights-sha256", FROZEN_MODEL_SHA256,
        "--frozen-weights", str(weights_path),
        "--frozen-training-receipt", str(receipt_path),
        "--output-dir", str(output),
        "--time-budget-seconds", "1200",
    ], check=False, cwd=source_root)

    # Verify every original real option transition and its public-observation
    # seed selection BEFORE packaging/relocating any large raw files.
    v7_qualifier = import_verified_module(
        harness_root / "scripts/craci/rokoko-mujoco-v7-feasibility-qualification.py",
        "v7_independent_full_transition_verifier")
    training = v7_qualifier.read_json(output / "training.json")
    manifest = v7_qualifier.read_json(output / "manifest.json")
    check = verify_paired_train_result(training, manifest, requested_head,
                                       output, v7_qualifier)
    readout_path = output / "paired-readout.json"
    readout = load_json(readout_path)
    require(manifest.get("auxiliary_file_sha256", {}).get("paired-readout.json") ==
            sha_file(readout_path) and
            readout.get("executed_head") == requested_head and
            readout.get("dataset_sha256") == training["dataset_sha256"],
            "V8_ADVISORY_READOUT_SOURCE_OR_DATASET_MISMATCH")
    require(result.returncode == 0, "V8_PROSPECTIVE_PRODUCER_NONZERO")

    # Re-execute all claimed positive trajectories on the exact original
    # MuJoCo dynamics AND independently confirm each frozen policy proposal.
    replayer = import_verified_module(
        harness_root / "scripts/craci/rokoko-mujoco-v7-positive-replay.py",
        "v7_independent_true_physics_replayer")
    sys.path.insert(0, str(source_root / V7_PHYSICS))
    from physics import MovingContactEnv
    product_runner = import_verified_module(product / "rollout_train.py",
                                            "v8_actual_frozen_policy_runner")
    require(callable(product_runner.policy_factory),
            "V8_FROZEN_POLICY_FACTORY_REQUIRED_FOR_INDEPENDENT_REPLAY")
    # The product exposes factories bound to exactly the checkpoint frozen
    # in source control; no oracle, privileged state or retrospective labels.
    def factory(name):
        return product_runner.policy_factory(name, weights_path)

    replay = replayer.replay_positive(
        output, lambda: MovingContactEnv(max_options=60),
        factory, product_runner.v7.v6.v5.v4.v3.v2.v1._world_signature)
    require(replay["claim_verified"] is True and
            replay["selection_scan_replayed"] >= EXPECTED_COHORT and
            replay["verified_near_corridor_success_worlds"] ==
            check["worlds_safe_corridor_success"],
            "V8_POLICY_AND_PHYSICS_REPLAY_FAILED")
    check["independent_true_physics_positive_replay"] = replay
    check["producer_exit_code"] = result.returncode
    check["experiment_complete"] = True
    check["promotion_authorized"] = False
    check["dev_cal_test_ood_opened"] = False
    check["decision"] = "valid_prospective_train_only_evidence"
    with (output / "independent-positive-replay.json").open("x", encoding="utf8") as f:
        json.dump(replay, f, sort_keys=True, indent=2)
        f.write("\n")
    with (output / "independent-qualification.json").open("x", encoding="utf8") as f:
        json.dump(check, f, sort_keys=True, indent=2)
        f.write("\n")
    print(json.dumps(check, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
