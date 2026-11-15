"""Read-only V13 forensic loader for immutable original V12 MuJoCo TRAIN.

Never substitutes synthetic data for actual executed options. A verified
source-reported receipt and independently replayed full raw are mandatory;
not a signed provider billing attestation or a prospective V13 result.
"""
from __future__ import annotations

import collections
import gzip
import hashlib
import json
import math
from pathlib import Path
import zipfile


SOURCE_HEAD="78f1b9de566dedf9ba3800ebee60fffa8ed0cc4f"
HARNESS_HEAD="4874d15dd68d3a809aaf7d769d6b5bef85d378bd"
RUN_ID="craci.43657058944.1.93edebd476b31661"
MODEL_SHA="82cfa42ba2240aff6d00ec3e2b15c06d78386d3c0682986a23e478977f2dbf9e"
PLAN_SHA="8074f8f8978e2e55bdf201eeb9713888e44befe1d93856da44c1830bb86cfc48"
ARM_V5="frozen_v5"
ARM_V12="v12_phase_dwell_supported_actions"
ARM_RIGHT="v12_right_side_action4_exploration_train_only"
ARMS=(ARM_V5,ARM_V12,ARM_RIGHT)
PROOF_SHAS={
 "receipt.json":"3d7711b8153284d26beb24f0350069593a4f3f3fbc0eb34003c2738a76660711",
 "manifest.json":"f71bd40a8eb317f57c74a89fd229e368557c95e93a11bdee7001f74a1fdc484c",
 "independent-qualification.json":"a370a001a368d43ae8fb46847d73c6623ef692b290f0decbe94ba00018d15e88",
 "paired-readout.json":"2245497c68da38e12353a6f43846ec2a14ad527d57c42491084ada8581873fa5",
 "retention-manifest.json":"4b860f9240eb1c6cdbf0e64c9403aad6c5d90aef90ed4eaed2032abeea7823be",
}
RAW_SHAS={"training.json":"cdc4d9d8729d61c730048c802579d25813dc45b55cf4e68d61d680840b7e7a2d",
          "full_transitions.jsonl.gz":"7e8d7c80cb8d035d904338e1a544662181a93933cc5c324458f7195c56f90b91"}
ZIP_SHAS={"training.json.part000.zip":"65dd9c43c00c5bb7b24be3f480e0852d7167f64227f03e54a67346d8a83725fb",
          "full_transitions.jsonl.gz.part000.zip":"8c161afc69619e467d1bc26a6c8ef29706e425c9a80ff74a83cd05faca363bbf"}


def require(ok,code):
    if not ok:raise ValueError(code)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def checked(path,checksum):
    require(path.is_file() and not path.is_symlink() and path.stat().st_nlink==1,
            "V13_ORIGINAL_EVIDENCE_MISSING_OR_UNSAFE")
    raw=path.read_bytes()
    require(sha(raw)==checksum,"V13_ORIGINAL_EVIDENCE_SHA_MISMATCH")
    return raw


def public(obs,mask):
    require(len(obs)==18 and len(mask)==7 and
        all(type(x) in (int,float) and math.isfinite(x) for x in obs) and
        all(type(x) in (bool,int) and x in (0,1) for x in mask) and any(mask),
        "V13_ONLY_FINITE_PUBLIC18D_AND_ORIGINAL_SEVEN_MASK")


def _reassemble(root,retention):
    require(set(source["name"] for source in retention["sources"])==set(RAW_SHAS),
            "V13_RETENTION_SOURCE_SET_DRIFT")
    rebuilt={}
    for source in retention["sources"]:
        name=source["name"]
        chunks=[]
        for part in source["parts"]:
            p=root/part["archive"]
            checked(p,ZIP_SHAS[part["archive"]])
            with zipfile.ZipFile(p) as z:
                require(z.namelist()==[part["entry"]],"V13_UNEXPECTED_ARCHIVE_MEMBER")
                raw=z.read(part["entry"])
            require(len(raw)==part["raw_bytes"] and sha(raw)==part["raw_sha256"],
                    "V13_RETENTION_PART_SHA_DRIFT")
            chunks.append(raw)
        rebuilt[name]=b"".join(chunks)
        require(sha(rebuilt[name])==RAW_SHAS[name] and
                source["original_sha256"]==RAW_SHAS[name],
                "V13_ORIGINAL_FULL_RAW_DRIFT")
    return rebuilt


def load_original_v12(archive_dir,receipt_path):
    root=Path(archive_dir).resolve(strict=True)
    require(root.is_dir() and not root.is_symlink(),"V13_SOURCE_ARCHIVE_NOT_SAFE")
    receipt=json.loads(checked(Path(receipt_path).resolve(strict=True),
                               PROOF_SHAS["receipt.json"]))
    proofs={name:json.loads(checked(root/name,checksum)) for name,checksum in
            PROOF_SHAS.items() if name!="receipt.json"}
    manifest,qual,readout=(proofs[name] for name in
            ("manifest.json","independent-qualification.json","paired-readout.json"))
    b=receipt["binding"]
    require(b["sourceSha"]==SOURCE_HEAD and b["harnessSha"]==HARNESS_HEAD and
        b["runId"]==RUN_ID and b["workload"]=="rokoko-mujoco-v12-pilot" and
        receipt["sourceVerified"] is True and receipt["harnessVerified"] is True and
        receipt["evidenceLevel"]=="source-reported" and
        receipt["command"]["binding"]==b,
        "V13_ORIGINAL_SOURCE_RECEIPT_INVALID")
    # The job status strings use succeeded/success, intentionally exact.
    require(receipt["status"]=="succeeded" and receipt["jobStatus"]=="success" and
        receipt["command"]["exitCode"]==receipt["command"]["wrapperExitCode"]==0 and
        manifest["executed_head"]==qual["executed_head"]==SOURCE_HEAD and
        qual["harness_head"]==HARNESS_HEAD and
        qual["experiment_complete"] is True and
        qual["full_144_real_episode_physics_replay"]["claim_verified"] is True and
        qual["full_144_real_episode_physics_replay"]["all_144_complete_real_episodes_replayed"] is True and
        qual["full_144_real_episode_physics_replay"]["all_512_public_initial_worlds_replayed"] is True and
        qual["full_144_real_episode_physics_replay"]["exact_real_full_options_replayed"]==4228 and
        qual["dev_cal_test_ood_opened"] is False and
        qual["new_model_promotion_authorized"] is False and
        manifest["model_sha256"]==qual["model_sha256"]==MODEL_SHA and
        manifest["plan_sha256"]==qual["plan_sha256"]==PLAN_SHA and
        manifest["actual_trials"]==qual["actual_trials"]==144 and
        manifest["actual_option_transitions"]==qual["actual_option_transitions"]==4228 and
        manifest["file_sha256"]["training.json"]==RAW_SHAS["training.json"] and
        manifest["file_sha256"]["full_transitions.jsonl.gz"]==RAW_SHAS["full_transitions.jsonl.gz"] and
        readout["scienceDecision"]=="STOP" and readout["frozenV5SafeGoals"]==12 and
        readout["candidateSafeGoals"]==12 and
        readout["candidateNovelSafeGoalWorldSeeds"]==readout["candidateLostV5GoalWorldSeeds"]==[] and
        readout["candidateUnsafeWorldSeeds"]==readout["explorationOnlyUnsafeWorldSeeds"]==[],
        "V13_ORIGINAL_FULL_PHYSICS_QUALIFICATION_NEGATIVE_SCIENCE_CHANGED")
    original=_reassemble(root,proofs["retention-manifest.json"])
    training=json.loads(original["training.json"])
    full=[json.loads(raw) for raw in
          gzip.decompress(original["full_transitions.jsonl.gz"]).splitlines()]
    require(training["actual_trials"]==len(full)==144 and
            training["actual_option_transitions"]==4228 and
            len(training["all_512_public_initial_scans"])==512 and
            training["strategies"]==list(ARMS) and
            training["executed_head"]==SOURCE_HEAD and
            training["no_dev_test_ood"] is True and
            training["model_promotion_authorized"] is False,
            "V13_ORIGINAL_144_TRAIN_MATRIX_DRIFT")
    scans=training["all_512_public_initial_scans"]
    require([w["seed"] for w in scans]==list(range(518000,518512)),
            "V13_V12_ALL_512_PUBLIC_SCANS_MISSING")
    for w in scans:public(w["observation"],w["mask"])
    near=[];clear=[]
    for w in scans:
        if abs(w["observation"][7])<.122 and len(near)<40:near.append(w["seed"])
        if abs(w["observation"][7])>=.122 and len(clear)<8:clear.append(w["seed"])
    require(sorted([*near,*clear])==[w["seed"] for w in training["cohort"]],
            "V13_UNTRUSTED_PRODUCER_48_PUBLIC_WORLD_SELECTION")
    rows={(row["seed"],row["strategy"]):row for row in training["trials"]}
    traces={}
    options=0
    for row in full:
        key=(row["seed"],row["strategy"])
        require(key in rows and key not in traces and
                len(row["transitions"])==rows[key]["full_transition_count"],
                "V13_MISSING_OR_DUPLICATED_ORIGINAL_EPISODE")
        steps=row["transitions"]
        require(sha(json.dumps(steps,sort_keys=True,separators=(",",":"),
                     ensure_ascii=False,allow_nan=False).encode())==rows[key]["full_transition_sha256"],
                "V13_ORIGINAL_OPTION_TRACE_SHA_MISMATCH")
        for step in steps:
            public(step["observation"],step["mask"])
            require(type(step["action"]) is int and 0<=step["action"]<7 and
                    step["mask"][step["action"]]==1 and
                    len(step["next_observation"])==18 and
                    all(math.isfinite(v) for v in step["next_observation"]),
                    "V13_ORIGINAL_UNMASKED_OR_NONPUBLIC_ACTION")
        options+=len(steps)
        traces[key]=steps
    require(len(rows)==len(traces)==144 and options==4228,
            "V13_ORIGINAL_COMPLETE_4228_OPTION_MATRIX_DRIFT")
    return {"training":training,"rows":rows,"traces":traces,
            "sourceSha":SOURCE_HEAD,"harnessSha":HARNESS_HEAD,
            "fullTransitionsSha256":RAW_SHAS["full_transitions.jsonl.gz"],
            "independentReplayQualified":True,"newPhysicsPerformed":False}


def source_failure_diagnosis(source):
    rows,traces=source["rows"],source["traces"]
    worlds=sorted(seed for seed,arm in rows if arm==ARM_V5)
    require(len(worlds)==48,"V13_ORIGINAL_48_WORLDS_REQUIRED")
    wins=[s for s in worlds if rows[s,ARM_V5]["success"]]
    failed=[s for s in worlds if s not in wins]
    require(len(wins)==12 and len(failed)==36,"V13_BASELINE_GOALS_CHANGED")
    changes={arm:[] for arm in (ARM_V12,ARM_RIGHT)}
    for arm in changes:
        changes[arm]=[s for s in worlds if [a["action"] for a in traces[s,arm]]!=
                      [a["action"] for a in traces[s,ARM_V5]]]
        require(len(changes[arm])==31 and all(s in failed for s in changes[arm]),
                "V13_PILOT_SOURCE_GOAL_PRESERVATION_TRAJECTORY_CHANGED")
    live_dropped=[s for s in failed if any(step["next_observation"][10]==0
                   for step in traces[s,ARM_V5])]
    early_abstain=[s for s in failed if rows[s,ARM_V5]["abstained"]]
    require(len(live_dropped)==10 and len(early_abstain)==26 and
            all(next(i+1 for i,t in enumerate(traces[s,ARM_V5]) if t["next_observation"][10]==0)==17
                for s in live_dropped),"V13_REAL_DEADMAN_VS_ABSTAIN_CLASSIFICATION_DRIFT")
    near_failed=sum(rows[s,ARM_V5]["observed_corridor"] for s in failed)
    require(near_failed==35,"V13_REAL_OBSTACLE_NEAR_FAILURE_LABEL_DRIFT")
    right_pairs=[]
    for s in changes[ARM_RIGHT]:
        probe=traces[s,ARM_RIGHT]
        idx=next(i for i,t in enumerate(probe) if t["action"]==4)
        baseline=traces[s,ARM_V5]
        require(idx<len(baseline) and all(a["action"]==b["action"] for a,b in zip(probe[:idx],baseline[:idx])) and
                probe[idx]["observation"]==baseline[idx]["observation"] and
                probe[idx]["mask"]==baseline[idx]["mask"],
                "V13_RIGHT4_UNMATCHED_ORIGINAL_PUBLIC_DECISION")
        original_action=baseline[idx]["action"]
        require(original_action in (3,6),"V13_ORIGINAL_RIGHT4_BASE_ACTION_DRIFT")
        dist=lambda o:math.hypot(o[16]-o[0],o[17]-o[1])
        gain=(dist(probe[idx]["observation"])-dist(probe[idx]["next_observation"]))-(
             dist(baseline[idx]["observation"])-dist(baseline[idx]["next_observation"]))
        right_pairs.append({"seed":s,"optionIndexZeroBased":idx,
                            "v5Action":original_action,"untrainedAction4":4,
                            "observedOneOptionGoalProgressGainMeters":gain})
    require(len(right_pairs)==31,"V13_RIGHT4_FIRST_ACTION_PAIRED_PROOF_FAILED")
    return {"schema":"junction.rokoko.v13.original-v12-causal-failure-diagnosis.v1",
      "originalSourceSha":SOURCE_HEAD,"originalHarnessSha":HARNESS_HEAD,
      "originalRealEpisodes":144,"originalExecutedOptions":4228,
      "sourceReportedIndependentReplay":True,"novelGoal250":0,
      "v5WinningWorlds":wins,"v5FailedWorlds":failed,
      "v5FailedLiveDropAtOption17Worlds":live_dropped,
      "v5FailedEarlyLegalAbstainWorlds":early_abstain,
      "v5FailedNearCorridorCount":near_failed,
      "bothV12ArmsDivergedOnlyOn31BaselineFailedWorlds":True,
      "candidateActionChangedWorlds":changes[ARM_V12],
      "right4ChangedWorlds":changes[ARM_RIGHT],
      "right4ExactPrefixMatchedOneOptionPairs":right_pairs,
      "allBaselineFailuresHadZero250TickDwell":all(
        not any(t["dwell_ticks_current"]>0 for t in traces[s,arm])
        for s in failed for arm in ARMS),
      "notProofOfUnreachability":True,"newPhysicsPerformed":False,
      "devCalTestOodOpened":False,"modelPromotionAuthorized":False}
