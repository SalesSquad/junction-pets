"""V12 frozen fresh-TRAIN cohort and true 250tick goal evidence contracts.

No simulator call here. A separate independently reviewed hosted harness MUST
execute the original environment, retain all actual full options losslessly and
replay positive/clear physics before interpreting any preliminary readout.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path


# Do not use the generic `import policy`: original V5 physics uses exactly
# that top-level module name; V11 hosted failed before physics on collision.
_spec=importlib.util.spec_from_file_location(
    "rokoko_v12_public_state_policy_protocol",Path(__file__).with_name("policy.py"))
if _spec is None or _spec.loader is None:
    raise ImportError("V12_UNIQUE_PUBLIC_POLICY_MODULE_REQUIRED")
_policy=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_policy)
public_abi,require=_policy.public_abi,_policy.require

PLAN_SHA256="8074f8f8978e2e55bdf201eeb9713888e44befe1d93856da44c1830bb86cfc48"
MODEL_SHA256="82cfa42ba2240aff6d00ec3e2b15c06d78386d3c0682986a23e478977f2dbf9e"
PILOT_ARMS=("frozen_v5","v12_phase_dwell_supported_actions",
            "v12_right_side_action4_exploration_train_only")
FOLLOWUP_ARMS=("frozen_v5","one_preregistered_v12_nonexploratory_candidate")


def seed_sha(first,last):
    return hashlib.sha256(json.dumps(list(range(first,last+1)),sort_keys=True,
                         separators=(",",":"),allow_nan=False).encode()).hexdigest()


def bound_plan_object(plan):
    """Never trust externally supplied cohort/plan metadata without proof."""
    require(type(plan) is dict,"V12_FROZEN_PLAN_OBJECT_REQUIRED")
    try:
        canonical=(json.dumps(plan,sort_keys=True,indent=2,ensure_ascii=False,
                              allow_nan=False)+"\n").encode()
    except (TypeError,ValueError) as exc:
        raise ValueError("V12_NONCANONICAL_PROSPECTIVE_PLAN") from exc
    require(hashlib.sha256(canonical).hexdigest()==PLAN_SHA256,
            "V12_FROZEN_PROSPECTIVE_PLAN_OBJECT_SHA_CHANGED")
    return plan


def verified_plan(path):
    p=Path(path)
    require(p.is_file() and not p.is_symlink() and p.stat().st_nlink==1,
            "V12_PROSPECTIVE_PLAN_MISSING_OR_UNSAFE")
    raw=p.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==PLAN_SHA256,
            "V12_PROSPECTIVE_PLAN_SHA_CHANGED")
    plan=bound_plan_object(json.loads(raw))
    require(plan["frozenModelSha256"]==MODEL_SHA256 and
        plan["pilotTrainSeedRangeInclusive"]==[518000,518511] and
        plan["pilotAll512ScanSeedsSha256"]==seed_sha(518000,518511) and
        plan["followupIfPositiveNewTrainSeedRangeInclusive"]==[518512,519023] and
        plan["followupAll512ScanSeedsSha256"]==seed_sha(518512,519023) and
        plan["pilotPairedArms"]==list(PILOT_ARMS) and
        plan["pilotCohort"]["near"]==40 and plan["pilotCohort"]["clear"]==8 and
        plan["followupFreshCohort"]["near"]==128 and
        plan["followupFreshCohort"]["clear"]==32 and
        plan["hardStopIfAnyNewUnsafeOrLostV5PhysicalGoal"] is True and
        plan["hardStopIfZeroNovel250TickSafeGoalsInPilot"] is True and
        plan["modelPromotionAuthorized"] is False and
        plan["dispatchAuthorized"] is False and
        plan["devCalTestOodOpened"] is False,
        "V12_PROSPECTIVE_FRESH_TRAIN_PROTOCOL_CHANGED")
    return plan


def derive_cohort(all_512_initial_public_worlds,plan,stage):
    """Never trust a list of hand-selected seeds from an external producer."""
    plan=bound_plan_object(plan)
    require(stage in ("pilot","followup"),"V12_UNKNOWN_COHORT_STAGE")
    if stage=="pilot":
        first,last=plan["pilotTrainSeedRangeInclusive"]
        near_need,clear_need=40,8
    else:
        first,last=plan["followupIfPositiveNewTrainSeedRangeInclusive"]
        near_need,clear_need=128,32
    require(len(all_512_initial_public_worlds)==512 and
        [w["seed"] for w in all_512_initial_public_worlds]==list(range(first,last+1)),
        "V12_MISSING_NONSEQUENTIAL_OR_EXTRA_FRESH_TRAIN_WORLD")
    near=[];clear=[]
    all_hashes=set()
    for world in all_512_initial_public_worlds:
        obs,mask=public_abi(world["observation"],world["mask"])
        world_hash=world.get("world_hash")
        require(type(world_hash) is str and len(world_hash)>=8 and
                world_hash not in all_hashes,"V12_PAIRED_PUBLIC_WORLD_ID_INVALID_OR_DUPLICATE")
        all_hashes.add(world_hash)
        is_near=abs(obs[7])<.122
        rec={"seed":world["seed"],"world_hash":world_hash,
             "initial_public_obstacle_y":obs[7],"initial_mask":list(mask),
             "observed_corridor":is_near}
        if is_near and len(near)<near_need:near.append(rec)
        if not is_near and len(clear)<clear_need:clear.append(rec)
    require(len(near)==near_need and len(clear)==clear_need,
            "V12_PUBLIC_INITIAL_FRESH_COHORT_UNDERFILLED")
    return sorted([*near,*clear],key=lambda w:w["seed"])


def paired_physical_goal_readout(trials,cohort,stage,*,all_512_initial_public_worlds,plan):
    """Preliminary physics; rederive 512-world cohort, not producer selection."""
    require(stage in ("pilot","followup"),"V12_UNKNOWN_PHYSICAL_COHORT_STAGE")
    independently_derived=derive_cohort(all_512_initial_public_worlds,plan,stage)
    require(cohort==independently_derived,
            "V12_UNTRUSTED_PRODUCER_COHORT_NOT_REDERIVED_FROM_FROZEN_FULL_SCAN")
    arms=PILOT_ARMS if stage=="pilot" else FOLLOWUP_ARMS
    expected={w["seed"]:w["world_hash"] for w in cohort}
    require(len(expected)==(48 if stage=="pilot" else 160),
            "V12_PAIRED_COHORT_SIZE_DRIFT")
    require(len(trials)==len(arms)*len(expected),
            "V12_REAL_PHYSICS_INCOMPLETE_OR_PARTIAL_LOSS_FORBIDDEN")
    paired={}
    for row in trials:
        seed,arm=row["seed"],row["strategy"]
        require(seed in expected and arm in arms and row["world_hash"]==expected[seed],
                "V12_UNPAIRED_WORLD_OR_UNKNOWN_STRATEGY")
        choices=paired.setdefault(seed,{})
        require(arm not in choices and all(type(row[k]) is bool for k in
                   ("success","unsafe","abstained")),
                "V12_DUPLICATE_OR_INVALID_ORIGINAL_PHYSICAL_RESULT")
        # An original MuJoCo goal requires 250 consecutive dwell ticks within
        # 20mm *and* physical contact. A bare producer success=True cannot turn
        # a non-completing path into a novel goal and bypass the pilot STOP.
        dwell=row.get("dwell_ticks_final")
        contact=row.get("contacts")
        error=row.get("final_error")
        require(type(dwell) is int and dwell>=0 and
                type(contact) is int and contact>=0 and
                type(error) in (int,float) and math.isfinite(error) and error>=0,
                "V12_ORIGINAL_PHYSICAL_GOAL_FIELDS_REQUIRED")
        original_goal=bool(dwell>=250 and contact>0 and error<.02 and
                           not row["unsafe"] and not row["abstained"])
        require(row["success"] is original_goal,
                "V12_ORIGINAL_250TICK_PHYSICAL_GOAL_MISMATCH")
        choices[arm]=row
    require(set(paired)==set(expected) and all(set(a)==set(arms) for a in paired.values()),
            "V12_PAIRED_FRESH_MUJOCO_WORLD_MATRIX_INCOMPLETE")
    safe=lambda r: bool(r["success"] and not r["unsafe"] and not r["abstained"])
    candidate=arms[1]
    lost=sorted(s for s,a in paired.items() if safe(a["frozen_v5"]) and
                not safe(a[candidate]))
    novel=sorted(s for s,a in paired.items() if safe(a[candidate]) and
                 not safe(a["frozen_v5"]))
    unsafe=sorted(s for s,a in paired.items() if a[candidate]["unsafe"])
    exploration_unsafe=sorted(s for s,a in paired.items() if
                   stage=="pilot" and a[arms[2]]["unsafe"])
    # TRAIN-only probing cannot erase a frozen V5 real safe250tick win.
    # The source-registered right-action probe has no supported model.
    exploration_lost=sorted(s for s,a in paired.items() if
                   stage=="pilot" and safe(a["frozen_v5"]) and not safe(a[arms[2]]))
    stop=bool(lost or unsafe or exploration_unsafe or exploration_lost or not novel)
    return {"schema":"junction.rokoko.v12.preliminary-physical-goal250-readout.v1",
      "stage":stage,"totalOriginalRealEpisodes":len(trials),
      "frozenV5SafeGoals":sum(safe(a["frozen_v5"]) for a in paired.values()),
      "candidateSafeGoals":sum(safe(a[candidate]) for a in paired.values()),
      "candidateNovelSafeGoalWorldSeeds":novel,
      "candidateLostV5GoalWorldSeeds":lost,
      "candidateUnsafeWorldSeeds":unsafe,
      "explorationOnlyUnsafeWorldSeeds":exploration_unsafe,
      "explorationOnlyLostV5GoalWorldSeeds":exploration_lost,
      "hardStopNoFurtherPhysics":stop,
      "scienceDecision":"STOP" if stop else "REVIEW_FRESH_TRAIN_EVIDENCE_ONLY",
      "goalDefinition":"original MuJoCo contact + object within 20mm for >=250 real ticks + zero unsafe",
      "trainingOnly":True,"independentPhysicsReplayQualified":False,
      "devCalTestOodOpened":False,"modelPromotionAuthorized":False}
