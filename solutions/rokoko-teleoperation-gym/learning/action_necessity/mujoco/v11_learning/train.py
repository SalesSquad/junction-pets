#!/usr/bin/env python3
"""Freeze V11 goal-protection gate from qualified 800 V10 real TRAIN worlds.

Does not run physics, submit CRACI work or auto-promote a candidate.  Fit and
diagnostic are disjoint world groups; both are TRAIN-only.  The entire source
archive is independently SHA/publisher-manifest verified before use.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import evidence
import learn_gate


SCHEMA = "junction.rokoko.v11.goal-preserving-abstain-gate.v1"
START = 517000
SCAN = 512
NEXT_NEAR = 128
NEXT_CLEAR = 32
NEXT_STRATEGIES = ("frozen_v5", "frozen_v6", "frozen_v8",
                   "v10_loss_informed", "v11_goal_preserving")


def digest(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",", ":"),
                              allow_nan=False).encode()).hexdigest()


def build_outputs(archive, receipt, source_root):
    training, rows, traces, proofs = evidence.load_retained_raw(archive,receipt,source_root)
    worlds = learn_gate.compile_features(rows,traces)
    result=learn_gate.train_goal_preserving_gate(worlds)
    budget=learn_gate.derive_bounded_rescue_options(traces)
    evidence.require(result["decision"]=="SOURCE_ONLY_PUBLIC_GATE_REVIEW_CANDIDATE" and
                     result["fit_train"]["fired_on_v5_goal_worlds"]==0 and
                     result["held_train"]["fired_on_v5_goal_worlds"]==0,
                     "V11_GOAL_PRESERVATION_DIAGNOSTIC_NOT_SATISFIED")
    v5_won={s for (s,k),r in rows.items() if k=="frozen_v5" and r["success"] and not r["unsafe"]}
    v10_won={s for (s,k),r in rows.items() if k=="v10_loss_informed" and r["success"] and not r["unsafe"]}
    loss=sorted(v5_won-v10_won)
    evidence.require(len(v5_won)==37 and len(v10_won)==26 and len(loss)==11 and
                     len(v10_won-v5_won)==0 and
                     result["fit_train"]["source_worlds"]+
                     result["held_train"]["source_worlds"]==160,
                     "V11_ACTUAL_GOAL_REGRET_DISAGREES_WITH_RAW")
    source={"repository":"SalesSquad/junction-pets", "sourceSha":evidence.V10_SOURCE_SHA,
            "harnessSha":evidence.V10_HARNESS_SHA, "githubRun":evidence.V10_RUN,
            "receiptRunId":evidence.V10_RECEIPT_RUN,
            "trainingSha256":evidence.V10_RAW["training.json"],
            "fullTransitionsSha256":evidence.V10_RAW["full_transitions.jsonl.gz"],
            "independentQualificationSha256":evidence.V10_PROOFS["independent-qualification.json"],
            "independentClearGoalReplaySha256":evidence.V10_PROOFS["independent-clear-goal-replay.json"],
            "sourceEvidence":"source-reported plus independent full TRAIN-only replay"}
    model={"schema":SCHEMA,"model_type":"bounded-public-abstain-rescue-controller",
           "source":source,"gate":result["candidate_params"],
           "safety": {"exactSevenActionMaskRequired":True,
                      "inferenceInputs":["public18D_observation","sevenBitLegalMask",
                                         "localPreviousOptions"],
                      "maxRescueRounds":1,"maxRescueOptionsPerRound":budget["cap"],
                      "returnToFrozenV5WhenForwardLegal":True,
                      "neverContinueRescueInsidePublicGoalZone":True,
                      "fallbackToLegalV5OnRescueStop":True},
           "training":{"worlds":160,"actualMuJoCoEpisodes":800,
                       "originalRealOptionTransitions":38569,
                       "frozenV5Wins":len(v5_won),"v10Wins":len(v10_won),
                       "v10NovelVsV5":0,"v10LostV5Goals":len(loss),
                       "v10LostV5Seeds":loss,
                       "fitTrainWorlds":result["fit_train"]["source_worlds"],
                       "heldTrainWorlds":result["held_train"]["source_worlds"],
                       "firedOnV5SuccessFit":result["fit_train"]["fired_on_v5_goal_worlds"],
                       "firedOnV5SuccessHeld":result["held_train"]["fired_on_v5_goal_worlds"],
                       "coveredV10ReopenFit":result["fit_train"]["covered_v10_reopen_opportunity_worlds"],
                       "coveredV10ReopenHeld":result["held_train"]["covered_v10_reopen_opportunity_worlds"],
                       "sourceObservedMotorBudgetFitHeld":budget},
           "frozenGoalsProtectedOnlyByObservedTriggerNoninterference":True,
           "futurePhysicsVerified":False,
           "devCalTestOodOpened":False,
           "modelPromotionAuthorized":False}
    seeds=list(range(START,START+SCAN))
    # The next run binds the on-disk bytes, not a different canonical JSON
    # representation that could accidentally disagree with the frozen gate.
    gate_bytes = (json.dumps(model,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()
    next_plan={"schema":"junction.rokoko.v11.fresh-train-only-next-step.v1",
               "sourceEvidence":source,"candidateModelGateSha256":hashlib.sha256(gate_bytes).hexdigest(),
               "trainSeedRangeInclusive":[START,START+SCAN-1],
               "trainScanSeedsSha256":digest(seeds),
               "publicOnlyInitialSelection":{"observedYThresholdAbsLt":.122,
                   "near":NEXT_NEAR,"clear":NEXT_CLEAR,
                   "noOutcomeBasedSelection":True},
               "pairedStrategies":list(NEXT_STRATEGIES),
               "expectedEpisodesIfCohortComplete":(NEXT_NEAR+NEXT_CLEAR)*len(NEXT_STRATEGIES),
               "goal250TickDwellPhysicalScorePrimary":True,
               "collectorRequirement":{"completeOriginalFullTransitions":True,
                    "noOmittedTrialOrLossAllowed":True,
                    "losslessSourceHashBoundChunks":True,
                    "failClosedOnPerFileCaptureCap":True,
                    "independentDeriveActualNear128Clear32From512PublicStarts":True},
               "hardNoGoIfAnyFrozenV5WinLost":True,
               "hardNoGoIfAnyNewUnsafe":True,
               "strictNovelSafeGoalImprovementRequired":True,
               "preregisteredHeldTrainNotDevTest":True,
               "needReviewedSourceAndLosslessCollector":True,
               "dispatchAuthorized":False,
               "modelPromotionAuthorized":False}
    analysis={"schema":"junction.rokoko.v11.goal-first-train-analysis.v1",
              "sourceEvidence":source,"actualPairedV5Goals":37,
              "actualPairedV10Goals":26,"safeV5WinsLostByV10":loss,
              "V10NovelGoals":[],"V10UnsafeTrials":0,
              "scienceVerdict":"V10_NO_GO_ZERO_NOVEL_AND_11_V5_GOALS_LOST",
              "nextCandidateFit":result,"observedMotorBudget":budget,
              "limitations":["No new MuJoCo physics run or 250-tick dwell improvement was measured for V11.",
                   "V5 source winning actions are never replaced by V11 gate along their original TRAIN trajectories, but this is not a prospective performance guarantee.",
                   "V10 same-world forward reopens are opportunity signals on distinct trajectories, not counterfactual evidence that rescue from V5 state succeeds.",
                   "The 8-option budget is selected from V10 observed public blocked-side-to-forward-reopen windows, not goal dwell outcomes; even perfect reopen prediction would not imply goal success.",
                   "Both fit/held are TRAIN world-group-disjoint diagnostics, not sealed dev/test/OOD qualification.",
                   "CRACI receipt is source reported, not a signed provider billing or robot safety certificate."]}
    return {"gate.json":model,"analysis.json":analysis,"next-train-plan.json":next_plan}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--retained",type=Path,required=True)
    parser.add_argument("--receipt",type=Path,required=True)
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    outputs=build_outputs(args.retained,args.receipt,args.source_root)
    evidence.require(not args.out.exists(),"V11_CHECKPOINT_OUTPUT_MUST_BE_NEW")
    args.out.mkdir(parents=True,mode=0o700)
    hashed={}
    for name,value in outputs.items():
        text=json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+"\n"
        with (args.out/name).open("x",encoding="utf8") as target:target.write(text)
        hashed[name]=hashlib.sha256(text.encode()).hexdigest()
    manifest={"schema":"junction.rokoko.v11.frozen-local-train-output.v1",
              "producedAt":datetime.now(timezone.utc).isoformat(),
              "sourceCommit":evidence.V10_SOURCE_SHA,
              "sourceTrainingSha256":evidence.V10_RAW["training.json"],
              "fileSha256":hashed,"physicsExecuted":False,
              "modelPromotionAuthorized":False}
    with (args.out/"manifest.json").open("x",encoding="utf8") as target:
        json.dump(manifest,target,sort_keys=True,indent=2);target.write("\n")
    print(json.dumps({"outputDir":str(args.out),"sha256":hashed,
                      "scienceVerdict":outputs["analysis.json"]["scienceVerdict"],
                      "fit":outputs["analysis.json"]["nextCandidateFit"]["fit_train"],
                      "held":outputs["analysis.json"]["nextCandidateFit"]["held_train"],
                      "newPhysics":False,"dispatchAuthorized":False},sort_keys=True))


if __name__=="__main__":main()
