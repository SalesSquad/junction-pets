#!/usr/bin/env python3
"""V9: immutable MuJoCo TRAIN traces -> stage evidence -> adaptive learning.

This is OFFLINE learning, not a new physics experiment or a deployment gate.
V8 results are deliberately unavailable until a reviewer updates the literal
V8_EVIDENCE_LOCK using a completed, independently qualified CRACI receipt and
byte hashes. Input-supplied pins/manifest digests never establish trust.
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
import os
from pathlib import Path
import tempfile

import numpy as np


WORK_ID = "J26-ROKOKO-V9-ADAPTIVE-LOOP-20261114"
SCHEMA = "junction.rokoko.mujoco-v9.stage-graph-learning.v1"
REVIEWED_V8_HEAD = "6dcb577ada4314d7776025ace12d4684a136fc39"
REVIEWED_V8_TRAINER_GIT_BLOB = "53a730b71197b18de5b3f4e03b2e870f07f9cdb0"
V7_RUN_ID = "craci.43640728389.1.ebec06d6f3461523"
V7_SOURCE = "127ceb9be4374ba46908cd398ced6b740275a434"
V7_TRAINING_SHA256 = "06ffeb5f4d5a639eba15f0bd2c260b6d0c046ea13665a8f5e884848bb1a236d8"
V7_TRACES_SHA256 = "3888fd350c66f3a1ca6a2bebb7731097c86181b5644d921b0bb580855bae4d64"
V8_FROZEN_MODEL_SHA256 = "9dd1011cd267899da4b9205fb73bdd2f5a8453719b1003351a24a82a2743e0ea"
V8_PROSPECTIVE_RUN_NUMBER = 43644437088
V8_TRAIN_SEED_START = 513_000
V9_TRAIN_SEED_START = 514_000
V9_SELECTION_SCAN_LAST = 514_511
V9_NEAR_COUNT = 128
V9_CLEAR_COUNT = 32
V9_STRATEGIES = ("frozen_v5", "frozen_v6", "repeat_left", "frozen_v8", "v9_stage_weighted")
V9_EXPECTED_EPISODES = (V9_NEAR_COUNT + V9_CLEAR_COUNT) * len(V9_STRATEGIES)
MIN_SAFE_LATERAL = .025
MIN_DWELL = 250
LEARNING_SEED = 20261115
EPOCHS = 65
LEARNING_RATE = .035
L2 = .004
DISCOUNT = .93

# Literal, code-reviewed external CRACI evidence only; NOT populated with
# self-reported manifest checksums. When the real V8 job and independent physics
# replay finish, pin runId/source/harness/receipt AND training/raw hashes here
# in a separate reviewed change. Until then V8 is epistemically UNSEEN.
V8_EVIDENCE_LOCK = None


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def canonical_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def checked_v8_trainer():
    """Import only inherited, byte-exact V8 verifier and public feature ABI."""
    previous = Path(__file__).resolve().parents[1] / "v8_learning" / "run.py"
    require(previous.is_file() and git_blob(previous) == REVIEWED_V8_TRAINER_GIT_BLOB,
            "V9_INHERITED_V8_VERIFIER_BYTES_NOT_REVIEWED")
    spec = importlib.util.spec_from_file_location("v9_trusted_v8_verifier", previous)
    require(spec is not None and spec.loader is not None, "V9_V8_VERIFIER_IMPORT_FAILURE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.V7_CRACI_RUN_ID == V7_RUN_ID and
            module.V7_PINNED_FILES["training.json"] == V7_TRAINING_SHA256 and
            module.V7_PINNED_FILES["full_transitions.jsonl.gz"] == V7_TRACES_SHA256,
            "V9_V7_CONTRACT_DRIFT")
    return module


def git_blob(path: Path) -> str:
    payload = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()


@contextlib.contextmanager
def immutable_v7_evidence(restored: Path, retained: Path, archive: Path, v8):
    """Map a split read-only CRACI download to the exact V8 verifier contract."""
    artifact = retained / "artifacts" / "rokoko-mujoco-v7-feasibility"
    paths = {
        "training.json": restored / "training.json",
        "full_transitions.jsonl.gz": restored / "full_transitions.jsonl.gz",
        "manifest.json": artifact / "manifest.json",
        "independent-qualification.json": artifact / "independent-qualification.json",
        "independent-positive-replay.json": artifact / "independent-positive-replay.json",
        "receipt.json": retained / "receipt.json",
        "artifact.zip": archive,
    }
    require(set(paths) == set(v8.V7_PINNED_FILES), "V9_V7_VERIFIED_INPUT_LAYOUT_CHANGED")
    require(all(p.is_file() and file_sha256(p) == v8.V7_PINNED_FILES[name]
                for name, p in paths.items()), "V9_V7_IMMUTABLE_CRACI_BYTES_REQUIRED")
    with tempfile.TemporaryDirectory(prefix="v9-verified-v7-") as tmp:
        root = Path(tmp)
        for name, source in paths.items():
            os.symlink(source.resolve(strict=True), root / name)
        training, manifest, qualification, replay, rows = v8.verified_v7_evidence(root)
        yield root, training, rows, {
            "run_id": V7_RUN_ID,
            "source_sha": V7_SOURCE,
            "dataset_sha256": training["dataset_sha256"],
            "training_file_sha256": V7_TRAINING_SHA256,
            "full_transitions_file_sha256": V7_TRACES_SHA256,
            "independent_qualification_sha256": file_sha256(paths["independent-qualification.json"]),
            "independent_positive_replay_sha256": file_sha256(paths["independent-positive-replay.json"]),
            "qualification_complete": qualification["experiment_complete"],
            "positive_replay_verified": replay["claim_verified"],
        }


def verify_v8_locked_evidence(root: Path):
    """No caller-provided pin is trusted. Real V8 must first be reviewed."""
    lock = V8_EVIDENCE_LOCK
    require(isinstance(lock, dict), "V9_V8_UNSEEN_NO_IMMUTABLE_REVIEWED_RECEIPT")
    fixed = lock.get("files", {})
    required = {"training.json", "full_transitions.jsonl.gz", "manifest.json",
                "receipt.json", "independent-qualification.json"}
    require(set(fixed) == required and all(
        isinstance(v, str) and len(v) == 64 and
        all(c in "0123456789abcdef" for c in v) for v in fixed.values()),
        "V9_V8_REVIEWED_LOCK_INCOMPLETE")
    require(all((root / f).is_file() and file_sha256(root / f) == sha
                for f, sha in fixed.items()), "V9_V8_SOURCE_BOUND_BYTES_MISMATCH")
    receipt = json.loads((root / "receipt.json").read_text())
    binding = receipt.get("binding", {})
    require(receipt.get("runId") == lock["run_id"] and
            binding.get("runId") == lock["run_id"] and
            binding.get("sourceSha") == REVIEWED_V8_HEAD and
            binding.get("harnessSha") == lock["harness_sha"] and
            binding.get("repository") == "SalesSquad/junction-pets" and
            receipt.get("status") == "succeeded" and
            receipt.get("sourceVerified") is True and
            receipt.get("harnessVerified") is True and
            receipt.get("issues") == [],
            "V9_V8_REAL_CRACI_RECEIPT_NOT_QUALIFIED")
    training = json.loads((root / "training.json").read_text())
    qualification = json.loads((root / "independent-qualification.json").read_text())
    require(training.get("schema") == "junction.rokoko.mujoco-v8.prospective-train.v1.training" and
            training.get("executed_head") == REVIEWED_V8_HEAD and
            training.get("actual_physics_engine") == "mujoco-3.3.7" and
            training.get("training_only") is True and
            len(training.get("trials", [])) == 640 and
            training.get("frozen_weights_sha256") == V8_FROZEN_MODEL_SHA256 and
            qualification.get("dev_cal_test_ood_opened") is False and
            qualification.get("promotion_authorized") is False,
            "V9_V8_REAL_TRAIN_CONTRACT_MISMATCH")
    require(training.get("no_dev_evaluation") is True and
            training.get("dev_cal_test_ood_opened") is False and
            training.get("model_promotion_authorized") is False and
            training.get("selected_near_count") == 128 and
            training.get("selected_clear_count") == 32 and
            training.get("train_first_seed") == V8_TRAIN_SEED_START and
            training.get("strategies") == ["frozen_v5", "frozen_v6",
                                           "repeat_left", "v8_hierarchical"] and
            digest(training["trials"]) == training.get("dataset_sha256"),
            "V9_V8_PAIRED_PROSPECTIVE_TRAIN_INVALID")
    rows = {}
    world_hashes = {}
    for row in training["trials"]:
        seed, strategy = row["seed"], row["strategy"]
        require(type(seed) is int and V8_TRAIN_SEED_START <= seed <= V8_TRAIN_SEED_START + 511 and
                strategy in training["strategies"] and (seed, strategy) not in rows and
                type(row.get("observed_corridor")) is bool,
                "V9_V8_PROSPECTIVE_TRAIN_IDENTITY_INVALID")
        rows[seed, strategy] = row
        world_hashes.setdefault(seed, row["world_hash"])
        require(world_hashes[seed] == row["world_hash"],
                "V9_V8_WORLD_PAIR_SIGNATURE_MISMATCH")
    require(len(world_hashes) == 160 and len(rows) == 640 and all(
        sum(pair[0] == seed for pair in rows) == 4 for seed in world_hashes),
        "V9_V8_PROSPECTIVE_PAIRED_COHORT_INCOMPLETE")
    return training, rows, {"run_id": lock["run_id"], "source_sha": REVIEWED_V8_HEAD,
        "training_file_sha256": fixed["training.json"],
        "full_transitions_file_sha256": fixed["full_transitions.jsonl.gz"]}


def signed_away(first, last) -> float:
    require(len(first) == len(last) == 18, "V9_PUBLIC_OBSERVATION_ABI")
    sign = -1.0 if first[7] >= first[1] else 1.0
    return float(last[1] - first[1]) * sign


def grade_stage_graph(transitions, row):
    """Independently reconstruct chronological stages from ALL raw transitions.

    Event indices are evidence labels; inferred private contact counts are NEVER
    passed to the policy features. A proposed 'reopen' must have a real next mask.
    """
    require(bool(transitions), "V9_NO_REAL_OPTION_TRANSITIONS")
    first = transitions[0]["observation"]
    contact = lateral = reopen = None
    any_lateral = False
    any_reopen = False
    last_contacts = 0
    for i, event in enumerate(transitions):
        before, after, mask = event["observation"], event["next_observation"], event["mask"]
        require(len(before) == len(after) == 18 and len(mask) == 7 and
                all(type(m) in (bool, int) and m in (0, 1) for m in mask) and
                all(math.isfinite(float(x)) for x in before + after) and
                type(event["action"]) is int and 0 <= event["action"] < 7 and
                bool(mask[event["action"]]), "V9_FULL_TRACE_PUBLIC_SHIELD_INVALID")
        contacts = event["contacts_cumulative"]
        require(type(contacts) is int and contacts >= last_contacts,
                "V9_CONTACT_HISTORY_DECREASED")
        last_contacts = contacts
        if contact is None and contacts > 0:
            contact = i
        did_lateral = signed_away(first, after) >= MIN_SAFE_LATERAL
        any_lateral |= did_lateral
        if contact is not None and lateral is None and i >= contact and did_lateral:
            lateral = i
        did_reopen = bool(i + 1 < len(transitions) and event["action"] in (3, 4) and
                          not (mask[1] or mask[2]) and
                          (transitions[i + 1]["mask"][1] or transitions[i + 1]["mask"][2]))
        any_reopen |= did_reopen
        if lateral is not None and reopen is None and i >= lateral and did_reopen:
            reopen = i
    terminal = transitions[-1]
    require(bool(terminal["done"]) == bool(row["success"] or row["unsafe"] or
                                         row["abstained"] or row["option_steps"] == len(transitions)),
            "V9_TERMINAL_TRACE_INCONSISTENT")
    require(bool(terminal["success_info"]) == bool(row["success"]) and
            int(terminal["contacts_cumulative"]) == row["contacts"],
            "V9_FULL_TRACE_TERMINAL_MISMATCH")
    safe = not row["unsafe"] and not row["abstained"] and all(e["cost"] == 0
                                                                for e in transitions)
    goal = bool(safe and row["success"] and
                terminal["dwell_ticks_current"] >= MIN_DWELL)
    milestones = (contact, lateral, reopen, len(transitions) - 1 if goal and
                  reopen is not None else None)
    return {
        "safe": safe, "contact": contact is not None,
        "lateral25_after_contact": lateral is not None,
        "reopen_after_lateral25": reopen is not None,
        "full_stage_safe_goal_dwell": milestones[-1] is not None,
        "any_signed_lateral25": any_lateral,
        "any_forward_reopen_side": any_reopen,
        "safe_goal_dwell_any_path": goal,
        "milestone_option_indices": list(milestones),
        "raw_option_count": len(transitions),
    }


def replay_full_train(root: Path, rows, v8):
    """Reject missing/duplicated/mismatched raw traces, even if summary is fine."""
    observed = set()
    results = {}
    full = {}
    transitions_count = 0
    with gzip.open(root / "full_transitions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            raw = json.loads(line)
            key = (raw.get("seed"), raw.get("strategy"))
            require(key in rows and key not in observed, "V9_RAW_TRAIN_PAIR_DUPLICATE_OR_UNKNOWN")
            observed.add(key)
            row = rows[key]
            events = raw.get("transitions", [])
            require(len(events) == row["full_transition_count"] and
                    v8.digest(events) == row["full_transition_sha256"],
                    "V9_RAW_FULL_OPTION_TRACE_HASH_MISMATCH")
            results[key] = grade_stage_graph(events, row)
            full[key] = events
            transitions_count += len(events)
    require(observed == set(rows), "V9_INCOMPLETE_QUALIFIED_RAW_TRAIN_TRACES")
    return results, full, transitions_count


def wilson(success: int, total: int):
    if total == 0:
        return [None, None]
    z = 1.959963984540054
    p = success / total
    d = 1 + z * z / total
    mean = (p + z * z / (2 * total)) / d
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / d
    return [round(max(0.0, mean - half), 6), round(min(1.0, mean + half), 6)]


def stage_readout(rows, graphs, strategies):
    per_seed = defaultdict(dict)
    for (seed, strategy), row in rows.items():
        require((seed, strategy) in graphs, "V9_TRAIN_RAW_STAGE_EVIDENCE_REQUIRED")
        per_seed[seed][strategy] = row
    require(all(set(p) == set(strategies) and
                len({r["world_hash"] for r in p.values()}) == 1 for p in per_seed.values()),
            "V9_TRAIN_BASELINES_NOT_PAIRED_BY_WORLD")
    near = sorted(seed for seed, p in per_seed.items()
                  if next(iter(p.values()))["observed_corridor"])
    clear = sorted(set(per_seed) - set(near))
    result = {"near_world_count": len(near), "clear_world_count": len(clear),
              "strategies": {}, "paired_vs_frozen_safe_near": {}}
    fields = ("contact", "lateral25_after_contact", "reopen_after_lateral25",
              "full_stage_safe_goal_dwell", "safe_goal_dwell_any_path")
    for name in strategies:
        chosen = [graphs[seed, name] for seed in near]
        safe = [g for g in chosen if g["safe"]]
        counts = {field: sum(g[field] for g in safe) for field in fields}
        result["strategies"][name] = {
            "safe_near_worlds": len(safe),
            "unsafe_near": sum(per_seed[s][name]["unsafe"] for s in near),
            "abstained_near": sum(per_seed[s][name]["abstained"] for s in near),
            "chronological_counts": counts,
            "chronological_rates": {field: {
                "count": count, "denominator": len(near),
                "wilson95": wilson(count, len(near))} for field, count in counts.items()},
        }
        wins = losses = ties = 0
        for seed in near:
            baseline = any(graphs[seed, strategy]["safe_goal_dwell_any_path"] for
                           strategy in ("frozen_v5", "frozen_v6"))
            candidate = graphs[seed, name]["safe_goal_dwell_any_path"]
            wins += int(candidate and not baseline)
            losses += int(baseline and not candidate)
            ties += int(candidate == baseline)
        result["paired_vs_frozen_safe_near"][name] = {
            "new_wins": wins, "lost_frozen_wins": losses,
            "ties": ties, "net_paired_delta": wins - losses,
            "rate_delta": round((wins - losses) / len(near), 6) if near else None,
        }
    return result


def diagnostic_worlds(seeds, protected_success_seeds=()):
    """Group-level TRAIN split, rare safe-goal teachers protected for fitting.

    The goal completion diagnostic is UNAVAILABLE when all rare successes are
    protected. Never report it as measured cross-world generalization.
    """
    seeds = sorted(set(seeds))
    require(len(seeds) >= 10, "V9_INSUFFICIENT_SAFE_TEACHER_WORLDS")
    protected = set(protected_success_seeds)
    require(protected.issubset(seeds), "V9_SUCCESS_PROTECTION_NOT_FROM_TRAIN_TEACHERS")
    candidates = [seed for seed in seeds if seed not in protected]
    require(len(candidates) >= 10, "V9_NOT_ENOUGH_NON_GOAL_DIAGNOSTIC_WORLDS")
    ranked = sorted(candidates, key=lambda seed: hashlib.sha256(
        f"{WORK_ID}:train-diagnostic:{seed}".encode()).digest())
    held = set(ranked[:max(1, len(ranked) // 5)])
    require(held and held.isdisjoint(protected) and held != set(seeds),
            "V9_WORLD_GROUP_SPLIT_FAILED")
    return held


def mine_safe_teachers(rows, graphs, raw, v8):
    """Discounted *observed* milestone-action behavior; no untried-action labels."""
    examples = []
    worlds = set()
    witnesses = Counter()
    for key in sorted(rows):
        row, graph = rows[key], graphs[key]
        if not row["observed_corridor"] or not graph["safe"]:
            continue
        # Safe lateral demonstrations are MOTOR skills, never fictitious wins.
        if not graph["any_signed_lateral25"] and not graph["safe_goal_dwell_any_path"]:
            continue
        if row["strategy"] not in ("repeat_left", "frozen_v5", "frozen_v6",
                                   "v8_hierarchical"):
            continue
        events = raw[key]
        memory = v8.PublicMemory()
        milestones = [x for x in graph["milestone_option_indices"] if x is not None]
        for i, event in enumerate(events):
            stage, features, mask = memory.features(event["observation"], event["mask"])
            action = event["action"]
            require(mask[action] and event["cost"] == 0,
                    "V9_UNSAFE_TEACHER_ACTION_OR_SHIELD_BYPASS")
            if action != 6:
                # Outcome-derived CREDIT labels only: features remain public past.
                credit = sum(DISCOUNT ** (event_idx - i) for event_idx in milestones
                             if event_idx >= i)
                weight = (1 + min(4.0, credit)) / max(len(events), 1)
                if graph["safe_goal_dwell_any_path"]:
                    weight *= 3.0
                examples.append((key[0], stage, features, mask, action, weight))
            memory.remember(action)
        worlds.add(row["seed"])
        witnesses[row["strategy"]] += 1
    require(len(worlds) >= 10 and len(examples) >= 100,
            "V9_INSUFFICIENT_REAL_SAFE_TEACHERS")
    return examples, sorted(worlds), dict(sorted(witnesses.items()))


def loss(examples, weights, v8):
    if not examples:
        return None
    x, masks, y, w = v8.stage_matrix(examples)
    p = v8.probability(x, masks, weights)
    return float((-np.log(np.maximum(p[np.arange(len(y)), y], 1e-12)) * w).sum() / w.sum())


def fit_stage_weighted(examples, v8, protected_success_seeds=()):
    """Real gradient-based weighted, legal-mask softmax; no physics claim."""
    held = diagnostic_worlds((e[0] for e in examples), protected_success_seeds)
    heads, checks = [], []
    for stage in range(v8.STAGE_COUNT):
        fit = [e for e in examples if e[1] == stage and e[0] not in held]
        diagnostic = [e for e in examples if e[1] == stage and e[0] in held]
        weights = np.zeros((v8.FEATURE_COUNT, v8.ACTION_COUNT), np.float64)
        before_fit = loss(fit, weights, v8)
        before_diag = loss(diagnostic, weights, v8)
        if fit:
            x, masks, labels, w = v8.stage_matrix(fit)
            require(np.all(w > 0) and np.all(np.isfinite(w)),
                    "V9_TRAIN_TEACHER_WEIGHT_INVALID")
            w = w / w.mean()
            rng = np.random.default_rng(LEARNING_SEED + stage)
            for epoch in range(EPOCHS):
                for batch in np.array_split(rng.permutation(len(fit)),
                                            max(1, math.ceil(len(fit) / 256))):
                    xb, mb, yb, wb = x[batch], masks[batch], labels[batch], w[batch]
                    probs = v8.probability(xb, mb, weights)
                    probs[np.arange(len(yb)), yb] -= 1
                    probs *= wb[:, None] / max(float(wb.sum()), 1e-12)
                    gradient = xb.T @ probs + L2 * weights
                    norm = float(np.linalg.norm(gradient))
                    if norm > 5:
                        gradient *= 5 / norm
                    weights -= LEARNING_RATE * gradient
        checks.append({
            "stage": stage, "fit_examples": len(fit),
            "held_train_diagnostic_examples": len(diagnostic),
            "initial_fit_cross_entropy": before_fit,
            "final_fit_cross_entropy": loss(fit, weights, v8),
            "initial_held_train_cross_entropy": before_diag,
            "final_held_train_cross_entropy": loss(diagnostic, weights, v8),
            "fit_improved": bool(fit and loss(fit, weights, v8) < before_fit),
            "held_train_improved": bool(diagnostic and
                                        loss(diagnostic, weights, v8) < before_diag),
        })
        heads.append(weights)
    require(any(check["fit_improved"] for check in checks),
            "V9_REAL_GRADIENT_TRAINING_DID_NOT_LEARN")
    stacked = np.stack(heads)
    require(np.all(np.isfinite(stacked)), "V9_MODEL_PARAMETERS_INVALID")
    return stacked, checks, sorted(held)


def adaptive_curriculum(readout, source_present: str):
    """Preregister decisions from actual stage bottlenecks; no test tuning."""
    strategy = "v8_hierarchical" if source_present == "V8_VERIFIED" else "repeat_left"
    counts = readout["strategies"][strategy]["chronological_counts"]
    funnel = [counts[k] for k in ("contact", "lateral25_after_contact",
                                 "reopen_after_lateral25", "full_stage_safe_goal_dwell")]
    if readout["strategies"][strategy]["unsafe_near"] > 0:
        focus = "safety_shield_repair"
    elif funnel[0] == 0:
        focus = "safe_contact_observation"
    elif funnel[1] < max(1, funnel[0] // 2):
        focus = "contact_to_signed_lateral_25mm"
    elif funnel[2] < max(1, funnel[1] // 2):
        focus = "safe_lateral_to_direct_forward_reopen"
    else:
        focus = "forward_reopen_to_250_tick_safe_goal_dwell"
    return {
        "decision_input": source_present,
        "decision_strategy": strategy,
        "chronological_stage_funnel_counts": funnel,
        "selected_training_focus": focus,
        "focus_rule": "preregistered-first-sub-half-stage-transition-or-final-dwell",
        "next_seed_policy": {
            "train_seed_start": V9_TRAIN_SEED_START,
            "last_public_observation_selection_seed": V9_SELECTION_SCAN_LAST,
            "cohort_near": V9_NEAR_COUNT, "cohort_clear": V9_CLEAR_COUNT,
            "selection": "first ascending seeds: public initial abs(observation[7]) < 0.122 for near; else clear",
            "strategy_order": list(V9_STRATEGIES),
            "paired_real_physics_episodes": V9_EXPECTED_EPISODES,
            "no_future_result_relabeling": True,
        },
        "qualification": {
            "only_train_fresh_worlds": True, "strict_original_7_mask": True,
            "no_dev_cal_test_ood": True,
            "frozen_v5_v6_preserved": True,
            "new_physics_and_independent_positive_replay_required": True,
            "no_model_promotion_authorized": True,
            "checkpoint_does_not_imply_control_improvement": True,
        },
    }


def save_outputs(output: Path, analysis: dict, model: dict, curriculum: dict):
    require(not output.exists(), "V9_REFUSE_OVERWRITE_EXISTING_RUN_EVIDENCE")
    output.mkdir(parents=True)
    files = {
        "stage-readout.json": analysis,
        "candidate-weights.json": model,
        "v9-next-train-plan.json": curriculum,
    }
    for name, value in files.items():
        (output / name).write_text(json.dumps(value, sort_keys=True, indent=2,
                                            ensure_ascii=False, allow_nan=False) + "\n")
    manifest = {
        "schema": SCHEMA + ".output-manifest",
        "source_kind": "verified-train-reanalysis-not-new-physics",
        "file_sha256": {name: file_sha256(output / name) for name in files},
        "never_external_evidence_authority": True,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, sort_keys=True,
                                                       indent=2) + "\n")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v7-restored", required=True, type=Path)
    parser.add_argument("--v7-retained", required=True, type=Path)
    parser.add_argument("--v7-artifact-zip", required=True, type=Path)
    parser.add_argument("--v8-verified", type=Path,
                        help="only when literal V8_EVIDENCE_LOCK has been independently reviewed")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    v8 = checked_v8_trainer()
    with immutable_v7_evidence(args.v7_restored.resolve(), args.v7_retained.resolve(),
                               args.v7_artifact_zip.resolve(), v8) as (root, training, rows, evidence):
        graphs, traces, transition_count = replay_full_train(root, rows, v8)
        require(transition_count == training["actual_transition_count"],
                "V9_REAL_V7_TRANSITION_COUNT_MISMATCH")
        analysis = {
            "schema": SCHEMA + ".readout",
            "work_id": WORK_ID, "evidence": {"v7": evidence},
            "v7": stage_readout(rows, graphs, v8.EXPECTED_STRATEGIES),
            "actual_v7_real_option_transitions": transition_count,
            "negative_evidence": [
                "V7 six novel macros produced no new near-world safe goal wins.",
                "V7 repeat_left provides safe lateral motor demonstration, not new complete wins.",
                "Only two existing near-world goal witness seeds: substantial overfit uncertainty.",
            ],
        }
        source_present = "V7_ONLY_V8_UNSEEN"
        all_rows, all_graphs, all_traces = rows, graphs, traces
        if args.v8_verified is not None:
            # The V8 gate cannot be unlocked via user files/arguments alone.
            v8_root = args.v8_verified.resolve(strict=True)
            v8_training, v8_rows, v8_evidence = verify_v8_locked_evidence(v8_root)
            v8_graphs, v8_traces, v8_count = replay_full_train(v8_root, v8_rows, v8)
            require(v8_count == v8_training["actual_transition_count"],
                    "V9_V8_RAW_PROSPECTIVE_OPTION_COUNT_MISMATCH")
            require(not set(v8_rows).intersection(rows),
                    "V9_V7_V8_TRAIN_COHORT_SEED_LEAK")
            analysis["v8"] = stage_readout(v8_rows, v8_graphs,
                                           tuple(v8_training["strategies"]))
            analysis["evidence"]["v8"] = v8_evidence
            analysis["actual_v8_real_option_transitions"] = v8_count
            all_rows = dict(rows)
            all_rows.update(v8_rows)
            all_graphs = dict(graphs)
            all_graphs.update(v8_graphs)
            all_traces = dict(traces)
            all_traces.update(v8_traces)
            source_present = "V8_VERIFIED"
        samples, worlds, teacher_counts = mine_safe_teachers(all_rows, all_graphs,
                                                               all_traces, v8)
        protected = sorted({seed for (seed, strategy), graph in all_graphs.items()
                            if graph["safe_goal_dwell_any_path"] and
                            all_rows[seed, strategy]["observed_corridor"] and
                            all_rows[seed, strategy]["strategy"] in
                            ("frozen_v5", "frozen_v6", "v8_hierarchical")})
        weights, checks, held = fit_stage_weighted(samples, v8, protected)
        blocked_heads = [c["stage"] for c in checks if
                         not c["fit_improved"] or not c["held_train_improved"]]
        model = {
            "schema": SCHEMA + ".candidate",
            "work_id": WORK_ID,
            "model_type": "stage-progress-weighted four-head public-feature masked-softmax",
            "stage_count": v8.STAGE_COUNT, "feature_count": v8.FEATURE_COUNT,
            "action_count": v8.ACTION_COUNT,
            "weights": weights.tolist(),
            "weights_canonical_sha256": digest(weights.tolist()),
            "v7_immutable_training_sha256": V7_TRAINING_SHA256,
            "v7_immutable_trace_sha256": V7_TRACES_SHA256,
            "v8_model_comparator_sha256": V8_FROZEN_MODEL_SHA256,
            "v8_comparator_outcome_qualified": source_present == "V8_VERIFIED",
            "train_teacher_world_count": len(worlds),
            "train_teacher_transition_count": len(samples),
            "teacher_witness_strategy_counts": teacher_counts,
            "protected_rare_safe_goal_train_world_seeds": protected,
            "train_diagnostic_world_seeds": held,
            "goal_completion_diagnostic_available": False,
            "fit_and_train_diagnostic": checks,
            "blocked_stages_on_train_diagnostic": blocked_heads,
            "learning_seed": LEARNING_SEED, "gradient_epochs": EPOCHS,
            "deployment_authorized": False,
            "ready_for_new_prospective_physics": not blocked_heads and
                                                source_present == "V8_VERIFIED",
            "physics_gain_observed": False,
            "limitations": ["weighted behavior cloning cannot estimate unchosen-action effects",
                            "TRAIN diagnostic is not dev/test qualification",
                            "no independent V8 prospective results yet",
                            "rare safe goal witnesses may overfit"],
        }
        curriculum = adaptive_curriculum(analysis["v8"] if source_present == "V8_VERIFIED"
                                         else analysis["v7"], source_present)
        curriculum["learner_readiness"] = {
            "blocked_stages_on_train_diagnostic": blocked_heads,
            "prospective_v9_episode_dispatch_authorized": False,
            "next_development_action": (
                "first repair underfit/overfit stage heads using new qualified TRAIN teachers; "
                "then freeze revised candidate before running preregistered fresh physics"),
            "never_select_by_dev_cal_test_ood": True,
        }
        analysis["v8_status"] = ("IMMUTABLE_CRACI_REAL_TRAIN_VERIFIED" if source_present ==
                                 "V8_VERIFIED" else
                                 "UNSEEN_PENDING_BYTE_EXACT_INDEPENDENT_CRACI_QUALIFICATION")
        analysis["v9_status"] = "TRAINED_OFFLINE_UNPROMOTED_NO_NEW_PHYSICS"
    output = args.output_dir.resolve()
    manifest = save_outputs(output, analysis, model, curriculum)
    print(json.dumps({"status": "offline_train_only", "work_id": WORK_ID,
                      "stage_readout_sha256": manifest["file_sha256"]["stage-readout.json"],
                      "candidate_weights_sha256": manifest["file_sha256"]["candidate-weights.json"],
                      "prereg_plan_sha256": manifest["file_sha256"]["v9-next-train-plan.json"],
                      "train_teacher_transitions": len(samples),
                      "v8_outcomes_verified": source_present == "V8_VERIFIED"}, sort_keys=True))


if __name__ == "__main__":
    main()
