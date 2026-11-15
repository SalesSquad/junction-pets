#!/usr/bin/env python3
"""Independent source-bound replay of ORIGINAL V12 CRACI TRAIN pilot.

Supply the exact hosted ZIP and an extracted wrapper directory. This script
never downloads, dispatches, modifies source evidence, or claims new physics.
"""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import zipfile

import numpy as np

EXPECTED_ARTIFACT_SHA="f2bed411c74bd99a4a622bd3ed1853a2542313ede8acc219b9f1d57c08729311"
SOURCE="78f1b9de566dedf9ba3800ebee60fffa8ed0cc4f"
HARNESS="4874d15dd68d3a809aaf7d769d6b5bef85d378bd"
MODEL="82cfa42ba2240aff6d00ec3e2b15c06d78386d3c0682986a23e478977f2dbf9e"
PLAN="8074f8f8978e2e55bdf201eeb9713888e44befe1d93856da44c1830bb86cfc48"
ARMS=("frozen_v5","v12_phase_dwell_supported_actions",
      "v12_right_side_action4_exploration_train_only")

def demand(value,reason):
    if not value:raise AssertionError(reason)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()

def read(path):
    return json.loads(path.read_bytes())

def public_mask(observation):
    o=np.asarray(observation,dtype=np.float32)
    demand(o.shape==(18,) and np.isfinite(o).all(),"PUBLIC_18D_NONFINITE")
    goal=np.array([.16,0.])
    allowed=np.ones(7,dtype=bool)
    if o[15] or not o[10] or not o[11] or o[8]>.1 or o[9]<.8:
        allowed[:6]=False
        return allowed.astype(int).tolist()
    obj,obstacle=o[:2],o[6:8]
    vec=goal-obj
    nearest=obj+np.clip(np.dot(obstacle-obj,vec)/
                        max(np.dot(vec,vec),1e-12),0.,1.)*vec
    if np.linalg.norm(nearest-obstacle)<.060:
        allowed[:5]=False
    if np.linalg.norm(o[2:4]-obj)<.029:
        allowed[2]=False
    obj64=np.asarray(o[:2],dtype=np.float64)
    obstacle64=np.asarray(o[6:8],dtype=np.float64)
    to_goal=goal-obj64
    unit=to_goal/max(float(np.linalg.norm(to_goal)),1e-9)
    nearest64=obj64+np.clip(np.dot(obstacle64-obj64,to_goal)/
                            max(np.dot(to_goal,to_goal),1e-12),0.,1.)*to_goal
    if float(np.linalg.norm(obstacle64-nearest64))<.060:
        lateral=np.array([-unit[1],unit[0]])
        for option in (0,3,4):
            destination=obj64-(.041 if option==0 else .024)*unit+(
                0. if option==0 else (.019 if option==3 else -.019))*lateral
            allowed[option]=bool(np.linalg.norm(destination-obstacle64)>.055)
    return allowed.astype(int).tolist()

def unpack(artifact_zip:Path,extracted_root:Path):
    demand(artifact_zip.is_file() and not artifact_zip.is_symlink() and
           extracted_root.is_dir() and not extracted_root.is_symlink(),
           "ORIGINAL_ZIP_OR_EXTRACT_ROOT_MISSING")
    product=extracted_root/"artifacts/rokoko-mujoco-v12-pilot"
    demand(sha(artifact_zip.read_bytes())==EXPECTED_ARTIFACT_SHA,
           "HOSTED_ARTIFACT_SHA_MISMATCH")
    receipt=read(extracted_root/"receipt.json")
    wrapper=read(extracted_root/"manifest.json")
    demand(wrapper["complete"] is True and
           receipt["status"]=="succeeded" and receipt["jobStatus"]=="success" and
           receipt["stageOutcome"]=="success" and receipt["command"]["exitCode"]==0 and
           receipt["binding"]["sourceSha"]==SOURCE and
           receipt["binding"]["harnessSha"]==HARNESS and
           receipt["sourceVerified"] is True and receipt["harnessVerified"] is True and
           receipt["providerAttestationVerified"] is False and
           sha((extracted_root/"manifest.json").read_bytes())==receipt["manifest"]["sha256"],
           "HOSTED_RECEIPT_OR_WRAPPER_BAD")
    for file in wrapper["files"]:
        p=extracted_root/file["path"]
        demand(p.is_file() and not p.is_symlink() and
               len(p.read_bytes())==file["bytes"] and sha(p.read_bytes())==file["sha256"],
               "HOSTED_WRAPPED_FILE_SHA_BAD_"+file["path"])
    retention=read(product/"retention-manifest.json")
    manifest=read(product/"manifest.json")
    qualification=read(product/"independent-qualification.json")
    readout=read(product/"paired-readout.json")
    demand(retention["status"]=="COMPLETE_TRAIN_ONLY" and
           retention["exact_source_sha"]==manifest["executed_head"]==SOURCE and
           manifest["model_sha256"]==qualification["model_sha256"]==MODEL and
           manifest["plan_sha256"]==qualification["plan_sha256"]==PLAN and
           qualification["harness_head"]==HARNESS and
           manifest["actual_trials"]==qualification["actual_trials"]==144 and
           manifest["actual_option_transitions"]==qualification["actual_option_transitions"]==4228 and
           manifest["training_only"] is True and
           manifest["dev_cal_test_ood_opened"] is False and
           qualification["new_model_promotion_authorized"] is False and
           qualification["dev_cal_test_ood_opened"] is False and
           qualification["experiment_complete"] is True and
           qualification["full_144_real_episode_physics_replay"]["claim_verified"] is True and
           qualification["full_144_real_episode_physics_replay"]["all_144_complete_real_episodes_replayed"] is True and
           qualification["full_144_real_episode_physics_replay"]["all_512_public_initial_worlds_replayed"] is True and
           qualification["full_144_real_episode_physics_replay"]["dev_cal_test_ood_opened"] is False and
           qualification["right4_exploration_is_untrained"] is True and
           readout["scienceDecision"]=="STOP",
           "PRODUCT_SOURCE_GOAL_SEAL_OR_SCIENCE_DRIFT")
    originals={}
    for original in retention["sources"]:
        chunks=[]
        for part in original["parts"]:
            packed=(product/part["archive"]).read_bytes()
            demand(len(packed)==part["archive_bytes"] and
                   sha(packed)==part["archive_sha256"],
                   "ORIGINAL_ZIP_PART_BYTES_TAMPERED")
            with zipfile.ZipFile(io.BytesIO(packed)) as z:
                demand(z.namelist()==[part["entry"]],"ORIGINAL_ZIP_ENTRY_CHANGED")
                chunk=z.read(part["entry"])
            demand(len(chunk)==part["raw_bytes"] and sha(chunk)==part["raw_sha256"],
                   "ORIGINAL_ZIP_CHUNK_SHA_BAD")
            chunks.append(chunk)
        data=b"".join(chunks)
        name=original["name"]
        demand(len(data)==original["original_bytes"] and
               sha(data)==original["original_sha256"]==
               retention["original_sha256"][name]==manifest["file_sha256"][name]==
               qualification["original_sha256"][name],
               "ORIGINAL_LOSSLESS_RAW_MANIFEST_MISMATCH_"+name)
        originals[name]=data
    demand(set(originals)=={"training.json","full_transitions.jsonl.gz"} and
           sha((product/"paired-readout.json").read_bytes())==
           manifest["file_sha256"]["paired-readout.json"],
           "ORIGINAL_FULL_SOURCE_INCOMPLETE")
    return receipt,manifest,qualification,readout,originals

def derive_public_cohort(scans):
    demand(len(scans)==512 and
           [row["seed"] for row in scans]==list(range(518000,518512)),
           "FRESH_TRAIN_SCAN_GAP_OR_LEAK")
    near,clear=[],[]
    for record in scans:
        obs=record["observation"]
        demand(record["mask"]==public_mask(obs) and
               isinstance(record["world_hash"],str) and len(record["world_hash"])>=8,
               "PUBLIC_INITIAL_MASK_OR_WORLD_BAD")
        tag=abs(obs[7])<.122
        if tag and len(near)<40:near.append(record)
        if not tag and len(clear)<8:clear.append(record)
    selected=sorted([*near,*clear],key=lambda r:r["seed"])
    demand(len(selected)==48,"FRESH_COHORT_HANDPICKED_OR_UNDERFILLED")
    return selected


def validate_terminal_goal250(row,events):
    last=events[-1]
    demand(row["success"]==last["success_info"] and
           row["contacts"]==last["contacts_cumulative"] and
           row["dwell_ticks_final"]==last["dwell_ticks_current"] and
           row["unsafe"]==bool(any(e["cost"] for e in events)) and
           abs(row["total_reward"]-sum(e["reward"] for e in events))<1e-4,
           "REAL_TERMINAL_FLAG_OR_PHYSICS_SUM_CHANGED")
    demand(not row["abstained"] or last["action"]==6,
           "ABSTAIN_REQUIRES_FINAL_MASKED_SIX_OPTION")
    safe=bool(row["success"] and not row["unsafe"] and not row["abstained"])
    if safe:
        observation=last["next_observation"]
        goal_distance=math.hypot(observation[0]-observation[16],
                                 observation[1]-observation[17])
        demand(last["dwell_ticks_current"]>=250 and
               last["dwell_ticks_cumulative"]>=250 and
               last["contacts_cumulative"]>0 and goal_distance<.025 and
               last["action"]!=6 and row["physics_steps"]>0,
               "FAKE_GOAL250_NO_PHYSICAL_CONTACT_OR_DWELL")
    return safe


def validate_signed_public_progress(row,events):
    first=events[0]["observation"]
    last=events[-1]["next_observation"]
    sign=-1 if first[7]>=first[1] else 1
    signed_away=(last[1]-first[1])*sign
    demand(abs(row["lateral_displacement"]-signed_away)<1e-5 and
           abs(row["away_lateral_displacement"]-max(0.,signed_away))<1e-5,
           "FORGED_SIGNED_PUBLIC_OBSTACLE_AWAY_DISPLACEMENT")
    return signed_away


def audit(artifact_zip:Path,extracted_root:Path):
    receipt,manifest,qualification,readout,originals=unpack(
        artifact_zip,extracted_root)
    training=json.loads(originals["training.json"])
    demand(training["executed_head"]==SOURCE and
           training["actual_physics_engine"]=="mujoco-3.3.7" and
           training["model_sha256"]==MODEL and training["plan_sha256"]==PLAN and
           training["training_only"] is True and
           training["no_dev_test_ood"] is True and
           training["model_promotion_authorized"] is False and
           training["actual_trials"]==144 and
           training["actual_option_transitions"]==4228 and
           training["strategies"]==list(ARMS),
           "PRODUCER_TRAIN_IDENTITY_OR_SEAL_BAD")
    scans=training["all_512_public_initial_scans"]
    selected=derive_public_cohort(scans)
    cohort=training["cohort"]
    demand(len(selected)==48 and len(cohort)==48 and
           [r["seed"] for r in selected]==[r["seed"] for r in cohort],
           "FRESH_COHORT_HANDPICKED_OR_UNDERFILLED")
    by_seed={r["seed"]:r for r in selected}
    for row in cohort:
        original=by_seed[row["seed"]]
        demand(row["world_hash"]==original["world_hash"] and
               row["initial_mask"]==original["mask"] and
               row["observed_corridor"]==(abs(original["observation"][7])<.122) and
               abs(row["initial_public_obstacle_y"]-original["observation"][7])<1e-8,
               "COHORT_PUBLIC_SOURCE_HASH_MISMATCH")
    trials={}
    for row in training["trials"]:
        key=(row["seed"],row["strategy"])
        demand(key not in trials and key[0] in by_seed and key[1] in ARMS and
               row["world_hash"]==by_seed[key[0]]["world_hash"] and
               isinstance(row["success"],bool) and isinstance(row["unsafe"],bool) and
               isinstance(row["abstained"],bool),
               "DUPLICATE_OR_UNPAIRED_REAL_TRIAL")
        trials[key]=row
    demand(len(trials)==144 and
           set(trials)=={(row["seed"],name) for row in selected for name in ARMS},
           "REAL_144_PAIRED_WORLD_GRID_INCOMPLETE")
    seen=set()
    executed=Counter()
    legal=Counter()
    world_action=defaultdict(set)
    episodes_action=defaultdict(set)
    per_strategy=defaultdict(lambda:Counter())
    option_count=0
    goal_successes=defaultdict(set)
    right_examples=[]
    raw_right_instances=[]
    with gzip.GzipFile(fileobj=io.BytesIO(originals["full_transitions.jsonl.gz"])) as gz:
        for raw_line in gz:
            rec=json.loads(raw_line)
            key=(rec["seed"],rec["strategy"])
            demand(key in trials and key not in seen,"ORIGINAL_STREAM_DUPLICATE_OR_UNKNOWN")
            seen.add(key)
            row=trials[key]
            events=rec["transitions"]
            n=len(events)
            indices=sorted(set(range(min(12,n)))|set(range(max(0,n-8),n))|
                           set(range(0,n,5)))
            demand(1<=n<=60 and row["full_transition_count"]==row["option_steps"]==n and
                   row["full_transition_sha256"]==sha(canonical(events)) and
                   row["sparse_transition_indices"]==indices and
                   row["transitions"]==[events[j] for j in indices],
                   "ORIGINAL_FULL_VS_SPARSE_SHA_BAD")
            prev_contacts=0
            prev_dwell_peak=0
            for index,ev in enumerate(events):
                o=ev["observation"]
                nxt=ev["next_observation"]
                action=ev["action"]
                m=ev["mask"]
                demand(len(o)==len(nxt)==18 and
                       all(isinstance(x,(float,int)) and math.isfinite(x) for x in o+nxt) and
                       m==public_mask(o) and type(action) is int and 0<=action<7 and m[action]==1 and
                       type(ev["cost"]) is int and ev["cost"] in (0,1) and
                       ev["done"] is (index==n-1) and
                       type(ev["contacts_cumulative"]) is int and
                       ev["contacts_cumulative"]>=prev_contacts and
                       type(ev["dwell_ticks_cumulative"]) is int and
                       ev["dwell_ticks_cumulative"]>=prev_dwell_peak and
                       type(ev["success_info"]) is bool,
                       "PUBLIC_18D_SHIELD_CONTACT_DWELL_EVENT_BAD")
                prev_contacts=ev["contacts_cumulative"]
                prev_dwell_peak=ev["dwell_ticks_cumulative"]
                if index:
                    before=events[index-1]["next_observation"]
                    demand(all(abs(a-b)<1e-5 for a,b in zip(before,o)),
                           "ORIGINAL_OBSERVATION_CHAIN_BROKEN")
                executed[action]+=1
                demand(action!=4 or rec["strategy"]==ARMS[2],
                       "UNTRAINED_RIGHT4_EXECUTED_IN_NONEXPLORATION_ARM")
                world_action[action].add(rec["seed"])
                episodes_action[action].add(key)
                if action==4:
                    right_examples.append(dict(seed=rec["seed"],strategy=rec["strategy"],
                                               step=index+1,legal=m[action],
                                               before=o[0:2],after=nxt[0:2]))
                    raw_right_instances.append(dict(seed=rec["seed"],
                                                    option_index=index,
                                                    original_seven_mask=m))
                for a in range(7):legal[a]+=int(bool(m[a]))
                option_count+=1
            validate_signed_public_progress(row,events)
            if validate_terminal_goal250(row,events):
                goal_successes[rec["strategy"]].add(rec["seed"])
            if row["unsafe"]:per_strategy[rec["strategy"]]["unsafe"]+=1
            if row["abstained"]:per_strategy[rec["strategy"]]["abstained"]+=1
    demand(seen==set(trials) and option_count==4228 and
           option_count==qualification["full_144_real_episode_physics_replay"]["exact_real_full_options_replayed"] and
           executed[4]==qualification["full_144_real_episode_physics_replay"]["untrained_right4_actual_legal_executions"]==31 and
           sum(len(v) for v in goal_successes.values())==
           qualification["full_144_real_episode_physics_replay"]["real_safe_clear_goal_trajectories_replayed"]+
           qualification["full_144_real_episode_physics_replay"]["real_safe_near_goal_trajectories_replayed"],
           "INDEPENDENT_REAL_OPTION_OR_GOAL_COUNTER_DISAGREES")
    producer_right=training["observed_exploration_action4_instances"]
    # Producer logs the zero-based option index and the original seven-mask;
    # compare directly to each executed action4 event in the full raw stream.
    demand(len(producer_right)==executed[4] and
           producer_right==raw_right_instances and
           sha(canonical(producer_right))==
           qualification["full_144_real_episode_physics_replay"]["original_exploration_option4_instances_sha256"],
           "FORGED_RIGHT4_EXECUTED_ACTION_INSTANCES")
    baseline=goal_successes[ARMS[0]]
    candidate=goal_successes[ARMS[1]]
    explore=goal_successes[ARMS[2]]
    lost=sorted(baseline-candidate)
    novel=sorted(candidate-baseline)
    cand_unsafe=sorted(seed for (seed,name),r in trials.items()
                       if name==ARMS[1] and r["unsafe"])
    exploration_unsafe=sorted(seed for (seed,name),r in trials.items()
                              if name==ARMS[2] and r["unsafe"])
    demand(len(baseline)==readout["frozenV5SafeGoals"] and
           len(candidate)==readout["candidateSafeGoals"] and
           lost==readout["candidateLostV5GoalWorldSeeds"] and
           novel==readout["candidateNovelSafeGoalWorldSeeds"] and
           cand_unsafe==readout["candidateUnsafeWorldSeeds"] and
           exploration_unsafe==readout["explorationOnlyUnsafeWorldSeeds"] and
           readout["hardStopNoFurtherPhysics"] is True and
           readout["scienceDecision"]=="STOP",
           "INDEPENDENT_GOAL250_PAIRED_SCIENCE_MISMATCH")
    result={
      "work_id":"V12-CRACI-PILOT-20261115",
      "source_head":SOURCE,"harness_head":HARNESS,
      "run_id":receipt["runId"],"hosted_run":43657058944,
      "archive_id":14139070947,"original_github_artifact_zip_sha256":EXPECTED_ARTIFACT_SHA,
      "lossless_original_sha256":{name:sha(b) for name,b in originals.items()},
      "verified_fresh_train_scans":512,"paired_distinct_train_worlds":48,
      "near_worlds":40,"clear_worlds":8,
      "paired_real_muJoCo_3_3_7_episodes":len(trials),
      "real_public_18D_seven_mask_events":option_count,
      "baseline_safe_goal250":len(baseline),"candidate_safe_goal250":len(candidate),
      "explore_safe_goal250":len(explore),
      "baseline_goal_seed_ids":sorted(baseline),
      "candidate_goal_seed_ids":sorted(candidate),
      "explore_goal_seed_ids":sorted(explore),
      "candidate_novel":novel,"candidate_lost":lost,
      "candidate_unsafe":cand_unsafe,"right_explore_unsafe":exploration_unsafe,
      "real_executed_per_action":[executed[a] for a in range(7)],
      "real_mask_legal_per_action":[legal[a] for a in range(7)],
      "distinct_real_worlds_per_action":[len(world_action[a]) for a in range(7)],
      "distinct_real_episodes_per_action":[len(episodes_action[a]) for a in range(7)],
      "right4_actual_executed":executed[4],
      "right4_distinct_worlds":len(world_action[4]),
      "right4_distinct_episodes":len(episodes_action[4]),
      "right4_world_ids":sorted(world_action[4]),
      "right4_samples":right_examples[:40],
      "per_strategy":{name:{"safe_goal250":len(goal_successes[name]),
                            "unsafe":per_strategy[name]["unsafe"],
                            "abstained":per_strategy[name]["abstained"]}
                      for name in ARMS},
      "science":"STOP_ZERO_NOVEL_TRUE_GOAL250",
      "future_confirmation_518512_519023_authorized":False,
      "no_model_promotion":True,"no_dev_test_ood":True,
      "provider_billing_unknown":True,"signed_provider_attestation":False,
      "independent_new_physics_rerun":False,
    }
    return result

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_artifact_zip",type=Path)
    parser.add_argument("extracted_wrapper_root",type=Path)
    parser.add_argument("--output-summary",type=Path,
                        help="optional NEW file outside the original evidence directory")
    args=parser.parse_args()
    result=audit(args.original_artifact_zip,args.extracted_wrapper_root)
    encoded=canonical(result)+b"\n"
    if args.output_summary:
        target=args.output_summary
        demand(not target.is_symlink() and
               not target.resolve().is_relative_to(args.extracted_wrapper_root.resolve()) and
               target.resolve()!=args.original_artifact_zip.resolve(),
               "EVIDENCE_MUST_NEVER_BE_OVERWRITTEN")
        with target.open("xb") as output:
            output.write(encoded)
    print(json.dumps({k:result[k] for k in
          ("science","paired_real_muJoCo_3_3_7_episodes","real_public_18D_seven_mask_events",
           "baseline_safe_goal250","candidate_safe_goal250","explore_safe_goal250",
           "candidate_novel","candidate_lost","candidate_unsafe",
           "right_explore_unsafe","right4_actual_executed","right4_distinct_worlds",
           "right4_distinct_episodes","real_executed_per_action",
           "right4_world_ids")},sort_keys=True))
    print("independent_audit_summary_sha256="+sha(encoded))
