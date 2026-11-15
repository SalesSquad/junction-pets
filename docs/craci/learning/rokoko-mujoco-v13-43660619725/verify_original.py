#!/usr/bin/env python3
"""Fail-closed V13 original ZIP evidence audit. No physics, deploy or provider calls.

This accepts a *safety-negative* from an incomplete hosted run. It explicitly
rejects any efficacy/promotion claim. The small committed manifest contains
only identifiers and SHA256 hashes, never original private 18D trajectories.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile

import numpy as np

RUN=43660619725
ARTIFACT=14139354188
ZIP_SHA="cbbd78d255121102c39708ee2771f88c962e33e831ebce2b2c1c5d58769495b0"
SOURCE="0751d78b93855bf70820b03b0a543e123d218baf"
HARNESS="dc6d745c5facb56eed85016830dfe8f19b25032f"
V12_SOURCE="78f1b9de566dedf9ba3800ebee60fffa8ed0cc4f"
V12_HASH_INDEX_SHA="24460b2ed49635b33db66233dd854f84593e6f65484cde229ee17ec483dd0245"
RAW_SHA={
    "full_transitions.jsonl.gz":"6bb153cb699ebadd35ee32a3f940473341560855e512c4e174d0ab5990ba9e74",
    "option_journal.jsonl.gz":"dfb479ea92cd97a57722fdb69719817011cb3ac192ed47aeccf6196734fc9d3d",
    "partial_training.json":"8bbc9b7df5539c3d4cf10963c1ea098f7a488cd31c5e9d365f1df6fc8710e612",
}
UNSAFE_HASH="4702034192e3877e42278a1b297e9b8c787955fbe2a30e411dd06fd9a7fee4ba"
SCHEMA="craci.rokoko.v13.unsafe-original-hash-index.v1"
PRODUCT="artifacts/rokoko-mujoco-v13-causal/"
V12_INDEX_DEFAULT=Path(__file__).resolve().parent.parent/"rokoko-mujoco-v12-43657058944/trajectory-sha256.json"


def demand(condition,why):
    if not condition:
        raise AssertionError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()


def public_mask(observation):
    """Recompute the frozen seven-action public shield, never hidden physics."""
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


def original_bytes(archive):
    demand(archive.is_file() and not archive.is_symlink() and
           sha(archive.read_bytes())==ZIP_SHA,"HOSTED_ZIP_SHA_MISMATCH")
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        demand(len(names)==len(set(names)) and
               all(not n.startswith("/") and ".." not in Path(n).parts for n in names),
               "OUTER_ZIP_DUPLICATE_OR_TRAVERSAL")
        def load(name):
            demand(name in names,"HOSTED_ORIGINAL_MISSING_"+name)
            return z.read(name)
        wrapper=json.loads(load("manifest.json"))
        receipt=json.loads(load("receipt.json"))
        demand(wrapper["complete"] is True and
               sha(load("manifest.json"))==receipt["manifest"]["sha256"] and
               receipt["binding"]["sourceSha"]==SOURCE and
               receipt["binding"]["harnessSha"]==HARNESS and
               receipt["runId"]=="craci.43660619725.1.9de4a2c284947110" and
               receipt["status"]=="failed" and receipt["jobStatus"]=="failure" and
               receipt["stageOutcome"]=="failure" and receipt["command"]["exitCode"]==3 and
               receipt["sourceVerified"] is True and
               receipt["harnessVerified"] is True and
               receipt["providerAttestationVerified"] is False and
               receipt["cost"]["actual"] is None,
               "RECEIPT_SOURCE_OR_INCOMPLETE_STOP_CHANGED")
        for item in wrapper["files"]:
            data=load(item["path"])
            demand(len(data)==item["bytes"] and sha(data)==item["sha256"],
                   "WRAPPER_FILE_SHA_MISMATCH_"+item["path"])
        retention=json.loads(load(PRODUCT+"retention-manifest.json"))
        early=json.loads(load(PRODUCT+"early_stop.json"))
        demand(retention["status"]==early["status"]=="INCOMPLETE_STOP" and
               retention["exact_source_sha"]==early["executed_head"]==SOURCE and
               early["harness_head"]==HARNESS and
               early["reason"]=="V13_REAL_PHYSICS_UNSAFE" and
               early["recorded_branches"]==23 and
               early["recorded_real_options"]==394 and
               early["durably_journaled_all_executed_option_events"]==394 and
               early["model_promotion_authorized"] is False and
               retention["proof_sha256"]["early_stop.json"]==sha(load(PRODUCT+"early_stop.json")) and
               early["raw_sha256"]==retention["original_sha256"]==RAW_SHA,
               "EARLY_STOP_OR_RETENTION_PROOF_CHANGED")
        restored={}
        for source in retention["sources"]:
            chunks=[]
            for part in source["parts"]:
                packed=load(PRODUCT+part["archive"])
                demand(len(packed)==part["archive_bytes"] and
                       sha(packed)==part["archive_sha256"],"RETAINED_PART_SHA_BAD")
                with zipfile.ZipFile(io.BytesIO(packed)) as nested:
                    demand(nested.namelist()==[part["entry"]],"RETAINED_ENTRY_CHANGED")
                    chunk=nested.read(part["entry"])
                demand(len(chunk)==part["raw_bytes"] and
                       sha(chunk)==part["raw_sha256"],"RETAINED_CHUNK_SHA_BAD")
                chunks.append(chunk)
            original=b"".join(chunks)
            name=source["name"]
            demand(name not in restored and name in RAW_SHA and
                   len(original)==source["original_bytes"] and
                   sha(original)==source["original_sha256"]==RAW_SHA[name],
                   "RECONSTRUCTED_ORIGINAL_SHA_BAD")
            restored[name]=original
        demand(set(restored)==set(RAW_SHA),"INCOMPLETE_ORIGINAL_RAW_SET")
        return receipt,early,restored


def load_v12_index(path):
    demand(path.is_file() and not path.is_symlink() and
           sha(path.read_bytes())==V12_HASH_INDEX_SHA,
           "V12_PUBLIC_INDEX_SHA_MISMATCH")
    index=json.loads(path.read_bytes())
    demand(index["executed_product_head"]==V12_SOURCE and
           index["hosted_run"]==43657058944 and
           index["contains_original_18d_observations"] is False and
           len(index["worlds"])==48 and len(index["trajectories"])==144,
           "V12_PINNED_PUBLIC_INDEX_BAD")
    return {row["seed"]:row["world_hash"] for row in index["worlds"]}


def transition_contract(event):
    obs=event["observation"]
    nxt=event["next_observation"]
    action=event["action"]
    mask=event["mask"]
    demand(len(obs)==len(nxt)==18 and
           all(type(x) in (int,float) and math.isfinite(x) for x in obs+nxt) and
           mask==public_mask(obs) and
           type(action) is int and 0<=action<7 and mask[action]==1 and
           type(event["cost"]) is int and event["cost"] in (0,1) and
           type(event["done"]) is bool and
           type(event["success_info"]) is bool and
           type(event["contacts_cumulative"]) is int and
           type(event["dwell_ticks_cumulative"]) is int and
           type(event["dwell_ticks_current"]) is int,
           "UNSAFE_EVIDENCE_PUBLIC_ACTION_MASK_OR_STATE_INVALID")


def validate_branches_and_journal(full_rows,journal_rows,v12_worlds):
    demand(len(full_rows)==23 and len(journal_rows)==394,
           "INCOMPLETE_OR_FORGED_BRANCH_OPTION_COUNT")
    groups=defaultdict(list)
    for item in journal_rows:
        groups[item["branchId"]].append(item)
    demand(len(groups)==23,"ORIGINAL_BRANCH_JOURNAL_MAPPING_BAD")
    traces=[]
    costs=[]
    branch_worlds=set()
    branches=[]
    for idx,(name,items) in enumerate(groups.items()):
        row=full_rows[idx]
        events=row["transitions"]
        seed=row["seed"]
        demand(row["branch_id"]==idx and seed in v12_worlds and
               len(events)==len(items)>0 and
               [x["action"] for x in events]==row["actions"] and
               all(x["seed"]==seed and x["branchId"]==name and
                   x["sourceWorldHash"]==v12_worlds[seed] for x in items) and
               0<=row["source_prefix"]<=len(events),
               "ORIGINAL_BRANCH_JOURNAL_MAPPING_BAD")
        branch_worlds.add(seed)
        prev_contacts=0
        prev_dwell=0
        option_hashes=[]
        for option,(event,item) in enumerate(zip(events,items)):
            transition_contract(event)
            digest=sha(canonical(event))
            demand(item["optionIndexZeroBased"]==option and
                   item["forkOptionIndexZeroBased"]==row["source_prefix"] and
                   item["phase"]==("ORIGINAL_PREFIX" if
                                      option<row["source_prefix"] else "COUNTERFACTUAL") and
                   item["transition"]==event and item["transitionSha256"]==digest and
                   item["sourceOnlyUnattestedExecution"] is True and
                   item["physicsQualificationPending"] is True and
                   event["contacts_cumulative"]>=prev_contacts and
                   event["dwell_ticks_cumulative"]>=prev_dwell,
                   "ORIGINAL_394_JOURNAL_HASH_OR_ORDER_BAD")
            if option:
                prior=events[option-1]["next_observation"]
                demand(all(abs(a-b)<1e-5 for a,b in zip(prior,event["observation"])),
                       "ORIGINAL_BRANCH_PUBLIC_OBSERVATION_CHAIN_BAD")
            prev_contacts=event["contacts_cumulative"]
            prev_dwell=event["dwell_ticks_cumulative"]
            option_hashes.append(digest)
            if event["cost"]:
                costs.append(dict(seed=seed,branch_id=idx,branch_name=name,
                                  option_index_zero_based=option,action=event["action"],
                                  mask=event["mask"],cost=event["cost"],done=event["done"],
                                  transition_sha256=digest))
        traces.extend(option_hashes)
        branches.append(dict(branch_id=idx,branch_name=name,seed=seed,
                             source_world_hash=v12_worlds[seed],
                             source_prefix=row["source_prefix"],
                             original_option_count=len(events),
                             full_transitions_sha256=sha(canonical(events)),
                             option_transition_sha256=option_hashes))
    demand(len(traces)==394 and branch_worlds=={518003,518006} and
           sum(int(item["transition"]["done"]) for item in journal_rows)==1 and
           all(item["transition"]["success_info"] is False for item in journal_rows),
           "ORIGINAL_394_TRANSITIONS_OR_TWO_WORLD_COUNT_BAD")
    expected_unsafe=dict(seed=518006,branch_id=22,
                         branch_name="v13-seen-train-518006-16",
                         option_index_zero_based=37,action=2,mask=[1]*7,
                         cost=1,done=True,transition_sha256=UNSAFE_HASH)
    demand(costs==[expected_unsafe] and
           sum(1 for x in journal_rows if x["transition"]["cost"]==0)==393,
           "EXACT_SOLE_PHYSICS_UNSAFE_EVIDENCE_MISMATCH")
    return branches,expected_unsafe


def audit(archive,v12_index_path,claim="safety-negative"):
    demand(claim in ("safety-negative","efficacy"),"UNKNOWN_CLAIM_MODE")
    receipt,early,raw=original_bytes(archive)
    v12_worlds=load_v12_index(v12_index_path)
    training=json.loads(raw["partial_training.json"])
    demand(training["status"]=="INCOMPLETE_STOP" and
           training["allWorldsComplete"] is False and
           training["hardStopReason"]=="V13_REAL_PHYSICS_UNSAFE" and
           training["executed_head"]==SOURCE and training["harness_head"]==HARNESS and
           training["source_v12_head"]==V12_SOURCE and
           training["sourceOriginalHead"]==V12_SOURCE and
           training["sourceV12RawSha256"]["full_transitions.jsonl.gz"]==
                "7e8d7c80cb8d035d904338e1a544662181a93933cc5c324458f7195c56f90b91" and
           training["source_mode"]=="REGENERATED_ALL144_AUDITED_TRACE_PINS" and
           training["recorded_branches"]==early["recorded_branches"]==23 and
           training["recorded_real_options"]==early["recorded_real_options"]==394 and
           training["durably_journaled_all_executed_option_events"]==394 and
           training["originalSeenTrainWorldCount"]==48 and
           training["trainingOnly"] is True and training["training_only"] is True and
           training["devCalTestOodOpened"] is False and
           training["dev_cal_test_ood_opened"] is False and
           training["model_promotion_authorized"] is False and
           training["modelPromotionAuthorized"] is False and
           training["novel_prospective_goal_claim"] is False and
           training["no_automatic_retry_or_seed_fishing"] is True and
           training["new_real_mujoco_performed"] is True and
           len(training["worldResults"])==2 and
           [(row["seed"],row["status"],row["executedBudgetBranches"])
            for row in training["worldResults"]]==[
                (518003,"NONE_REACHABLE_WITHIN_FINITE_BUDGET",6),
                (518006,"SAFETY_STOP",17)] and
           all(row["actual250TickWitnessTraceSha256"] is None and
               row["notProofOfGlobalUnreachability"] is True
               for row in training["worldResults"]),
           "V13_INCOMPLETE_TRAIN_SOURCE_OR_EFFICACY_SEAL_CHANGED")
    full=[json.loads(line) for line in gzip.decompress(
          raw["full_transitions.jsonl.gz"]).splitlines()]
    journal=[json.loads(line) for line in gzip.decompress(
          raw["option_journal.jsonl.gz"]).splitlines()]
    branches,unsafe=validate_branches_and_journal(full,journal,v12_worlds)
    # A genuine unsafe observation from a failed, incomplete run is valid
    # safety-negative evidence. It is categorically NOT an efficacy qualification.
    classify_original_claim(training["status"],claim)
    return {
        "schema":SCHEMA,
        "hosted_run":RUN,"artifact_id":ARTIFACT,
        "original_zip_sha256":ZIP_SHA,
        "executed_product_head":SOURCE,"executed_harness_head":HARNESS,
        "pinned_original_v12_source_head":V12_SOURCE,
        "pinned_original_v12_public_trace_index_sha256":V12_HASH_INDEX_SHA,
        "original_raw_sha256":RAW_SHA,
        "status":"INCOMPLETE_STOP","safety_decision":"STOP_UNSAFE",
        "efficacy_qualified":False,"model_promotion_authorized":False,
        "source_reported_original_physics":True,
        "independent_new_physics_replay_performed":False,
        "provider_signed_attestation":False,"actual_provider_cost_known":False,
        "unsafe_hazard_causal_category":"UNKNOWN",
        "opened_dev_cal_test_ood":False,
        "distinct_source_train_worlds":2,
        "branch_rollouts":23,"original_recorded_options":394,
        "safe_recorded_prior_options":393,"unsafe_events":1,
        "unsafe_terminal":unsafe,
        "branches":branches,
    }


def check_manifest(path,result):
    demand(path.is_file() and not path.is_symlink() and
           path.read_bytes()==canonical(result)+b"\n",
           "PINNED_UNSAFE_HASH_ONLY_MANIFEST_MISMATCH")


def classify_original_claim(status,claim):
    demand(claim in ("safety-negative","efficacy"),"UNKNOWN_CLAIM_MODE")
    demand(status=="INCOMPLETE_STOP","UNEXPECTED_ORIGINAL_STATUS")
    demand(claim!="efficacy","INCOMPLETE_STOP_CANNOT_QUALIFY_EFFICACY")
    return "STOP_UNSAFE"


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("original_zip",type=Path)
    p.add_argument("--v12-index",type=Path,default=V12_INDEX_DEFAULT)
    p.add_argument("--claim",choices=("safety-negative","efficacy"),default="safety-negative")
    p.add_argument("--verify-manifest",type=Path)
    p.add_argument("--write-manifest",type=Path,
                   help="new exclusive output outside original evidence; never overwrite")
    args=p.parse_args()
    result=audit(args.original_zip,args.v12_index,args.claim)
    data=canonical(result)+b"\n"
    if args.verify_manifest:
        check_manifest(args.verify_manifest,result)
    if args.write_manifest:
        target=args.write_manifest
        demand(not target.is_symlink() and
               target.resolve()!=args.original_zip.resolve(),
               "DO_NOT_OVERWRITE_ORIGINAL_ZIP")
        with target.open("xb") as output:
            output.write(data)
    print(json.dumps({k:result[k] for k in
                     ("status","safety_decision","efficacy_qualified",
                      "distinct_source_train_worlds","branch_rollouts",
                      "original_recorded_options","unsafe_events","unsafe_terminal")},
                     sort_keys=True))
    print("sha256_canonical_hash_only_manifest="+sha(data))
