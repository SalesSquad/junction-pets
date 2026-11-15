#!/usr/bin/env python3
"""Reproducible V12 FIT/CAL/DIAG from genuine V10+V11 original CRACI TRAIN.

No physical simulator invocation, autonomous GPU/CRACI dispatch, hidden state,
sequential test peeking or model promotion. The model file is only an auditable
candidate pending future NEW 518000+ real MuJoCo TRAIN physics.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path

import evidence
import fit


HERE=Path(__file__).resolve().parent
V11_GATE=HERE.parent/"v11_learning"/"frozen-v10-train-approved"/"gate.json"
V11_GATE_SHA=evidence.V11_GATE_SHA
PILOT_FIRST=518000
PILOT_LAST=518511
FUTURE_FIRST=518512
FUTURE_LAST=519023


def file_sha(value):return hashlib.sha256(value).hexdigest()


def file_bytes(value):
    return (json.dumps(value,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+"\n").encode()


def seeds_sha(first,last):
    return hashlib.sha256(json.dumps(list(range(first,last+1)),sort_keys=True,
                         separators=(",",":"),allow_nan=False).encode()).hexdigest()


def load_v11_gate_scoring():
    source=HERE.parent/"v11_learning"/"learn_gate.py"
    spec=importlib.util.spec_from_file_location("v12_frozen_v11_gate_scoring",source)
    fit.require(spec is not None and spec.loader is not None,"V12_FROZEN_V11_GATE_SCORING_MISSING")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_outputs(v10,v11):
    runs={"v10":v10,"v11":v11}
    model=fit.fit_action_models(runs)
    gate=json.loads(evidence.checked(V11_GATE,V11_GATE_SHA))
    frozen_gate=gate["gate"]
    scoring=load_v11_gate_scoring()
    frozen_winners={}
    for run,data in runs.items():
        winners=sorted(seed for (seed,name),row in data["rows"].items()
                       if name=="frozen_v5" and row["success"] and not row["unsafe"])
        fired=sorted(seed for seed in winners if scoring.episodes_with_gate(
            data["traces"][seed,"frozen_v5"],frozen_gate) is not None)
        fit.require(not fired,"V12_V5_GOAL_SOURCE_GATE_REGRESSION_STOP")
        frozen_winners[run]={"realV5SafeGoalWorlds":len(winners),
                             "firedOnV5OriginalWinningWorlds":len(fired),
                             "originalWinningSeedIds":winners}
    fit.require(frozen_winners["v10"]["realV5SafeGoalWorlds"]==37 and
                frozen_winners["v11"]["realV5SafeGoalWorlds"]==18,
                "V12_SOURCE_GOAL_WITNESSES_CHANGED")
    source={run:{k:data[k] for k in ("sourceSha","harnessSha","trainingSha256",
                                       "fullTransitionsSha256")} for run,data in runs.items()}
    model["sourceEvidence"]=source
    model["sourceOriginalRealMuJoCoTrials"]=1600
    model["sourceOriginalRealOptionTransitions"]=73561
    model["frozenV5WinningTrajectoryGateNoninterference"]=frozen_winners
    model["frozenV11GateSha256"]=V11_GATE_SHA
    model["frozenV11GateParameters"]=frozen_gate
    model["unseenOrUnsupportedActionsForbiddenAtInference"]=[int(a) for a,m in model["models"].items()
                                                      if not m["supported"]]
    model["stateAndSafetyContract"]={"inferenceInputs":["public18D_observation",
         "sevenOptionOriginalShieldMask","localPriorPublicObservationsAndActions"],
         "noPrivilegedWorldState":True,"noSeedOrRewardOrOutcomeAtInference":True,
         "originalShieldAlwaysFinal":True,"sourceV5WinsProtectedOnlyInObservedPaths":True,
         "maxRescueRounds":1,"maxRescueOptions":8,
         "physicalGoalRequiresContactWithin20mmFor250TicksAndZeroUnsafe":True}
    action4=sum(run["executed"][4] for run in model["sourceActualExecutedActionCounts"].values())
    action4legal=sum(run["legal"][4] for run in model["sourceActualExecutedActionCounts"].values())
    action4worlds=sum(run[4] for run in model["sourceDistinctWorldsPerAction"].values())
    fit.require(action4==3 and action4legal==48800 and
                action4worlds==1 and
                model["models"]["4"]["supported"] is False,
                "V12_ACTION4_UNSUPPORTED_REAL_SOURCE_CHANGED")
    model["scienceVerdict"]="V11_GOAL_NO_GO; V12_ACTION_CONDITIONED_TRAIN_ONLY_UNQUALIFIED"
    model["trainingSupervisionCaveat"]="Only actual executed actions and after-step physical labels; no synthetic counterfactual actions. No V12 physics has been executed."
    model_sha=file_sha(file_bytes(model))
    next_plan={"schema":"junction.rokoko.v12.fresh-train-action4-support-curriculum.v1",
       "frozenModelSha256":model_sha,"sourceEvidence":source,
       "pilotTrainSeedRangeInclusive":[PILOT_FIRST,PILOT_LAST],
       "pilotAll512ScanSeedsSha256":seeds_sha(PILOT_FIRST,PILOT_LAST),
       "pilotRequiresAll512PublicInitialWorldScans":True,
       "pilotCohort":{"near":40,"clear":8,"publicObservedObstacleYAbsNearLt":.122,
                     "selectionMayNotUseOutcomes":True},
       "pilotPairedArms":["frozen_v5","v12_phase_dwell_supported_actions",
                          "v12_right_side_action4_exploration_train_only"],
       "pilotExpectedRealMuJoCoEpisodes":144,
       "rightSideAction4ExplorationOnly":{"sourceActualExecuted":action4,
            "sourceLegalOpportunities":action4legal,"distinctObservedWorlds":action4worlds,
            "modelSupported":False,
            "requireIndependentSafeMuJoCoBeforeAnyModelTraining":True,
            "neverPromoteExploratoryArm":True},
       "hardStopIfAnyNewUnsafeOrLostV5PhysicalGoal":True,
       "hardStopIfZeroNovel250TickSafeGoalsInPilot":True,
       "followupIfPositiveNewTrainSeedRangeInclusive":[FUTURE_FIRST,FUTURE_LAST],
       "followupAll512ScanSeedsSha256":seeds_sha(FUTURE_FIRST,FUTURE_LAST),
       "followupFreshCohort":{"near":128,"clear":32,"initialPublicOnly":True},
       "followupPairedArms":["frozen_v5","one_preregistered_v12_nonexploratory_candidate"],
       "followupExpectedRealMuJoCoEpisodes":320,
       "primaryPhysicalGoal":"original contact + object distance to goal <.02 m for >=250 real MuJoCo ticks, zero unsafe",
       "allOriginalActionMasksRequired":True,
       "fullRawAndIndependentNearClearPositivePhysicsReplayRequired":True,
       "devCalTestOodOpened":False,"dispatchAuthorized":False,"modelPromotionAuthorized":False}
    analysis={"schema":"junction.rokoko.v12.actual-source-learning-readout.v1",
      "sourceEvidence":source,
      "observedV10RealTrials":800,"observedV10RealOptions":38569,
      "observedV11RealTrials":800,"observedV11RealOptions":34992,
      "actualV10V5Goals":37,"actualV10CandidateGoals":26,
      "actualV11V5Goals":18,"actualV11CandidateGoals":18,
      "V11NovelGoals":0,"V11LostV5Goals":0,"V11NewUnsafe":0,
      "frozenV5OriginalSuccessNoninterference":frozen_winners,
      "split":model["worldDisjointSplits"],
      "sourceActionCounts":model["sourceActualExecutedActionCounts"],
      "action4ActualExecutions":action4,
      "action4LegalObservations":action4legal,
      "action4DistinctRealWorldSupport":action4worlds,
      "action4TrainingDecision":"UNSUPPORTED_NO_MODEL; PROPOSE_SOURCE_BOUND_REAL_TRAIN_EXPLORATION",
      "supportedCandidateActionModels":[int(a) for a,m in model["models"].items() if m["supported"]],
      "scienceLimitations":["Post-step dwell labels train only and never enter inference.",
        "Predictive position calibration is a world-disjoint TRAIN diagnostic, not an unsafe-event guarantee.",
        "No unseen action4 counterfactual is labeled; 3 executed samples are insufficient to learn it.",
        "No candidate V12 250-tick physical goal improvement has been measured.",
        "The unpromoted policy must not be deployed or dispatched until independent source/harness review and authorized fresh TRAIN physics."]}
    return {"model.json":model,"next-train-plan.json":next_plan,"analysis.json":analysis}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--v10-archive",type=Path,required=True)
    p.add_argument("--v10-receipt",type=Path,required=True)
    p.add_argument("--v10-source-root",type=Path,required=True)
    p.add_argument("--v11-archive",type=Path,required=True)
    p.add_argument("--v11-receipt",type=Path,required=True)
    p.add_argument("--v11-packer",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    v10=evidence.load_v10(args.v10_archive,args.v10_receipt,args.v10_source_root)
    v11=evidence.load_v11(args.v11_archive,args.v11_receipt,args.v11_packer)
    outputs=build_outputs(v10,v11)
    fit.require(not args.out.exists(),"V12_FREEZE_ONLY_TO_NEW_DIRECTORY")
    args.out.mkdir(mode=0o700,parents=True)
    hashes={}
    for name,content in outputs.items():
        encoded=file_bytes(content)
        with (args.out/name).open("xb") as dest:dest.write(encoded)
        hashes[name]=file_sha(encoded)
    manifest={"schema":"junction.rokoko.v12.frozen-source-learned-checkpoint.v1",
              "producedAt":datetime.now(timezone.utc).isoformat(),
              "sourceV10Head":outputs["model.json"]["sourceEvidence"]["v10"]["sourceSha"],
              "sourceEvidence":outputs["model.json"]["sourceEvidence"],
              "fileSha256":hashes,"sourceOnlyTraining":True,
              "newPhysicsPerformed":False,"devCalTestOodOpened":False,
              "modelPromotionAuthorized":False,"dispatchAuthorized":False}
    with (args.out/"manifest.json").open("xb") as dest:dest.write(file_bytes(manifest))
    print(json.dumps({"outputDirectory":str(args.out),"fileSha256":hashes,
       "sourceActualOptions":73561,"action4ActuallyExecuted":3,
       "action4OriginalLegalOpportunities":48800,
       "candidateSupportedActions":outputs["analysis.json"]["supportedCandidateActionModels"],
       "newPhysicsPerformed":False,"modelPromotionAuthorized":False},sort_keys=True))


if __name__=="__main__":main()
