#!/usr/bin/env python3
"""V7 train-only real-MuJoCo ACTION feasibility, not model promotion.

Frozen v6 source/science RED is retained. Every exploratory option obeys the
original 7-action `env.mask`, health/deadman and actual MuJoCo physics. Eight
source-frozen strategies span side, align, retreat and contact-probe variants;
candidate branch decisions see only public 18D observations and own history.
No dev/cal/test/OOD seed is generated, scored or used for selection.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import time

import numpy as np

HERE=Path(__file__).resolve().parent
MUJOCO_DIR=HERE.parent
V6=MUJOCO_DIR/"v6_learning"
V6_SHA="0fcf7fe87e6169aa383807ec8616cc6f98694aca"
for path in (str(V6),str(MUJOCO_DIR)):
    if path not in sys.path:
        sys.path.insert(0,path)
spec=importlib.util.spec_from_file_location("rokoko_frozen_v6_feasibility_parent",V6/"run.py")
if spec is None or spec.loader is None:
    raise ImportError("IMMUTABLE_V6_RUNNER_MISSING")
v6=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v6)

SCHEMA="junction.rokoko.mujoco-v7.action-feasibility.v1"
FIRST_SEED=512_000
MAX_SELECTION_SEEDS=512
TARGET_NEAR=128
TARGET_CLEAR=32
NEXT_TRAIN_SEED=513_000
FROZEN_SEED_MIN=120_000
FROZEN_SEED_MAX_EXCLUSIVE=520_000
OBSERVED_CORRIDOR_THRESHOLD=.122
MAX_OPTIONS=60
RNG_SEED=20261114
STRATEGIES=("frozen_v5","frozen_v6","repeat_left","repeat_right",
            "align_left","align_right","retreat_left","observed_branch")

# Immutable actual v6 CRACI #43637420554 artifact 14131030766, source0fcf...
FROZEN_V6_WEIGHTS={
    "align_budget":3,"contact_probe_period":4,"corridor_exit_x":.125665,
    "desired_lane_y":.0346771,"lateral_progress_epsilon":.0025979,
    "pusher_clearance":.055,"replan_budget":3,"side_budget":10,
}
FROZEN_V6_WEIGHTS_SHA="ce00c75b40f508713011e522643910cc41cb2c900324e09275d5ae46ff077578"


def canonical_bytes(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def write_compact_new(path,value):
    """Keep 1,280-trial human-inspectable sparse receipt under 32 MiB."""
    with path.open("x",encoding="utf-8") as stream:
        stream.write(canonical_bytes(value).decode("utf-8")+"\n")


if digest(FROZEN_V6_WEIGHTS)!=FROZEN_V6_WEIGHTS_SHA:
    raise RuntimeError("IMMUTABLE_ACTUAL_V6_MODEL_SHA_MISMATCH")
v6.validate_weights(FROZEN_V6_WEIGHTS)


class ExploratoryMacro:
    """Seven-option observation-only masked contact exploration controller."""
    PLAN={
        "repeat_left":(3,3,3,3,1,3,3,1),
        "repeat_right":(4,4,4,4,1,4,4,1),
        "align_left":(0,0,3,3,1,3,1,3),
        "align_right":(0,0,4,4,1,4,1,4),
        "retreat_left":(5,0,3,3,1,3,1,0),
    }

    def __init__(self,style):
        if style not in (*self.PLAN,"observed_branch"):
            raise ValueError("UNKNOWN_FEASIBILITY_MACRO")
        self.style=style
        self.ticks=0
        self.previous=None
        self.previous_action=None
        self.stall=0
        self.last_option=None

    def _branch(self,o):
        # Deterministic branch policy observes only noisy object, pusher and
        # mapped obstacle; never a seed/world latent or true contact force.
        sign=1 if float(o[7])>=float(o[1]) else -1
        side=3 if sign>0 else 4
        if self.previous is not None and self.previous_action in (1,3,4):
            moved=(float(self.previous[1])-float(o[1]))*sign
            self.stall=0 if moved>.0015 else self.stall+1
        self.previous=o.copy()
        if self.ticks in (0,1):
            return 0
        if self.stall>=5:
            self.stall=0
            return 5
        if self.ticks%4==0:
            return 1
        if self.ticks%9==0:
            return 0
        return side

    def __call__(self,obs,mask):
        o=np.asarray(obs,dtype=float)
        m=np.asarray(mask,dtype=bool)
        if o.shape!=(18,) or m.shape!=(7,):
            raise ValueError("FEASIBILITY_18D_7MASK_ABI_REQUIRED")
        if not m[:6].any():
            self.previous_action=6
            self.last_option=6
            return 6  # frozen health/deadman always wins
        if self.style=="observed_branch":
            preferred=self._branch(o)
        else:
            seq=self.PLAN[self.style]
            preferred=seq[self.ticks%len(seq)]
        self.ticks+=1
        # No off-mask actuation: consider bounded alternative *masked* options
        # in a fixed, predeclared order when the primary action is not allowed.
        for action in (preferred,0,5,1,3,4,2):
            if m[action]:
                self.previous_action=int(action)
                self.last_option=int(action)
                return int(action)
        self.previous_action=6
        self.last_option=6
        return 6


def policy_factory(name):
    if name=="frozen_v5":
        return v6.v5.make_factory(v6.V5_FROZEN_WEIGHTS)
    if name=="frozen_v6":
        return v6.make_factory(FROZEN_V6_WEIGHTS)
    if name not in STRATEGIES:
        raise ValueError("NONREGISTERED_FEASIBILITY_STRATEGY")
    return lambda:ExploratoryMacro(name)


def parse_args(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode",choices=("train-feasibility",),required=True)
    p.add_argument("--require-git",action="store_true")
    p.add_argument("--expected-head",required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--max-seeds",type=int,default=512)
    p.add_argument("--time-budget-seconds",type=int,default=1200)
    return p.parse_args(argv)


def validate_args(args):
    if not 1<=args.max_seeds<=MAX_SELECTION_SEEDS:
        raise ValueError("SELECTION_LIMIT_OUT_OF_BOUNDS")
    if not 60<=args.time_budget_seconds<=1380:
        raise ValueError("TIME_LIMIT_OUT_OF_BOUNDS")
    if not (FROZEN_SEED_MIN<=FIRST_SEED<FIRST_SEED+MAX_SELECTION_SEEDS<=
            NEXT_TRAIN_SEED and NEXT_TRAIN_SEED+999<FROZEN_SEED_MAX_EXCLUSIVE):
        raise ValueError("FROZEN_CONTACT_ENV_SEED_DOMAIN_BREACH")
    if FIRST_SEED <= v6.v5.v4.v3.v2.v1.SEED_BANDS["ood"][1]:
        raise ValueError("FEASIBILITY_TRAIN_AND_HOLDOUT_BANDS_OVERLAP")


def source_identity(require_git,expected_head):
    if not require_git or len(expected_head)!=40 or any(c not in "0123456789abcdef"
                                                     for c in expected_head):
        raise PermissionError("V7_EXACT_SOURCE_GIT_HEAD_REQUIRED")
    root=subprocess.check_output(["git","-C",str(HERE),"rev-parse","--show-toplevel"],
                                 text=True,timeout=15).strip()
    head=subprocess.check_output(["git","-C",root,"rev-parse","HEAD"],
                                 text=True,timeout=15).strip()
    if head!=expected_head:
        raise RuntimeError("V7_GIT_HEAD_MISMATCH")
    dirty=subprocess.check_output(["git","-C",root,"status","--porcelain=v1",
                                    "--untracked-files=no"],text=True,timeout=15).strip()
    if dirty:
        raise RuntimeError("V7_TRACKED_SOURCE_OVERLAY_REFUSED")
    if subprocess.run(["git","-C",root,"merge-base","--is-ancestor",V6_SHA,head],
                      capture_output=True,timeout=15).returncode:
        raise RuntimeError("V7_NOT_DESCENDED_FROM_IMMUTABLE_V6_NEGATIVE")
    return head


def select_train_worlds(env,max_seeds):
    """Select first near128 / clear32 by ascending *train-only* seed.

    Near/clear uses solely the first *public noisy observed* obstacle y,
    never hidden true obstacle choices or post-outcome labels.
    """
    near=[]
    clear=[]
    selection_scan=[]
    for seed in range(FIRST_SEED,FIRST_SEED+max_seeds):
        observed=env.reset(seed=seed,ood=False)
        world_hash=v6.v5.v4.v3.v2.v1._world_signature(env)
        row=dict(seed=seed,world_hash=world_hash,
                 initial_observed_obstacle_y=float(observed[7]),
                 observed_corridor=abs(float(observed[7]))<OBSERVED_CORRIDOR_THRESHOLD)
        selection_scan.append(dict(seed=seed,
                                   initial_observed_obstacle_y=row["initial_observed_obstacle_y"],
                                   world_hash=world_hash))
        if row["observed_corridor"] and len(near)<TARGET_NEAR:
            near.append(row)
        elif not row["observed_corridor"] and len(clear)<TARGET_CLEAR:
            clear.append(row)
        if len(near)==TARGET_NEAR and len(clear)==TARGET_CLEAR:
            break
    if len(near)<TARGET_NEAR or len(clear)<TARGET_CLEAR:
        raise RuntimeError("TRAIN_ONLY_PUBLIC_WORLD_COHORT_INSUFFICIENT")
    return (sorted(near,key=lambda r:r["seed"]),
            sorted(clear,key=lambda r:r["seed"]),selection_scan)


def scheduled_trials(near,clear):
    """ALL eight strategies on identical first128 near + first32 clear worlds.

    Fully paired design pre-registered before any outcome. This is train-only
    feasibility comparison; never infer a validated generalization gain.
    """
    plan=[]
    for row in sorted([*near,*clear],key=lambda item:item["seed"]):
        for strategy in STRATEGIES:
            plan.append((row,strategy,"all_eight_paired_train_feasibility"))
    return plan


def sparse_indices(n):
    return sorted(set(range(min(12,n))) |
                  set(range(max(0,n-8),n)) |
                  set(range(0,n,5)))


def signed_obstacle_away_displacement(first_observation,last_observation):
    """Signed public-observation-only object progress away from obstacle.

    An obstacle at or above the object requires negative delta-y; one below
    requires positive delta-y. Negative values denote motion *toward* it.
    """
    first=np.asarray(first_observation,dtype=float)
    last=np.asarray(last_observation,dtype=float)
    if first.shape!=(18,) or last.shape!=(18,):
        raise ValueError("SIGNED_LATERAL_18D_REQUIRED")
    sign=-1. if float(first[7])>=float(first[1]) else 1.
    return (float(last[1])-float(first[1]))*sign


def verify_contact_trace(transitions,contacts):
    """Cumulative physics contacts must grow monotonically and end at total."""
    if not transitions:
        raise ValueError("CONTACT_EVIDENCE_EMPTY")
    cumulative=[int(t["contacts_cumulative"]) for t in transitions]
    if any(c<0 for c in cumulative) or any(b<a for a,b in zip(cumulative,cumulative[1:])):
        raise ValueError("CONTACT_CUMULATIVE_NOT_MONOTONE")
    if cumulative[-1]!=int(contacts):
        raise ValueError("CONTACT_TERMINAL_TOTAL_MISMATCH")


def verify_terminal_success(transitions,result):
    """No source-valid 'win' without contact, dwell, physics and public goal."""
    if not transitions:
        raise ValueError("SUCCESS_EVIDENCE_EMPTY")
    last=transitions[-1]
    if bool(result["success"])!=bool(last["success_info"]):
        raise ValueError("SUCCESS_INFO_MISMATCH")
    if bool(result["abstained"]) and int(last["action"])!=6:
        raise ValueError("ABSTAIN_LAST_ACTION_INVALID")
    dwell=[int(t["dwell_ticks_cumulative"]) for t in transitions]
    if any(b<a for a,b in zip(dwell,dwell[1:])):
        raise ValueError("DWELL_RUNNING_PEAK_NONMONOTONE")
    if int(result["dwell_ticks_final"])!=int(last["dwell_ticks_current"]):
        raise ValueError("DWELL_TERMINAL_RAW_COUNTER_MISMATCH")
    if bool(result["success"]):
        final=np.asarray(last["next_observation"],dtype=float)
        goal_distance=float(np.linalg.norm(final[:2]-final[16:18]))
        if (int(result["dwell_ticks_final"])<250 or
            int(last["contacts_cumulative"])<1 or
            int(result["physics_steps"])<=0 or
            bool(result["unsafe"]) or bool(result["abstained"]) or
            int(last["action"])==6 or goal_distance>=.025):
            raise ValueError("NONPHYSICAL_OR_UNSAFE_SUCCESS_CLAIM")


def real_rollout(env,seed,strategy,deadline):
    """No shortcut/synthetic physics. Complete raw transitions are returned."""
    from env import ACTIONS
    factory=policy_factory(strategy)
    controller=factory()
    observed=env.reset(seed=seed,ood=False)
    world_hash=v6.v5.v4.v3.v2.v1._world_signature(env)
    initial_observation=np.asarray(observed,dtype=float).copy()
    all_transitions=[]
    last=None
    saw_forward_masked=False
    forward_reopened_after_side=0
    side_proposals=0
    side_contact_option_steps=[]
    previous_contacts=0
    peak_dwell=0
    side_forward_reopen_trace=[]
    for option in range(MAX_OPTIONS):
        if time.monotonic()>=deadline:
            raise TimeoutError("V7_REAL_PHYSICS_TRIAL_TIME_CEILING")
        allowed=env.mask(observed)
        action=controller(observed.copy(),allowed.copy())
        if type(action) is not int or not 0<=action<=6 or not allowed[action]:
            raise RuntimeError("V7_OPTION_OUTSIDE_SEVEN_OPTION_SHIELD")
        before=np.asarray(observed,dtype=float).tolist()
        m=np.asarray(allowed,dtype=bool).astype(int).tolist()
        saw_forward_masked|=not(m[1] or m[2])
        observed,reward,done,last=env.step(action)
        peak_dwell=max(peak_dwell,int(env.dwell))
        if action in (3,4) and int(last["contacts"])>previous_contacts:
            side_contact_option_steps.append(option+1)
        previous_contacts=int(last["contacts"])
        now_mask=env.mask(observed)
        if action in (3,4):
            side_proposals+=1
        if saw_forward_masked and action in (3,4) and (now_mask[1] or now_mask[2]):
            forward_reopened_after_side+=1
            side_forward_reopen_trace.append(option+1)
            saw_forward_masked=False
        all_transitions.append(dict(observation=before,mask=m,action=int(action),
                                    reward=float(reward),cost=int(last["cost"]),
                                    done=bool(done),
                                    contacts_cumulative=int(last["contacts"]),
                                    dwell_ticks_current=int(env.dwell),
                                    dwell_ticks_cumulative=peak_dwell,
                                    success_info=bool(last["success"]),
                                    next_observation=np.asarray(observed,dtype=float).tolist()))
        if done:
            break
    if not all_transitions or last is None:
        raise AssertionError("NO_REAL_MUJOCO_OPTION_TRANSITIONS")
    verify_contact_trace(all_transitions,env.contacts)
    zero_physics=int(env.physics_steps)==0
    if zero_physics and not (len(all_transitions)==1 and all_transitions[0]["action"]==6
                             and env.abstained and not last["success"] and not env.unsafe):
        raise AssertionError("UNACCOUNTED_FIRST_ABSTAIN_ZERO_PHYSICS")
    signed_away=signed_obstacle_away_displacement(initial_observation,observed)
    result=dict(seed=seed,world_hash=world_hash,strategy=strategy,
                success=bool(last["success"]),unsafe=bool(last["unsafe"]),
                abstained=bool(last["abstained"]),
                zero_physics_abstain=zero_physics,
                physics_steps=int(env.physics_steps),option_steps=int(env.steps),
                contacts=int(env.contacts),
                side_contact_option_steps=side_contact_option_steps,
                dwell_ticks_final=int(env.dwell),
                lateral_displacement=round(signed_away,8),
                away_lateral_displacement=round(max(0.,signed_away),8),
                final_error=float(last["error"]),
                total_reward=round(sum(x["reward"] for x in all_transitions),8),
                side_proposals=side_proposals,
                forward_reopened_after_side=forward_reopened_after_side,
                forward_reopen_option_steps=side_forward_reopen_trace,
                contact_to_forward_to_dwell=bool(
                    side_contact_option_steps and side_forward_reopen_trace and
                    int(env.dwell)>=250 and bool(last["success"])),
                full_transition_count=len(all_transitions),
                full_transition_sha256=digest(all_transitions),
                sparse_trace=True,
                sparse_transition_indices=sparse_indices(len(all_transitions)))
    verify_terminal_success(all_transitions,result)
    result["transitions"]=[all_transitions[i] for i in result["sparse_transition_indices"]]
    return result,all_transitions


def assess(trials,near,clear):
    stats={}
    for strategy in STRATEGIES:
        rows=[r for r in trials if r["strategy"]==strategy]
        corridor=[r for r in rows if r["observed_corridor"]]
        stats[strategy]=dict(trials=len(rows),near_trials=len(corridor),
                             near_safe_success=sum(int(r["success"] and not r["unsafe"])
                                                   for r in corridor),
                             near_unsafe=sum(int(r["unsafe"]) for r in corridor),
                             near_abstain=sum(int(r["abstained"]) for r in corridor),
                             near_contact=sum(int(r["contacts"]>0) for r in corridor),
                             near_side_lateral_ge_025=sum(int(r["away_lateral_displacement"]>=.025)
                                                          for r in corridor),
                             near_forward_reopen=sum(r["forward_reopened_after_side"]
                                                     for r in corridor))
    safe_near=[r for r in trials if r["observed_corridor"] and r["success"] and
               not r["unsafe"]]
    lateral=[r for r in trials if r["observed_corridor"] and
             r["away_lateral_displacement"]>=.025 and not r["unsafe"]]
    any_positive=bool(safe_near)
    return dict(schema=SCHEMA+".qualification",advisory_only=True,
                no_dev_evaluation=True,promotion_authorized=False,
                mechanism_positive=any_positive,
                at_least_one_safe_near_success=any_positive,
                at_least_one_safe_lateral_ge_025=bool(lateral),
                near_distinct_worlds=len(near),clear_distinct_worlds=len(clear),
                safe_near_trial_count=len(safe_near),
                safe_near_distinct_worlds=len({r["seed"] for r in safe_near}),
                safe_near_success_seed_examples=sorted({r["seed"] for r in safe_near})[:16],
                per_strategy=stats,
                scientific_interpretation=("feasibility demonstrated in sampled synthetic MuJoCo task"
                                           if any_positive else
                                           "safe feasibility not demonstrated among tested policies; "
                                           "NOT a mathematical impossibility proof"))


def next_experiment(qualification):
    if qualification["mechanism_positive"]:
        objective="train an observation-only policy from witnessed safe contact sequences"
        candidate="new action-policy learning, then frozen new dev with independent review"
    else:
        objective="investigate whether current seven primitive actions can cross near obstacle"
        candidate="separate explicit physics/env primitive version proposal; no silent env patch"
    return dict(schema=SCHEMA+".next_experiment",proposal_only=True,
                no_auto_dispatch=True,no_auto_env_change=True,
                evidence_source="train-only actual MuJoCo receipts",
                objective=objective,candidate=candidate,
                future_train_seeds=f"{NEXT_TRAIN_SEED}..{NEXT_TRAIN_SEED+999}",
                existing_dev_cal_test_ood_unopened=True)


def main(argv=None):
    args=parse_args(argv)
    validate_args(args)
    head=source_identity(args.require_git,args.expected_head)
    try:
        import mujoco
        from physics import MovingContactEnv
    except ImportError as exc:
        raise RuntimeError("REAL_MUJOCO_3_3_7_REQUIRED_NOT_EMULATED") from exc
    if mujoco.__version__!="3.3.7":
        raise RuntimeError("MUJOCO_3_3_7_PIN_REQUIRED")
    output=v6.v5.output_root(args.output_dir)
    deadline=time.monotonic()+args.time_budget_seconds
    env=MovingContactEnv(max_options=MAX_OPTIONS)
    near,clear,selection_scan=select_train_worlds(env,args.max_seeds)
    schedule=scheduled_trials(near,clear)
    trials=[]
    artifact=output/"full_transitions.jsonl.gz"
    with gzip.open(artifact,"xt",encoding="utf-8",newline="\n",compresslevel=6) as stream:
        for definition,strategy,phase in schedule:
            if time.monotonic()>=deadline:
                raise TimeoutError("V7_COHORT_TIME_CEILING_BEFORE_COMPLETE_EXPERIMENT")
            row,full=real_rollout(env,definition["seed"],strategy,deadline)
            if row["world_hash"]!=definition["world_hash"]:
                raise AssertionError("V7_LATENT_WORLD_MISMATCH_ACROSS_STRATEGIES")
            row.update(initial_observed_obstacle_y=definition["initial_observed_obstacle_y"],
                       observed_corridor=definition["observed_corridor"],
                       allocation_phase=phase)
            trials.append(row)
            record=dict(seed=row["seed"],strategy=strategy,transitions=full)
            stream.write(canonical_bytes(record).decode("utf-8")+"\n")
    if (len({r["seed"] for r in trials if r["observed_corridor"]})!=TARGET_NEAR or
            len({r["seed"] for r in trials if not r["observed_corridor"]})!=TARGET_CLEAR):
        raise AssertionError("V7_DISTINCT_TRAIN_COHORT_INCOMPLETE")
    training=dict(schema=SCHEMA+".training",executed_head=head,
                  actual_physics_engine=f"mujoco-{mujoco.__version__}",
                  train_first_seed=FIRST_SEED,selection_seed_limit=args.max_seeds,
                  selection_scan=selection_scan,
                  selected_near_count=len(near),selected_clear_count=len(clear),
                  near_seeds=[r["seed"] for r in near],
                  clear_seeds=[r["seed"] for r in clear],
                  strategies=list(STRATEGIES),allocation="all eight fixed strategies on identical 160 training worlds",
                  no_dev_evaluation=True,
                  frozen_v5_weights_sha256=v6.V5_FROZEN_WEIGHTS_SHA256,
                  frozen_v6_weights_sha256=FROZEN_V6_WEIGHTS_SHA,
                  actual_transition_count=sum(r["full_transition_count"] for r in trials),
                  trials=trials,dataset_sha256=digest(trials),
                  source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (HERE/"run.py",)},
                  no_provider_billing_assertion=True)
    write_compact_new(output/"training.json",training)
    qualification=assess(trials,near,clear)
    qualification["executed_head"]=head
    v6.v5.write_new(output/"qualification.json",qualification)
    suggestion=next_experiment(qualification)
    suggestion["executed_head"]=head
    v6.v5.write_new(output/"next_experiment.json",suggestion)
    manifest=dict(schema=SCHEMA+".manifest",executed_head=head,
                  file_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (output/"training.json",output/"full_transitions.jsonl.gz")},
                  auxiliary_file_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in (output/"qualification.json",output/"next_experiment.json")},
                  source_sha256=training["source_sha256"],
                  generated_at=datetime.now(timezone.utc).isoformat(),
                  no_external_spend_proof=True)
    v6.v5.write_new(output/"manifest.json",manifest)
    print(json.dumps(dict(executed_head=head,real_trials=len(trials),
                          actual_transition_count=training["actual_transition_count"],
                          selected_near_count=len(near),selected_clear_count=len(clear),
                          dataset_sha256=training["dataset_sha256"],
                          advisory=qualification["scientific_interpretation"],
                          evidence=str(output)),sort_keys=True))
    # Feasibility absence is a meaningful negative finding, not a workflow
    # failure. Exit 0 only when the complete source-bound evidence exists.
    return 0


if __name__=="__main__":
    raise SystemExit(main())
