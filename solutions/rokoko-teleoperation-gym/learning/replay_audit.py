#!/usr/bin/env python3
"""A fixed, result-blind subset of held-out source-bound MuJoCo RL episodes.

Use exactly the frozen policy; do not train, tune, or change any result.
CPU-vs-CUDA model inference differences are preserved as mismatches.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import torch

from env import ContactEnv
from train import Q

# These 20 offsets are fixed before inspecting the sealed test outcome.
PRESELECTED_TEST_OFFSETS = (
    0,1,2,3,4,5,10,20,30,50,75,100,125,150,175,200,225,250,275,299
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--device", choices=("cpu","cuda"), default="cpu")
    args = ap.parse_args()
    results = args.results.resolve()
    cfg = json.loads((results/"frozen-config.json").read_text())
    original = json.loads((results/"receipt.json").read_text())
    if cfg["test_episodes"] != 300:
        raise ValueError("Audit requires exact 300-test-world frozen protocol")
    if sha256(results/"weights.pt") != original["weights_sha256"]:
        raise ValueError("Saved model differs from original model receipt")
    if original["source_commit"] != "a9911f7e9d68114bd5d911eed322a65177fdf086":
        raise ValueError("Unexpected source commit")
    rows=list(csv.DictReader((results/"episodes.csv").open(newline="",encoding="utf8")))
    expected = {
        int(row["seed"]):row
        for row in rows if row["split"]=="test" and row["method"]=="dqn"
    }
    if len(expected)!=300 or set(expected)!=set(range(320000,320300)):
        raise ValueError("Sealed test is incomplete")
    device=torch.device(args.device)
    if args.device=="cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA requested but unavailable")
    net=Q().to(device)
    net.load_state_dict(torch.load(results/"weights.pt",map_location=device,
                                  weights_only=True))
    net.eval()
    env=ContactEnv(max_options=int(cfg["max_options"]))
    outcomes=[]
    for offset in PRESELECTED_TEST_OFFSETS:
        seed=320000+offset
        obs=env.reset(seed,ood=False)
        done=False
        last_info=None
        while not done:
            mask=env.mask(obs)
            with torch.no_grad():
                q=net(torch.as_tensor(obs,device=device))
                choice=int(q.masked_fill(
                    ~torch.as_tensor(mask,device=device),-torch.inf).argmax())
            obs, reward, done, last_info=env.step(choice)
        reference=expected[seed]
        match={
            "success":str(bool(last_info["success"]))==reference["success"],
            "unsafe":str(bool(last_info["unsafe"]))==reference["unsafe"],
            "options":env.steps==int(reference["options"]),
            "physics_steps":env.physics_steps==int(reference["physics_steps"]),
            "abstained":str(bool(last_info["abstained"]))==reference["abstained"],
        }
        outcomes.append({
            "seed":seed,"match":match,
            "replayed_success":bool(last_info["success"]),
            "reference_success":reference["success"],
            "replayed_unsafe":bool(last_info["unsafe"]),
            "reference_unsafe":reference["unsafe"],
        })
    mismatch=sum(not all(record["match"].values()) for record in outcomes)
    report={
        "schema":"motionbridge.learning-replay-audit.v1",
        "checked_at_utc":datetime.now(timezone.utc).isoformat(),
        "source_commit":original["source_commit"],
        "weights_sha256":original["weights_sha256"],
        "eval_device":str(device),
        "sample_count":len(outcomes),
        "selection":"Predeclared fixed offsets; no result-based selection",
        "mismatched_episodes":mismatch,
        "outcomes":outcomes,
        "never_hardware_or_real_sensor":True,
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
        "sample_count":len(outcomes),
        "mismatched_episodes":mismatch,
        "eval_device":str(device),
        "source_commit":original["source_commit"],
        "weights_sha256":original["weights_sha256"],
    }))
    if mismatch:
        raise SystemExit(3)


if __name__=="__main__":
    main()
