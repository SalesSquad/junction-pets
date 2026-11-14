#!/usr/bin/env python3
"""SHA-verify original CRACI TRAIN artifacts and export paired world results for R."""
import argparse
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

PINS = {
 "v10": dict(zipsha="c9bd2ae587d16111213ae7f3e142976d39575850605c312d66cc63ce5e125ccb",
    source="9cc583d3f0f24484b79c1929ba875c7a3b667806",
    harness="a64e6fcc73a1d47485fe052990e31c9d9e45100f",
    dataset="ac101715484383b1b5add91eeaac5e8f1f532de7a476aca1e53393c5686469c1",
    n=800, transitions=38569,
    arms=["frozen_v5","frozen_v6","repeat_left","frozen_v8","v10_loss_informed"],
    expected={"frozen_v5":37,"v10_loss_informed":26}),
 "hybrid": dict(zipsha="286f83c729303a7fe159d68ca494b94f51f685370ffff3e8578cefe62eaf5e0c",
    source="39f48031f7bff3970516a3c055efe47603e78be5",
    harness="e977ee1eb9c64a3be75b9967e8153f89a7772d76",
    dataset="57ae3dc1d8149f55f29e8d8758d66ff8a694c5ad597e059d6b4bee498bab533f",
    n=640, transitions=24167,
    arms=["frozen_v5","v8_hierarchical","near-early-side-mask-rescue","rescue_off_v5"],
    expected={"frozen_v5":30,"near-early-side-mask-rescue":30})
}
FIELDS=["seed","stratum","world_hash","strategy","safe_goal","unsafe",
        "success","dwell_ticks","abstained","forward_reopened_after_side",
        "full_transition_count"]

def check(condition, explanation):
    if not condition:
        raise ValueError(explanation)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def original(z, source):
    check(0 < source["original_bytes"] <= 30000000, "unbounded source")
    out=[]
    names=z.namelist()
    for i, part in enumerate(source["parts"]):
        check(part["archive"].endswith(".part%03d.zip" % i), "part order")
        hit=[p for p in names if p.endswith("/"+part["archive"])]
        check(len(hit)==1, "ambiguous archive part")
        blob=z.read(hit[0])
        check(len(blob)==part["archive_bytes"] and sha(blob)==part["archive_sha256"],"archive part SHA")
        with zipfile.ZipFile(io.BytesIO(blob)) as inner:
            check(inner.namelist()==[part["entry"]], "unexpected inner members")
            data=inner.read(part["entry"])
        check(len(data)==part["raw_bytes"] and sha(data)==part["raw_sha256"],"raw part SHA")
        out.append(data)
    full=b"".join(out)
    check(len(full)==source["original_bytes"] and sha(full)==source["original_sha256"],"original SHA")
    return full

def load_run(path, run):
    p=PINS[run]
    check(path.is_file() and sha(path.read_bytes())==p["zipsha"],run+" outer ZIP SHA")
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        receipt=json.loads(z.read("receipt.json"))
        binding=receipt["binding"]
        check(binding["sourceSha"]==p["source"] and binding["harnessSha"]==p["harness"],
              "source/harness CRACI receipt binding")
        check(receipt.get("providerAttestationVerified") is not True,
              "provider attestation semantics changed: review required")
        matched=[n for n in names if n.endswith("/retention-manifest.json")]
        check(len(matched)==1, "missing retention manifest")
        retention=json.loads(z.read(matched[0]))
        check(retention["exact_source_sha"]==p["source"], "retention source SHA")
        sources={s["name"]:s for s in retention["sources"]}
        check({"training.json","full_transitions.jsonl.gz"}<=set(sources), "missing original trace")
        training=json.loads(original(z,sources["training.json"]))
        original(z,sources["full_transitions.jsonl.gz"]) # SHA verified, not replayed
    checks={"executed_head":p["source"],
            "dataset_sha256":p["dataset"],"actual_trials":p["n"],
            "actual_transition_count":p["transitions"],
            "training_only":True,"dev_cal_test_ood_opened":False,
            "model_promotion_authorized":False}
    for key, expected in checks.items():
        check(training.get(key)==expected,run+" mismatch: "+key)
    if "original_public_observation_count" in training:
        check(training["original_public_observation_count"]==18,"observation ABI")
    if "original_seven_action_mask" in training:
        check(training["original_seven_action_mask"]==7,"action-mask ABI")
    check(training["actual_physics_engine"]=="mujoco-3.3.7","physics engine")
    check(training["strategies"]==p["arms"],"strategy/source drift")
    trials=training["trials"]
    check(len(trials)==p["n"],"trial count")
    near, clear=set(training["near_seeds"]),set(training["clear_seeds"])
    check(len(near)==128 and len(clear)==32 and not (near & clear),"world strata")
    worlds={w["seed"]:w["world_hash"] for w in training["cohort"]}
    check(len(worlds)==160 and set(worlds)==near|clear, "cohort/source mismatch")
    rows=[]; seen=set()
    for t in trials:
        s,a=t["seed"],t["strategy"]
        check(s in worlds and a in p["arms"] and (s,a) not in seen,"unpaired world")
        seen.add((s,a))
        check(t["world_hash"]==worlds[s], "world hash mismatch")
        for transition in t["transitions"]:
            check(len(transition["observation"])==18 and
                  len(transition["next_observation"])==18,"18D public observation")
            mask=transition["mask"]
            check(len(mask)==7 and all(type(bit) is int and bit in (0,1) for bit in mask),
                  "7-action original legal mask")
            action=transition["action"]
            check(type(action) is int and 0<=action<7 and mask[action]==1,
                  "illegal recorded action")
        check(type(t["success"]) is bool and type(t["unsafe"]) is bool,"goal/safety flag")
        dwell=t["dwell_ticks_final"]
        check(type(dwell) in (int,float) and dwell>=0,"dwell flag")
        goal=t["success"] and dwell>=250 and not t["unsafe"]
        if "safe_goal_dwell250" in t:
            check(type(t["safe_goal_dwell250"]) is bool and
                  t["safe_goal_dwell250"]==goal,"original goal flag mismatch")
        rows.append(dict(seed=s,stratum="near" if s in near else "clear",
                         world_hash=worlds[s],strategy=a,safe_goal=int(goal),
                         unsafe=int(t["unsafe"]),success=int(t["success"]),
                         dwell_ticks=dwell,abstained=int(t["abstained"]),
                         forward_reopened_after_side=int(t["forward_reopened_after_side"]>0),
                         full_transition_count=t["full_transition_count"]))
    check(len(seen)==p["n"],"missing world/strategy pairs")
    check(sum(r["full_transition_count"] for r in rows)==p["transitions"],"transition count")
    check(sum(r["unsafe"] for r in rows)==0,"unexpected unsafe trial")
    for arm, expect in p["expected"].items():
        check(sum(r["safe_goal"] for r in rows if r["strategy"]==arm)==expect,
              run+" source goal control: "+arm)
    proof=dict(run=run,original_zip_sha256=p["zipsha"],source=p["source"],harness=p["harness"],
               training_sha256=sources["training.json"]["original_sha256"],
               transitions_gzip_sha256=sources["full_transitions.jsonl.gz"]["original_sha256"],
               original_transitions=p["transitions"],train_only=True,
               qualification="independent stats; NOT provider-signed or model promotion")
    return rows,proof

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v10-zip",type=Path,required=True)
    parser.add_argument("--hybrid-zip",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args()
    v10,p10=load_run(args.v10_zip,"v10")
    hybrid,ph=load_run(args.hybrid_zip,"hybrid")
    args.output_dir.mkdir(parents=True,exist_ok=False)
    for key,rows in (("v10",v10),("hybrid",hybrid)):
        with (args.output_dir/(key+"-trials.csv")).open("x",newline="") as f:
            w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    with (args.output_dir/"verified-provenance.json").open("x") as f:
        json.dump(dict(runs=[p10,ph],promotion_authorized=False,
                       new_physics=False),f,indent=2,sort_keys=True);f.write("\n")
    print("EXTRACT_OK v10:800/38569 hybrid:640/24167 original TRAIN")

if __name__=="__main__":
    main()
