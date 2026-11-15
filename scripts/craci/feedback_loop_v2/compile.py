#!/usr/bin/env python3
"""Read-only, source-pinned CRACI TRAIN→failure→next-experiment compiler.

This does not learn from legal-but-unchosen actions, promote a model, dispatch
provider jobs, open dev/cal/test/OOD, or change the seven-action physics.
Actual source-bound negative results are useful input to a future independent
TRAIN experiment, not an excuse to repeat failed evaluation cohorts.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

SCHEMA="junction.craci.source-bound-feedback-v2.v1"
PARENT_HEAD="3ddc0fcf8b13df0e2dc750c02d84fdb9f2fb76ad"
REPO="SalesSquad/junction-pets"
SOURCE={"v10":"9cc583d3f0f24484b79c1929ba875c7a3b667806",
        "v11":"ab6df4054ef6ed350b479469590a48046a0c0a68"}
RUN={"v10":43649224059,"v11":43653579339}
RAW_SHA={"v10":"739c30a13ecacdecd404774fc9dadd887944f32df5cef14cfd2758a639460419",
         "v11":"0a38081a43426ee4774d09d22886202aaf56d59f6b925a0a75cb2f2da14c848b"}

# Exact existing, independently audited source bytes at #186 PARENT_HEAD.
# Git blob identities bind all evidence; no self-attested alternate fixture.
PINNED_INPUTS={
  "v10_registry":("ops/experiments/runs/rokoko.v10.43649224059.science.json",
                  "4af1b63d58d2891c4003b1bdeade9d7a0853306a"),
  "v11_registry":("ops/experiments/runs/rokoko.v11.43653579339.science.json",
                  "e750b3f45ef26ba8dbadd6d9f1c1a75d60cf8315"),
  "action_support":("docs/craci/learning/rokoko-mujoco-v11-43653579339/action-support-v10-v11.json",
                    "0031aadfc793b0aea6d55e956a4a4e483c9d46cc"),
  "v10_readout":("docs/craci/learning/rokoko-mujoco-v10-43649224059/paired-readout.json",
                 "78ccc4bcb4ea04aebe94db2e84e3fa66f418c89c"),
  "v11_readout":("docs/craci/learning/rokoko-mujoco-v11-43653579339/paired-readout.json",
                 "30492fb6f06a1c37df635d9f1540683eea2f1f71"),
  "v11_qualification":("docs/craci/learning/rokoko-mujoco-v11-43653579339/independent-qualification.json",
                       "0d243e64eb32048e74c1f28dbfec613bbd3c8410"),
  "v11_integrity":("docs/craci/learning/rokoko-mujoco-v11-43653579339/source-integrity.json",
                   "b35ffc35d5699228918c0f3ab709a8d644bf24bb"),
  "v11_manifest":("docs/craci/learning/rokoko-mujoco-v11-43653579339/manifest.json",
                  "52f359a3ad2973355b1b485babcfbc2b420982f5"),
}
NEXT_TRAIN={
  "pilot":{"start":518000,"end":518511,"scan_seeds":512,
           "near":40,"clear":8,"arms":3,"paired_episodes":144},
  "independent_confirmation":{"start":518512,"end":519023,"scan_seeds":512,
           "near":128,"clear":32,"arms":2,"paired_episodes":320},
}
KNOWN_USED=[(512000,512511),(513000,513511),(514000,514511),
            (515000,515511),(516000,516511),(517000,517511)]
ACTION_NAMES=("ALIGN","PUSH_SLOW","PUSH_MEDIUM","SIDE_LEFT",
              "SIDE_RIGHT","RETREAT","ABSTAIN_TERMINAL")
SUPPORTED_WORLD_MIN=20
# Owner-authorized no-new-CRACI-admission margin before the global close.
ADMISSION_GUARD_MINUTES=31

class FeedbackStop(ValueError):
    pass

def demand(condition,code):
    if not condition:
        raise FeedbackStop(code)

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode("utf-8")

def sha256(data):
    return hashlib.sha256(data).hexdigest()

def git_blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def read_pinned(root):
    found={}
    provenance={}
    for label,(relative,expected_blob) in PINNED_INPUTS.items():
        path=root/relative
        demand(path.is_file() and not path.is_symlink(),
               "PINNED_EVIDENCE_MISSING_"+label.upper())
        raw=path.read_bytes()
        actual_blob=git_blob(raw)
        demand(actual_blob==expected_blob,"PINNED_EVIDENCE_BLOB_DRIFT_"+label.upper())
        found[label]=json.loads(raw)
        provenance[label]=dict(path=relative,git_blob_sha1=actual_blob,
                               file_sha256=sha256(raw))
    return found,provenance

def source_head(root,expected):
    demand(len(expected)==40 and all(c in "0123456789abcdef" for c in expected),
           "EXACT_COMPILER_HEAD_REQUIRED")
    try:
        head=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],
                                     text=True,timeout=15).strip()
        clean=subprocess.check_output(["git","-C",str(root),"status","--porcelain=v1",
                                       "--untracked-files=no"],text=True,timeout=15).strip()
        ancestry=subprocess.run(["git","-C",str(root),"merge-base","--is-ancestor",
                                 PARENT_HEAD,head],capture_output=True,timeout=15)
    except (OSError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
        raise FeedbackStop("EXACT_GIT_CHECK_UNAVAILABLE") from exc
    demand(head==expected,"COMPILER_HEAD_MISMATCH")
    demand(not clean,"DIRTY_TRACKED_SOURCE_OVERLAY")
    demand(ancestry.returncode==0,"COMPILER_PARENT_EVIDENCE_ANCESTRY_MISSING")
    return head

def registry_metrics(registry,version):
    demand(registry.get("status")=="succeeded" and
           registry.get("source",{}).get("repository")==REPO and
           registry["source"].get("commit")==SOURCE[version] and
           registry.get("projectId")=="rokoko" and
           registry.get("kind")=="synthetic-test" and
           registry.get("taskId")=="rokoko.mujoco-prospective-train" and
           registry.get("evidence",{}).get("level")=="source-reported" and
           len(registry["evidence"].get("receiptSha256",""))==64 and
           registry.get("dataset",{}).get("split")=="train" and
           registry["dataset"].get("sampleCount")==800 and
           registry["dataset"].get("sha256")==RAW_SHA[version] and
           registry.get("evaluation",{}).get("kind")=="train-only-prospective-physics" and
           registry["evaluation"].get("independentHoldout") is False and
           registry.get("policySha256") is None,
           "REGISTRY_SOURCE_TRAIN_PROVENANCE_BAD_"+version.upper())
    demand(str(RUN[version]) in registry["evidence"].get("ref",""),
           "REGISTRY_WRONG_HOSTED_RUN_"+version.upper())
    result={}
    for metric in registry["metrics"]:
        k=metric["id"]
        demand(k not in result,"DUPLICATE_REGISTRY_METRIC_"+k)
        result[k]=metric["value"]
    return result

def metric(metrics,name):
    value=metrics.get(name)
    demand(type(value) is int and value>=0,"MISSING_OR_NONINTEGER_GOAL_METRIC_"+name)
    return value

def verify_proofs(d,m10,m11):
    r10=d["v10_readout"]
    r11=d["v11_readout"]
    q=d["v11_qualification"]
    i=d["v11_integrity"]
    manifest=d["v11_manifest"]
    demand(r10.get("executed_head")==SOURCE["v10"] and
           r10.get("dev_cal_test_ood_opened") is False and
           r10.get("model_promotion_authorized") is False and
           len(r10.get("near_seeds",[]))==128 and len(r10.get("clear_seeds",[]))==32 and
           len(set(r10["near_seeds"]+r10["clear_seeds"]))==160 and
           all(515000<=s<=515511 for s in r10["near_seeds"]+r10["clear_seeds"]),
           "V10_PUBLIC_TRAIN_COHORT_OR_SEAL_BROKEN")
    demand(r11.get("dev_cal_test_ood_opened") is False and
           r11.get("new_model_promotion_authorized") is False and
           r11.get("physical_goal250_tick_dwell_primary") is True,
           "V11_GOAL250_OR_SEAL_BROKEN")
    demand(q.get("experiment_complete") is True and
           q.get("independent_full_trace_public_mask_replay") is True and
           q.get("all_512_real_initial_worlds_replayed") is True and
           q.get("dev_cal_test_ood_opened") is False and
           q.get("independentHoldout") is False and
           q.get("promotion_authorized") is False and
           q.get("model_improvement_verified") is False and
           q.get("exact_source_sha")==SOURCE["v11"] and
           q.get("train_only_seed_start")==517000 and
           q.get("selected_near_worlds")==128 and
           q.get("selected_clear_worlds")==32 and
           q.get("trials")==800 and
           q.get("actual_real_option_transitions")==34992 and
           q.get("independent_true_physics_positive_replay",{}).get("claim_verified") is True and
           q.get("independent_true_physics_clear_goal_replay",{}).get("claim_verified") is True and
           manifest.get("executed_head")==SOURCE["v11"] and
           manifest.get("training_only") is True and
           manifest.get("dev_cal_test_ood_opened") is False and
           manifest.get("model_promotion_authorized") is False and
           manifest.get("file_sha256",{}).get("full_transitions.jsonl.gz")==RAW_SHA["v11"] and
           i.get("source_head")==SOURCE["v11"] and
           i.get("promotion_authorized") is False,
           "V11_INDEPENDENT_PROOF_OR_GOAL250_SEAL_BROKEN")
    demand(manifest["file_sha256"]==q["original_three_files_sha256"]==
           i["original_sha256"] and
           i["real_source_options"]==q["actual_real_option_transitions"] and
           q["dataset_sha256"]==d["v11_registry"]["dataset"]["sampleSetSha256"],
           "ORIGINAL_MANIFEST_PROOF_SHA_CROSSCHECK_BAD")
    for arm,source,version,metric_name in [
        ("frozen_v5",r10["strategies"],"v10","frozen-v5-safe-goals-total"),
        ("v10_loss_informed",r10["strategies"],"v10","v10-safe-goals-total"),
        ("frozen_v5",r11["strategies"],"v11","frozen-v5-safe-goals-total"),
        ("v11_goal_preserving",r11["strategies"],"v11","v11-safe-goals-total")]:
        count_key="safe_goals" if version=="v11" else "safe_goals_all"
        m=m10 if version=="v10" else m11
        demand(source[arm][count_key]==metric(m,metric_name),
               "REGISTRY_VS_RAW_DERIVED_GOAL_COUNT_"+version.upper()+"_"+arm)
    demand(len(r11["novel_v11_safe_goal_seed_ids"])==
           metric(m11,"v11-novel-safe-goals-vs-frozen-v5") and
           len(r11["lost_frozen_v5_goal_seed_ids"])==
           metric(m11,"v11-lost-frozen-v5-safe-goals") and
           len(r11["unsafe_v11_seed_ids"])==metric(m11,"v11-unsafe-trials") and
           q["novel_v11_safe_goal_seed_ids"]==r11["novel_v11_safe_goal_seed_ids"] and
           q["lost_v5_goal_seed_ids"]==r11["lost_frozen_v5_goal_seed_ids"] and
           i["novel_v11_goals"]==r11["novel_v11_safe_goal_seed_ids"] and
           i["lost_v5_goals"]==r11["lost_frozen_v5_goal_seed_ids"] and
           i["new_unsafe"]==r11["unsafe_v11_seed_ids"] and
           i["safe_v5_goals"]==metric(m11,"frozen-v5-safe-goals-total") and
           i["safe_v11_goals"]==metric(m11,"v11-safe-goals-total"),
           "V11_NOVEL_LOST_UNSAFE_PAIRS_MISMATCH")
    demand(metric(m10,"v10-novel-safe-goals-vs-frozen-v5")==0 and
           len(r10["novel_v10_safe_near_goal_seeds"])==0 and
           metric(m10,"v10-lost-frozen-v5-safe-goals")>=len(r10["lost_baseline_safe_near_goal_seeds"]),
           "V10_NEGATIVE_PAIR_PROOF_MISMATCH")

def verify_action_support(d,m10,m11):
    support=d["action_support"]
    demand(support.get("publicObservationDimensions")==18 and
           support.get("shieldedActionCount")==7 and
           [(a["id"],a["name"]) for a in support["actions"]]==list(enumerate(ACTION_NAMES)),
           "PUBLIC_18D_SEVEN_MASK_CONTRACT_DRIFT")
    sources=support.get("sources",[])
    demand({x.get("version") for x in sources}=={"v10","v11"} and len(sources)==2,
           "ORIGINAL_ACTION_SUPPORT_SOURCES_INCOMPLETE")
    summed={k:[0]*7 for k in ("executedPerAction","maskLegalPerAction",
                              "distinctWorldsWithExecutedAction")}
    for entry in sources:
        ver=entry["version"]
        metrics=m10 if ver=="v10" else m11
        demand(entry.get("githubRun")==RUN[ver] and
               entry.get("sourceSha")==SOURCE[ver] and
               entry.get("originalTransitionsSha256")==RAW_SHA[ver] and
               entry.get("pairedTrainWorlds")==160 and entry.get("episodes")==800 and
               entry.get("optionEvents")==metric(metrics,"independently-verified-public-mask-transitions"),
               "SOURCE_BOUND_EXECUTED_SUPPORT_DRIFT_"+ver.upper())
        for key in (*summed,"distinctEpisodesWithExecutedAction"):
            array=entry.get(key)
            demand(isinstance(array,list) and len(array)==7 and
                   all(type(n) is int and 0<=n<=entry["optionEvents"] for n in array),
                   "INVALID_SEVEN_ACTION_SUPPORT_"+ver.upper()+"_"+key)
        demand(sum(entry["executedPerAction"])==entry["optionEvents"] and
               all(entry["executedPerAction"][a]<=entry["maskLegalPerAction"][a]
                   for a in range(7)) and
               all(n<=160 for n in entry["distinctWorldsWithExecutedAction"]) and
               all(n<=800 for n in entry["distinctEpisodesWithExecutedAction"]),
               "ACTION_SUPPORT_COUNTER_EXCEEDS_PHYSICS_"+ver.upper())
        for key in summed:
            summed[key]=[a+b for a,b in zip(summed[key],entry[key])]
    c=support.get("combined",{})
    demand(c.get("optionEvents")==sum(summed["executedPerAction"])==73561 and
           c.get("sideLeftExecuted")==summed["executedPerAction"][3] and
           c.get("sideRightExecuted")==summed["executedPerAction"][4] and
           c.get("sideRightMaskLegal")==summed["maskLegalPerAction"][4] and
           c.get("sideRightDistinctWorlds")==summed["distinctWorldsWithExecutedAction"][4],
           "COMBINED_ORIGINAL_ACTION_SUPPORT_TAMPERED")
    return sources,summed

def raw_support(gzip_path,sha_expected):
    demand(gzip_path.is_file() and not gzip_path.is_symlink(),"ORIGINAL_FULL_GZIP_MISSING")
    demand(sha256(gzip_path.read_bytes())==sha_expected,
           "ORIGINAL_COMPRESSED_TRANSITIONS_HASH_MISMATCH")
    executed=[0]*7
    legal=[0]*7
    worlds=[set() for _ in range(7)]
    episodes=[set() for _ in range(7)]
    keys=set()
    option_count=0
    with gzip.open(gzip_path,"rt",encoding="utf-8") as source:
        for line in source:
            trial=json.loads(line)
            seed,strategy=trial["seed"],trial["strategy"]
            key=(seed,strategy)
            demand(key not in keys and isinstance(seed,int) and
                   isinstance(strategy,str) and strategy,
                   "ORIGINAL_RAW_TRIAL_DUPLICATE_OR_INVALID")
            keys.add(key)
            events=trial["transitions"]
            demand(isinstance(events,list) and 1<=len(events)<=60,
                   "ORIGINAL_RAW_OPTIONS_MISSING")
            for ev in events:
                obs,mask=ev["observation"],ev["mask"]
                action=ev["action"]
                demand(len(obs)==18 and len(ev["next_observation"])==18 and
                       len(mask)==7 and all(x in (0,1,True,False) for x in mask) and
                       type(action) is int and 0<=action<7 and bool(mask[action]) and
                       ev["cost"] in (0,1) and isinstance(ev["done"],bool),
                       "ORIGINAL_RAW_PUBLIC_MASK_OR_18D_CORRUPT")
                executed[action]+=1
                worlds[action].add(seed)
                episodes[action].add(key)
                for a in range(7):
                    legal[a]+=int(bool(mask[a]))
                option_count+=1
    return dict(optionEvents=option_count,episodes=len(keys),
                pairedTrainWorlds=len({seed for seed,_ in keys}),
                executedPerAction=executed,maskLegalPerAction=legal,
                distinctWorldsWithExecutedAction=[len(x) for x in worlds],
                distinctEpisodesWithExecutedAction=[len(x) for x in episodes],
                seed_ids=sorted({seed for seed,_ in keys}))

def verify_original_raw(sources,raw_paths):
    if not raw_paths:
        return dict(reverified_here=False,source_bound_previous_audit_only=True)
    demand(set(raw_paths)=={"v10","v11"},"BOTH_ORIGINAL_GZIP_STREAMS_REQUIRED")
    all_seeds={}
    for s in sources:
        ver=s["version"]
        counts=raw_support(raw_paths[ver],RAW_SHA[ver])
        for key in ("optionEvents","episodes","pairedTrainWorlds","executedPerAction",
                    "maskLegalPerAction","distinctWorldsWithExecutedAction",
                    "distinctEpisodesWithExecutedAction"):
            demand(counts[key]==s[key],"FULL_RAW_SUPPORT_AGGREGATE_MISMATCH_"+ver.upper()+"_"+key)
        bounds=(515000,515511) if ver=="v10" else (517000,517511)
        demand(all(bounds[0]<=seed<=bounds[1] for seed in counts["seed_ids"]),
               "ORIGINAL_RAW_TRAIN_COHORT_OUT_OF_BOUNDS_"+ver.upper())
        all_seeds[ver]=set(counts["seed_ids"])
    demand(all_seeds["v10"].isdisjoint(all_seeds["v11"]),
           "V10_V11_RAW_WORLD_OVERLAP")
    return dict(reverified_here=True,source_bound_previous_audit_only=False,
                original_full_gzip_sha256=RAW_SHA.copy())

def wilson(successes,n,z=1.96):
    if n==0:
        return [0.,1.]
    p=successes/n
    d=1+z*z/n
    c=(p+z*z/(2*n))/d
    h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [round(max(0.,c-h),6),round(min(1.,c+h),6)]

def action_support_summary(summed):
    total_worlds=320  # confirmed disjoint V10 and V11 TRAIN cohorts
    result=[]
    for a,name in enumerate(ACTION_NAMES):
        worlds=summed["distinctWorldsWithExecutedAction"][a]
        result.append(dict(action=a,name=name,
            executed_events=summed["executedPerAction"][a],
            legal_mask_events=summed["maskLegalPerAction"][a],
            independent_train_worlds_executing=worlds,
            world_execution_coverage=round(worlds/total_worlds,6),
            wilson95_world_execution_coverage=wilson(worlds,total_worlds),
            train_support_status=("TERMINAL_ABSTAIN_NOT_PHYSICAL_ACTION" if a==6 else
                "UNTRAINED_INSUFFICIENT_DISTINCT_EXECUTED_WORLDS"
                    if worlds<SUPPORTED_WORLD_MIN else
                "DESCRIPTIVE_EXECUTED_SUPPORT_ONLY"),
            legal_not_an_unchosen_action_reward_label=True))
    return result

def parse_utc(value):
    try:
        parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
    except (ValueError,TypeError) as exc:
        raise FeedbackStop("INVALID_CREDIT_CUTOFF_UTC") from exc
    demand(parsed.tzinfo is not None,"UTC_CUTOFF_TIMEZONE_REQUIRED")
    return parsed.astimezone(timezone.utc)

def check_next_ranges(ledger):
    future=[NEXT_TRAIN["pilot"],NEXT_TRAIN["independent_confirmation"]]
    demand(all(120000<=x["start"]<=x["end"]<520000 for x in future) and
           future[0]["end"]<future[1]["start"],
           "FROZEN_ENV_SEED_DOMAIN_OR_FUTURE_COHORT_OVERLAP")
    for obj in ledger:
        demand(type(obj) is dict and type(obj.get("start")) is int and
               type(obj.get("end")) is int and obj["start"]<=obj["end"] and
               obj.get("split")=="train" and obj.get("verified") is True,
               "UNVERIFIED_OR_UNBOUNDED_COHORT_LEDGER")
        for row in future:
            demand(row["end"]<obj["start"] or row["start"]>obj["end"],
                   "PROPOSED_FRESH_TRAIN_COHORT_ALREADY_USED")
    for start,end in KNOWN_USED:
        for row in future:
            demand(row["end"]<start or row["start"]>end,
                   "KNOWN_PRIOR_TRAIN_COHORT_REUSE")
    return True

def compile_feedback(d,provenance,*,candidate="v11",raw_evidence=None,
                     ledger=(),credit_cutoff=None,clock=None):
    demand(candidate in ("v10","v11"),"UNKNOWN_CANDIDATE_VERSION")
    m10=registry_metrics(d["v10_registry"],"v10")
    m11=registry_metrics(d["v11_registry"],"v11")
    verify_proofs(d,m10,m11)
    originals,summed=verify_action_support(d,m10,m11)
    raw=verify_original_raw(originals,raw_evidence)
    check_next_ranges(ledger)
    if credit_cutoff is not None:
        cutoff=parse_utc(credit_cutoff)
        now=parse_utc(clock) if clock else datetime.now(timezone.utc)
        demand(now<cutoff,"CREDIT_WINDOW_EXPIRED_NO_NEW_DISPATCH")
        demand(now<cutoff-timedelta(minutes=ADMISSION_GUARD_MINUTES),
               "CREDIT_WINDOW_31MIN_ADMISSION_STOP_NO_NEW_DISPATCH")
    metrics=m10 if candidate=="v10" else m11
    baseline=metric(metrics,"frozen-v5-safe-goals-total")
    candidate_name="v10" if candidate=="v10" else "v11"
    won=metric(metrics,candidate_name+"-safe-goals-total")
    novel=metric(metrics,candidate_name+"-novel-safe-goals-vs-frozen-v5")
    lost=metric(metrics,candidate_name+"-lost-frozen-v5-safe-goals")
    unsafe=metric(metrics,candidate_name+"-unsafe-trials")
    demand(won==baseline+novel-lost,"PAIRED_GOAL250_ARITHMETIC_OR_SOURCE_DRIFT")
    support=action_support_summary(summed)
    unsupported=[row["action"] for row in support if row["action"]!=6 and
                 row["train_support_status"].startswith("UNTRAINED")]
    if lost or unsafe:
        decision="STOP"
        reason=["BASELINE_GOAL250_LOSS" if lost else ""]+(
            ["UNSAFE_CANDIDATE_TRIAL"] if unsafe else [])
        reason=[r for r in reason if r]
    elif novel:
        if raw["reverified_here"]:
            decision="INDEPENDENT_TRAIN_CONFIRMATION"
            reason=["NOVEL_SAFE_GOAL250_ON_TRAIN_NO_LOSS_NO_UNSAFE",
                    "NOT_HOLDOUT_NO_MODEL_PROMOTION"]
        else:
            decision="NO_PROMOTION"
            reason=["NOVEL_GOAL_CLAIM_REQUIRES_ORIGINAL_RAW_RECHECK"]
    elif unsupported:
        decision="TRAIN_MORE_FOR_UNSUPPORTED_ACTION"
        reason=["ZERO_NOVEL_GOAL250_ON_TRAIN",
                "ACTUAL_ACTION_SUPPORT_MISSING_FOR_"+",".join(map(str,unsupported))]
    else:
        decision="NO_PROMOTION"
        reason=["ZERO_NOVEL_GOAL250_ON_TRAIN"]
    return dict(schema=SCHEMA,decision=decision,reasons=reason,
        source_integrator_parent=PARENT_HEAD,
        verified_inputs=provenance,source_runs={
          "v10":{"source":SOURCE["v10"],"run":RUN["v10"],"raw_sha256":RAW_SHA["v10"]},
          "v11":{"source":SOURCE["v11"],"run":RUN["v11"],"raw_sha256":RAW_SHA["v11"]}},
        candidate_version=candidate,goal_definition="safe contact + >=250 consecutive MuJoCo goal-dwell ticks",
        paired_goal250=dict(baseline_safe_goals=baseline,candidate_safe_goals=won,
                            novel=novel,lost=lost,unsafe=unsafe,paired_worlds=160),
        action_support=support,action_support_interpretation=(
          "Executed actions and distinct training worlds only; mask-legal actions "
          "are NOT counterfactual reward/outcome labels."),
        raw_reverification=raw,
        next_experiment=dict(type="ADVISORY_TRAIN_ONLY_FRESH_SEED_COHORT",
          pilot=NEXT_TRAIN["pilot"],independent_confirmation=NEXT_TRAIN["independent_confirmation"],
          requires_independent_source_review=True,
          requires_revalidated_fresh_cohort_ledger_at_dispatch=True,
          requires_current_credit_window_and_budget_admission=True,
          no_auto_craci_dispatch=True,no_auto_model_promotion=True,
          preserve_frozen_v5=True,forbid_dev_cal_test_ood=True,
          next_hypothesis=("Acquire right-action observations only where original "
                           "7-action mask permits, protect frozen V5 true goal250 "
                           "wins, stop at first new unsafe or baseline loss.")),
        sealed_splits_unopened=True,verified_independent_holdout=False,
        provider_attestation_verified=False,actual_spend_unknown=True,
        model_promotion_authorized=False,job_dispatch_authorized=False)

def parse_args(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode",required=True,choices=["compile"])
    p.add_argument("--require-git",action="store_true")
    p.add_argument("--expected-head",required=True)
    p.add_argument("--repo-root",type=Path,default=Path.cwd())
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--candidate",choices=["v10","v11"],default="v11")
    p.add_argument("--v10-raw-gz",type=Path)
    p.add_argument("--v11-raw-gz",type=Path)
    p.add_argument("--used-seed-ledger",type=Path)
    p.add_argument("--credit-cutoff-utc")
    p.add_argument("--at-utc")
    return p.parse_args(argv)

def write_new(path,value):
    with path.open("x",encoding="utf-8") as f:
        f.write(canonical(value).decode()+"\n")

def main(argv=None):
    args=parse_args(argv)
    out=args.output_dir
    demand(not out.is_symlink(),"OUTPUT_SYMLINK_REFUSED")
    out.mkdir(parents=True,exist_ok=True,mode=0o700)
    demand(not any(out.iterdir()),"OUTPUT_MUST_BE_EMPTY")
    provenance={}
    try:
        demand(args.require_git,"SOURCE_GIT_IDENTITY_REQUIRED")
        exact=source_head(args.repo_root,args.expected_head)
        inputs,provenance=read_pinned(args.repo_root)
        raw_paths={}
        if args.v10_raw_gz:raw_paths["v10"]=args.v10_raw_gz
        if args.v11_raw_gz:raw_paths["v11"]=args.v11_raw_gz
        ledger=json.loads(args.used_seed_ledger.read_text()) if args.used_seed_ledger else []
        demand(isinstance(ledger,list),"COHORT_LEDGER_MUST_BE_ARRAY")
        record=compile_feedback(inputs,provenance,candidate=args.candidate,
                                raw_evidence=raw_paths,ledger=ledger,
                                credit_cutoff=args.credit_cutoff_utc,clock=args.at_utc)
        record["executed_head"]=exact
        # A scientifically honest STOP is not an execution PASS even when
        # its original source evidence was fully verified (e.g. V10 lost 11
        # true V5 goal250 wins). Persist the receipt but exit nonzero.
        valid=record["decision"]!="STOP"
    except (FeedbackStop,FileNotFoundError,KeyError,TypeError,ValueError,
            json.JSONDecodeError,UnicodeDecodeError,gzip.BadGzipFile) as exc:
        record=dict(schema=SCHEMA,decision="STOP",reasons=[str(exc)],
                    executed_head=args.expected_head,
                    verified_inputs=provenance,
                    model_promotion_authorized=False,job_dispatch_authorized=False,
                    sealed_splits_unopened="UNVERIFIED",
                    actual_spend_unknown=True)
        valid=False
    write_new(out/"feedback.json",record)
    write_new(out/"manifest.json",dict(schema=SCHEMA+".manifest",
        feedback_sha256=sha256((out/"feedback.json").read_bytes()),
        exact_input_blobs={key:value["git_blob_sha1"] for key,value in provenance.items()},
        source_compiler_expected_head=args.expected_head,
        requires_external_independent_review=True,dispatch_authorized=False))
    print(json.dumps(dict(decision=record["decision"],
                          reasons=record["reasons"],
                          output=str(out),status="VALID" if valid else "STOP"),
                     sort_keys=True))
    return 0 if valid else 2

if __name__=="__main__":
    sys.exit(main())
