#!/usr/bin/env python3
"""Exact-source CRACI validator for a *training* run followed by fresh dev evaluation.

The trainer is product-owned and may produce a scientific RED. This validator
never transforms that result into a pass, and never samples cal/test/OOD.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import subprocess
import sys


PRODUCT = Path(
    "solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v6_learning"
)
TRAIN_FIRST = 511_000  # Frozen ContactEnv.reset permits 120000 <= seed < 520000
TRAIN_COUNT = 48
DEV_FIRST = 129_250
DEV_COUNT = 80
POLICIES = ("constant", "learned_v5", "learned_v6")
SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
HASH = re.compile(r"^[0-9a-f]{64}$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_json(path: Path):
    require(path.is_file() and not path.is_symlink(), f"missing or symlink evidence {path.name}")
    require(path.stat().st_size <= 32 * 1024 * 1024, f"oversized evidence {path.name}")
    with path.open(encoding="utf8") as handle:
        return json.load(handle)


def canonical_sha256(value) -> str:
    """Exact payload bytes used by the product trainer, not a producer claim."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf8")).hexdigest()


def paired_ci_from_worlds(worlds: list[dict]) -> list[float]:
    """Reproduce unchanged frozen MuJoCo bootstrap from raw paired successes."""
    differences = [int(w["learned_v6"]["success"]) - int(w["constant"]["success"])
                   for w in worlds]
    require(differences, "EMPTY_PAIRED_SCIENCE_COHORT")
    rng = random.Random(20261114)
    n, draws = len(differences), 2000
    means = sorted(sum(differences[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(draws))
    return [round(100 * means[int(.025 * (draws - 1))], 3),
            round(100 * means[int(.975 * (draws - 1))], 3)]


def finite_vector(x, length: int) -> bool:
    return (isinstance(x, list) and len(x) == length and
            all(type(v) in (int, float) and math.isfinite(v) for v in x))


def verify_dev_receipt(training: dict, model: dict, dev: dict, source: str) -> dict:
    """Contract assertions independent of the producer's claimed verdict."""
    require(429_199 < TRAIN_FIRST and 120_000 <= TRAIN_FIRST and
            TRAIN_FIRST + TRAIN_COUNT <= 520_000,
            "TRAIN_SEEDS_OUTSIDE_FROZEN_MUJOCO_ENV_ADMISSIBLE_RANGE")
    require(SOURCE_SHA.fullmatch(source) is not None, "INVALID_EXACT_SOURCE_SHA")
    require(training.get("executed_head") == source, "TRAIN_SOURCE_MISMATCH")
    require(dev.get("executed_head") == source, "DEV_SOURCE_MISMATCH")
    require(model.get("executed_head") == source, "MODEL_SOURCE_MISMATCH")
    require(training.get("actual_physics_engine") == "mujoco-3.3.7",
            "ACTUAL_TRAINING_PHYSICS_VERSION_REQUIRED")
    require(HASH.fullmatch(training.get("dataset_sha256", "")) is not None,
            "UNHASHED_DATASET")
    require(HASH.fullmatch(training.get("weights_sha256", "")) is not None,
            "UNHASHED_WEIGHTS")
    require(training.get("actual_transition_count", 0) > 0,
            "NO_REAL_LEARNING_TRANSITIONS")
    require(isinstance(training.get("rollouts"), list) and training["rollouts"],
            "NO_ACTUAL_TRAINING_ROLLOUTS")
    require(all(isinstance(row, dict) and isinstance(row.get("transitions"), list)
                for row in training["rollouts"]), "INVALID_TRAINING_EPISODE_SCHEMA")
    by_candidate = {}
    for row in training["rollouts"]:
        generation, candidate = row.get("generation"), row.get("candidate")
        require(type(generation) is int and generation in (0, 1) and
                type(candidate) is int and candidate in (0, 1, 2),
                "UNEXPECTED_TRAINING_GENERATION_OR_CANDIDATE")
        require(type(row.get("seed")) is int and
                TRAIN_FIRST <= row["seed"] < TRAIN_FIRST + TRAIN_COUNT,
                "TRAINING_ROLLOUT_CONTAINS_EXPOSED_OR_HELDOUT_SEED")
        require(HASH.fullmatch(row.get("world_hash", "")) is not None,
                "UNHASHED_TRAINING_WORLD_IDENTITY")
        by_candidate.setdefault((generation, candidate), []).append(row["seed"])
        require(row["transitions"], "EMPTY_TRAINING_TRANSITION_SEQUENCE")
        for event in row["transitions"]:
            require(isinstance(event, dict) and
                    finite_vector(event.get("observation"), 18) and
                    finite_vector(event.get("next_observation"), 18),
                    "TRAINING_TRANSITION_WITHOUT_OBSERVED_STATE")
            mask = event.get("mask")
            action = event.get("action")
            require(isinstance(mask, list) and len(mask) == 7 and
                    all(type(v) is int and v in (0, 1) for v in mask) and
                    type(action) is int and 0 <= action < 7 and mask[action] == 1,
                    "TRAINING_TRANSITION_BYPASSED_SHARED_SHIELD")
            require(type(event.get("reward")) in (int, float) and
                    math.isfinite(event["reward"]) and
                    type(event.get("cost")) is int and event["cost"] in (0, 1) and
                    type(event.get("done")) is bool,
                    "INVALID_TRAINING_REWARD_OR_SAFETY_COST")
    require(set(by_candidate) == {(g, c) for g in (0, 1) for c in (0, 1, 2)} and
            all(sorted(seeds) == list(range(TRAIN_FIRST, TRAIN_FIRST + TRAIN_COUNT))
                for seeds in by_candidate.values()),
            "INCOMPLETE_OR_DUPLICATED_SIX_CANDIDATE_TRAINING_COHORT")
    require(sum(len(row["transitions"]) for row in training["rollouts"]) ==
            training["actual_transition_count"], "TRAINING_TRANSITION_COUNT_MISMATCH")
    require(training["dataset_sha256"] == canonical_sha256(training["rollouts"]),
            "FORGED_TRAINING_DATASET_DIGEST")
    require(isinstance(model.get("weights"), dict) and model["weights"],
            "NO_LEARNED_MODEL_WEIGHTS")
    require(training["weights_sha256"] == canonical_sha256(model["weights"]),
            "FORGED_CANDIDATE_WEIGHTS_DIGEST")
    require(training.get("selected", {}).get("weights") == model["weights"],
            "SELECTED_MODEL_IS_NOT_FROZEN_WEIGHTS")
    require(dev.get("split") == "dev", "NOT_DEVELOPMENT_ONLY")
    require(dev.get("actual_physics_engine") == "mujoco-3.3.7",
            "ACTUAL_REAL_PHYSICS_VERSION_REQUIRED")
    require(dev.get("first_seed") == DEV_FIRST and dev.get("episodes") == DEV_COUNT,
            "EXPOSED_OR_WRONG_DEV_SEED_COHORT")
    require(training.get("train_first_seed") == TRAIN_FIRST and
            training.get("train_episodes") == TRAIN_COUNT, "UNREGISTERED_TRAIN_COHORT")
    # No parameters inferred from dev rows, and all per-world comparisons are
    # identical initial worlds. Model-hash and dataset-hash must be carried
    # through both artifacts to make a switched candidate observable.
    require(model.get("weights_sha256") == training["weights_sha256"] ==
            dev.get("weights_sha256"), "CANDIDATE_WEIGHT_BINDING_MISMATCH")
    require(dev.get("dataset_sha256") == training["dataset_sha256"],
            "TRAIN_DATASET_BINDING_MISMATCH")
    require(model.get("dataset_sha256") == training["dataset_sha256"],
            "MODEL_TRAIN_DATASET_BINDING_MISMATCH")
    worlds = dev.get("paired_worlds")
    require(isinstance(worlds, list) and len(worlds) == DEV_COUNT,
            "MISSING_RAW_PAIRED_DEVELOPMENT_WORLDS")
    counts = {name: {"success": 0, "unsafe": 0, "abstain": 0} for name in POLICIES}
    for offset, world in enumerate(worlds):
        require(isinstance(world, dict) and set(world) == set(POLICIES),
                "NONPAIRED_POLICY_ARMS")
        hashes = set()
        for name in POLICIES:
            row = world[name]
            require(isinstance(row, dict) and row.get("seed") == DEV_FIRST + offset,
                    "DEVELOPMENT_WORLD_ORDER_OR_SEED_MISMATCH")
            wh = row.get("world_hash")
            require(isinstance(wh, str) and HASH.fullmatch(wh) is not None,
                    "UNHASHED_WORLD_IDENTITY")
            hashes.add(wh)
            for field in ("success", "unsafe", "abstained", "zero_physics_abstain"):
                require(type(row.get(field)) is bool, "UNQUALIFIED_EPISODE_BOOLEAN")
            steps = row.get("physics_steps")
            require(type(steps) is int and steps >= 0, "INVALID_MUJOCO_PHYSICS_STEPS")
            require(not (row["success"] and (row["unsafe"] or row["abstained"])),
                    "UNSAFE_OR_ABSTAINED_SUCCESS_CLAIM")
            if steps == 0:
                require(row["abstained"] and row["zero_physics_abstain"] and
                        not row["success"] and not row["unsafe"] and
                        row.get("option_steps") == 1,
                        "INVENTED_ZERO_STEP_PHYSICS_OR_SUCCESS")
            else:
                require(not row["zero_physics_abstain"], "ZERO_STEP_FLAG_WITH_REAL_PHYSICS")
            counts[name]["success"] += int(row["success"])
            counts[name]["unsafe"] += int(row["unsafe"])
            counts[name]["abstain"] += int(row["abstained"])
        require(len(hashes) == 1, "UNMATCHED_MUJOCO_INITIAL_WORLD")
    summary = dev.get("summaries", {}).get("learned_v6", {})
    require(summary.get("candidate_success") == counts["learned_v6"]["success"] and
            summary.get("constant_success") == counts["constant"]["success"] and
            summary.get("candidate_unsafe") == counts["learned_v6"]["unsafe"] and
            summary.get("constant_unsafe") == counts["constant"]["unsafe"],
            "SUMMARY_COUNTS_DO_NOT_MATCH_RAW_WORLDS")
    ci = summary.get("paired_bootstrap95_pp")
    require(isinstance(ci, list) and len(ci) == 2 and
            all(type(x) in (int, float) and -100 <= x <= 100 for x in ci) and
            ci[0] <= ci[1], "INVALID_PAIRED_CONFIDENCE_INTERVAL")
    require(ci == paired_ci_from_worlds(worlds),
            "PRODUCER_CONFIDENCE_INTERVAL_NOT_REPRODUCED_FROM_RAW_PAIRED_WORLDS")
    # Preserve the frozen v5 and constant safety performance; no safety-cost
    # regression is accepted in exchange for task success.
    scientific_ok = (
        counts["learned_v6"]["success"] > counts["constant"]["success"]
        and counts["learned_v6"]["success"] >= counts["learned_v5"]["success"]
        and counts["learned_v6"]["unsafe"] <= counts["constant"]["unsafe"]
        and counts["learned_v6"]["unsafe"] <= counts["learned_v5"]["unsafe"]
        and ci[0] > 0
    )
    # A failed *development* world is evidence about a failure category, not
    # permission to replay that world as new training or a fresh holdout.
    lost_to_constant = sum(
        int(w["constant"]["success"] and not w["learned_v6"]["success"])
        for w in worlds
    )
    lost_to_v5 = sum(
        int(w["learned_v5"]["success"] and not w["learned_v6"]["success"])
        for w in worlds
    )
    novel_wins_over_v5 = sum(
        int(w["learned_v6"]["success"] and not w["learned_v5"]["success"])
        for w in worlds
    )
    # Reject net-positive numbers that silently sacrifice worlds already solved
    # by either frozen baseline; demand a genuine prospective new skill.
    scientific_ok = (scientific_ok and lost_to_constant == 0 and
                     lost_to_v5 == 0 and novel_wins_over_v5 >= 5)
    failure_priority = (
        "learn_contact_risk_on_fresh_train_seeds"
        if counts["learned_v6"]["unsafe"] > min(counts["constant"]["unsafe"],
                                                  counts["learned_v5"]["unsafe"])
        else "reduce_safe_refusals_or_stalls_on_fresh_train_seeds"
        if counts["learned_v6"]["abstain"] or lost_to_constant or lost_to_v5
        else "increase_robust_success_on_fresh_train_seeds"
    )
    return {
        "schema": "junction.rokoko.mujoco-v6-learning.craci.dev.v1",
        "exact_source_sha": source,
        "training_transitions": training["actual_transition_count"],
        "train_only_first_seed": TRAIN_FIRST,
        "fresh_dev_first_seed": DEV_FIRST,
        "dev_world_count": DEV_COUNT,
        "dataset_sha256": training["dataset_sha256"],
        "weights_sha256": training["weights_sha256"],
        "counts": counts,
        "paired_bootstrap95_pp": ci,
        "failure_mining": {
            "candidate_loses_worlds_constant_wins": lost_to_constant,
            "candidate_loses_worlds_v5_wins": lost_to_v5,
            "candidate_new_wins_v5_misses": novel_wins_over_v5,
            "candidate_unsafe_worlds": counts["learned_v6"]["unsafe"],
            "candidate_abstained_worlds": counts["learned_v6"]["abstain"],
        },
        "next_learning_round": {
            "suggested_failure_class": failure_priority,
            "new_train_only_seed_start": 512_000,
            "new_fresh_dev_seed_start": 129_330,
            "previous_dev_seeds_exposed": True,
            "requires_new_source_and_weight_hashes": True,
            "dispatch_authorized": False,
            "notes": "advisory only; do not train on opened dev/cal/test/OOD worlds",
        },
        "science_gate_passed": scientific_ok,
        "promotion_authorized": False,
        "independent_review_pending": True,
        "prior_v5_red_run": 43635488617,
        "decision": "review_candidate_on_dev_only" if scientific_ok else "science_red_keep_training_evidence",
        "limits": "real MuJoCo CPU dev-only; no calibration/test/OOD; no real robot safety claim",
    }


def main() -> int:
    src = Path(os.environ["CRACI_SOURCE_ROOT"]).resolve()
    receipt_root = Path(os.environ["CRACI_RECEIPT_DIR"]).resolve()
    evidence = receipt_root / "artifacts" / "rokoko-mujoco-v6-learning"
    require(not evidence.exists(), "NO_OVERWRITE_V6_LEARNING_EVIDENCE")
    evidence.mkdir(parents=True)
    requested = os.environ["CRACI_SOURCE_SHA"]
    require(SOURCE_SHA.fullmatch(requested) is not None, "EXACT_COMMIT_SHA_REQUIRED")
    observed = subprocess.check_output(["git", "-C", str(src), "rev-parse", "HEAD"], text=True).strip()
    require(observed == requested, "GIT_SOURCE_PIN_MISMATCH")
    require(subprocess.run(["git", "-C", str(src), "status", "--porcelain"],
                           capture_output=True, text=True, check=True).stdout == "",
            "TRAIN_SOURCE_NOT_CLEAN")
    ancestor = "4987f28540c5319deaa81dff5d700dcac9eab483"
    require(subprocess.run(["git", "-C", str(src), "merge-base", "--is-ancestor",
                            ancestor, requested], check=False).returncode == 0,
            "V6_DOES_NOT_DESCEND_FROM_REVIEWED_V5")
    python = Path(os.environ["RUNNER_TEMP"]) / "mujoco-venv/bin/python"
    require(python.is_file(), "REAL_MUJOCO_PYTHON_MISSING")
    module = src / PRODUCT
    subprocess.run([str(python), "-m", "unittest", "discover", "-v", "-s", str(module),
                    "-p", "test_contract.py"], cwd=src, check=True)
    # This inexpensive *real* MuJoCo smoke catches an invalid world band in
    # the inherited ContactEnv before allocating any six-candidate training.
    subprocess.run([
        str(python), "-c",
        "import sys;sys.path.insert(0,sys.argv[1]);"
        "from physics import MovingContactEnv;"
        f"o=MovingContactEnv(max_options=60).reset(seed={TRAIN_FIRST},ood=False);"
        "assert len(o)==18, 'TRAIN_SEED_PHYSICS_OBSERVATION_ABI_MISMATCH'",
        str(src / PRODUCT.parent),
    ], cwd=src, check=True)
    process = subprocess.run([
        str(python), str(module / "run.py"), "--mode", "train-dev",
        "--require-git", "--expected-head", requested,
        "--train-episodes", str(TRAIN_COUNT), "--dev-episodes", str(DEV_COUNT),
        "--output-dir", str(evidence),
    ], cwd=src, check=False)
    training = load_json(evidence / "training.json")
    model = load_json(evidence / "model.json")
    dev = load_json(evidence / "dev.json")
    manifest = load_json(evidence / "manifest.json")
    require(manifest.get("executed_head") == requested,
            "LEARNING_MANIFEST_SOURCE_MISMATCH")
    file_hashes = manifest.get("file_sha256", {})
    require(isinstance(file_hashes, dict) and
            set(file_hashes) == {"training.json", "model.json", "dev.json"},
            "INCOMPLETE_LEARNING_EVIDENCE_MANIFEST")
    for name, recorded_hash in file_hashes.items():
        require(HASH.fullmatch(recorded_hash) is not None and
                hashlib.sha256((evidence / name).read_bytes()).hexdigest() == recorded_hash,
                "LEARNING_ARTIFACT_BYTES_HASH_MISMATCH")
    result = verify_dev_receipt(training, model, dev, requested)
    result["trainer_exit_code"] = process.returncode
    result["science_gate_passed"] &= process.returncode == 0
    if process.returncode not in (0, 2):
        result["decision"] = "trainer_execution_or_source_failure"
    with (evidence / "qualification.json").open("x", encoding="utf8") as output:
        json.dump(result, output, sort_keys=True, indent=2)
        output.write("\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["science_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
