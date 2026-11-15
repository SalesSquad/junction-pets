"""V11 goal-preserving arbitration learned from *observed* V10 TRAIN failures.

This is a finite, auditable, source-bound hypothesis search, not an RL reward
claim.  World-level labels use observed real MuJoCo success and forward reopen;
inference uses only public 18D observation, 7D mask and bounded local history.
The primary objective is ZERO interference with known V5 goal winners.  A
covered failed world is only an opportunity, never a candidate GOAL claim.
"""

from __future__ import annotations

import hashlib
import json
import math


GATE_KINDS = ("blocked_side", "v5_abstain_side", "blocked_or_abstain_side",
              "blocked_side_no_align")
GOAL_DISTANCES = (.035, .045, .060, .080)
STREAKS = (1, 2, 3)
OBSTACLE_LIMITS = (.122, .100)
OBS_COUNT = 18
MASK_COUNT = 7
BASELINE = "frozen_v5"
RESCUE = "v10_loss_informed"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def public_distance(observation):
    require(len(observation) == OBS_COUNT and all(isinstance(v, (int, float)) and
            math.isfinite(v) for v in observation), "V11_INVALID_PUBLIC_OBSERVATION")
    return math.hypot(observation[16] - observation[0],
                      observation[17] - observation[1])


def candidate_input(kind, observation, mask, v5_action, min_distance, obstacle_limit):
    require(kind in GATE_KINDS and len(mask) == MASK_COUNT and
            all(m in (0, 1) for m in mask) and
            isinstance(v5_action, int) and 0 <= v5_action < MASK_COUNT and
            mask[v5_action] == 1, "V11_INVALID_PUBLIC_ACTION_MASK")
    if public_distance(observation) <= min_distance or abs(observation[7]) >= obstacle_limit:
        return False
    lateral = bool(mask[3] or mask[4])
    blocked = not mask[1] and not mask[2] and lateral
    abstain = v5_action == 6 and lateral
    if kind == "blocked_side": return bool(blocked)
    if kind == "v5_abstain_side": return bool(abstain)
    if kind == "blocked_or_abstain_side": return bool(blocked or abstain)
    return bool(blocked and not mask[0])


def episodes_with_gate(trace, params):
    """Report if/when the gate would fire on an ORIGINAL V5 observed trajectory.

    This never fabricates the altered trajectory that would follow a rescue.
    """
    streak = 0
    for idx, step in enumerate(trace):
        allowed = candidate_input(params["kind"], step["observation"],step["mask"],
                                  step["action"], params["min_distance"],
                                  params["obstacle_limit"])
        streak = streak+1 if allowed else 0
        if streak >= params["min_streak"]:
            return idx
    return None


def _group(seed):
    """Fixed, no outcomes in split: 4/5 FIT, 1/5 disjoint TRAIN diagnostic."""
    return "held_train" if seed % 5 == 0 else "fit_train"


def compile_features(rows, full):
    seeds=sorted(seed for seed,strategy in rows if strategy == BASELINE)
    require(len(seeds) == 160 and len(set(seeds)) == 160,
            "V11_EXPECT_160_FRESH_PAIRED_TRAIN_WORLDS")
    worlds=[]
    for seed in seeds:
        v5, v10=rows[seed,BASELINE],rows[seed,RESCUE]
        require(v5["world_hash"]==v10["world_hash"] and
                not v5["unsafe"] and not v10["unsafe"],
                "V11_PAIRED_SOURCE_WORLD_OR_SAFETY_DRIFT")
        trace=full[seed,BASELINE]
        # This is a candidate *opportunity* on the same world but different
        # trajectory. Never call it a demonstrated cross-policy action label.
        v10_reopened=bool(v10["forward_reopened_after_side"]>0)
        worlds.append({"seed":seed,"split":_group(seed),
                       "v5_goal":bool(v5["success"]),
                       "v10_goal":bool(v10["success"]),
                       "v10_reopened":v10_reopened,
                       "v5_options":len(trace),"trace":trace,
                       "observed_corridor":bool(v5["observed_corridor"])})
    require(sum(w["v5_goal"] for w in worlds)==37 and
            sum(w["v10_goal"] for w in worlds)==26 and
            all(not w["v10_goal"] or w["v5_goal"] for w in worlds),
            "V11_BASELINE_GOAL_DOMINANCE_CHANGED")
    return worlds


def score_gate(worlds, params, split):
    subset=[w for w in worlds if w["split"]==split]
    fired=[(w,episodes_with_gate(w["trace"],params)) for w in subset]
    positive=[w for w,t in fired if t is not None and w["v5_goal"]]
    eligible=[w for w,t in fired if t is not None and not w["v5_goal"] and
              w["v10_reopened"] and w["observed_corridor"]]
    anyfail=[w for w,t in fired if t is not None and not w["v5_goal"]]
    return {"source_worlds":len(subset),"v5_winning_worlds":sum(w["v5_goal"] for w in subset),
            "fired_on_v5_goal_worlds":len(positive),
            "triggered_baseline_failure_worlds":len(anyfail),
            "covered_v10_reopen_opportunity_worlds":len(eligible),
            "triggered_world_seeds":[w["seed"] for w,t in fired if t is not None],
            "fired_winning_world_seeds":[w["seed"] for w in positive],
            "v10_reopen_opportunity_seed_ids":[w["seed"] for w in eligible]}


def train_goal_preserving_gate(worlds):
    configs=[{"kind":kind,"min_distance":distance,"min_streak":streak,
              "obstacle_limit":obstacle}
             for kind in GATE_KINDS for distance in GOAL_DISTANCES
             for streak in STREAKS for obstacle in OBSTACLE_LIMITS]
    ranked=[]
    for params in configs:
        fit=score_gate(worlds,params,"fit_train")
        # Hard frozen-V5 success preservation. Gate cannot pass FIT with a
        # single observed safe-goal-world trigger, regardless of opportunity.
        if fit["fired_on_v5_goal_worlds"]:continue
        ranked.append((params,fit))
    require(bool(ranked),"V11_NO_GOAL_PRESERVING_PUBLIC_GATE")
    ranked.sort(key=lambda pair:(-pair[1]["covered_v10_reopen_opportunity_worlds"],
                  -pair[1]["triggered_baseline_failure_worlds"],
                  GATE_KINDS.index(pair[0]["kind"]),
                  pair[0]["min_distance"],pair[0]["min_streak"],
                  pair[0]["obstacle_limit"]))
    params,fit=ranked[0]
    held=score_gate(worlds,params,"held_train")
    # No tuning on held diagnostics: if frozen V5 wins are touched, STOP.
    decision=("SOURCE_ONLY_PUBLIC_GATE_REVIEW_CANDIDATE" if
              held["fired_on_v5_goal_worlds"]==0 and
              fit["covered_v10_reopen_opportunity_worlds"]>0 else
              "NO_GO_UNPROTECTED_FROZEN_GOAL_OR_NO_RESCUE_OPPORTUNITY")
    return {"schema":"junction.rokoko.v11.goal-preserving-abstain-gate.v1",
            "hypothesis":("V5 wins are baseline; V10 is allowed only as bounded "
                          "early public-mask rescue. Navigational reopen is NOT success."),
            "selection_objective":("max V10 observed reopen coverage among V5-failed FIT "
                                   "worlds, subject to zero gate triggers on every V5 FIT winner"),
            "candidate_params":params,"fit_train":fit,"held_train":held,
            "selection_pool_configs":len(configs),"fit_eligible_configs":len(ranked),
            "decision":decision,"new_physics_executed":False,
            "dev_cal_test_ood_opened":False,"model_promotion_authorized":False}


def derive_bounded_rescue_options(real_v10_traces):
    """Learn only the motor *budget* from real V10 public TRAIN traces.

    A visible blocked+side option followed by first legal forward option is
    observed navigation, not physical goal success.  Pick the smallest integer
    with >=97% coverage on FIT TRAIN; require >=97% on disjoint HELD TRAIN.
    Never inspect environment internals, sealed labels or other data.
    """
    by_split={"fit_train":[], "held_train":[]}
    for (seed,strategy),trace in real_v10_traces.items():
        if strategy != RESCUE:continue
        entry=None
        for idx,step in enumerate(trace):
            mask=step["mask"]
            if entry is None and step["action"] in (3,4) and not(mask[1] or mask[2]):
                entry=idx
            elif entry is not None and (mask[1] or mask[2]) and idx > entry:
                by_split[_group(seed)].append(idx-entry)
                break
    require(len(by_split["fit_train"]) >= 50 and len(by_split["held_train"]) >= 15,
            "V11_SOURCE_OBSERVED_REOPEN_WINDOWS_INSUFFICIENT")
    fit=by_split["fit_train"]
    cap=next((options for options in range(1,13)
              if sum(gap<=options for gap in fit)/len(fit) >= .97),None)
    require(cap is not None,"V11_NO_BOUNDED_REOPEN_BUDGET_FITS")
    held=by_split["held_train"]
    require(sum(gap<=cap for gap in held)/len(held) >= .97,
            "V11_HELD_PUBLIC_REOPEN_BUDGET_NOT_SUPPORTED")
    return {"cap":cap,"selectionRule":"minimum options covering >=97% FIT observed V10 blocked-side-to-forward-reopen windows, supported by HELD TRAIN",
            "fit": {"count":len(fit),"withinCap":sum(gap<=cap for gap in fit),"max":max(fit)},
            "held":{"count":len(held),"withinCap":sum(gap<=cap for gap in held),"max":max(held)},
            "physicalGoalPerformanceMeasured":False}
