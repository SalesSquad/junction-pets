#!/usr/bin/env python3
"""Independent source-bound CRACI TRAIN-only MuJoCo V10 five-way qualification.

The producer runs 800 actual episodes.  A successful job proves data
completeness, not superiority, safety certification, an unlocked test result,
or permission to promote/deploy V10.  Keep the original 20 MiB per-file and
63 MiB total CRACI collector caps: package both complete original traces via
the separately reviewed V7 lossless evidence packer after qualification.
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


PRODUCT = Path("solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v10_prospective")
V10_TRAINED = PRODUCT.parent / "v10_learning"
V8_FROZEN = PRODUCT.parent / "v8_learning"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
V10_TRAIN_HEAD = "58c972e58575f022f2e97f09612f7c7fb244d4cb"
EXPECTED_STRATEGIES = ("frozen_v5", "frozen_v6", "repeat_left",
                       "frozen_v8", "v10_loss_informed")
EXPECTED_TRIALS = 800
TRAIN_FIRST = 515_000
V10_WEIGHTS_FILE_SHA = "3a926fdd80bc5bfe069ba4ab50792aaed760d81480eb68a80b6e087beec71f3d"
V8_WEIGHTS_FILE_SHA = "07823dcc52ea85b64e18767e1b1af29e63e3236613598cb349610a6b4fd37dc1"
V8_RECEIPT_FILE_SHA = "dc22f5538f19ef346d6b9965e7b28beed15e813b4b149ae5711d7dfae1771e73"


def require(ok, code):
    if not ok:
        raise AssertionError(code)


def sha_file(path: Path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def import_verified(path: Path, name: str):
    require(path.is_file() and not path.is_symlink(),
            "V10_INDEPENDENT_QUALIFIER_SOURCE_MISSING")
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None,
            "V10_INDEPENDENT_QUALIFIER_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_frozen_input_files(source_root: Path, private_dir: Path):
    original = {
        "candidate-weights.json": (V10_TRAINED / "checkpoints/candidate-weights.json",
                                   V10_WEIGHTS_FILE_SHA),
        "weights.json": (V8_FROZEN / "checkpoints/weights.json", V8_WEIGHTS_FILE_SHA),
        "training-receipt.json": (V8_FROZEN / "checkpoints/training-receipt.json",
                                  V8_RECEIPT_FILE_SHA),
    }
    require(not private_dir.exists(), "V10_PRIVATE_CHECKPOINT_DIR_EXISTS")
    private_dir.mkdir(parents=True, mode=0o700)
    staged = {}
    for name, (repo_path, required_sha) in original.items():
        original_path = source_root / repo_path
        require(original_path.is_file() and not original_path.is_symlink() and
                sha_file(original_path) == required_sha,
                "V10_FROZEN_REVIEWED_REPO_CHECKPOINT_SHA_INVALID")
        staged_path = private_dir / name
        shutil.copyfile(original_path, staged_path)
        require(sha_file(staged_path) == required_sha,
                "V10_PRIVATE_IMMUTABLE_CHECKPOINT_COPY_FAILED")
        staged[name] = staged_path
    return staged


def verify_independent_comparison(training, manifest, source_sha, evidence_dir,
                                  v7_qualifier):
    require(training.get("schema") ==
            "junction.rokoko.mujoco-v10.prospective-train.v1.training" and
            training.get("training_only") is True and
            training.get("dev_cal_test_ood_opened") is False and
            training.get("model_promotion_authorized") is False and
            manifest.get("schema") ==
            "junction.rokoko.mujoco-v10.prospective-train.v1.manifest" and
            manifest.get("immutable_v10_training_head") == V10_TRAIN_HEAD and
            manifest.get("candidate_v10_weights_file_sha256") == V10_WEIGHTS_FILE_SHA and
            manifest.get("promotion_authorized") is False,
            "V10_PROSPECTIVE_PRODUCT_SCHEMA_OR_SCIENCE_SCOPE_DRIFT")
    require(training.get("train_first_seed") == TRAIN_FIRST and
            training.get("strategies") == list(EXPECTED_STRATEGIES) and
            training.get("actual_trials") == EXPECTED_TRIALS and
            len(training.get("trials", [])) == EXPECTED_TRIALS and
            training.get("selected_near_count") == 128 and
            training.get("selected_clear_count") == 32 and
            training.get("candidate_v10_weights_file_sha256") == V10_WEIGHTS_FILE_SHA,
            "V10_PROSPECTIVE_PRE_REGISTERED_FIVE_WAY_COHORT_DRIFT")
    # The same already-reviewed V7 complete FULL option-trace verifier is
    # re-used, with only the preregistered TRAIN seed and strategy count.
    v7_qualifier.TRAIN_FIRST = TRAIN_FIRST
    v7_qualifier.MIN_STRATEGIES = len(EXPECTED_STRATEGIES)
    check = v7_qualifier.verify_training(training, manifest, source_sha,
                                         evidence_dir)
    require(check["trials"] == EXPECTED_TRIALS and
            check["actual_real_option_transitions"] ==
            training["actual_transition_count"] and
            check["selected_near_worlds"] == 128 and
            check["selected_clear_worlds"] == 32 and
            set(check["strategies"]) == set(EXPECTED_STRATEGIES) and
            all(x == 160 for x in check["strategies"].values()),
            "V10_PROSPECTIVE_PHYSICS_TRACE_INCOMPLETE")
    return check


def independent_masks_and_reopens(evidence_dir, training, env_factory):
    """Do not trust producer's original legal-mask or reopen counters alone."""
    rows = {(row["seed"], row["strategy"]): row for row in training["trials"]}
    require(len(rows) == EXPECTED_TRIALS,
            "V10_INDEPENDENT_DUPLICATED_STRATEGY_SEED")
    observed = set()
    reopen_worlds = {strategy: set() for strategy in EXPECTED_STRATEGIES}
    env = env_factory()
    with gzip.open(evidence_dir / "full_transitions.jsonl.gz", "rt",
                   encoding="utf8") as stream:
        for line in stream:
            doc = json.loads(line)
            key = (doc["seed"], doc["strategy"])
            require(key in rows and key not in observed,
                    "V10_INDEPENDENT_MASK_SOURCE_IDENTITY_MISMATCH")
            observed.add(key)
            env.reset(seed=doc["seed"], ood=False)
            reopens = []
            for index, transition in enumerate(doc["transitions"]):
                before = np.asarray(transition["observation"], dtype=np.float64)
                after = np.asarray(transition["next_observation"], dtype=np.float64)
                require(before.shape == after.shape == (18,) and
                        np.all(np.isfinite(before)) and np.all(np.isfinite(after)),
                        "V10_INDEPENDENT_MALFORMED_PUBLIC_18D_OBSERVATION")
                mask_before = [int(x) for x in env.mask(before)]
                mask_after = [int(x) for x in env.mask(after)]
                require(mask_before == transition["mask"] and
                        len(mask_before) == len(mask_after) == 7 and
                        mask_before[transition["action"]] == 1,
                        "V10_INDEPENDENT_ORIGINAL_SEVEN_ACTION_SHIELD_MISMATCH")
                if (transition["action"] in (3, 4) and
                        not (mask_before[1] or mask_before[2]) and
                        (mask_after[1] or mask_after[2])):
                    reopens.append(index + 1)
            row = rows[key]
            require(row["forward_reopened_after_side"] == len(reopens) and
                    row["forward_reopen_option_steps"] == reopens and
                    row["stage_funnel"]["any_forward_reopen_after_side"] == bool(reopens),
                    "V10_INDEPENDENT_REOPEN_TRACE_NOT_ORIGINAL_MASK")
            if reopens and row["observed_corridor"]:
                reopen_worlds[row["strategy"]].add(row["seed"])
    require(observed == set(rows),
            "V10_INDEPENDENT_INCOMPLETE_SEVEN_MASK_REPLAY")
    return {strategy: len(worlds) for strategy, worlds in reopen_worlds.items()}


def verify_readout(training, readout):
    require(readout.get("schema") ==
            "junction.rokoko.mujoco-v10.prospective-train.v1.readout" and
            readout.get("dataset_sha256") == training["dataset_sha256"] and
            readout.get("executed_head") == training["executed_head"] and
            readout.get("candidate_v10_weights_file_sha256") == V10_WEIGHTS_FILE_SHA and
            readout.get("model_promotion_authorized") is False and
            readout.get("dev_cal_test_ood_opened") is False,
            "V10_INDEPENDENT_PAIRED_READOUT_SOURCE_BINDING_FAILED")
    summaries = readout.get("strategies", {})
    require(set(summaries) == set(EXPECTED_STRATEGIES),
            "V10_INDEPENDENT_PAIRED_READOUT_WRONG_ARMS")
    actual_near = sorted({r["seed"] for r in training["trials"]
                          if r["observed_corridor"]})
    actual_clear = sorted({r["seed"] for r in training["trials"]
                           if not r["observed_corridor"]})
    require(len(actual_near) == 128 and len(actual_clear) == 32 and
            readout.get("near_seeds") == actual_near and
            readout.get("clear_seeds") == actual_clear,
            "V10_INDEPENDENT_PAIRED_COHORT_LISTS_NOT_RAW_OBSERVATIONS")
    for name in EXPECTED_STRATEGIES:
        rows = [r for r in training["trials"] if r["strategy"] == name]
        safe = [r for r in rows if not r["unsafe"] and not r["abstained"]]
        near = [r for r in safe if r["observed_corridor"]]
        clear = [r for r in safe if not r["observed_corridor"]]
        require(summaries[name]["paired_trials"] == len(rows) == 160 and
                summaries[name]["unsafe"] == sum(r["unsafe"] for r in rows) and
                summaries[name]["abstained"] == sum(r["abstained"] for r in rows) and
                summaries[name]["safe_goals_all"] == sum(r["success"] for r in safe) and
                summaries[name]["safe_goals_near"] == sum(r["success"] for r in near) and
                summaries[name]["safe_goals_clear"] == sum(r["success"] for r in clear) and
                summaries[name]["safe_near_lateral25_after_contact"] == sum(
                    r["stage_funnel"]["signed_lateral25_after_contact"] for r in near) and
                summaries[name]["safe_near_forward_reopen_after_lateral"] == sum(
                    r["stage_funnel"]["forward_reopen_after_lateral25"] for r in near) and
                summaries[name]["safe_near_dwell_after_reopen"] == sum(
                    r["stage_funnel"]["full_contact_lateral_reopen_goal_dwell"]
                    for r in near),
                "V10_INDEPENDENT_PAIRED_SCIENCE_COUNTS_NOT_RAW")
    rows = {(r["seed"], r["strategy"]): r for r in training["trials"]}
    losses, new_goals, new_unsafe = [], [], []
    for seed in actual_near:
        candidate = rows[seed, "v10_loss_informed"]
        safe_goal = candidate["success"] and not candidate["unsafe"]
        old = any(rows[seed, name]["success"] and not rows[seed, name]["unsafe"]
                  for name in ("frozen_v5", "frozen_v6"))
        if old and not safe_goal:
            losses.append(seed)
        if safe_goal and not old:
            new_goals.append(seed)
        if candidate["unsafe"] and not any(rows[seed, n]["unsafe"]
                                            for n in EXPECTED_STRATEGIES
                                            if n != "v10_loss_informed"):
            new_unsafe.append(seed)
    require(readout["lost_baseline_safe_near_goal_seeds"] == losses and
            readout["novel_v10_safe_near_goal_seeds"] == new_goals and
            readout["v10_new_unsafe_vs_frozen_controls"] == new_unsafe,
            "V10_INDEPENDENT_PAIRED_WIN_LOSS_NOT_FROM_ORIGINAL_TRIALS")


def main():
    source_root = Path(os.environ["CRACI_SOURCE_ROOT"]).resolve(strict=True)
    harness_root = Path(os.environ["CRACI_HARNESS_ROOT"]).resolve(strict=True)
    receipt_root = Path(os.environ["CRACI_RECEIPT_DIR"]).resolve(strict=True)
    head = os.environ["CRACI_SOURCE_SHA"]
    require(SHA40.fullmatch(head) is not None and
            subprocess.check_output(["git", "-C", str(source_root),
                                     "rev-parse", "HEAD"], text=True).strip() == head and
            subprocess.check_output(["git", "-C", str(source_root),
                                     "status", "--porcelain=v1"], text=True).strip() == "",
            "V10_CRACI_CLEAN_EXACT_PRODUCT_SOURCE_REQUIRED")
    require(os.environ.get("CRACI_WORKLOAD") == "rokoko-mujoco-v10-prospective" and
            subprocess.run(["git", "-C", str(source_root), "merge-base",
                            "--is-ancestor", V10_TRAIN_HEAD, "HEAD"],
                           capture_output=True).returncode == 0,
            "V10_CRACI_WRONG_WORKLOAD_OR_PRODUCT_LINEAGE")
    python = Path(os.environ["RUNNER_TEMP"]) / "mujoco-venv/bin/python"
    require(python.is_file(), "V10_CRACI_ORIGINAL_PINNED_MUJOCO_VENV_REQUIRED")
    product = source_root / PRODUCT
    private_dir = Path(os.environ["RUNNER_TEMP"]) / "v10-reviewed-private-checkpoint"
    inputs = verify_frozen_input_files(source_root, private_dir)
    subprocess.run([str(python), "-B", "-c",
                    "import mujoco,numpy;assert mujoco.__version__=='3.3.7'"],
                   cwd=source_root, check=True)
    subprocess.run([str(python), "-B", "-m", "unittest", "discover", "-q",
                    "-s", str(product), "-p", "test_contract.py"],
                   cwd=source_root, check=True)
    # CRITICAL: 800 full sparse trial summaries are ~22 MiB, above the 20 MiB
    # individual CRACI collector gate. Neither originals nor temporary files
    # ever enter CRACI_RECEIPT_DIR. The whole original is independently read
    # from private runner temp before being losslessly ZIP-published.
    output = Path(os.environ["RUNNER_TEMP"]) / "v10-prospective-private-originals"
    require(not output.exists(), "V10_CRACI_NON_OVERWRITING_OUTPUT_REQUIRED")
    result = subprocess.run([
        str(python), "-B", str(product / "run.py"),
        "--mode", "prospective-train", "--require-git",
        "--expected-head", head,
        "--v10-weights", str(inputs["candidate-weights.json"]),
        "--v8-weights", str(inputs["weights.json"]),
        "--v8-training-receipt", str(inputs["training-receipt.json"]),
        "--output-dir", str(output), "--time-budget-seconds", "1800",
    ], cwd=source_root, check=False, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    # Never transform or package originals until source/physics qualifier has
    # read BOTH full raw streams, every public shield and every claimed gain.
    v7 = import_verified(harness_root /
                         "scripts/craci/rokoko-mujoco-v7-feasibility-qualification.py",
                         "independent_v7_unchanged_true_physics_verifier")
    training = v7.read_json(output / "training.json")
    manifest = v7.read_json(output / "manifest.json")
    check = verify_independent_comparison(training, manifest, head, output, v7)
    readout_path = output / "paired-readout.json"
    require(sha_file(readout_path) == manifest["auxiliary_file_sha256"]["paired-readout.json"],
            "V10_INDEPENDENT_READOUT_FILE_SHA_INVALID")
    readout = v7.read_json(readout_path, max_bytes=1024 * 1024)
    verify_readout(training, readout)
    require(result.returncode == 0,
            "V10_CRACI_PRODUCER_EXIT_NONZERO_AFTER_TRACE_QUALIFICATION")
    sys.path.insert(0, str(source_root / PRODUCT.parent))
    from physics import MovingContactEnv
    reopened = independent_masks_and_reopens(
        output, training, lambda: MovingContactEnv(max_options=60))
    check["independent_five_way_forward_reopen_worlds"] = reopened
    replayer = import_verified(harness_root /
                               "scripts/craci/rokoko-mujoco-v7-positive-replay.py",
                               "v10_independent_true_physics_policy_replayer")
    product_module = import_verified(product / "run.py", "v10_pinned_product_policy_factory")
    v7_source, _ = product_module.v8.import_v7_and_physics()
    frozen_v8, _, _ = product_module.v8.verify_frozen_model(
        inputs["weights.json"], inputs["training-receipt.json"],
        product_module.v8.FROZEN_WEIGHTS_SHA256)

    def independent_factory(name):
        return product_module.policy_factory(name,
                    inputs["candidate-weights.json"], frozen_v8, frozen_v7=v7_source)

    signature = v7_source.v6.v5.v4.v3.v2.v1._world_signature
    replay = replayer.replay_positive(
        output, lambda: MovingContactEnv(max_options=60),
        independent_factory, signature)
    require(replay["claim_verified"] is True and
            replay["selection_scan_replayed"] >= 160 and
            replay["verified_near_corridor_success_worlds"] ==
            check["worlds_safe_corridor_success"],
            "V10_INDEPENDENT_TRUE_PHYSICS_POSITIVE_POLICY_REPLAY_FAILED")
    candidate_unsafe = readout["strategies"]["v10_loss_informed"]["unsafe"]
    # Even an unsafe trial must remain in the immutable evidence.  It is an
    # explicit science STOP, never a reason to suppress/retry inconvenient
    # worlds or alter the original safety mask after outcome inspection.
    check.update(schema="junction.rokoko.mujoco-v10-prospective.craci.train.v1",
                 decision="valid_source_bound_five_way_train_only_evidence",
                 independent_full_trace_public_mask_replay=True,
                 independent_true_physics_positive_replay=replay,
                 experiment_complete=True, producer_exit_code=result.returncode,
                 independentHoldout=False, model_improvement_verified=False,
                 candidate_unsafe_trials=candidate_unsafe,
                 science_gate=("STOP_CANDIDATE_UNSAFE" if candidate_unsafe else
                               "INDEPENDENT_PAIRED_GOAL_REVIEW_REQUIRED"),
                 promotion_authorized=False, dev_cal_test_ood_opened=False,
                 science_warning="Physical-goal delta is TRAIN-only and needs separate review")
    with (output / "independent-positive-replay.json").open("x", encoding="utf8") as file:
        json.dump(replay, file, indent=2, sort_keys=True)
        file.write("\n")
    with (output / "independent-qualification.json").open("x", encoding="utf8") as file:
        json.dump(check, file, indent=2, sort_keys=True)
        file.write("\n")
    collector_output = receipt_root / "artifacts" / "rokoko-mujoco-v10-prospective"
    require(not collector_output.exists(), "V10_CRACI_COLLECTOR_PREEXISTING_OUTPUT")
    packer = import_verified(harness_root /
                             "scripts/craci/rokoko-mujoco-v10-retain-evidence.py",
                             "v10_private_after_full_original_qualification_packer")
    packed = packer.publish_private_source(output, collector_output)
    require(packed["source_count"] == 2 and packed["archives"] >= 2 and
            packed["exact_source_sha"] == head and
            packed["original_sha256"] == manifest["file_sha256"],
            "V10_CRACI_PACKED_COLLECTOR_EVIDENCE_NOT_EXACT_OR_COMPLETE")
    print(json.dumps({"source_head": head, "producer_exit": result.returncode,
                      "trials": check["trials"],
                      "option_transitions": check["actual_real_option_transitions"],
                      "policy_replayed_positive": replay["fully_replayed_positive_train_trials"],
                      "losslessly_packed_originals": packed["source_count"],
                      "collector_published_bytes": packed["collector_bytes"],
                      "unsafe_v10_near": readout["strategies"]["v10_loss_informed"]["unsafe"],
                      "safe_v10_near_goals": readout["strategies"]["v10_loss_informed"]["safe_goals_near"],
                      "promotion_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
