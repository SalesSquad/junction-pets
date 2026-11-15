#!/usr/bin/env python3
"""V10: learn from immutable V8 TRAIN losses against V5 real goal teachers.

V8 produced zero near-goal wins on fresh TRAIN where frozen V5 won nine.
Those paired losses SELECT observed V5 teacher demonstrations; they do NOT
prove any unchosen action would succeed in a different state. Train a KL-
anchored, seven-mask, public-history policy with disjoint TRAIN diagnostics.
Never run fresh physics, deploy or promote this unqualified policy here.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import contextlib
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np


WORK_ID = "J26-ROKOKO-V10-TRAIN-FROM-REAL-FAILURE-20261114"
SCHEMA = "junction.rokoko.mujoco-v10.source-bound-loss-learning.v1"
FROZEN_V9_HEAD = "e683e54b21dc108791c39ac42861ead727074a78"
FROZEN_V9_RUN_BLOB = "7483aa12cab9448a779bf34e77f33da841429580"
V8_SOURCE_SHA = "87c91de52cef5c3e745115f737abc4ab8d654a32"
V8_HARNESS_SHA = "251f003b56b9eea1aff79568ad351f615acaee20"
V8_RUN_ID = "craci.43645486985.1.0627c4e23e4a1296"
V8_DATASET_SHA = "217bf81618cb6641dd106540b5dbc9f2ae7bd89d232684b7675d59479bc7ad4c"
V8_MODEL_SHA = "9dd1011cd267899da4b9205fb73bdd2f5a8453719b1003351a24a82a2743e0ea"
V8_FROZEN_WEIGHTS_FILE_SHA = "07823dcc52ea85b64e18767e1b1af29e63e3236613598cb349610a6b4fd37dc1"
# Exact bytes of the locally trained, TRAIN-only V10 checkpoint. A source-
# reviewed update is required for ANY other candidate weights. Runtime code
# cannot set this pin from command line, manifest, argument or receipt.
V10_CANDIDATE_WEIGHTS_FILE_SHA = "3a926fdd80bc5bfe069ba4ab50792aaed760d81480eb68a80b6e087beec71f3d"
V8_PINS = {
    "training.json": "af84ec8c6552383e29b8a8dd18ef237c8e3dfd3080729b16f445239618327965",
    "full_transitions.jsonl.gz": "cbaeacd5a7a2a46a30e6b63afeb12614552da032b68e78a6a90fa7d75c49101a",
    "receipt.json": "59e200ce7570157f643174b9f0d8dce8a9c47fdf99aa5080afaab8b7da337e6f",
    "manifest.json": "08915667f14bdbeed191b457cb3576fde55180aaedc1499614f9f81db41238c5",
    "independent-qualification.json": "1215cbbaf9807830121c396f8348065b7c6451ee5436e697b2258d0622e24f59",
    "independent-positive-replay.json": "af11a65aa2599973830df743b02ab6838622e7c1ee0ff26061f3ca305fbd95bf",
    "paired-readout.json": "852947f49dd8c9533a2e3fdd1d375a9a4fb0f002dd9e6b73027c58cc6b27d457",
    "original-craci-artifact.zip": "8e33c0b87a8e98cf3be2d4116a8bc4eca2e45efc3707e9fc8d385566319febb8",
}
NEXT_TRAIN_FIRST_SEED = 515_000
NEXT_TRAIN_LAST_SELECTION_SEED = 515_511
NEXT_NEAR = 128
NEXT_CLEAR = 32
NEXT_COMPARATORS = ("frozen_v5", "frozen_v6", "repeat_left", "frozen_v8",
                    "v10_loss_informed")
EPOCHS = 80
LR = .013
PRIOR_KL = .24
PRIOR_L2 = .012
DISCOUNT = .93
RANDOM_SEED = 20261115


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def load_frozen_v9():
    source = Path(__file__).resolve().parents[1] / "v9_learning" / "run.py"
    # We import only a reviewed exact byte contract, never arbitrary local code.
    raw = source.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    require(blob == FROZEN_V9_RUN_BLOB, "V10_FROZEN_V9_SOURCE_BYTES_MISMATCH")
    spec = importlib.util.spec_from_file_location("v10_frozen_v9", source)
    require(spec is not None and spec.loader is not None, "V10_FROZEN_V9_IMPORT_INVALID")
    v9 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v9)
    require(v9.REVIEWED_V8_HEAD == "6dcb577ada4314d7776025ace12d4684a136fc39",
            "V10_FROZEN_V9_IDENTITY_CHANGED")
    return v9


def immutable_v8_training_paths(restored: Path, retained: Path, archive: Path):
    artifact = retained / "artifacts" / "rokoko-mujoco-v8-prospective"
    return {
        "training.json": restored / "training.json",
        "full_transitions.jsonl.gz": restored / "full_transitions.jsonl.gz",
        "receipt.json": retained / "receipt.json",
        "manifest.json": artifact / "manifest.json",
        "independent-qualification.json": artifact / "independent-qualification.json",
        "independent-positive-replay.json": artifact / "independent-positive-replay.json",
        "paired-readout.json": artifact / "paired-readout.json",
        "original-craci-artifact.zip": archive,
    }


def verify_immutable_v8(restored: Path, retained: Path, archive: Path, v9, v8):
    """Require *literal* external hashes and independent positive replay.

    The source-reported CRACI receipt is independently replayed evidence, not
    hardware safety certification, a dev/test score, or an unseen run's own SHA.
    """
    paths = immutable_v8_training_paths(restored, retained, archive)
    require(set(paths) == set(V8_PINS) and all(p.is_file() and
            v9.file_sha256(p) == V8_PINS[name] for name, p in paths.items()),
            "V10_V8_IMMUTABLE_EXTERNAL_CRACI_BYTES_REQUIRED")
    receipt = json.loads(paths["receipt.json"].read_text())
    binding, command = receipt.get("binding", {}), receipt.get("command", {})
    require(receipt.get("runId") == V8_RUN_ID and
            binding.get("runId") == V8_RUN_ID and
            binding.get("sourceSha") == V8_SOURCE_SHA and
            binding.get("harnessSha") == V8_HARNESS_SHA and
            binding.get("workload") == "rokoko-mujoco-v8-prospective" and
            binding.get("repository") == "SalesSquad/junction-pets" and
            receipt.get("status") == "succeeded" and
            receipt.get("jobStatus") == "success" and
            receipt.get("sourceVerified") is True and
            receipt.get("harnessVerified") is True and
            receipt.get("issues") == [] and
            command.get("state") == "completed" and
            command.get("exitCode") == 0 and
            command.get("wrapperExitCode") == 0 and
            command.get("binding") == binding,
            "V10_V8_CRACI_SOURCE_BINDING_OR_SUCCESS_INVALID")
    training = json.loads(paths["training.json"].read_text())
    manifest = json.loads(paths["manifest.json"].read_text())
    qualification = json.loads(paths["independent-qualification.json"].read_text())
    replay = json.loads(paths["independent-positive-replay.json"].read_text())
    readout = json.loads(paths["paired-readout.json"].read_text())
    require(manifest.get("schema") == "junction.rokoko.mujoco-v8.prospective-train.v1.manifest" and
            manifest.get("executed_head") == V8_SOURCE_SHA and
            manifest.get("frozen_weights_sha256") == V8_MODEL_SHA and
            manifest.get("file_sha256") == {
                "training.json": V8_PINS["training.json"],
                "full_transitions.jsonl.gz": V8_PINS["full_transitions.jsonl.gz"]} and
            manifest.get("auxiliary_file_sha256", {}).get("paired-readout.json") ==
            V8_PINS["paired-readout.json"] and
            manifest.get("train_only") is True and
            manifest.get("promotion_authorized") is False and
            manifest.get("dev_cal_test_ood_opened") is False,
            "V10_V8_FULL_SOURCE_BOUND_MANIFEST_INVALID")
    require(training.get("schema") == "junction.rokoko.mujoco-v8.prospective-train.v1.training" and
            training.get("executed_head") == V8_SOURCE_SHA and
            training.get("actual_physics_engine") == "mujoco-3.3.7" and
            training.get("training_only") is True and
            training.get("no_dev_evaluation") is True and
            training.get("dev_cal_test_ood_opened") is False and
            training.get("model_promotion_authorized") is False and
            training.get("frozen_weights_sha256") == V8_MODEL_SHA and
            training.get("train_first_seed") == 513_000 and
            training.get("selected_near_count") == 128 and
            training.get("selected_clear_count") == 32 and
            training.get("strategies") == ["frozen_v5", "frozen_v6", "repeat_left",
                                           "v8_hierarchical"] and
            training.get("actual_trials") == 640 and
            len(training.get("trials", [])) == 640 and
            training.get("actual_transition_count") == 29923 and
            v8.digest(training["trials"]) == V8_DATASET_SHA ==
            training.get("dataset_sha256"),
            "V10_V8_PROSPECTIVE_640_REAL_TRAIN_INTEGRITY_INVALID")
    require(qualification.get("decision") == "valid_prospective_train_only_evidence" and
            qualification.get("experiment_complete") is True and
            qualification.get("producer_exit_code") == 0 and
            qualification.get("promotion_authorized") is False and
            qualification.get("dev_cal_test_ood_opened") is False and
            qualification.get("independent_full_trace_public_mask_replay") is True and
            qualification.get("actual_real_option_transitions") == 29923 and
            qualification.get("dataset_sha256") == V8_DATASET_SHA and
            qualification.get("full_transition_archive_sha256") ==
            V8_PINS["full_transitions.jsonl.gz"] and
            qualification.get("independent_true_physics_positive_replay") == replay and
            replay.get("claim_verified") is True and
            replay.get("no_dev_cal_test_ood") is True and
            replay.get("model_promotion_authorized") is False and
            replay.get("fully_replayed_positive_train_trials") == 202 and
            replay.get("selection_scan_replayed") == 365 and
            readout.get("dataset_sha256") == V8_DATASET_SHA and
            readout.get("model_promotion_authorized") is False,
            "V10_V8_INDEPENDENT_TRAIN_REPLAY_NOT_QUALIFIED")
    rows = {}
    seeds = defaultdict(set)
    world_hashes = {}
    for row in training["trials"]:
        seed, strategy = row["seed"], row["strategy"]
        require(type(seed) is int and 513_000 <= seed <= 513_511 and
                strategy in training["strategies"] and (seed, strategy) not in rows and
                type(row.get("observed_corridor")) is bool and
                type(row.get("success")) is bool and
                type(row.get("unsafe")) is bool,
                "V10_V8_SOURCE_WORLD_OR_STRATEGY_IDENTITY_INVALID")
        rows[seed, strategy] = row
        seeds[seed].add(strategy)
        world_hashes.setdefault(seed, row["world_hash"])
        require(world_hashes[seed] == row["world_hash"], "V10_V8_PAIRED_WORLD_HASH_DRIFT")
    require(len(seeds) == 160 and all(set(training["strategies"]) == x
                                      for x in seeds.values()) and
            sum(rows[s, "v8_hierarchical"]["observed_corridor"] for s in seeds) == 128,
            "V10_V8_160_PAIRED_TRAIN_WORLDS_INVALID")
    return rows, training, {
        "craci_run_id": V8_RUN_ID, "source_sha": V8_SOURCE_SHA,
        "harness_sha": V8_HARNESS_SHA, "dataset_sha256": V8_DATASET_SHA,
        "source_reported_receipt_sha256": V8_PINS["receipt.json"],
        "training_file_sha256": V8_PINS["training.json"],
        "raw_full_option_trace_sha256": V8_PINS["full_transitions.jsonl.gz"],
        "independent_qualification_sha256": V8_PINS["independent-qualification.json"],
        "independent_positive_replay_sha256": V8_PINS["independent-positive-replay.json"],
        "qualification_scope": "TRAIN_ONLY_REAL_MUJOCO_NO_MODEL_IMPROVEMENT_CERTIFICATION",
    }


def verified_frozen_v8_prior(path: Path, v9, v8):
    require(path.is_file() and v9.file_sha256(path) == V8_FROZEN_WEIGHTS_FILE_SHA,
            "V10_FROZEN_V8_PRIOR_WEIGHTS_SHA_MISMATCH")
    doc = json.loads(path.read_text())
    require(doc.get("schema") == "junction.rokoko.mujoco-v8.hierarchical-imitation.v1.weights" and
            doc.get("model_type") == "four-stage masked-observation linear softmax" and
            doc.get("feature_count") == 41 and doc.get("actions") == 7 and
            doc.get("stages") == 4 and
            doc.get("v7_training_sha256") == v9.V7_TRAINING_SHA256 and
            doc.get("v7_full_transitions_sha256") == v9.V7_TRACES_SHA256 and
            v8.digest(doc) == V8_MODEL_SHA,
            "V10_FROZEN_V8_PRIOR_TRAINING_LINEAGE_INVALID")
    weights = np.asarray(doc["weights"], np.float64)
    require(weights.shape == (4, 41, 7) and np.all(np.isfinite(weights)),
            "V10_FROZEN_PRIOR_MODEL_ABI_INVALID")
    return weights


class FrozenV10LegalPolicy:
    """Deterministic, new-memory-per-episode option policy.

    Only 18D PUBLIC observation and the ORIGINAL seven-bit safety mask enter
    inference. No env, seed, contact count, reward, goal, success, simulator
    state, hidden dynamics, or outside tool invocation is accepted.
    """

    def __init__(self, weights: np.ndarray, memory):
        require(weights.shape == (4, 41, 7) and np.all(np.isfinite(weights)),
                "V10_POLICY_IMMUTABLE_WEIGHT_SHAPE_INVALID")
        self._weights = weights.copy()
        self._weights.setflags(write=False)
        self._memory = memory

    def __call__(self, observation, legal_mask):
        stage, features, legal = self._memory.features(observation, legal_mask)
        require(0 <= stage < 4 and features.shape == (41,) and legal.shape == (7,),
                "V10_PUBLIC_POLICY_ABI_DRIFT")
        scores = features @ self._weights[stage]
        scores[~legal] = -np.inf
        action = int(np.argmax(scores))
        require(0 <= action < 7 and bool(legal[action]),
                "V10_UNSAFE_OPTION_PROPOSAL_BLOCKED")
        self._memory.remember(action)
        return action


def policy_factory(candidate_weights_path: Path):
    """Freeze a reviewed exact candidate, then create fresh episode policies.

    No caller-controlled SHA override; this is a TRAIN-testable policy contract,
    not authorization to run CRACI, use unseen data or deploy a robot.
    """
    source = Path(candidate_weights_path).resolve(strict=True)
    v9 = load_frozen_v9()
    v8 = v9.checked_v8_trainer()
    require(v9.file_sha256(source) == V10_CANDIDATE_WEIGHTS_FILE_SHA,
            "V10_POLICY_UNREVIEWED_OR_EDITED_WEIGHTS_REJECTED")
    checkpoint = json.loads(source.read_text())
    require(checkpoint.get("schema") == SCHEMA + ".unpromoted-checkpoint" and
            checkpoint.get("base_frozen_v8_model_sha256") == V8_MODEL_SHA and
            checkpoint.get("model_type") ==
            "loss-informed KL-anchored four-head seven-mask public-observation softmax" and
            checkpoint.get("feature_count") == 41 and
            checkpoint.get("stage_count") == 4 and
            checkpoint.get("action_count") == 7 and
            checkpoint.get("model_promotion_authorized") is False and
            checkpoint.get("new_physics_performed") is False and
            checkpoint.get("canonical_weights_sha256") ==
            v8.digest(checkpoint.get("weights")),
            "V10_POLICY_CHECKPOINT_PROVENANCE_INVALID")
    weights = np.asarray(checkpoint["weights"], np.float64)
    require(weights.shape == (4, 41, 7) and np.all(np.isfinite(weights)),
            "V10_POLICY_WEIGHTS_NOT_FINITE_OR_NOT_SHIELDED")
    return lambda: FrozenV10LegalPolicy(weights, v8.PublicMemory())


def paired_loss_worlds(rows, graphs):
    """Real pair outcomes select teachers; NEVER label unchosen actions bad."""
    losses = []
    near = sorted({seed for (seed, strategy), row in rows.items()
                   if row["observed_corridor"]})
    require(len(near) == 128, "V10_V8_NEAR_TRAIN_COHORT_WRONG_SIZE")
    for seed in near:
        baseline = any(graphs[seed, strategy]["safe_goal_dwell_any_path"]
                       for strategy in ("frozen_v5", "frozen_v6"))
        candidate = graphs[seed, "v8_hierarchical"]["safe_goal_dwell_any_path"]
        if baseline and not candidate:
            losses.append(seed)
    return losses


def select_teacher_rows(rows, graphs, v8_loss_worlds):
    target = {}
    losses = set(v8_loss_worlds)
    for key in sorted(rows):
        seed, strategy = key
        row, graph = rows[key], graphs[key]
        if not row["observed_corridor"] or not graph["safe"]:
            continue
        if strategy in ("frozen_v5", "frozen_v6"):
            # Rare, physically achieved positive goal/dwell trajectories only.
            if graph["safe_goal_dwell_any_path"]:
                target[key] = {"class": "observed_safe_goal_teacher",
                               "paired_v8_goal_loss": seed in losses}
        elif strategy == "repeat_left" and graph["any_signed_lateral25"]:
            target[key] = {"class": "observed_safe_motor_teacher",
                           "paired_v8_goal_loss": False}
        elif strategy == "v8_hierarchical" and (graph["lateral25_after_contact"] or
                                                 graph["reopen_after_lateral25"]):
            target[key] = {"class": "observed_safe_non_goal_stage_teacher",
                           "paired_v8_goal_loss": False}
    return target


def choose_world_splits(teacher_seeds, fresh_v8_goal_seeds, old_v7_goal_seeds):
    """Keep 2 of 9 new real V8 goal worlds strictly held as TRAIN diagnosis.

    All 2 V7 goal witnesses and 7/9 new V8 goal worlds are TRAIN fit; the
    remaining teacher worlds get disjoint held and inner TRAIN validation.
    No dev/test/OOD data or cross-strategy seed leakage.
    """
    worlds = set(teacher_seeds)
    goals_new = set(fresh_v8_goal_seeds)
    old = set(old_v7_goal_seeds)
    require(len(goals_new) == 9 and len(old) == 2 and goals_new.isdisjoint(old) and
            goals_new.union(old).issubset(worlds) and len(worlds) >= 100,
            "V10_QUALIFIED_SAFE_GOAL_WITNESS_AND_MOTOR_COVERAGE_REQUIRED")
    ranked_goals = sorted(goals_new, key=lambda s: hashlib.sha256(
        f"{WORK_ID}:fresh-goal-held:{s}".encode()).digest())
    held_goals = set(ranked_goals[:2])
    other = worlds - goals_new - old
    ranked_other = sorted(other, key=lambda s: hashlib.sha256(
        f"{WORK_ID}:other-world:{s}".encode()).digest())
    held_other = set(ranked_other[:max(1, len(ranked_other) // 5)])
    inner = set(ranked_other[len(held_other):len(held_other) + max(1, len(ranked_other) // 10)])
    held = held_goals | held_other
    fit = worlds - held - inner
    require(len(goals_new & fit) == 7 and old.issubset(fit) and
            len(goals_new & held) == 2 and not goals_new.intersection(inner) and
            fit.isdisjoint(held) and fit.isdisjoint(inner) and held.isdisjoint(inner) and
            fit | held | inner == worlds, "V10_WORLD_DISJOINT_DIAGNOSTIC_SPLIT_INVALID")
    return {"fit": sorted(fit), "inner_train_validation": sorted(inner),
            "held_train_diagnostic": sorted(held),
            "fresh_goal_train_fit_worlds": sorted(goals_new & fit),
            "fresh_goal_held_train_worlds": sorted(held_goals),
            "v7_goal_fit_worlds": sorted(old)}


def mine_observed_teacher_actions(rows, graphs, traces, teacher_labels, v8, losses):
    samples = []
    strategy_examples = Counter()
    for key in sorted(teacher_labels):
        row, graph, events = rows[key], graphs[key], traces[key]
        memory = v8.PublicMemory()
        completed = graph["safe_goal_dwell_any_path"]
        milestones = [i for i in graph["milestone_option_indices"] if i is not None]
        for index, event in enumerate(events):
            stage, features, mask = memory.features(event["observation"], event["mask"])
            action = event["action"]
            require(mask[action] and event["cost"] == 0,
                    "V10_REAL_TEACHER_ACTION_BYPASSED_SHIELD")
            if action != 6:
                credit = sum(DISCOUNT ** (j - index) for j in milestones if j >= index)
                weight = (1 + min(4., credit)) / len(events)
                if completed:
                    weight *= 3.0
                if stage == 3 and completed:
                    weight *= 3.0
                if row["seed"] in losses and completed:
                    weight *= 1.6  # paired-loss teacher emphasis, not causal negation
                samples.append((row["seed"], stage, features, mask, action, weight))
                strategy_examples[row["strategy"]] += 1
            memory.remember(action)
    require(len(samples) >= 1000 and all(e[5] > 0 for e in samples),
            "V10_NOT_ENOUGH_REAL_SAFE_OPTION_TEACHERS")
    return samples, dict(sorted(strategy_examples.items()))


def weighted_nll(samples, weights, v8):
    if not samples:
        return None
    x, masks, y, w = v8.stage_matrix(samples)
    p = v8.probability(x, masks, weights)
    return float((-np.log(np.maximum(p[np.arange(len(y)), y], 1e-12)) * w).sum() / w.sum())


def train_kl_anchored_head(fit, inner, held, prior, stage, v8):
    """Gradient updates with explicit KL-to-frozen V8 and L2-to-prior."""
    w = prior.copy()
    before = weighted_nll(fit, prior, v8)
    prior_inner = weighted_nll(inner, prior, v8)
    prior_held = weighted_nll(held, prior, v8)
    if fit:
        x, masks, labels, importance = v8.stage_matrix(fit)
        importance = importance / importance.mean()
        rng = np.random.default_rng(RANDOM_SEED + stage)
        # Fixed optimization budget; the held TRAIN diagnostic is never used
        # for early stopping, head selection or hyperparameter tuning.
        for _ in range(EPOCHS):
            for batch in np.array_split(rng.permutation(len(fit)),
                                        max(1, math.ceil(len(fit) / 192))):
                xb, mb, yb, wb = x[batch], masks[batch], labels[batch], importance[batch]
                predicted = v8.probability(xb, mb, w)
                frozen = v8.probability(xb, mb, prior)
                grad_probs = predicted.copy()
                grad_probs[np.arange(len(yb)), yb] -= 1
                grad_probs *= wb[:, None] / max(float(wb.sum()), 1e-12)
                grad_kl = PRIOR_KL * (predicted - frozen) / len(batch)
                gradient = xb.T @ (grad_probs + grad_kl) + PRIOR_L2 * (w - prior)
                norm = float(np.linalg.norm(gradient))
                if norm > 5:
                    gradient *= 5 / norm
                w -= LR * gradient
    after_fit = weighted_nll(fit, w, v8)
    after_inner = weighted_nll(inner, w, v8)
    after_held = weighted_nll(held, w, v8)
    fit_improved = bool(fit and after_fit is not None and before is not None and
                        after_fit < before)
    held_improved = bool(held and prior_held is not None and after_held is not None and
                         after_held < prior_held)
    return w, {
        "stage": stage, "fit_actions": len(fit), "inner_train_validation_actions": len(inner),
        "held_train_diagnostic_actions": len(held),
        "frozen_v8_fit_nll": before, "v10_fit_nll": after_fit,
        "frozen_v8_inner_train_nll": prior_inner, "v10_inner_train_nll": after_inner,
        "frozen_v8_held_train_nll": prior_held, "v10_held_train_nll": after_held,
        "fit_improved": fit_improved, "held_train_improved": held_improved,
        "head_not_qualified_if_held_worse": not held_improved,
    }


def train_v10(samples, splits, prior, v8):
    fit_set = set(splits["fit"])
    inner_set = set(splits["inner_train_validation"])
    held_set = set(splits["held_train_diagnostic"])
    require(fit_set.isdisjoint(inner_set) and fit_set.isdisjoint(held_set) and
            inner_set.isdisjoint(held_set), "V10_LEAKED_WORLDS_ACROSS_TRAIN_SPLITS")
    heads, diagnostics = [], []
    for stage in range(4):
        fit = [e for e in samples if e[1] == stage and e[0] in fit_set]
        inner = [e for e in samples if e[1] == stage and e[0] in inner_set]
        held = [e for e in samples if e[1] == stage and e[0] in held_set]
        model, info = train_kl_anchored_head(fit, inner, held, prior[stage], stage, v8)
        heads.append(model)
        diagnostics.append(info)
    weights = np.stack(heads)
    require(np.all(np.isfinite(weights)) and
            any(np.any(abs(weights[stage] - prior[stage]) > 1e-9) for stage in range(4)),
            "V10_REAL_LOSS_TRAINING_DID_NOT_UPDATE_MODEL")
    return weights, diagnostics


def plan_next_train(readout, diagnostics, splits):
    blocked = [d["stage"] for d in diagnostics if not d["fit_improved"] or
               not d["held_train_improved"]]
    # This is a preregistration proposal. A separate source review must freeze
    # an executable candidate and authorize physics before dispatch.
    return {
        "schema": SCHEMA + ".next-train-plan",
        "preregistered_seed_start": NEXT_TRAIN_FIRST_SEED,
        "preregistered_public_initial_observation_scan_last_seed": NEXT_TRAIN_LAST_SELECTION_SEED,
        "near_worlds": NEXT_NEAR, "clear_worlds": NEXT_CLEAR,
        "selection": "ascending TRAIN seeds; public initial abs(observation[7]) < 0.122 near",
        "comparators": list(NEXT_COMPARATORS),
        "planned_paired_real_episodes": (NEXT_NEAR + NEXT_CLEAR) * len(NEXT_COMPARATORS),
        "does_not_modify_v9_frozen_514000_cohort": True,
        "current_train_loss_world_count": len(readout["v8_lost_safe_goals_vs_frozen"]),
        "v10_stage_head_unqualified": blocked,
        "goal_train_diagnostic_worlds": splits["fresh_goal_held_train_worlds"],
        "prospective_physics_dispatched": False,
        "new_spending_authorized": False,
        "model_promotion_authorized": False,
        "dev_cal_test_ood_opened": False,
        "requirements_before_rollout": [
            "independent source/science review of V10 code, exact model and train readout",
            "fresh 515000+ TRAIN-only cohort and frozen 5-way paired schedule",
            "original seven-action safety shield without overrides",
            "full real-MuJoCo option traces with independent replay and no model promotion",
            "no regression on preregistered held TRAIN goal worlds",
        ],
    }


def save(output: Path, analysis: dict, candidate: dict, plan: dict, v9):
    require(not output.exists(), "V10_REFUSE_TO_REWRITE_PRIOR_TRAIN_RECEIPT")
    output.mkdir(parents=True)
    docs = {"paired-failure-readout.json": analysis,
            "candidate-weights.json": candidate,
            "v10-next-train-plan.json": plan}
    for name, body in docs.items():
        (output / name).write_text(json.dumps(body, sort_keys=True, indent=2,
                                            ensure_ascii=False, allow_nan=False) + "\n")
    manifest = {"schema": SCHEMA + ".local-output-inventory",
                "external_craci_qualification_is_not_self_attested": True,
                "file_sha256": {name: v9.file_sha256(output / name) for name in docs}}
    (output / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("v7-restored", "v7-retained", "v7-artifact-zip", "v8-restored",
                 "v8-retained", "v8-artifact-zip", "v8-frozen-weights", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    v9 = load_frozen_v9()
    v8 = v9.checked_v8_trainer()
    output = args.output_dir.resolve()
    require(not output.is_relative_to(Path(__file__).resolve().parents[6]),
            "V10_PRIVATE_TRAIN_OUTPUT_OUTSIDE_SOURCE_CHECKOUT_REQUIRED")
    prior = verified_frozen_v8_prior(args.v8_frozen_weights.resolve(), v9, v8)
    v8_rows, v8_training, v8_evidence = verify_immutable_v8(
        args.v8_restored.resolve(), args.v8_retained.resolve(),
        args.v8_artifact_zip.resolve(), v9, v8)
    v8_graphs, v8_traces, v8_actual_options = v9.replay_full_train(
        args.v8_restored.resolve(), v8_rows, v8)
    require(v8_actual_options == 29923, "V10_INCOMPLETE_REAL_V8_FULL_OPTION_REPLAY")
    loss_worlds = paired_loss_worlds(v8_rows, v8_graphs)
    require(len(loss_worlds) == 9 and all(v8_graphs[s, "frozen_v5"]["safe_goal_dwell_any_path"]
                                          for s in loss_worlds),
            "V10_EXPECTED_NINE_REAL_TRAIN_PAIRED_V8_LOSSES_NOT_VERIFIED")
    with v9.immutable_v7_evidence(
            args.v7_restored.resolve(), args.v7_retained.resolve(),
            args.v7_artifact_zip.resolve(), v8) as (root, v7_training, v7_rows, v7_evidence):
        v7_graphs, v7_traces, v7_actual_options = v9.replay_full_train(root, v7_rows, v8)
        require(v7_actual_options == 68568 and
                v7_actual_options == v7_training["actual_transition_count"],
                "V10_V7_ORIGINAL_POSITIVE_REPLAY_DRIFT")
    require(not set(v8_rows).intersection(v7_rows), "V10_V7_V8_WORLD_SEED_LEAKAGE")
    combined_rows = {**v7_rows, **v8_rows}
    combined_graphs = {**v7_graphs, **v8_graphs}
    combined_traces = {**v7_traces, **v8_traces}
    teachers = select_teacher_rows(combined_rows, combined_graphs, set(loss_worlds))
    samples, strategy_samples = mine_observed_teacher_actions(
        combined_rows, combined_graphs, combined_traces, teachers, v8, set(loss_worlds))
    fresh_goal = sorted({s for (s, strat), graph in v8_graphs.items() if
                         v8_rows[s, strat]["observed_corridor"] and
                         graph["safe_goal_dwell_any_path"]})
    old_goal = sorted({s for (s, strat), graph in v7_graphs.items() if
                       v7_rows[s, strat]["observed_corridor"] and
                       graph["safe_goal_dwell_any_path"]})
    splits = choose_world_splits([key[0] for key in teachers], fresh_goal, old_goal)
    weights, diagnostics = train_v10(samples, splits, prior, v8)
    analysis = {
        "schema": SCHEMA + ".paired-real-train-analysis",
        "work_id": WORK_ID,
        "immutable_sources": {"v7": v7_evidence, "v8": v8_evidence},
        "actual_real_option_transitions": {"v7": v7_actual_options,
                                           "v8": v8_actual_options},
        "v7_within_cohort": v9.stage_readout(v7_rows, v7_graphs, v8.EXPECTED_STRATEGIES),
        "v8_within_cohort": v9.stage_readout(v8_rows, v8_graphs,
                                             tuple(v8_training["strategies"])),
        "v8_lost_safe_goals_vs_frozen": loss_worlds,
        "observed_goal_teachers": {"old_v7_worlds": old_goal,
                                   "fresh_v8_worlds": fresh_goal},
        "candidate_training_examples": len(samples),
        "safe_teacher_strategy_action_counts": strategy_samples,
        "negative_evidence": [
            "Actual source-qualified fresh TRAIN: frozen V5 won nine near worlds; V8 won zero.",
            "V8 safe lateral/reopen traces did not convert to near-goal dwell.",
            "Paired world loss is a teacher selection signal, NOT an unchosen-action causal label.",
            "No new physics, dev/test qualification, action safety certificate, or model gain is claimed.",
        ],
    }
    candidate = {
        "schema": SCHEMA + ".unpromoted-checkpoint", "work_id": WORK_ID,
        "model_type": "loss-informed KL-anchored four-head seven-mask public-observation softmax",
        "base_frozen_v8_model_sha256": V8_MODEL_SHA,
        "base_frozen_v8_weights_file_sha256": V8_FROZEN_WEIGHTS_FILE_SHA,
        "feature_count": 41, "stage_count": 4, "action_count": 7,
        "weights": weights.tolist(), "canonical_weights_sha256": v8.digest(weights.tolist()),
        "training_seed": RANDOM_SEED, "epochs": EPOCHS,
        "learning_rate": LR, "prior_kl": PRIOR_KL, "delta_l2": PRIOR_L2,
        "train_split_worlds": splits,
        "diagnostics_vs_frozen_v8_prior": diagnostics,
        "blocked_stages_on_train_diagnostic": [d["stage"] for d in diagnostics if
                                                 not d["fit_improved"] or
                                                 not d["held_train_improved"]],
        "model_promotion_authorized": False,
        "new_physics_performed": False,
        "training_only_goal_diagnostic_not_dev_or_test": True,
        "limitations": ["nine fresh goal witnesses are limited TRAIN data",
                        "behavioral teacher learning cannot prove causal action improvements",
                        "held TRAIN fit is not unseen dev/test evidence",
                        "prospective original-MuJoCo 515000+ verification still required"],
    }
    plan = plan_next_train(analysis, diagnostics, splits)
    manifest = save(output, analysis, candidate, plan, v9)
    print(json.dumps({"status": "real_v7_v8_train_reanalysis_unpromoted",
                      "work_id": WORK_ID, "teacher_actions": len(samples),
                      "goal_held_train_worlds": splits["fresh_goal_held_train_worlds"],
                      "blocked_stages": candidate["blocked_stages_on_train_diagnostic"],
                      "model_file_sha256": manifest["file_sha256"]["candidate-weights.json"],
                      "readout_file_sha256": manifest["file_sha256"]["paired-failure-readout.json"],
                      "plan_file_sha256": manifest["file_sha256"]["v10-next-train-plan.json"]},
                     sort_keys=True))


if __name__ == "__main__":
    main()
