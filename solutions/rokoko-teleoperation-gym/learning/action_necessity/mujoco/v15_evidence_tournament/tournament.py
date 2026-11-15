"""Risk-first, world-disjoint adaptive experiment *analysis*, not a robot policy.

One genuinely observed MuJoCo TRAIN world supplies all three whole-policy
outcomes. A learned context rule can choose between *already observed complete*
V5 and V12-phase trajectories for an offline paired comparison. The rule never
chooses individual unexecuted actions; the untrained RIGHT4 arm is diagnostic
only. Five folds select rules from FIT worlds and score held-out worlds without
peeking. Diagnostic folds are repeatedly inspected and NOT a final untouched
holdout; no policy leaves this module and no CRACI work is launched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from evidence import (V5, PHASE, EXPLORATORY, STRATEGIES, require,
                      read_unsafe_v13_manifest, read_v12, sha256)

SCHEMA = "junction.rokoko.v15.source-bound-paired-active-tournament.v1"
FOLDS = 5
MIN_RULE_SUPPORT = 3
MIN_FIT_OPTION_SAVINGS = 3
MIN_FIT_IMPROVED_WORLDS = 2
MOTOR_AUTHORIZED = False
MODEL_PROMOTION_AUTHORIZED = False


def fold_for_world(world: dict) -> int:
    """Seed is a partition provenance key, never a policy feature."""
    seed = world["seed"]
    require(type(seed) is int, "V15_WORLD_PROVENANCE_MISSING")
    return seed % FOLDS


def _choice(rule: dict, world: dict) -> str:
    """Only the frozen public initial observation is consulted at inference."""
    if rule["kind"] == "always_v5":
        return V5
    obs, mask = world["public_initial_observation"], world["original_mask"]
    require(len(obs) == 18 and len(mask) == 7 and mask[6] == 1,
            "V15_PUBLIC_INITIAL_INPUT_INVALID")
    y = obs[7]
    require(type(y) in (float, int) and math.isfinite(y),
            "V15_INVALID_PUBLIC_OBSTACLE_Y")
    if rule["kind"] == "threshold_le":
        return PHASE if y <= rule["threshold"] else V5
    if rule["kind"] == "threshold_ge":
        return PHASE if y >= rule["threshold"] else V5
    if rule["kind"] == "public_corridor":
        return PHASE if abs(y) < 0.122 else V5
    raise ValueError("V15_UNREVIEWED_CANDIDATE_GRAMMAR")


def metrics(rule: dict, worlds: list[dict]) -> dict:
    """Paired factual *whole-strategy* outcomes, not counterfactual actions."""
    require(bool(worlds) and len({w["seed"] for w in worlds}) == len(worlds),
            "V15_PAIRED_WORLDS_DUPLICATED_OR_MISSING")
    base_goals = 0
    challenger_goals = 0
    unsafe = 0
    lost = 0
    novel = 0
    phase_worlds = 0
    improved = 0
    worsened = 0
    option_diff = []
    physics_diff = []
    for w in worlds:
        base = w["outcomes"][V5]
        arm = _choice(rule, w)
        require(arm in (V5, PHASE), "V15_UNTRAINED_EXPLORATORY_ARM_SELECTED")
        candidate = w["outcomes"][arm]
        phase_worlds += arm == PHASE
        require(all(type(p["safe_goal"]) is bool and
                    type(p["unsafe"]) is bool and
                    type(p["options"]) is int and p["options"] >= 0 and
                    type(p["physics_ticks"]) is int and p["physics_ticks"] >= 0
                    for p in (base, candidate)),
                "V15_PHYSICAL_OUTCOME_SCHEMA_INVALID")
        base_goals += base["safe_goal"] and not base["unsafe"]
        challenger_goals += candidate["safe_goal"] and not candidate["unsafe"]
        unsafe += candidate["unsafe"]
        lost += (base["safe_goal"] and not base["unsafe"] and
                 (not candidate["safe_goal"] or candidate["unsafe"]))
        novel += (candidate["safe_goal"] and not candidate["unsafe"] and
                  not base["safe_goal"])
        delta = candidate["options"] - base["options"]
        option_diff.append(delta)
        physics_diff.append(candidate["physics_ticks"] - base["physics_ticks"])
        improved += delta < 0
        worsened += delta > 0
    return {"worlds": len(worlds), "baseline_goals": int(base_goals),
            "candidate_goals": int(challenger_goals), "unsafe_worlds": int(unsafe),
            "lost_baseline_goal_worlds": int(lost), "novel_goal_worlds": int(novel),
            "phase_selected_worlds": int(phase_worlds),
            "improved_option_worlds": int(improved),
            "worsened_option_worlds": int(worsened),
            "option_delta_candidate_minus_v5": int(sum(option_diff)),
            "physics_tick_delta_candidate_minus_v5": int(sum(physics_diff)),
            "world_paired_option_deltas": option_diff,
            "world_paired_physics_deltas": physics_diff}


def candidate_grammar(fit: list[dict]) -> list[dict]:
    """Predeclared finite family: two directions per FIT-derived threshold."""
    ys = sorted({float(w["public_initial_observation"][7]) for w in fit})
    rules = [{"kind": "always_v5"}, {"kind": "public_corridor"}]
    for a, b in zip(ys, ys[1:]):
        threshold = (a + b) / 2.
        for kind in ("threshold_le", "threshold_ge"):
            rule = {"kind": kind, "threshold": threshold}
            support = sum(_choice(rule, w) == PHASE for w in fit)
            if MIN_RULE_SUPPORT <= support <= len(fit) - MIN_RULE_SUPPORT:
                rules.append(rule)
    return rules


def choose_on_fit(fit: list[dict]) -> tuple[dict, dict]:
    """Zero unsafe/lost plus savings support are hard gates; tie => V5."""
    baseline = {"kind": "always_v5"}
    best, best_m = baseline, metrics(baseline, fit)
    best_key = (0, 0, 0, 0)
    for rule in candidate_grammar(fit):
        if rule["kind"] == "always_v5":
            continue
        m = metrics(rule, fit)
        if (m["unsafe_worlds"] or m["lost_baseline_goal_worlds"] or
                m["phase_selected_worlds"] < MIN_RULE_SUPPORT or
                m["improved_option_worlds"] < MIN_FIT_IMPROVED_WORLDS or
                m["option_delta_candidate_minus_v5"] > -MIN_FIT_OPTION_SAVINGS or
                m["physics_tick_delta_candidate_minus_v5"] > 0):
            continue
        # The first term rewards true paired complete-trajectory efficiency;
        # later terms penalize more intervention, ticks and grammar complexity.
        key = (-(m["option_delta_candidate_minus_v5"]),
               -(m["physics_tick_delta_candidate_minus_v5"]),
               -m["phase_selected_worlds"],
               -int(rule["kind"] != "public_corridor"))
        if key > best_key:
            best, best_m, best_key = rule, m, key
    return best, best_m


def _individual_deltas(rule: dict, worlds: list[dict]) -> list[int]:
    return [w["outcomes"][_choice(rule, w)]["options"] -
            w["outcomes"][V5]["options"] for w in worlds]


def uncertainty_bounds(deltas: list[int]) -> list[float]:
    """Deterministic world bootstrap, descriptive not an inferential safety CI.

    Returns mean option delta 2.5%/97.5% interval over distinct worlds. All
    samples are world-level and hash-derived, not independent option steps.
    """
    require(bool(deltas), "V15_EMPTY_UNCERTAINTY_SAMPLE")
    n = len(deltas)
    estimates = []
    for replicate in range(1000):
        draw = []
        for index in range(n):
            digest = hashlib.sha256(f"v15|{n}|{replicate}|{index}".encode()).digest()
            draw.append(deltas[int.from_bytes(digest[:8], "big") % n])
        estimates.append(sum(draw) / n)
    estimates.sort()
    return [round(estimates[24], 7), round(estimates[974], 7)]


def source_arm_readout(worlds: list[dict]) -> dict:
    arms = {}
    for arm in STRATEGIES:
        outcomes = [w["outcomes"][arm] for w in worlds]
        arms[arm] = {
            "real_episodes": len(outcomes),
            "original_actual_safe_goal_worlds": sum(o["safe_goal"] and not o["unsafe"]
                                                     for o in outcomes),
            "unsafe_worlds": sum(o["unsafe"] for o in outcomes),
            "original_actual_option_total": sum(o["options"] for o in outcomes),
            "original_actual_physics_ticks": sum(o["physics_ticks"] for o in outcomes),
            "is_untrained_exploration": arm == EXPLORATORY,
            "may_be_selected_by_learned_rule": arm != EXPLORATORY,
        }
    return arms


def summarize_counterexamples(worlds: list[dict]) -> list[dict]:
    """Learn a future source-only question from real *paired* regressions."""
    losses = []
    gains = []
    no_goal = []
    for w in worlds:
        base = w["outcomes"][V5]
        other = w["outcomes"][PHASE]
        delta = other["options"] - base["options"]
        sample = {"world_sha256": w["world_hash"],
                  "initial_public_corridor": abs(w["public_initial_observation"][7]) < .122,
                  "option_delta_phase_minus_v5": delta}
        if delta > 0:
            losses.append(sample)
        if delta < 0:
            gains.append(sample)
        if not base["safe_goal"]:
            no_goal.append(sample)
    return [
        {"hypothesis": "why_all_baseline_policies_fail_goal250",
         "distinct_original_train_worlds": len(no_goal),
         "observed_world_sha256_examples": [x["world_sha256"] for x in no_goal[:3]],
         "needed_next_evidence": "new source-reviewed disjoint MuJoCo TRAIN, only after unsafe V13 stop resolved"},
        {"hypothesis": "why_supported_phase_adds_options",
         "distinct_original_train_worlds": len(losses),
         "observed_world_sha256_examples": [x["world_sha256"] for x in losses[:3]],
         "needed_next_evidence": "predeclared public-trigger change and prospective zero-goal-loss comparison"},
        {"hypothesis": "where_phase_saves_options_without_new_goals",
         "distinct_original_train_worlds": len(gains),
         "observed_world_sha256_examples": [x["world_sha256"] for x in gains[:3]],
         "needed_next_evidence": "world-disjoint repeat; no hidden outcome feature at inference"},
        {"hypothesis": "right4_has_no_qualified_learned_effect_model",
         "distinct_original_train_worlds": 48,
         "observed_world_sha256_examples": [],
         "needed_next_evidence": "many new distinct-world actually executed RIGHT4 actions with independent physics safety"},
    ]


def run_tournament(evidence: dict, quarantine: dict) -> dict:
    require(quarantine["source"] == "V13_INCOMPLETE_QUARANTINED" and
            quarantine["training_rows_accepted"] == 0 and
            quarantine["efficacy_rows_accepted"] == 0 and
            quarantine["physics_dispatch_allowed"] is False,
            "V15_UNSAFE_V13_SOURCE_MUST_BE_QUARANTINED")
    worlds = evidence["worlds"]
    require(len(worlds) == 48 and len({w["world_hash"] for w in worlds}) == 48 and
            evidence["actual_real_episodes"] == 144 and
            evidence["actual_mask_legal_options"] == 4228,
            "V15_SOURCE_BOUND_COMPLETE_PAIRED_DATA_REQUIRED")
    ids = {i: [w for w in worlds if fold_for_world(w) == i] for i in range(FOLDS)}
    require(all(len(ids[i]) >= 5 for i in range(FOLDS)) and
            sum(len(g) for g in ids.values()) == 48,
            "V15_TRAIN_DISJOINT_FOLD_TOO_SMALL")
    folds = []
    oof = []
    all_oof_deltas = []
    for held in range(FOLDS):
        diagnostic = ids[held]
        fit = [w for i,group in ids.items() if i != held for w in group]
        require(not ({w["world_hash"] for w in fit} &
                     {w["world_hash"] for w in diagnostic}),
                "V15_FIT_HELDOUT_WORLD_LEAKAGE")
        selected, fit_metrics = choose_on_fit(fit)
        held_metrics = metrics(selected, diagnostic)
        all_oof_deltas.extend(_individual_deltas(selected, diagnostic))
        oof.append((selected, diagnostic))
        folds.append({"fold": held, "fit_worlds": len(fit),
                      "held_original_worlds": len(diagnostic),
                      "fit_world_set_sha256": sha256("|".join(sorted(w["world_hash"] for w in fit)).encode()),
                      "held_world_set_sha256": sha256("|".join(sorted(w["world_hash"] for w in diagnostic)).encode()),
                      "learned_rule": selected,
                      "fit_option_delta": fit_metrics["option_delta_candidate_minus_v5"],
                      "held_option_delta": held_metrics["option_delta_candidate_minus_v5"],
                      "held_lost_baseline_goal_worlds": held_metrics["lost_baseline_goal_worlds"],
                      "held_unsafe_worlds": held_metrics["unsafe_worlds"],
                      "held_novel_goal_worlds": held_metrics["novel_goal_worlds"],
                      "held_phase_selected_worlds": held_metrics["phase_selected_worlds"]})
    oof_metrics = {"held_worlds": 48, "factual_world_paired_option_delta": sum(all_oof_deltas),
                   "per_world_mean_option_delta": round(sum(all_oof_deltas) / 48, 7),
                   "mean_option_delta_bootstrap_95pct": uncertainty_bounds(all_oof_deltas),
                   "held_lost_baseline_goal_worlds": sum(f["held_lost_baseline_goal_worlds"] for f in folds),
                   "held_unsafe_worlds": sum(f["held_unsafe_worlds"] for f in folds),
                   "held_novel_goal_worlds": sum(f["held_novel_goal_worlds"] for f in folds),
                   "held_selected_phase_worlds": sum(f["held_phase_selected_worlds"] for f in folds)}
    # No final untouched test set here. Even zero observed unsafe is not proof
    # of safety; failed V13 is a mandatory hard stop for further physics.
    return {
        "schema": SCHEMA,
        "evidence_level": "source-verified-original-V12-factual-paired-TRAIN-diagnostic-only",
        "original_source": {k: v for k, v in evidence.items() if k != "worlds"},
        "quarantined_v13": quarantine,
        "cohort": {"unique_original_worlds": 48, "paired_strategies": list(STRATEGIES),
                   "folds": FOLDS, "partition": "seed mod 5; grouped all arms by world; seed never inference",
                   "diagnostic_holdout_is_not_final_test": True,
                   "dev_cal_test_ood_opened": False},
        "original_observed_arm_readout": source_arm_readout(worlds),
        "adaptive_rule_training": {"policy_feature_allowlist": ["initial_public_obstacle_y", "original_public_mask"],
                                   "candidate_grammar": ["always_v5", "public_corridor",
                                                         "threshold_le", "threshold_ge"],
                                   "thresholds_fitted_only_on_nonheld_worlds": True,
                                   "exploratory_right4_excluded": True,
                                   "folds": folds, "crossfit_diagnostic": oof_metrics,
                                   "learner_emits_robot_actions": False},
        "counterexample_driven_next_questions": summarize_counterexamples(worlds),
        "science_decision": "STOP_V13_UNSAFE_AND_V12_ZERO_NOVEL_GOAL",
        "further_paid_physics_authorized": False,
        "model_promotion_authorized": MODEL_PROMOTION_AUTHORIZED,
        "robot_motor_execution_authorized": MOTOR_AUTHORIZED,
        "recommendation": "Retain frozen V5. Fix V13 unsafe causal uncertainty, then preregister and independently review a new source-disjoint prospective TRAIN test. This offline diagnostic cannot qualify physical gain."
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Offline original-V12 paired learning diagnostic; no CRACI dispatch")
    p.add_argument("--original-v12-artifact", type=Path, required=True)
    p.add_argument("--v13-sha-only-manifest", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True,
                   help="Absent local receipt; never overwrite historical evidence")
    args = p.parse_args(argv)
    require(not args.out.exists(), "V15_IMMUTABLE_RECEIPT_ALREADY_EXISTS")
    require(args.out.parent.is_dir() and not args.out.parent.is_symlink(),
            "V15_RECEIPT_PARENT_MUST_EXIST")
    evidence = read_v12(args.original_v12_artifact)
    quarantine = read_unsafe_v13_manifest(args.v13_sha_only_manifest)
    receipt = run_tournament(evidence, quarantine)
    text = json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
    # Exclusive creation avoids overwriting a previous run receipt.
    with args.out.open("x", encoding="utf-8") as f:
        f.write(text)
    print(json.dumps({"receipt": str(args.out),
                      "sha256": sha256(text.encode()),
                      "decision": receipt["science_decision"],
                      "crossfit": receipt["adaptive_rule_training"]["crossfit_diagnostic"]},
                     sort_keys=True))


if __name__ == "__main__":
    main()
