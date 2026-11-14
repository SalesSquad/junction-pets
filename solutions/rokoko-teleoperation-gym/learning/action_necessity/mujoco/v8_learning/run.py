#!/usr/bin/env python3
"""Train a shield-masked hierarchical option policy from qualified MuJoCo V7 TRAIN traces.

This is actual gradient-based imitation learning, not a claim of a better
controller. V7 exposed a safe lateral maneuver (repeat_left) and just two
near-world goal witnesses (frozen v5/v6). This trainer learns four stages from
their source-verified raw observations/actions, never simulator private state.
No existing dev/calibration/test/OOD set is opened, and there is no promotion.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess

import numpy as np


V7_SOURCE_SHA = "127ceb9be4374ba46908cd398ced6b740275a434"
V7_TRAIN_SCHEMA = "junction.rokoko.mujoco-v7.action-feasibility.v1.training"
V7_QUAL_SCHEMA = "junction.rokoko.mujoco-v7-feasibility.craci.train.v1"
SCHEMA = "junction.rokoko.mujoco-v8.hierarchical-imitation.v1"
TRAIN_SEED_MIN = 512_000
TRAIN_SEED_MAX = 512_511
NEXT_TRAIN_SEED_MIN = 513_000
EXPECTED_TRIALS = 1280
EXPECTED_WORLD_COUNT = 160
EXPECTED_STRATEGIES = ("frozen_v5", "frozen_v6", "repeat_left", "repeat_right",
                       "align_left", "align_right", "retreat_left", "observed_branch")
ACTION_COUNT = 7
OBSERVATION_COUNT = 18
STAGE_COUNT = 4
RANDOM_SEED = 20261114
LEARNING_RATE = .055
L2 = .003
EPOCHS = 55
FEATURE_COUNT = 41
EVIDENCE_DIR_FILES = ("training.json", "full_transitions.jsonl.gz", "manifest.json",
                      "independent-qualification.json", "independent-positive-replay.json")


def require(ok, code):
    if not ok:
        raise ValueError(code)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf8")


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def read_json(path):
    with path.open(encoding="utf8") as stream:
        return json.load(stream)


def write_new(path, payload):
    with path.open("x", encoding="utf8") as stream:
        stream.write(json.dumps(payload, sort_keys=True, indent=2,
                                ensure_ascii=False, allow_nan=False) + "\n")


def source_identity(expected_head):
    require(isinstance(expected_head, str) and len(expected_head) == 40 and
            all(c in "0123456789abcdef" for c in expected_head),
            "EXACT_V8_GIT_SOURCE_REQUIRED")
    root = Path(__file__).resolve().parent
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                   text=True, timeout=10).strip()
    require(head == expected_head, "V8_SOURCE_HEAD_MISMATCH")
    dirty = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain=v1",
                                     "--untracked-files=no"], text=True, timeout=10).strip()
    require(not dirty, "V8_TRACKED_SOURCE_DIRTY")
    base = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor",
                           V7_SOURCE_SHA, "HEAD"], capture_output=True, timeout=10)
    require(base.returncode == 0, "V8_NOT_DESCENDED_FROM_REVIEWED_V7")
    return head, Path(subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        text=True, timeout=10).strip()).resolve(strict=True)


def verified_v7_evidence(root):
    """Validate immutable source, independent physics proof, and all raw SHA claims."""
    require(root.is_dir() and all((root / name).is_file()
                                  for name in EVIDENCE_DIR_FILES),
            "V7_FULL_RESTORED_EVIDENCE_REQUIRED")
    manifest = read_json(root / "manifest.json")
    expected = manifest.get("file_sha256", {})
    require(set(expected) == {"training.json", "full_transitions.jsonl.gz"} and
            all(file_sha256(root / name) == checksum for name, checksum in expected.items()),
            "V7_FULL_RAW_EVIDENCE_SHA_MISMATCH")
    training = read_json(root / "training.json")
    qualification = read_json(root / "independent-qualification.json")
    replay = read_json(root / "independent-positive-replay.json")
    require(training.get("schema") == V7_TRAIN_SCHEMA and
            training.get("executed_head") == V7_SOURCE_SHA and
            manifest.get("executed_head") == V7_SOURCE_SHA and
            qualification.get("exact_source_sha") == V7_SOURCE_SHA,
            "V7_PINNED_TRAIN_SOURCE_MISMATCH")
    require(training.get("actual_physics_engine") == "mujoco-3.3.7" and
            training.get("no_dev_evaluation") is True and
            qualification.get("schema") == V7_QUAL_SCHEMA and
            qualification.get("experiment_complete") is True and
            qualification.get("dev_cal_test_ood_opened") is False and
            qualification.get("promotion_authorized") is False and
            qualification.get("producer_exit_code") == 0 and
            qualification.get("trials") == EXPECTED_TRIALS,
            "V7_REAL_TRAIN_ONLY_QUALIFICATION_REQUIRED")
    require(replay.get("claim_verified") is True and
            replay.get("model_promotion_authorized") is False and
            replay.get("no_dev_cal_test_ood") is True and
            replay.get("selection_scan_replayed", 0) >= EXPECTED_WORLD_COUNT and
            replay.get("fully_replayed_positive_train_trials", 0) > 0,
            "V7_INDEPENDENT_POSITIVE_PHYSICS_REPLAY_REQUIRED")
    trials = training.get("trials", [])
    require(len(trials) == EXPECTED_TRIALS and
            training.get("selected_near_count") == 128 and
            training.get("selected_clear_count") == 32 and
            training.get("strategies") == list(EXPECTED_STRATEGIES) and
            training.get("train_first_seed") == TRAIN_SEED_MIN and
            training.get("actual_transition_count") ==
            qualification.get("actual_real_option_transitions") and
            digest(trials) == training.get("dataset_sha256") ==
            qualification.get("dataset_sha256"),
            "V7_COMPLETE_PAIRED_TRAIN_DATASET_REQUIRED")
    keymap = {}
    worlds = {}
    for trial in trials:
        seed, strategy = trial["seed"], trial["strategy"]
        require(type(seed) is int and TRAIN_SEED_MIN <= seed <= TRAIN_SEED_MAX and
                strategy in EXPECTED_STRATEGIES and
                (seed, strategy) not in keymap and
                type(trial.get("unsafe")) is bool and
                type(trial.get("success")) is bool and
                type(trial.get("observed_corridor")) is bool,
                "V7_TRAIN_ROW_IDENTITY_INVALID")
        keymap[seed, strategy] = trial
        worlds.setdefault(seed, trial["world_hash"])
        require(worlds[seed] == trial["world_hash"], "V7_WORLD_HASH_UNPAIRED")
    require(len(worlds) == EXPECTED_WORLD_COUNT and
            all(sum(seed == key[0] for key in keymap) == len(EXPECTED_STRATEGIES)
                for seed in worlds), "V7_INCOMPLETE_WORLD_STRATEGY_PAIRS")
    return training, manifest, qualification, replay, keymap


class PublicMemory:
    """No simulator contacts, world hash, seed or hidden dynamics at inference."""
    def __init__(self):
        self.first_object_y = None
        self.away_sign = 1.
        self.ticks = 0
        self.side_steps = 0
        self.last_action = None

    def features(self, observation, mask):
        obs = np.asarray(observation, dtype=np.float64)
        legal = np.asarray(mask, dtype=bool)
        require(obs.shape == (OBSERVATION_COUNT,) and
                legal.shape == (ACTION_COUNT,) and np.all(np.isfinite(obs)) and
                np.any(legal), "V8_PUBLIC_18D_7MASK_ABI")
        if self.first_object_y is None:
            self.first_object_y = float(obs[1])
            self.away_sign = -1. if float(obs[7]) >= float(obs[1]) else 1.
        movement = (float(obs[1]) - self.first_object_y) * self.away_sign
        distance = math.hypot(float(obs[16] - obs[0]), float(obs[17] - obs[1]))
        forward = bool(legal[1] or legal[2])
        if distance < .035:
            stage = 3
        elif movement >= .010 and forward and self.side_steps:
            stage = 2
        elif movement >= .005 and self.side_steps:
            stage = 1
        else:
            stage = 0
        last = np.zeros(ACTION_COUNT)
        if self.last_action is not None:
            last[self.last_action] = 1.
        phases = np.zeros(STAGE_COUNT)
        phases[stage] = 1.
        f = np.concatenate((np.array([1.]), np.clip(obs * 4., -2., 2.),
                            legal.astype(float), last, phases,
                            np.array([np.clip(movement * 20., -2., 2.),
                                      min(self.ticks, 60) / 60.,
                                      min(self.side_steps, 10) / 10.,
                                      np.clip(distance * 5., 0., 2.)])))
        require(f.shape == (FEATURE_COUNT,), "V8_FIXED_FEATURE_CONTRACT")
        return stage, f, legal

    def remember(self, action):
        require(type(action) is int and 0 <= action < ACTION_COUNT,
                "V8_INVALID_REMEMBERED_ACTION")
        self.last_action = action
        self.side_steps += int(action in (3, 4))
        self.ticks += 1


class HierarchicalPolicy:
    """One trained linear-softmax expert per observable stage; mask always wins."""
    def __init__(self, weights):
        self.weights = np.asarray(weights, dtype=np.float64)
        require(self.weights.shape == (STAGE_COUNT, FEATURE_COUNT, ACTION_COUNT) and
                np.all(np.isfinite(self.weights)), "V8_POLICY_WEIGHTS_SHAPE")
        self.memory = PublicMemory()

    def __call__(self, observation, mask):
        stage, features, legal = self.memory.features(observation, mask)
        scores = features @ self.weights[stage]
        scores[~legal] = -np.inf
        action = int(np.argmax(scores))
        require(bool(legal[action]), "V8_POLICY_BYPASSED_ORIGINAL_SHIELD")
        self.memory.remember(action)
        return action


def safe_training_witness(row):
    if not row["observed_corridor"] or row["unsafe"] or row["abstained"]:
        return False
    if row["success"]:
        return True
    # Limited, source-preregistered motor-control curriculum. The six new
    # macros generated zero near goal wins; repeat_left showed 74 safe lateral
    # successes, which remain MOTOR demonstrations, not full task success.
    return (row["strategy"] == "repeat_left" and
            row["away_lateral_displacement"] >= .025)


def training_examples(root, rowmap):
    """Stream all 1,280 raw traces, but fit only safely witnessed TRAIN actions."""
    observed_keys = set()
    examples = []
    per_witness = Counter()
    actual_transitions = 0
    with gzip.open(root / "full_transitions.jsonl.gz", "rt", encoding="utf8") as stream:
        for line in stream:
            doc = json.loads(line)
            key = (doc.get("seed"), doc.get("strategy"))
            require(key in rowmap and key not in observed_keys, "V8_RAW_TRACE_IDENTITY")
            observed_keys.add(key)
            row = rowmap[key]
            transitions = doc.get("transitions", [])
            require(len(transitions) == row["full_transition_count"] and
                    digest(transitions) == row["full_transition_sha256"],
                    "V8_RAW_TRANSITION_HASH_MISMATCH")
            actual_transitions += len(transitions)
            if not safe_training_witness(row):
                continue
            memory = PublicMemory()
            weight = 12. if row["success"] else 1.
            for event in transitions:
                action = event["action"]
                require(type(action) is int and 0 <= action < ACTION_COUNT,
                        "V8_ILLEGAL_TRAINING_ACTION")
                stage, features, legal = memory.features(event["observation"],
                                                         event["mask"])
                require(legal[action] and event["cost"] == 0,
                        "V8_TEACHER_ACTION_OUTSIDE_SHIELD_OR_UNSAFE")
                # Do not fit zero-physics ABSTAIN nor terminal leakage.
                if action != 6:
                    examples.append((row["seed"], stage, features, legal,
                                     action, weight * (1.5 if action in (3, 4) and
                                                    not row["success"] else 1.)))
                memory.remember(action)
            per_witness[row["strategy"]] += 1
    require(observed_keys == set(rowmap), "V8_FULL_TRAINING_ARCHIVE_INCOMPLETE")
    require(len(examples) >= 100 and per_witness["repeat_left"] >= 1 and
            per_witness["frozen_v5"] + per_witness["frozen_v6"] >= 1,
            "V8_SAFE_CURRICULUM_WITNESSES_INSUFFICIENT")
    return examples, per_witness, actual_transitions


def probability(features, masks, weights):
    logits = features @ weights
    logits = np.where(masks, logits, -1e9)
    logits -= logits.max(axis=1, keepdims=True)
    exponent = np.exp(np.clip(logits, -100., 40.))
    return exponent / np.maximum(exponent.sum(axis=1, keepdims=True), 1e-12)


def stage_matrix(samples):
    return (np.stack([x[2] for x in samples]),
            np.stack([x[3] for x in samples]),
            np.asarray([x[4] for x in samples], dtype=np.int64),
            np.asarray([x[5] for x in samples], dtype=np.float64))


def cross_entropy(samples, weights):
    if not samples:
        return None
    x, legal, labels, importance = stage_matrix(samples)
    p = probability(x, legal, weights)
    return float((-np.log(np.maximum(p[np.arange(len(labels)), labels], 1e-12))
                  * importance).sum() / importance.sum())


def fit_stage(samples, stage, held_seed_set):
    fit = [e for e in samples if e[1] == stage and e[0] not in held_seed_set]
    diagnostic = [e for e in samples if e[1] == stage and e[0] in held_seed_set]
    weights = np.zeros((FEATURE_COUNT, ACTION_COUNT), dtype=np.float64)
    if not fit:
        return weights, {"stage": stage, "train_samples": 0,
                         "diagnostic_samples": len(diagnostic),
                         "fit_cross_entropy": None,
                         "train_diagnostic_cross_entropy": None,
                         "trained": False}
    x, masks, labels, importance = stage_matrix(fit)
    rng = np.random.default_rng(RANDOM_SEED + stage)
    for _ in range(EPOCHS):
        for subset in np.array_split(rng.permutation(len(fit)),
                                     max(1, math.ceil(len(fit) / 256))):
            xb, mb, yb, wb = x[subset], masks[subset], labels[subset], importance[subset]
            p = probability(xb, mb, weights)
            p[np.arange(len(yb)), yb] -= 1.
            p *= wb[:, None] / max(float(wb.sum()), 1e-12)
            grad = xb.T @ p + L2 * weights
            norm = float(np.linalg.norm(grad))
            if norm > 5.:
                grad *= 5. / norm
            weights -= LEARNING_RATE * grad
    return weights, {"stage": stage, "train_samples": len(fit),
                     "diagnostic_samples": len(diagnostic),
                     "fit_cross_entropy": cross_entropy(fit, weights),
                     "train_diagnostic_cross_entropy": cross_entropy(diagnostic, weights),
                     "trained": True}


def learn(examples, protected_success_seeds=()):
    seeds = sorted({e[0] for e in examples})
    require(len(seeds) >= 12, "V8_NO_INDEPENDENT_TRAIN_DIAGNOSTIC_SEEDS")
    rng = np.random.default_rng(RANDOM_SEED)
    # With only two existing near-goal witnesses, preserve BOTH as TRAIN
    # teachers. The diagnostic is only a split of remaining TRAIN motor worlds,
    # never an independent heldout or a performance promotion gate.
    candidates = [seed for seed in seeds if seed not in set(protected_success_seeds)]
    require(len(candidates) >= 10, "V8_FIT_SUCCESS_AND_DIAGNOSTIC_INSUFFICIENT")
    rng.shuffle(candidates)
    diagnostic = set(candidates[:max(1, len(seeds) // 5)])
    heads, diagnostics = [], []
    for stage in range(STAGE_COUNT):
        weights, info = fit_stage(examples, stage, diagnostic)
        heads.append(weights)
        diagnostics.append(info)
    stacked = np.stack(heads)
    require(np.any(abs(stacked) > 1e-12), "V8_ZERO_GRADIENT_UPDATE")
    return stacked, diagnostics, sorted(diagnostic)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline-train",), required=True)
    parser.add_argument("--require-git", action="store_true")
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--v7-evidence", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    require(args.require_git, "V8_EXACT_SOURCE_CHECK_REQUIRED")
    head, checkout_root = source_identity(args.expected_head)
    root = args.v7_evidence.resolve(strict=True)
    destination = args.output_dir.resolve()
    require(not root.is_relative_to(checkout_root) and
            not destination.is_relative_to(checkout_root) and
            not destination.is_relative_to(root),
            "PRIVATE_TRAINING_INPUT_AND_WEIGHTS_MUST_STAY_OUTSIDE_GIT")
    training, manifest, qualification, replay, rows = verified_v7_evidence(root)
    examples, witnesses, transitions = training_examples(root, rows)
    require(transitions == training["actual_transition_count"],
            "V8_RAW_OPTION_COUNT_MISMATCH")
    protected = {row["seed"] for row in rows.values()
                 if row["observed_corridor"] and row["success"] and not row["unsafe"]}
    weights, diagnostics, diagnostic_seeds = learn(examples, protected)
    frozen = {"schema": SCHEMA + ".weights", "source_head": head,
              "v7_source_head": V7_SOURCE_SHA,
              "v7_training_sha256": manifest["file_sha256"]["training.json"],
              "v7_full_transitions_sha256":
              manifest["file_sha256"]["full_transitions.jsonl.gz"],
              "model_type": "four-stage masked-observation linear softmax",
              "feature_count": FEATURE_COUNT, "stages": STAGE_COUNT,
              "actions": ACTION_COUNT, "seed": RANDOM_SEED,
              "weights": np.round(weights, 12).tolist()}
    checksum = digest(frozen)
    receipt = {"schema": SCHEMA + ".receipt", "executed_head": head,
               "model_weights_sha256": checksum,
               "v7_evidence_dataset_sha256": training["dataset_sha256"],
               "v7_qualification_sha256": file_sha256(root / "independent-qualification.json"),
               "v7_replay_sha256": file_sha256(root / "independent-positive-replay.json"),
               "actual_v7_raw_train_transitions": transitions,
               "gradient_epochs_per_stage": EPOCHS,
               "learn_rate": LEARNING_RATE, "l2": L2,
               "teacher_witness_world_trials": dict(witnesses),
               "fit_example_count": len(examples),
               "train_diagnostic_seed_count": len(diagnostic_seeds),
               "train_diagnostic_seed_min": min(diagnostic_seeds),
               "train_diagnostic_seed_max": max(diagnostic_seeds),
               "stage_diagnostics": diagnostics,
               "model_weights_frozen": True, "dev_cal_test_ood_opened": False,
               "independent_science_qualification": False,
               "deployment_authorized": False,
               "next_fresh_train_seed": NEXT_TRAIN_SEED_MIN,
               "limitations": ["Imitation training and internal train-only diagnostic, not success improvement.",
                               "Two near goal witnesses share existing V5/V6 policies; strong overfitting risk.",
                               "Must first compare with frozen baselines on new real MuJoCo worlds."]}
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_new(destination / "weights.json", frozen)
    write_new(destination / "training-receipt.json", receipt)
    print(json.dumps({"trained_weights_sha256": checksum,
                      "gradient_updates": EPOCHS,
                      "train_only_examples": len(examples),
                      "trained_stages": sum(x["trained"] for x in diagnostics),
                      "dev_opened": False, "promotion_authorized": False},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
