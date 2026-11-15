"""Bounded, public-only V13 causal reachability witness search.

This is an *offline TRAIN oracle* over already-seen V12 worlds. Branches are
reconstructed by reset(seed)+identical prefix replay, NOT mj_copyState (the
original environment also contains Python RNG, mutable model, motor target,
sensor/deadman and contact counters outside mjData). Every branch proposal
uses only the current public 18D observation and original seven-option mask.
Actual original MuJoCo result is measured AFTER execution for TRAIN evidence,
never supplied as a policy input. No result establishes deployment safety.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time

import forensic


SCHEMA="junction.rokoko.v13.finite-original-mujoco-causal-replay.v1"
MAX_ORIGINAL_OPTIONS=60
MAX_DEPTH=3
BEAM_WIDTH=2
MAX_WORLD_BRANCHES=20
MAX_TOTAL_BRANCHES=36*MAX_WORLD_BRANCHES
MAX_RUNTIME_SECONDS=1200
ORIGINAL_GOAL_TICKS=250


def require(ok,code):forensic.require(ok,code)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()


def public_goal_distance(o):
    return math.hypot(o[16]-o[0],o[17]-o[1])


def frozen_first_fork(v5_trace,seed):
    """Pre-registered first *public* recovery opportunity, TRAIN failure only.

    The source failure outcome is used solely to select a known-failed TRAIN
    world for diagnosis; future selection never observes future success.
    """
    require(bool(v5_trace),"V13_MISSING_ORIGINAL_V5_FULL_TRACE")
    for i,t in enumerate(v5_trace):
        o,m=t["observation"],t["mask"]
        forensic.public(o,m)
        if t["action"]==6 and o[10] and not o[15] and any(m[:6]):
            return i,"EARLY_LIVE_ABSTAIN"
    # Exogenous public live drops at option17: future release cannot be
    # predicted from the initial 18D. This is an early pre-release TRAIN
    # diagnostic at option6 (index5), not proof that release can be overcome.
    if any(t["next_observation"][10]==0 for t in v5_trace):
        require(len(v5_trace)>6,"V13_RELEASED_SOURCE_PREFIX_TOO_SHORT")
        return 5,"PRE_RELEASE_SOURCE_DIAGNOSTIC"
    # The original seen cohort's 36 failures partition exactly above.
    raise ValueError("V13_UNKNOWN_ORIGINAL_FAILURE_CLASS_STOP")


def supported_choices(obs,mask,prior_actions):
    """Only public mask/legal motor; *no* seed, hidden mover or reward."""
    forensic.public(obs,mask)
    if not obs[10]:
        require(not any(mask[:6]),"V13_LIVE_FALSE_WITH_UNEXPECTED_MOTOR_MASK")
        return []
    if obs[15] or not any(mask[:6]):return []
    # Forward progress is the objective, not opening a forward mask. Never
    # infer action4 dynamics from its previously untrained V12 state.
    preferred=(2,1,3,4,0,5) if (mask[1] or mask[2]) else (3,4,5,0,1,2)
    # V13 explores *both* lateral sides in a finite safe-masked matrix;
    # alternate repeated side3 when otherwise stuck.
    if len(prior_actions)>=2 and prior_actions[-2:]==[3,3]:
        preferred=(4,5,3,0,2,1)
    return [int(a) for a in preferred if mask[a]][:3]


def deterministic_tail_choice(obs,mask,prior_actions):
    candidates=supported_choices(obs,mask,prior_actions)
    if not candidates:return None
    # Among allowed options, prefer real forward physical push. If blocked,
    # alternate safe-side approaches, then retreat. This is a research
    # hypothesis only; no claimed prequalified policy or world advantage.
    return candidates[0]


def checked_env_state(env,observation):
    mask=[int(x) for x in env.mask(observation)]
    obs=[float(x) for x in observation]
    forensic.public(obs,mask)
    return obs,mask


def replay_actions(env_factory,world_signature,seed,original_trace,source_world_hash,prefix_count,
                   additional_actions=(),tail=False,deadline=None,
                   on_step=None,branch_id=None):
    """Reset and EXACT-replay source prefix; then execute legal interventions.

    No MuJoCo/Python state shallow copies; common-random-number experiments
    reconstruct the complete original state with identical seed+actions,
    independently check every observed prefix and original mask, then fork.
    """
    require(0<=prefix_count<len(original_trace) and
            prefix_count+len(additional_actions)<=MAX_ORIGINAL_OPTIONS,
            "V13_FINITE_PREFIX_AND_OPTION_BUDGET")
    require(on_step is None or callable(on_step),"V13_EXECUTED_OPTION_JOURNAL_REQUIRED")
    env=env_factory(max_options=MAX_ORIGINAL_OPTIONS)
    observation=env.reset(seed=seed,ood=False)
    expected_world=original_trace[0]["observation"]
    start_obs,start_mask=checked_env_state(env,observation)
    require(start_obs==expected_world and
            start_mask==original_trace[0]["mask"],
            "V13_REAL_MUJOCO_RESEEDED_FIRST_PUBLIC_STATE_MISMATCH")
    original_world_hash=str(world_signature(env))
    require(original_world_hash==source_world_hash,
            "V13_ORIGINAL_PAIRED_WORLD_HASH_CHANGED_AT_RESET")
    actions=[]
    trace=[]
    last=None
    max_dwell=0
    def one_action(action,expected_step=None):
        nonlocal observation,last,max_dwell
        if deadline is not None and time.monotonic()>deadline:
            raise TimeoutError("V13_FINITE_CAUSAL_REAL_PHYSICS_DEADLINE")
        o,m=checked_env_state(env,observation)
        if expected_step is not None:
            require(o==expected_step["observation"] and m==expected_step["mask"] and
                    action==expected_step["action"],
                    "V13_ORIGINAL_PREFIX_OBSERVATION_MASK_OR_ACTION_DRIFT")
        require(type(action) is int and 0<=action<7 and m[action]==1,
                "V13_ORIGINAL_SHIELD_LEGAL_ACTION_REQUIRED")
        # A permanent public deadman release cannot be bypassed, not even by
        # a nonmotor action in the causal search. This original prefix rule
        # has no exception after observed live=False.
        require(o[10]!=0 or action==6,"V13_DEADMAN_RELEASE_MOTOR_BYPASS_STOP")
        new,reward,done,info=env.step(action)
        next_obs=[float(x) for x in new]
        max_dwell=max(max_dwell,int(env.dwell))
        require(len(next_obs)==18 and all(math.isfinite(x) for x in next_obs),
                "V13_ORIGINAL_PUBLIC_NEXT_STATE_INVALID")
        new_step={"observation":o,"mask":m,"action":action,"reward":float(reward),
                  "cost":int(info["cost"]),"done":bool(done),
                  "contacts_cumulative":int(info["contacts"]),
                  "dwell_ticks_current":int(env.dwell),
                  "dwell_ticks_cumulative":max_dwell,
                  "success_info":bool(info["success"]),
                  "next_observation":next_obs}
        # Persist every completed original physical *option*, including all
        # replayed-prefix options, before testing exact source equality and
        # before attempting another option. If a later option times out or
        # raises, the host retains an explicitly INCOMPLETE branch journal.
        # No unobserved fraction of a currently running env.step is invented.
        if on_step is not None:
            event={"schema":SCHEMA+".option-journal.v1",
                   "branchId":branch_id,"seed":seed,
                   "sourceWorldHash":original_world_hash,
                   "forkOptionIndexZeroBased":prefix_count,
                   "optionIndexZeroBased":len(trace),
                   "phase":"ORIGINAL_PREFIX" if expected_step is not None else "COUNTERFACTUAL",
                   "transition":new_step,
                   "transitionSha256":hashlib.sha256(canonical(new_step)).hexdigest(),
                   "sourceOnlyUnattestedExecution":True,
                   "physicsQualificationPending":True}
            on_step(event)
        if expected_step is not None:
            require(new_step["next_observation"]==expected_step["next_observation"] and
                    new_step["reward"]==expected_step["reward"] and
                    new_step["done"]==expected_step["done"] and
                    new_step["success_info"]==expected_step["success_info"] and
                    new_step["cost"]==expected_step["cost"] and
                    new_step["dwell_ticks_current"]==expected_step["dwell_ticks_current"] and
                    new_step["dwell_ticks_cumulative"]==expected_step["dwell_ticks_cumulative"] and
                    new_step["contacts_cumulative"]==expected_step["contacts_cumulative"],
                    "V13_EXACT_REPLAY_PREFIX_REAL_PHYSICS_DIVERGED")
        trace.append(new_step)
        actions.append(action)
        observation=new
        last=info
        return bool(done)
    for i in range(prefix_count):
        done=one_action(int(original_trace[i]["action"]),original_trace[i])
        require(not done and not last["unsafe"],
                "V13_ORIGINAL_PREFIX_FINISHED_OR_UNSAFE_BEFORE_FORK")
    fork_obs,fork_mask=checked_env_state(env,observation)
    require(fork_obs==original_trace[prefix_count]["observation"] and
            fork_mask==original_trace[prefix_count]["mask"],
            "V13_FORK_ORIGINAL_PUBLIC_STATE_NOT_IDENTICAL")
    status="INTERVENTION_BUDGET_STOP"
    for action in additional_actions:
        o,m=checked_env_state(env,observation)
        if not o[10] and not any(m[:6]):
            status="PUBLIC_LIVE_FALSE_MOTOR_DISABLED"
            break
        if one_action(int(action)):
            status="ORIGINAL_PHYSICS_TERMINAL"
            break
        if last["unsafe"]:
            status="UNSAFE_HARD_STOP"
            break
    if tail and status=="INTERVENTION_BUDGET_STOP":
        while len(actions)<MAX_ORIGINAL_OPTIONS:
            o,m=checked_env_state(env,observation)
            if not o[10] and not any(m[:6]):
                status="PUBLIC_LIVE_FALSE_MOTOR_DISABLED"
                break
            act=deterministic_tail_choice(o,m,actions)
            if act is None:
                status="NO_LEGAL_MOTOR_PUBLIC_HOLD"
                break
            if one_action(act):
                status="ORIGINAL_PHYSICS_TERMINAL"
                break
            if last["unsafe"]:
                status="UNSAFE_HARD_STOP"
                break
        if status=="INTERVENTION_BUDGET_STOP":status="ORIGINAL_60_OPTIONS_EXHAUSTED"
    o,m=checked_env_state(env,observation)
    success=bool(last is not None and last["success"] and not last["unsafe"] and
                 env.dwell>=ORIGINAL_GOAL_TICKS and env.contacts>0)
    require(not success or status=="ORIGINAL_PHYSICS_TERMINAL",
            "V13_PHYSICS_SUCCESS_WITHOUT_ORIGINAL_TERMINAL")
    return {"schema":SCHEMA+".branch","seed":seed,"branchId":branch_id,
      "sourceWorldHash":original_world_hash,"forkOptionIndexZeroBased":prefix_count,
      "exactOriginalPrefixReplayed":True,"decisionPublic18D":fork_obs,
      "decisionOriginalMask7":fork_mask,"actions":actions,
      "lastPublicObservation18D":o,"lastOriginalMask7":m,
      "trace":trace,"traceSha256":hashlib.sha256(canonical(trace)).hexdigest(),
      "actualOptionSteps":len(trace),"actualPhysicsSteps":int(env.physics_steps),
      "actualContacts":int(env.contacts),"actualDwellTicks":int(env.dwell),
      "actualGoalSuccess250Tick":success,"actualUnsafe":bool(last and last["unsafe"]),
      "lastOriginalPhysicsErrorMeters":None if last is None else float(last["error"]),
      "lastPublicGoalErrorMeters":public_goal_distance(o),
      "status":status,"newRealMuJoCoExecuted":False,
      "sourceOnlyUnattestedExecution":True,"physicsQualificationPending":True,
      "trainingOnly":True,"modelPromotionAuthorized":False}


def _rank_partial(branch):
    # Heuristic is public predicted reachability (not proof). This reads no
    # hidden simulator state, contacts, poststep cost, seed or reward.
    return (branch["lastPublicGoalErrorMeters"]+.0001*branch["actualOptionSteps"],
            len(branch["actions"]),branch["actions"])


def run_budgeted_diagnostic(source,env_factory,world_signature,*,
         max_depth=MAX_DEPTH,beam_width=BEAM_WIDTH,
         max_world_branches=MAX_WORLD_BRANCHES,deadline=None,
         on_branch=None,on_step=None):
    """Return complete TRAIN-only diagnostics and exact original raw branches.

    Caller owns IO/retention/hosted runner. Both on_step and on_branch are
    required: on_step is invoked synchronously after each complete physical
    option (even prefix replay) before the next option / source equality
    check; on_branch follows each complete replay. Both must append+fsync a
    lossless journal, or raise to hard-stop. Their returns cannot alter search.
    The producer cannot independently attest its injected env_factory is real
    MuJoCo; only an independently source-verified hosted harness may do so.
    """
    require(max_depth==MAX_DEPTH and beam_width==BEAM_WIDTH and
            max_world_branches==MAX_WORLD_BRANCHES and
            callable(env_factory) and callable(world_signature) and
            callable(on_branch) and callable(on_step),
            "V13_PREREGISTERED_FINITE_DIAGNOSTIC_BUDGET_REQUIRED")
    now=time.monotonic()
    require(deadline is None or
            (type(deadline) in (int,float) and math.isfinite(deadline) and now<deadline),
            "V13_FINITE_MONOTONIC_DEADLINE_OR_DEFAULT_REQUIRED")
    # The caller cannot extend the hard internal 1200-second science budget.
    # The default is also bounded, even if no hosted deadline was supplied.
    deadline=min(now+MAX_RUNTIME_SECONDS,
                 deadline if deadline is not None else now+MAX_RUNTIME_SECONDS)
    require(source["sourceSha"]==forensic.SOURCE_HEAD and
            source["fullTransitionsSha256"]==forensic.RAW_SHAS["full_transitions.jsonl.gz"] and
            source["independentReplayQualified"] is True,
            "V13_UNVERIFIED_ORIGINAL_V12_REAL_SOURCE_NOT_ELIGIBLE")
    source_diag=forensic.source_failure_diagnosis(source)
    failed=source_diag["v5FailedWorlds"]
    output={"schema":SCHEMA+".readout","sourceOriginalHead":forensic.SOURCE_HEAD,
       "sourceV12RawSha256":forensic.RAW_SHAS,
       "sourceFailureDiagnosis":source_diag,
       "originalSeenTrainWorldCount":48,"originalSeenFailedWorlds":len(failed),
       "preregisteredMaxDepth":MAX_DEPTH,"preregisteredBeamWidth":BEAM_WIDTH,
       "preregisteredMaxPerWorldBranchRollouts":MAX_WORLD_BRANCHES,
       "preregisteredMaxTotalBranches":MAX_TOTAL_BRANCHES,
       "worldResults":[],"rawBranches":[],"allWorldsComplete":False,
       "status":"INCOMPLETE","hardStopReason":None,
       "newHostedPhysicsDispatched":False,"trainingOnly":True,
       "devCalTestOodOpened":False,"modelPromotionAuthorized":False}
    total=0
    for seed in failed:
        if deadline is not None and time.monotonic()>deadline:
            output["hardStopReason"]="V13_FINITE_DEADLINE"
            return output
        trace=source["traces"][seed,forensic.ARM_V5]
        fork_idx,kind=frozen_first_fork(trace,seed)
        prefix=[step["action"] for step in trace[:fork_idx]]
        expected_world_hash=source["rows"][seed,forensic.ARM_V5]["world_hash"]
        evaluated=set()
        world_branches=[]
        world_witness=None
        world_budget=0
        def evaluate(controls,tail=False):
            nonlocal total,world_budget
            require(world_budget<MAX_WORLD_BRANCHES and total<MAX_TOTAL_BRANCHES,
                    "V13_CAUSAL_BRANCH_BUDGET_HARD_STOP")
            branch_id=f"v13-seen-train-{seed}-{world_budget:02d}"
            state=replay_actions(env_factory,world_signature,seed,trace,
                 expected_world_hash,fork_idx,controls,tail=tail,deadline=deadline,
                 on_step=on_step,branch_id=branch_id)
            total+=1;world_budget+=1
            world_branches.append(state)
            if on_branch is not None:
                # A lossless retained journal writes synchronously; raising
                # interrupts the entire diagnostic rather than losing evidence.
                on_branch(state)
            return state
        try:
            initial=evaluate([])
            frontier=[([],initial)]
            for depth in range(MAX_DEPTH):
                expanded=[]
                for controls,parent in frontier:
                    if parent["status"]!="INTERVENTION_BUDGET_STOP":continue
                    # The original mask at the FINAL actual MuJoCo state is
                    # queried and retained; never reuse the *previous* mask.
                    choices=supported_choices(parent["lastPublicObservation18D"],
                          parent["lastOriginalMask7"],prefix+controls)
                    for action in choices:
                        if world_budget>=MAX_WORLD_BRANCHES:break
                        new=[*controls,action]
                        key=tuple(new)
                        if key in evaluated:continue
                        evaluated.add(key)
                        branch=evaluate(new)
                        if branch["actualUnsafe"]:
                            output["hardStopReason"]="V13_REAL_PHYSICS_UNSAFE"
                            break
                        if branch["actualGoalSuccess250Tick"]:
                            world_witness=branch
                            break
                        if branch["status"]=="INTERVENTION_BUDGET_STOP":
                            expanded.append((new,branch))
                    if output["hardStopReason"] or world_witness is not None:break
                if output["hardStopReason"] or world_witness is not None:break
                if not expanded:break
                expanded.sort(key=lambda p:_rank_partial(p[1]))
                frontier=expanded[:BEAM_WIDTH]
            if not output["hardStopReason"] and world_witness is None:
                for controls,parent in frontier:
                    if world_budget>=MAX_WORLD_BRANCHES:break
                    branch=evaluate(controls,tail=True)
                    if branch["actualUnsafe"]:
                        output["hardStopReason"]="V13_REAL_PHYSICS_UNSAFE"
                        break
                    if branch["actualGoalSuccess250Tick"]:
                        world_witness=branch
                        break
        except TimeoutError:
            output["hardStopReason"]="V13_FINITE_DEADLINE"
        output["rawBranches"].extend(world_branches)
        output["worldResults"].append({"seed":seed,"sourceV5FailureKind":kind,
          "sourceForkOptionZeroBased":fork_idx,
          "executedBudgetBranches":world_budget,
          "status":"WITNESS" if world_witness else
            "SAFETY_STOP" if output["hardStopReason"] else
            "NONE_REACHABLE_WITHIN_FINITE_BUDGET",
          "actual250TickWitnessTraceSha256":None if world_witness is None else
             world_witness["traceSha256"],
          "notProofOfGlobalUnreachability":True})
        if output["hardStopReason"]:return output
        require(total<=MAX_TOTAL_BRANCHES,"V13_TOTAL_BRANCH_EXCEEDED_PREREGISTERED_BUDGET")
    output["allWorldsComplete"]=True
    output["status"]="TRAIN_ONLY_DIAGNOSTIC_COMPLETE"
    output["hardStopReason"]=None
    return output
