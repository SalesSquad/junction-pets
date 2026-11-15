#!/usr/bin/env python3
"""Future V11 517000+ 800-episode real MuJoCo TRAIN; NO implicit dispatch.

Reuses frozen original V8 physics, seven-option shield and frozen V5/V6/V8/V10
factories. Running requires an external, authorized CRACI harness with original
source-provenance qualifier and lossless collector. This source alone does not
qualify, pay for, or launch a CRACI job.
"""

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load_v11_policy_with_unique_module_identity():
    """Never reserve Python's generic `policy` name used by frozen V5.

    V6 -> V5 imports `from policy import BOUNDS...` during actual V7 physics
    initialization. Importing this V11 `policy.py` as a top-level module would
    populate sys.modules['policy'] and irreversibly redirect that frozen V5
    import to the wrong file, crashing before a single MuJoCo option executes.
    """
    source = HERE / "policy.py"
    spec = importlib.util.spec_from_file_location(
        "rokoko_v11_frozen_goal_rescue_policy", source)
    if spec is None or spec.loader is None:
        raise ImportError("V11_UNAMBIGUOUS_PRODUCT_POLICY_MODULE_REQUIRED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Keep the public `policy` variable for the existing qualification API, while
# leaving sys.modules['policy'] unoccupied for the original V5 policy module.
policy = load_v11_policy_with_unique_module_identity()

ORIGINAL_V10 = ROOT / "v10_prospective" / "run.py"
ORIGINAL_V10_BLOB = "64dc947d5dbf09e305a6034c4c5d146f14db820b"
SOURCE_V10_HEAD = "9cc583d3f0f24484b79c1929ba875c7a3b667806"
GATE_FILE = HERE / "frozen-v10-train-approved" / "gate.json"
PLAN_FILE = HERE / "frozen-v10-train-approved" / "next-train-plan.json"
PLAN_SHA = "3b4fc425c5f9af4ab2e28b2afcaeae62543ba08a3064406c4150b84c4d57f494"
FIRST = 517000
SCAN = 512
NEAR = 128
CLEAR = 32
ARMS = ("frozen_v5", "frozen_v6", "frozen_v8", "v10_loss_informed",
        "v11_goal_preserving")
SCHEMA = "junction.rokoko.v11.goal-first-fresh-train.v1"


def require(ok, why):
    if not ok: raise ValueError(why)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_plan():
    require(sha(PLAN_FILE) == PLAN_SHA, "V11_PROSPECTIVE_FROZEN_PROTOCOL_SHA_CHANGED")
    plan=json.loads(PLAN_FILE.read_bytes())
    require(plan["trainSeedRangeInclusive"]==[FIRST,FIRST+SCAN-1] and
            plan["pairedStrategies"]==list(ARMS) and
            plan["trainScanSeedsSha256"]==hashlib.sha256(json.dumps(
                list(range(FIRST,FIRST+SCAN)),sort_keys=True,separators=(",",":"),
                allow_nan=False).encode()).hexdigest() and
            plan["expectedEpisodesIfCohortComplete"]==800 and
            plan["candidateModelGateSha256"]==policy.GATE_SHA256 and
            plan["dispatchAuthorized"] is False and
            plan["modelPromotionAuthorized"] is False,
            "V11_PROSPECTIVE_COHORT_PROTOCOL_CHANGED")
    policy.load_frozen_gate(GATE_FILE)
    return plan


def derive_cohort(full_scan):
    """Independently derive 128+32 from *all 512* initial public 18D worlds.

    Neither label, reward, success, hidden simulated state nor policy outcome
    appears as a selection argument. World hash is retained only for same-world
    verification during later paired actual physics.
    """
    require(len(full_scan)==SCAN and
            [row["seed"] for row in full_scan]==list(range(FIRST,FIRST+SCAN)),
            "V11_PROSPECTIVE_ALL_512_PUBLIC_STARTS_REQUIRED")
    near=[];clear=[]
    for row in full_scan:
        obs,_=policy.validate_public_inputs(row["observation"], row["mask"])
        require(isinstance(row["world_hash"],str) and bool(row["world_hash"]),
                "V11_PROSPECTIVE_WORLD_ID_MISSING")
        chosen={"seed":row["seed"],"world_hash":row["world_hash"],
                "initial_observed_obstacle_y":obs[7],
                "observed_corridor":abs(obs[7])<.122}
        if chosen["observed_corridor"] and len(near)<NEAR:near.append(chosen)
        if not chosen["observed_corridor"] and len(clear)<CLEAR:clear.append(chosen)
    require(len(near)==NEAR and len(clear)==CLEAR and
            len({r["seed"] for r in [*near,*clear]})==NEAR+CLEAR,
            "V11_PROSPECTIVE_UNDERFILLED_DISJOINT_PUBLIC_COHORT")
    return sorted([*near,*clear],key=lambda row:row["seed"])


def readout(trials, cohort):
    pairs={}
    for row in trials:
        assert row["strategy"] in ARMS
        arms=pairs.setdefault(row["seed"],{})
        require(row["strategy"] not in arms,"V11_PROSPECTIVE_DUPLICATE_ARM")
        arms[row["strategy"]]=row
    require(set(pairs)=={w["seed"] for w in cohort} and
            all(set(a)==set(ARMS) and len({r["world_hash"] for r in a.values()})==1
                for a in pairs.values()),"V11_PROSPECTIVE_INCOMPLETE_PAIRED_TRIALS")
    safe=lambda r: bool(r["success"] and not r["unsafe"] and not r["abstained"])
    lost=sorted(seed for seed,p in pairs.items() if safe(p["frozen_v5"]) and
                not safe(p["v11_goal_preserving"]))
    novel=sorted(seed for seed,p in pairs.items() if safe(p["v11_goal_preserving"]) and
                 not safe(p["frozen_v5"]))
    newly_unsafe=sorted(seed for seed,p in pairs.items() if p["v11_goal_preserving"]["unsafe"])
    per_arm={name:{"safe_goals":sum(safe(p[name]) for p in pairs.values()),
                   "unsafe":sum(bool(p[name]["unsafe"]) for p in pairs.values()),
                   "near_safe_goals":sum(safe(p[name]) and p[name]["observed_corridor"]
                                         for p in pairs.values()),
                   "clear_safe_goals":sum(safe(p[name]) and not p[name]["observed_corridor"]
                                          for p in pairs.values())} for name in ARMS}
    go=(not lost and not newly_unsafe and bool(novel))
    return {"schema":SCHEMA+".readout","strategies":per_arm,
            "lost_frozen_v5_goal_seed_ids":lost,
            "novel_v11_safe_goal_seed_ids":novel,
            "unsafe_v11_seed_ids":newly_unsafe,
            "physical_goal250_tick_dwell_primary":True,
            "source_only_preliminary_training_gate":"CANDIDATE_FOR_INDEPENDENT_QUALIFICATION" if go else "NO_GO_LOST_GOAL_UNSAFE_OR_ZERO_NOVEL",
            "new_model_promotion_authorized":False,"dev_cal_test_ood_opened":False}


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode",choices=("prospective-train",),required=True)
    ap.add_argument("--require-git",action="store_true")
    ap.add_argument("--expected-head",required=True)
    ap.add_argument("--v10-weights",type=Path,required=True)
    ap.add_argument("--v8-weights",type=Path,required=True)
    ap.add_argument("--v8-training-receipt",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--time-budget-seconds",type=int,default=1800)
    args=ap.parse_args(argv)
    require(args.require_git and 60<=args.time_budget_seconds<=3600,
            "V11_PROSPECTIVE_GIT_FINITE_BUDGET_REQUIRED")
    load_plan()
    raw=ORIGINAL_V10.read_bytes()
    require(hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()==ORIGINAL_V10_BLOB,
            "V11_ORIGINAL_V10_REVIEWED_RUNNER_CHANGED")
    spec=importlib.util.spec_from_file_location("v11_import_verified_v10_physics",ORIGINAL_V10)
    require(spec is not None and spec.loader is not None,"V11_ORIGINAL_V10_IMPORT_INVALID")
    original=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    v8=original.v8
    head,checkout=v8.v8.source_identity(args.expected_head)
    original.verify_historical_source(checkout)
    require(subprocess.run(["git","-C",str(checkout),"merge-base","--is-ancestor",
                            SOURCE_V10_HEAD,"HEAD"],capture_output=True,timeout=15).returncode==0 and
            subprocess.run(["git","-C",str(checkout),"diff","--quiet",SOURCE_V10_HEAD,"HEAD",
                            "--",str(ORIGINAL_V10.relative_to(checkout))],
                           capture_output=True,timeout=15).returncode==0,
            "V11_PROSPECTIVE_UNREVIEWED_V10_LINEAGE_OR_RUNNER_DRIFT")
    paths=[p.resolve(strict=True) for p in (args.v10_weights,args.v8_weights,args.v8_training_receipt)]
    output=args.output_dir.resolve()
    require(not output.exists() and all(not p.is_relative_to(checkout) for p in paths) and
            not output.is_relative_to(checkout) and len(set(paths))==3,
            "V11_PRIVATE_EXCLUSIVE_NEW_ORIGINAL_OUTPUT_REQUIRED")
    require(v8.v8.file_sha256(paths[0])==original.V10_WEIGHTS_FILE_SHA256 and
            v8.v8.file_sha256(paths[1])==original.V8_WEIGHTS_FILE_SHA256,
            "V11_FROZEN_ORIGINAL_MODEL_SHA_DRIFT")
    v8weights,_,_=v8.verify_frozen_model(paths[1],paths[2],v8.FROZEN_WEIGHTS_SHA256)
    v10factory=original.v10.policy_factory(paths[0])
    # Source-bound runtime imports must never silently bind V11's product
    # policy to original V5's legacy `from policy` import.
    v5_policy_file=(ROOT/"v5_learning"/"policy.py").resolve()
    cached_v5_policy=sys.modules.get("policy")
    require(cached_v5_policy is None or
            Path(getattr(cached_v5_policy,"__file__","")).resolve()==v5_policy_file,
            "V11_GENERIC_POLICY_MODULE_ALREADY_POISONED")
    v7,Env=v8.import_v7_and_physics()
    original_v5_policy=sys.modules.get("policy")
    require(original_v5_policy is not None and
            Path(getattr(original_v5_policy,"__file__","")).resolve()==v5_policy_file,
            "V11_ORIGINAL_V5_POLICY_MODULE_IDENTITY_DRIFT")
    signature=v7.v6.v5.v4.v3.v2.v1._world_signature
    env=Env(max_options=v8.MAX_OPTIONS)
    full_scan=[]
    for seed in range(FIRST,FIRST+SCAN):
        obs=env.reset(seed=seed,ood=False)
        full_scan.append({"seed":seed,"world_hash":str(signature(env)),
                          "observation":obs.tolist(),"mask":env.mask(obs).astype(int).tolist()})
    cohort=derive_cohort(full_scan)
    factories={name:original.policy_factory(name,paths[0],v8weights,frozen_v7=v7)
               for name in ARMS if name!="v11_goal_preserving"}
    factories["v11_goal_preserving"]=policy.policy_factory(
        factories["frozen_v5"],v10factory,GATE_FILE)
    deadline=time.monotonic()+args.time_budget_seconds
    output.mkdir(parents=True,mode=0o700)
    trials=[]
    with gzip.open(output/"full_transitions.jsonl.gz","xt",encoding="utf8",newline="\n",compresslevel=6) as gz:
        for world in cohort:
            for arm in ARMS:
                require(time.monotonic()<deadline,"V11_PROSPECTIVE_PHYSICS_TIME_BUDGET_EXCEEDED")
                result,trace=v8.run_real_episode(env,world["seed"],arm,factories[arm],
                                                 signature,deadline,v7)
                require(result["world_hash"]==world["world_hash"],
                        "V11_PROSPECTIVE_PAIRED_WORLD_HASH_DRIFT")
                result.update(observed_corridor=world["observed_corridor"],
                              initial_observed_obstacle_y=world["initial_observed_obstacle_y"])
                trials.append(result)
                gz.write(v8.v8.canonical_bytes({"seed":world["seed"],"strategy":arm,
                                                "transitions":trace}).decode()+"\n")
    science=readout(trials,cohort)
    manifest={"schema":SCHEMA+".manifest","executed_head":head,
              "sourceV10Head":SOURCE_V10_HEAD,"originalV10RunnerBlob":ORIGINAL_V10_BLOB,
              "gateSha256":policy.GATE_SHA256,"planSha256":PLAN_SHA,
              "training_only":True,"model_promotion_authorized":False,
              "new_qualification_performed":False,"dev_cal_test_ood_opened":False,
              "actual_trials":len(trials),"actual_option_transitions":sum(r["full_transition_count"] for r in trials),
              "file_sha256":{},"source_sha256":{"prospective_train.py":sha(Path(__file__))}}
    training={"schema":SCHEMA+".training","producedAt":datetime.now(timezone.utc).isoformat(),
              "executed_head":head,"training_only":True,"actual_physics_engine":"mujoco-3.3.7",
              "all_512_public_initial_scans":full_scan,"cohort":cohort,
              "strategies":list(ARMS),"actual_trials":len(trials),
              "actual_option_transitions":manifest["actual_option_transitions"],
              "candidate_source_gate_sha256":policy.GATE_SHA256,
              "no_dev_test_ood":True,"model_promotion_authorized":False,"trials":trials}
    for name,obj in [("training.json",training),("paired-readout.json",science)]:
        with (output/name).open("xb") as target:
            target.write(v8.v8.canonical_bytes(obj)+b"\n")
    manifest["file_sha256"]={name:sha(output/name) for name in
                              ("training.json","full_transitions.jsonl.gz","paired-readout.json")}
    with (output/"manifest.json").open("xb") as target:
        target.write(v8.v8.canonical_bytes(manifest)+b"\n")
    print(json.dumps({"realMuJoCoTrials":len(trials),"realOptions":manifest["actual_option_transitions"],
                      "scienceGate":science["source_only_preliminary_training_gate"],
                      "fullOriginalRetainedPrivate":True,"requiresIndependentQualification":True,
                      "modelPromotionAuthorized":False},sort_keys=True))
    return 0


if __name__=="__main__":raise SystemExit(main())
