"""Original-physics-safe future V13 TRAIN cohort contract; no dispatch.

520000+ is deliberately forbidden by original ContactEnv.reset. Both reserved
cohorts fit <520000 and exclude all historical V10/V11/V12 source/followup.
No DEV, CAL, TEST or OOD source is consulted to choose these future worlds.
"""
from __future__ import annotations

import hashlib
import json

import forensic


SCHEMA="junction.rokoko.v13.fresh-world-causal-goal-plan.v1"
FRESH_SCAN=(519024,519535)
CONFIRM_SCAN=(519536,519999)
SEEN_DIAGNOSTIC=(518000,518511)
COHORT_TARGET=(64,16)
GOAL_TICKS=250


def seed_sha(first,last):
    return hashlib.sha256(json.dumps(list(range(first,last+1)),sort_keys=True,
              separators=(",",":"),allow_nan=False).encode()).hexdigest()


def frozen_plan():
    return {"schema":SCHEMA,"sourceV12Head":forensic.SOURCE_HEAD,
        "sourceV12FullOptionsSha256":forensic.RAW_SHAS["full_transitions.jsonl.gz"],
        "originalPhysicsModelSha256":forensic.MODEL_SHA,
        "seenOriginalDiagnosticSeedRangeInclusive":list(SEEN_DIAGNOSTIC),
        "newTrainScanRangeInclusive":list(FRESH_SCAN),
        "newTrainScanAllSeedsSha256":seed_sha(*FRESH_SCAN),
        "conditionalConfirmationScanRangeInclusive":list(CONFIRM_SCAN),
        "confirmationScanAllSeedsSha256":seed_sha(*CONFIRM_SCAN),
        "trainScanCount":512,"conditionalConfirmScanCount":464,
        "perStageFirstNearAndClear":list(COHORT_TARGET),
        "publicObservedNearRule":"abs(initial_public_observation[7]) < 0.122",
        "initialWorldSelectionOutcomeIndependent":True,
        "hypothesis":"causal bounded public-action contact-to-250tick-goal",
        "trainingGoal":"original MuJoCo contacts>0 and object within20mm for>=250 real ticks and zero unsafe",
        "originalSevenOptionShieldFinal":True,
        "originalDeadmanNoMotorBypass":True,
        "requiresCompleteRawAndIndependentPhysicsReplay":True,
        "hardStopOnAnyNewUnsafeOrLostV5Goal":True,
        "positiveNovel250TickGoalRequired":True,
        "candidateModelSourceShaRequiredBeforeEvaluation":True,
        "seen48WorldOracleNeverPromotionEvidence":True,
        "noDevCalTestOod":True,"modelPromotionAuthorized":False,
        "dispatchAuthorized":False,"automatedSpendingAuthorized":False}


def plan_sha():
    return hashlib.sha256(json.dumps(frozen_plan(),sort_keys=True,
             separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def derive_public_cohort(all_public_initial_worlds,plan,stage):
    forensic.require(stage in ("new_train","confirmation"),"V13_UNKNOWN_FUTURE_TRAIN_STAGE")
    forensic.require(type(plan) is dict and
        hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(",",":"),
             ensure_ascii=False,allow_nan=False).encode()).hexdigest()==plan_sha(),
        "V13_FORGED_OR_MUTATED_FROZEN_FUTURE_TRAIN_PLAN")
    first,last=FRESH_SCAN if stage=="new_train" else CONFIRM_SCAN
    forensic.require(len(all_public_initial_worlds)==last-first+1 and
        [world["seed"] for world in all_public_initial_worlds]==list(range(first,last+1)),
        "V13_MISSING_HANDPICKED_OR_REORDERED_PUBLIC_WORLD_SCAN_STOP")
    near=[];clear=[];seen_world_hashes=set()
    for row in all_public_initial_worlds:
        obs,mask=row["observation"],row["mask"]
        forensic.public(obs,mask)
        world_hash=row["world_hash"]
        forensic.require(type(world_hash) is str and world_hash and
                        world_hash not in seen_world_hashes,
                        "V13_INVALID_DUPLICATE_ORIGINAL_WORLD_SIGNATURE")
        seen_world_hashes.add(world_hash)
        dest=near if abs(obs[7])<.122 else clear
        bound=COHORT_TARGET[0] if dest is near else COHORT_TARGET[1]
        if len(dest)<bound:
            dest.append({"seed":row["seed"],"world_hash":world_hash,
                         "initialPublicObs18":list(obs),"initialOriginalMask7":list(mask),
                         "publicNear":dest is near})
    forensic.require(len(near)==COHORT_TARGET[0] and len(clear)==COHORT_TARGET[1],
                    "V13_FUTURE_PUBLIC_NEAR_CLEAR_COHORT_UNDERFILLED")
    return sorted([*near,*clear],key=lambda w:w["seed"])
