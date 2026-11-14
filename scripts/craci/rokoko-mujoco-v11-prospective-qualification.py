#!/usr/bin/env python3
"""Independent source-bound CRACI TRAIN-only MuJoCo V11 five-way qualification.

The producer runs 800 actual episodes.  A successful job proves data
completeness, not superiority, safety certification, an unlocked test result,
or permission to promote/deploy V11.  Keep the original 20 MiB per-file and
63 MiB total CRACI collector caps: package both complete private originals
directly into bounded ZIP parts with the new source-reviewed V11 packer.
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
import tempfile

import numpy as np


PRODUCT = Path("solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v11_learning")
V11_TRAINED = PRODUCT
V10_TRAINED = PRODUCT.parent / "v10_learning"
V8_FROZEN = PRODUCT.parent / "v8_learning"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
V10_SOURCE_HEAD = "9cc583d3f0f24484b79c1929ba875c7a3b667806"
V11_GATE_SHA = "b115fc329b50f2557e8c6074734990dbcf6d1c5046516fbbda6158c5c513eaa8"
V11_PLAN_SHA = "3b4fc425c5f9af4ab2e28b2afcaeae62543ba08a3064406c4150b84c4d57f494"
TRAINING_SCHEMA = "junction.rokoko.v11.goal-first-fresh-train.v1.training"
MANIFEST_SCHEMA = "junction.rokoko.v11.goal-first-fresh-train.v1.manifest"
READOUT_SCHEMA = "junction.rokoko.v11.goal-first-fresh-train.v1.readout"
EXPECTED_STRATEGIES = ("frozen_v5", "frozen_v6", "frozen_v8",
                       "v10_loss_informed", "v11_goal_preserving")
EXPECTED_TRIALS = 800
TRAIN_FIRST = 517_000
V11_WEIGHTS_FILE_SHA = "3a926fdd80bc5bfe069ba4ab50792aaed760d81480eb68a80b6e087beec71f3d"
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
            "V11_INDEPENDENT_QUALIFIER_SOURCE_MISSING")
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None,
            "V11_INDEPENDENT_QUALIFIER_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_frozen_input_files(source_root: Path, private_dir: Path):
    original = {
        "candidate-weights.json": (V10_TRAINED / "checkpoints/candidate-weights.json",
                                   V11_WEIGHTS_FILE_SHA),
        "weights.json": (V8_FROZEN / "checkpoints/weights.json", V8_WEIGHTS_FILE_SHA),
        "training-receipt.json": (V8_FROZEN / "checkpoints/training-receipt.json",
                                  V8_RECEIPT_FILE_SHA),
    }
    require(not private_dir.exists(), "V11_PRIVATE_CHECKPOINT_DIR_EXISTS")
    private_dir.mkdir(parents=True, mode=0o700)
    staged = {}
    for name, (repo_path, required_sha) in original.items():
        original_path = source_root / repo_path
        require(original_path.is_file() and not original_path.is_symlink() and
                sha_file(original_path) == required_sha,
                "V11_FROZEN_REVIEWED_REPO_CHECKPOINT_SHA_INVALID")
        staged_path = private_dir / name
        shutil.copyfile(original_path, staged_path)
        require(sha_file(staged_path) == required_sha,
                "V11_PRIVATE_IMMUTABLE_CHECKPOINT_COPY_FAILED")
        staged[name] = staged_path
    return staged


def derive_legacy_read_only_view(training, manifest, v7_qualifier):
    """Adapt metadata only; immutable original files and original SHA stay intact.

    V11 freezes all 512 public initial observations and three original file
    checksums. V7 expects the shortest first-128+32 scan and two source files.
    This temporary view never replaces, rewrites, or shrinks V11 evidence.
    """
    require(training.get("schema") == TRAINING_SCHEMA and
            manifest.get("schema") == MANIFEST_SCHEMA and
            training.get("training_only") is True and
            training.get("no_dev_test_ood") is True and
            training.get("model_promotion_authorized") is False and
            manifest.get("training_only") is True and
            manifest.get("model_promotion_authorized") is False and
            manifest.get("new_qualification_performed") is False and
            manifest.get("dev_cal_test_ood_opened") is False and
            manifest.get("gateSha256") == V11_GATE_SHA and
            manifest.get("planSha256") == V11_PLAN_SHA and
            training.get("candidate_source_gate_sha256") == V11_GATE_SHA,
            "V11_PROSPECTIVE_PRODUCT_OR_TRAIN_ONLY_SCOPE_DRIFT")
    require(training.get("strategies") == list(EXPECTED_STRATEGIES) and
            training.get("actual_trials") == EXPECTED_TRIALS and
            len(training.get("trials", [])) == EXPECTED_TRIALS and
            manifest.get("actual_trials") == EXPECTED_TRIALS and
            manifest.get("actual_option_transitions") ==
            training.get("actual_option_transitions") and
            len(training.get("all_512_public_initial_scans", [])) == 512 and
            len(training.get("cohort", [])) == 160 and
            set(manifest.get("file_sha256", {})) ==
            {"training.json", "full_transitions.jsonl.gz", "paired-readout.json"},
            "V11_PROSPECTIVE_PRE_REGISTERED_FIVE_WAY_COHORT_DRIFT")
    prefix, near, clear = [], [], []
    for index, row in enumerate(training["all_512_public_initial_scans"]):
        require(row["seed"] == TRAIN_FIRST + index and
                isinstance(row["observation"], list) and
                len(row["observation"]) == 18 and
                isinstance(row["mask"], list) and len(row["mask"]) == 7 and
                all(bit in (0, 1) for bit in row["mask"]),
                "V11_ALL_512_PUBLIC_SELECTION_SCAN_INCOMPLETE")
        observed_y = row["observation"][7]
        incomplete = len(near) < 128 or len(clear) < 32
        if incomplete:
            prefix.append({"seed": row["seed"], "world_hash": row["world_hash"],
                           "initial_observed_obstacle_y": observed_y})
        if len(near) < 128 and abs(observed_y) < .122:
            near.append(row["seed"])
        elif len(clear) < 32 and abs(observed_y) >= .122:
            clear.append(row["seed"])
    require(len(near) == 128 and len(clear) == 32 and
            {row["seed"] for row in training["cohort"]} == set(near + clear) and
            [row["seed"] for row in training["cohort"]] == sorted(near + clear) and
            len(prefix) <= 512,
            "V11_FIRST_PUBLIC_128_NEAR_32_CLEAR_WORLDS_CHANGED")
    # V7's independent original complete-trace verifier accepts these precise
    # *derived metadata aliases*; actual SHA-checked originals are untouched.
    legacy = dict(training, train_first_seed=TRAIN_FIRST,
                  selection_seed_limit=512, selection_scan=prefix,
                  selected_near_count=128, selected_clear_count=32,
                  no_dev_evaluation=True,
                  actual_transition_count=training["actual_option_transitions"],
                  dataset_sha256=v7_qualifier.canonical_sha(training["trials"]))
    legacy_manifest = dict(manifest, file_sha256={
        key: manifest["file_sha256"][key] for key in (
            "training.json", "full_transitions.jsonl.gz")})
    return legacy, legacy_manifest


def verify_independent_comparison(training, manifest, source_sha, evidence_dir,
                                  v7_qualifier):
    legacy, legacy_manifest = derive_legacy_read_only_view(
        training, manifest, v7_qualifier)
    v7_qualifier.TRAIN_FIRST = TRAIN_FIRST
    v7_qualifier.MIN_STRATEGIES = len(EXPECTED_STRATEGIES)
    check = v7_qualifier.verify_training(
        legacy, legacy_manifest, source_sha, evidence_dir)
    require(check["trials"] == EXPECTED_TRIALS and
            check["actual_real_option_transitions"] ==
            training["actual_option_transitions"] and
            check["selected_near_worlds"] == 128 and
            check["selected_clear_worlds"] == 32 and
            set(check["strategies"]) == set(EXPECTED_STRATEGIES) and
            all(x == 160 for x in check["strategies"].values()),
            "V11_PROSPECTIVE_PHYSICS_TRACE_INCOMPLETE")
    return check, legacy


def independent_masks_and_reopens(evidence_dir, training, env_factory):
    """Do not trust producer's original legal-mask or reopen counters alone."""
    rows = {(row["seed"], row["strategy"]): row for row in training["trials"]}
    require(len(rows) == EXPECTED_TRIALS,
            "V11_INDEPENDENT_DUPLICATED_STRATEGY_SEED")
    observed = set()
    reopen_worlds = {strategy: set() for strategy in EXPECTED_STRATEGIES}
    env = env_factory()
    with gzip.open(evidence_dir / "full_transitions.jsonl.gz", "rt",
                   encoding="utf8") as stream:
        for line in stream:
            doc = json.loads(line)
            key = (doc["seed"], doc["strategy"])
            require(key in rows and key not in observed,
                    "V11_INDEPENDENT_MASK_SOURCE_IDENTITY_MISMATCH")
            observed.add(key)
            env.reset(seed=doc["seed"], ood=False)
            reopens = []
            for index, transition in enumerate(doc["transitions"]):
                before = np.asarray(transition["observation"], dtype=np.float64)
                after = np.asarray(transition["next_observation"], dtype=np.float64)
                require(before.shape == after.shape == (18,) and
                        np.all(np.isfinite(before)) and np.all(np.isfinite(after)),
                        "V11_INDEPENDENT_MALFORMED_PUBLIC_18D_OBSERVATION")
                mask_before = [int(x) for x in env.mask(before)]
                mask_after = [int(x) for x in env.mask(after)]
                require(mask_before == transition["mask"] and
                        len(mask_before) == len(mask_after) == 7 and
                        mask_before[transition["action"]] == 1,
                        "V11_INDEPENDENT_ORIGINAL_SEVEN_ACTION_SHIELD_MISMATCH")
                if (transition["action"] in (3, 4) and
                        not (mask_before[1] or mask_before[2]) and
                        (mask_after[1] or mask_after[2])):
                    reopens.append(index + 1)
            row = rows[key]
            require(row["forward_reopened_after_side"] == len(reopens) and
                    row["forward_reopen_option_steps"] == reopens and
                    row["stage_funnel"]["any_forward_reopen_after_side"] == bool(reopens),
                    "V11_INDEPENDENT_REOPEN_TRACE_NOT_ORIGINAL_MASK")
            if reopens and row["observed_corridor"]:
                reopen_worlds[row["strategy"]].add(row["seed"])
    require(observed == set(rows),
            "V11_INDEPENDENT_INCOMPLETE_SEVEN_MASK_REPLAY")
    return {strategy: len(worlds) for strategy, worlds in reopen_worlds.items()}


def verify_readout(training, readout):
    require(readout.get("schema") == READOUT_SCHEMA and
            readout.get("physical_goal250_tick_dwell_primary") is True and
            readout.get("new_model_promotion_authorized") is False and
            readout.get("dev_cal_test_ood_opened") is False,
            "V11_INDEPENDENT_PAIRED_READOUT_SOURCE_BINDING_FAILED")
    summaries = readout.get("strategies", {})
    require(set(summaries) == set(EXPECTED_STRATEGIES),
            "V11_INDEPENDENT_PAIRED_READOUT_WRONG_ARMS")
    actual_near = sorted({r["seed"] for r in training["trials"]
                          if r["observed_corridor"]})
    actual_clear = sorted({r["seed"] for r in training["trials"]
                           if not r["observed_corridor"]})
    require(len(actual_near) == 128 and len(actual_clear) == 32,
            "V11_INDEPENDENT_PAIRED_COHORT_LISTS_NOT_RAW_OBSERVATIONS")
    for name in EXPECTED_STRATEGIES:
        rows = [r for r in training["trials"] if r["strategy"] == name]
        safe = [r for r in rows if r["success"] and not r["unsafe"]
                and not r["abstained"]]
        require(len(rows) == 160 and
                set(summaries[name]) == {"safe_goals", "unsafe", "near_safe_goals",
                                         "clear_safe_goals"} and
                summaries[name]["unsafe"] == sum(r["unsafe"] for r in rows) and
                summaries[name]["safe_goals"] == len(safe) and
                summaries[name]["near_safe_goals"] == sum(
                    r["observed_corridor"] for r in safe) and
                summaries[name]["clear_safe_goals"] == sum(
                    not r["observed_corridor"] for r in safe),
                "V11_INDEPENDENT_PAIRED_SCIENCE_COUNTS_NOT_RAW")
    rows = {(r["seed"], r["strategy"]): r for r in training["trials"]}
    losses, new_goals, new_unsafe = [], [], []
    for seed in sorted(actual_near + actual_clear):
        candidate = rows[seed, "v11_goal_preserving"]
        safe_goal = (candidate["success"] and not candidate["unsafe"]
                     and not candidate["abstained"])
        old_row = rows[seed, "frozen_v5"]
        old = old_row["success"] and not old_row["unsafe"] and not old_row["abstained"]
        if old and not safe_goal:
            losses.append(seed)
        if safe_goal and not old:
            new_goals.append(seed)
        if candidate["unsafe"]:
            new_unsafe.append(seed)
    expected_gate = ("CANDIDATE_FOR_INDEPENDENT_QUALIFICATION" if
                     not losses and not new_unsafe and new_goals else
                     "NO_GO_LOST_GOAL_UNSAFE_OR_ZERO_NOVEL")
    require(readout["lost_frozen_v5_goal_seed_ids"] == losses and
            readout["novel_v11_safe_goal_seed_ids"] == new_goals and
            readout["unsafe_v11_seed_ids"] == new_unsafe and
            readout["source_only_preliminary_training_gate"] == expected_gate,
            "V11_INDEPENDENT_PAIRED_WIN_LOSS_NOT_FROM_ORIGINAL_TRIALS")


def replay_clear_goal_successes(evidence_dir, training, env_factory,
                                policy_factory, world_signature, near):
    """Physically re-execute *all* claimed clear-corridor safe goal successes.

    The original V7 replayer already covers every near success / significant
    near lateral movement. This disjoint independent replay closes its clear-
    goal gap without changing V7's frozen selection logic or verifier.
    """
    selected = {(r["seed"], r["strategy"]): r for r in training["trials"]
                if not r["observed_corridor"] and r["success"] and
                not r["unsafe"] and not r["abstained"]}
    seen = set()
    env = env_factory()
    with gzip.open(evidence_dir / "full_transitions.jsonl.gz", "rt",
                   encoding="utf8") as stream:
        for line in stream:
            doc = json.loads(line)
            key = (doc["seed"], doc["strategy"])
            if key not in selected:
                continue
            require(key not in seen, "V11_CLEAR_GOAL_DUPLICATE_OR_UNKNOWN_TRACE")
            row = selected[key]
            observation = env.reset(seed=doc["seed"], ood=False)
            require(world_signature(env) == row["world_hash"] and
                    near(observation, doc["transitions"][0]["observation"]),
                    "V11_CLEAR_GOAL_PHYSICS_WORLD_SOURCE_CHANGED")
            controller = policy_factory(doc["strategy"])()
            last_info = None
            max_dwell = 0
            for idx, event in enumerate(doc["transitions"]):
                require(near(observation, event["observation"]),
                        "V11_CLEAR_GOAL_TRUE_PHYSICS_BEFORE_OBSERVATION_CHANGED")
                original_mask = env.mask(observation)
                require([int(x) for x in original_mask] == event["mask"] and
                        int(original_mask[event["action"]]) == 1,
                        "V11_CLEAR_GOAL_ORIGINAL_SEVEN_MASK_VIOLATED")
                proposed = controller(observation.copy(), original_mask.copy())
                require(type(proposed) is int and proposed == event["action"],
                        "V11_CLEAR_GOAL_FROZEN_POLICY_ACTION_NOT_REPRODUCED")
                observation, reward, done, info = env.step(proposed)
                max_dwell = max(max_dwell, int(env.dwell))
                require(near(observation, event["next_observation"]) and
                        abs(float(reward) - float(event["reward"])) <= 1e-5 and
                        bool(done) == event["done"] and
                        int(info["cost"]) == event["cost"] and
                        int(info["contacts"]) == event["contacts_cumulative"] and
                        bool(info["success"]) == event["success_info"] and
                        max_dwell == event["dwell_ticks_cumulative"] and
                        int(env.dwell) == event["dwell_ticks_current"] and
                        (not done or idx == len(doc["transitions"]) - 1),
                        "V11_CLEAR_GOAL_TRUE_PHYSICS_TRANSITION_DIVERGED")
                last_info = info
            require(last_info is not None and bool(env.done) and
                    bool(last_info["success"]) and not bool(last_info["unsafe"]) and
                    not bool(last_info["abstained"]) and
                    int(env.dwell) >= 250 and int(env.contacts) > 0 and
                    int(env.steps) == row["option_steps"] and
                    int(env.physics_steps) == row["physics_steps"] and
                    int(last_info["contacts"]) == row["contacts"] and
                    abs(float(last_info["error"]) - row["final_error"]) < 1e-5,
                    "V11_CLEAR_GOAL_FROZEN_MUJOCO_TERMINAL_DWELL_NOT_REPRODUCED")
            seen.add(key)
    require(seen == set(selected), "V11_CLEAR_GOAL_POSITIVE_PHYSICS_REPLAY_INCOMPLETE")
    sorted_keys = sorted([list(key) for key in seen])
    key_sha = hashlib.sha256(json.dumps(sorted_keys, sort_keys=True,
                                       separators=(",", ":")).encode()).hexdigest()
    return {"schema": "junction.rokoko.mujoco-v11-clear-goal-replay.v1",
            "claimed_safe_clear_goal_trajectories": len(selected),
            "replayed_safe_clear_goal_trajectories": len(seen),
            "verified_clear_goal_trial_keys_sha256": key_sha,
            "claim_verified": True, "dev_cal_test_ood_opened": False,
            "model_promotion_authorized": False}


def replay_all_512_initial_public_worlds(training, env_factory, signature, near):
    """Independent genuine MuJoCo replay of EVERY preregistered public start.

    The 512-scan science fixture is more stringent than legacy shortest-prefix
    selection. No reward, hidden state, post-outcome training signal is used.
    """
    worlds = training["all_512_public_initial_scans"]
    require(len(worlds) == 512, "V11_PUBLIC_INITIAL_SCAN_COUNT_NOT_512")
    env = env_factory()
    digest = hashlib.sha256()
    for offset, frame in enumerate(worlds):
        seed = TRAIN_FIRST + offset
        obs = env.reset(seed=seed, ood=False)
        mask = env.mask(obs)
        require(frame["seed"] == seed and near(obs, frame["observation"]) and
                [int(x) for x in mask] == frame["mask"] and
                signature(env) == frame["world_hash"],
                "V11_ALL_512_REAL_MUJOCO_PUBLIC_STARTS_DIFFER_FROM_SOURCE")
        digest.update(json.dumps(frame, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False).encode())
        digest.update(b"\n")
    return {"count": 512, "public_start_lines_sha256": digest.hexdigest(),
            "independent_exact_real_mujoco_start_replay": True}


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
            "V11_CRACI_CLEAN_EXACT_PRODUCT_SOURCE_REQUIRED")
    harness_head = os.environ["CRACI_HARNESS_SHA"]
    require(SHA40.fullmatch(harness_head) is not None and
            subprocess.check_output(["git", "-C", str(harness_root),
                                     "rev-parse", "HEAD"], text=True).strip() ==
            harness_head,
            "V11_CRACI_EXACT_SEPARATE_EXECUTION_HARNESS_SHA_REQUIRED")
    require(os.environ.get("CRACI_WORKLOAD") == "rokoko-mujoco-v11-prospective" and
            subprocess.run(["git", "-C", str(source_root), "merge-base",
                            "--is-ancestor", V10_SOURCE_HEAD, "HEAD"],
                           capture_output=True).returncode == 0,
            "V11_CRACI_WRONG_WORKLOAD_OR_PRODUCT_LINEAGE")
    # Only the workflow controller may admit a new long job before the credit
    # cutoff. Check the explicit source-bound receipt of that admission too.
    require(os.environ.get("CRACI_CREDIT_WINDOW_OPEN") == "true" and
            float(os.environ.get("CRACI_CREDIT_REMAINING_SECONDS", "0")) >= 3600,
            "V11_CRACI_MIN_3600S_CREDIT_WINDOW_ADMISSION_REQUIRED")
    python = Path(os.environ["RUNNER_TEMP"]) / "mujoco-venv/bin/python"
    require(python.is_file(), "V11_CRACI_ORIGINAL_PINNED_MUJOCO_VENV_REQUIRED")
    product = source_root / PRODUCT
    private_dir = Path(os.environ["RUNNER_TEMP"]) / "v11-reviewed-private-checkpoint"
    inputs = verify_frozen_input_files(source_root, private_dir)
    subprocess.run([str(python), "-B", "-c",
                    "import mujoco,numpy,sys;"
                    "assert mujoco.__version__=='3.3.7';"
                    "assert numpy.__version__=='2.3.4';"
                    "assert sys.prefix!=sys.base_prefix"],
                   cwd=source_root, check=True)
    subprocess.run([str(python), "-B", "-m", "unittest", "discover", "-q",
                    "-s", str(product), "-p", "test_learning.py"],
                   cwd=source_root, check=True)
    # CRITICAL: 800 full sparse trial summaries are ~22 MiB, above the 20 MiB
    # individual CRACI collector gate. Neither originals nor temporary files
    # ever enter CRACI_RECEIPT_DIR. The whole original is independently read
    # from private runner temp before being losslessly ZIP-published.
    output = Path(os.environ["RUNNER_TEMP"]) / "v11-prospective-private-originals"
    require(not output.exists(), "V11_CRACI_NON_OVERWRITING_OUTPUT_REQUIRED")
    result = subprocess.run([
        str(python), "-B", str(product / "prospective_train.py"),
        "--mode", "prospective-train", "--require-git",
        "--expected-head", head,
        "--v10-weights", str(inputs["candidate-weights.json"]),
        "--v8-weights", str(inputs["weights.json"]),
        "--v8-training-receipt", str(inputs["training-receipt.json"]),
        "--output-dir", str(output), "--time-budget-seconds", "1800",
    ], cwd=source_root, check=False, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    # Source producer must finish; no truncated or interrupted run is
    # "salvaged" by reducing trials or falling back to synthetic traces.
    require(result.returncode == 0,
            "V11_CRACI_REAL_PRODUCT_PRODUCER_EXIT_NONZERO")
    subprocess.run([
        str(python), "-B", str(product / "qualification_inputs.py"),
        "--original-dir", str(output), "--expected-head", head,
        "--out", str(output / "source-integrity.json"),
    ], cwd=source_root, check=True,
       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    # Never transform or package originals until source/physics qualifier has
    # read BOTH full raw streams, every public shield and every claimed gain.
    v7 = import_verified(harness_root /
                         "scripts/craci/rokoko-mujoco-v7-feasibility-qualification.py",
                         "independent_v7_unchanged_true_physics_verifier")
    training = v7.read_json(output / "training.json")
    manifest = v7.read_json(output / "manifest.json")
    require(manifest.get("executed_head") == head and
            all(sha_file(output / name) == digest
                for name, digest in manifest["file_sha256"].items()),
            "V11_CRACI_ALL_THREE_ORIGINAL_MANIFEST_SHAS_REQUIRED")
    check, legacy = verify_independent_comparison(
        training, manifest, head, output, v7)
    readout_path = output / "paired-readout.json"
    require(sha_file(readout_path) == manifest["file_sha256"]["paired-readout.json"],
            "V11_INDEPENDENT_READOUT_FILE_SHA_INVALID")
    readout = v7.read_json(readout_path, max_bytes=1024 * 1024)
    verify_readout(training, readout)
    sys.path.insert(0, str(source_root / PRODUCT.parent))
    from physics import MovingContactEnv
    require(str(Path(sys.modules["physics"].__file__).resolve()) ==
            str((source_root / PRODUCT.parent / "physics.py").resolve()),
            "V11_CRACI_ORIGINAL_MUJOCO_PHYSICS_IMPORT_MISMATCH")
    reopened = independent_masks_and_reopens(
        output, training, lambda: MovingContactEnv(max_options=60))
    check["independent_five_way_forward_reopen_worlds"] = reopened
    replayer = import_verified(harness_root /
                               "scripts/craci/rokoko-mujoco-v7-positive-replay.py",
                               "v11_independent_true_physics_policy_replayer")
    product_module = import_verified(
        source_root / PRODUCT.parent / "v10_prospective/run.py",
        "v11_independent_verified_frozen_v10_policy_factory")
    product_module.verify_historical_source(source_root)
    v7_source, _ = product_module.v8.import_v7_and_physics()
    frozen_v8, _, _ = product_module.v8.verify_frozen_model(
        inputs["weights.json"], inputs["training-receipt.json"],
        product_module.v8.FROZEN_WEIGHTS_SHA256)

    # Never let generic Python module names resolve to an unrelated policy.
    expected_learner = product / "learn_gate.py"
    if "learn_gate" in sys.modules:
        require(Path(sys.modules["learn_gate"].__file__).resolve() ==
                expected_learner.resolve(),
                "V11_CRACI_GENERIC_LEARN_GATE_IMPORT_COLLISION")
    sys.path.insert(0, str(product))
    v11_policy = import_verified(product / "policy.py",
                                  "v11_independent_source_bound_policy_factory")
    require(Path(sys.modules["learn_gate"].__file__).resolve() ==
            expected_learner.resolve() and
            sha_file(product / "frozen-v10-train-approved/gate.json") ==
            V11_GATE_SHA,
            "V11_CRACI_GATE_MODULE_OR_SOURCE_SHA_DRIFT")
    frozen_v10_factory = product_module.v10.policy_factory(
        inputs["candidate-weights.json"])
    frozen_factories = {
        name: product_module.policy_factory(
            name, inputs["candidate-weights.json"], frozen_v8, frozen_v7=v7_source)
        for name in EXPECTED_STRATEGIES if name != "v11_goal_preserving"
    }
    frozen_factories["v11_goal_preserving"] = v11_policy.policy_factory(
        frozen_factories["frozen_v5"], frozen_v10_factory,
        product / "frozen-v10-train-approved/gate.json")

    def independent_factory(name):
        require(name in frozen_factories,
                "V11_CRACI_UNREGISTERED_FROZEN_OR_CANDIDATE_POLICY")
        return frozen_factories[name]

    signature = v7_source.v6.v5.v4.v3.v2.v1._world_signature
    initial_replay = replay_all_512_initial_public_worlds(
        training, lambda: MovingContactEnv(max_options=60),
        signature, replayer.near)
    # This *derived*, private replay view is required only because original
    # V7 verifier reads selection_scan from a file. Original V11 3-file
    # manifest and its 512 raw public scans stay byte-for-byte unchanged.
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="v11-private-v7-replay-view-",
                                     dir=runner_temp) as replay_tmp:
        replay_dir = Path(replay_tmp)
        with (replay_dir / "training.json").open("x", encoding="utf8") as sink:
            json.dump(legacy, sink, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
            sink.write("\n")
        shutil.copyfile(output / "full_transitions.jsonl.gz",
                        replay_dir / "full_transitions.jsonl.gz")
        require(sha_file(replay_dir / "full_transitions.jsonl.gz") ==
                manifest["file_sha256"]["full_transitions.jsonl.gz"],
                "V11_PRIVATE_POSITIVE_REPLAY_COPY_NOT_EXACT")
        replay = replayer.replay_positive(
            replay_dir, lambda: MovingContactEnv(max_options=60),
            independent_factory, signature)
    require(replay["claim_verified"] is True and
            replay["selection_scan_replayed"] >= 160 and
            replay["verified_near_corridor_success_worlds"] ==
            check["worlds_safe_corridor_success"],
            "V11_INDEPENDENT_TRUE_PHYSICS_POSITIVE_POLICY_REPLAY_FAILED")
    clear_replay = replay_clear_goal_successes(
        output, training, lambda: MovingContactEnv(max_options=60),
        independent_factory, signature, replayer.near)
    require(clear_replay["claim_verified"] is True and
            clear_replay["replayed_safe_clear_goal_trajectories"] ==
            sum(readout["strategies"][name]["clear_safe_goals"]
                for name in EXPECTED_STRATEGIES),
            "V11_INDEPENDENT_CLEAR_CORRIDOR_GOAL_POLICY_REPLAY_FAILED")
    candidate_unsafe = readout["strategies"]["v11_goal_preserving"]["unsafe"]
    losses = readout["lost_frozen_v5_goal_seed_ids"]
    novel = readout["novel_v11_safe_goal_seed_ids"]
    # Even an unsafe trial must remain in the immutable evidence.  It is an
    # explicit science STOP, never a reason to suppress/retry inconvenient
    # worlds or alter the original safety mask after outcome inspection.
    check.update(schema="junction.rokoko.v11-prospective.craci.train.v1",
                 decision="valid_source_bound_five_way_train_only_evidence",
                 independent_full_trace_public_mask_replay=True,
                 all_512_real_initial_worlds_replayed=True,
                 independent_all_512_initial_public_replay=initial_replay,
                 independent_true_physics_positive_replay=replay,
                 independent_true_physics_clear_goal_replay=clear_replay,
                 experiment_complete=True, producer_exit_code=result.returncode,
                 independentHoldout=False, model_improvement_verified=False,
                 candidate_unsafe_trials=candidate_unsafe,
                 lost_v5_goal_seed_ids=losses,
                 novel_v11_safe_goal_seed_ids=novel,
                 source_gate_sha256=V11_GATE_SHA, plan_sha256=V11_PLAN_SHA,
                 original_three_files_sha256=manifest["file_sha256"],
                 source_only_precheck="source-integrity.json",
                 science_gate=("STOP_UNSAFE_LOST_OR_ZERO_NOVEL" if
                               candidate_unsafe or losses or not novel else
                               "TRAIN_ONLY_HYPOTHESIS_READY_FOR_SEPARATE_REVIEW"),
                 promotion_authorized=False, dev_cal_test_ood_opened=False,
                 science_warning="Physical-goal delta is TRAIN-only and needs separate review")
    with (output / "independent-positive-replay.json").open("x", encoding="utf8") as file:
        json.dump(replay, file, indent=2, sort_keys=True)
        file.write("\n")
    with (output / "independent-clear-goal-replay.json").open("x", encoding="utf8") as file:
        json.dump(clear_replay, file, indent=2, sort_keys=True)
        file.write("\n")
    with (output / "independent-qualification.json").open("x", encoding="utf8") as file:
        json.dump(check, file, indent=2, sort_keys=True)
        file.write("\n")
    collector_output = receipt_root / "artifacts" / "rokoko-mujoco-v11-prospective"
    require(not collector_output.exists(), "V11_CRACI_COLLECTOR_PREEXISTING_OUTPUT")
    packer = import_verified(harness_root /
                             "scripts/craci/rokoko-mujoco-v11-retain-evidence.py",
                             "v11_private_after_full_original_qualification_packer")
    packed = packer.publish_private_source(output, collector_output)
    require(packed["source_count"] == 2 and packed["archives"] >= 2 and
            packed["exact_source_sha"] == head and
            packed["original_sha256"] == manifest["file_sha256"],
            "V11_CRACI_PACKED_COLLECTOR_EVIDENCE_NOT_EXACT_OR_COMPLETE")
    print(json.dumps({"source_head": head, "producer_exit": result.returncode,
                      "trials": check["trials"],
                      "option_transitions": check["actual_real_option_transitions"],
                      "policy_replayed_positive": replay["fully_replayed_positive_train_trials"],
                      "policy_replayed_clear_goal":
                      clear_replay["replayed_safe_clear_goal_trajectories"],
                      "losslessly_packed_originals": packed["source_count"],
                      "collector_published_bytes": packed["collector_bytes"],
                      "unsafe_v11_total": candidate_unsafe,
                      "safe_v11_near_goals": readout["strategies"]["v11_goal_preserving"]["near_safe_goals"],
                      "lost_v5_goals": len(losses),
                      "novel_v11_goals": len(novel),
                      "promotion_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
