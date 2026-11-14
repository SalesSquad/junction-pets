#!/usr/bin/env python3
"""Frozen v2: nonlinear fitted clone vs unchanged shielded FORWARD baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime,timezone
from pathlib import Path

from arena import RouteTeacher,constant_forward,make_world,run_episode
from run import paired_bootstrap,summarize
from v2_policy import FittedForest,fit_v2


# V1 exposed test320000..320299 and OOD420000..420199 are NEVER reused.
# Independent RL lane reserved test325000..325299 and OOD425000..425199.
# V2 lockbox ranges are declared here BEFORE any local or cloud execution.
SCORE_SPLITS = {
    "dev": ("dev",124000,200),
    "cal": ("cal",221000,200),
    "locked_test": ("test",326000,300),
    "locked_ood": ("ood",426000,200),
}


def evaluate(model:FittedForest,split:str,n:int) -> dict:
    if split not in SCORE_SPLITS:
        raise ValueError("unregistered evaluation split")
    underlying,first,maximum = SCORE_SPLITS[split]
    if not 1 <= n <= maximum:
        raise ValueError("episodes exceeds frozen split size")
    if split.startswith("locked") and n != maximum:
        raise ValueError("locked qualification requires full preregistered sample")
    model_results=[]
    teacher_results=[]
    constant_results=[]
    for i in range(n):
        world=make_world(underlying,first+i)
        model_results.append(run_episode(world,"v2_fitted_nonlinear_clone",
                                         lambda:FittedForest(model.trees)))
        teacher_results.append(run_episode(world,"observable_rule_teacher",RouteTeacher))
        constant_results.append(run_episode(world,"shielded_constant_forward",lambda:constant_forward))
    model_vs_null=paired_bootstrap(model_results,constant_results)
    learned=summarize(model_results)
    constant=summarize(constant_results)
    return {"split":split,"underlying_generator":underlying,
            "world_seed_range":[first,first+n-1],"episodes":n,
            "fitted":learned,"teacher":summarize(teacher_results),
            "unchanged_constant":constant,
            "model_minus_constant":model_vs_null,
            "teacher_minus_constant":paired_bootstrap(teacher_results,constant_results),
            "toy_acceptance": n>=100 and model_vs_null["delta_pp"]>=15
                              and model_vs_null["paired_bootstrap_95_pp"][0]>0
                              and learned["unsafe"]<=constant["unsafe"],
            "criterion":"at least 100 paired worlds, fitted success gain >=15pp; paired bootstrap lower95 >0; no greater unsafe count",
            "per_world":{"fitted":model_results,"teacher":teacher_results,"constant":constant_results}}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split",choices=tuple(SCORE_SPLITS),default="cal")
    ap.add_argument("--episodes",type=int,default=None)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--source-commit",default=None,
                    help="Optional full SHA asserted by caller; source-file hashes independently retained")
    args=ap.parse_args()
    if args.source_commit and not re.fullmatch(r"[0-9a-f]{40}",args.source_commit):
        ap.error("source commit must be exact 40-hex SHA")
    if args.output.exists():
        raise RuntimeError("refuse to overwrite a prior receipt")
    episodes=SCORE_SPLITS[args.split][2] if args.episodes is None else args.episodes
    start=time.monotonic()
    fitted,fit_stats=fit_v2()
    evaluation=evaluate(fitted,args.split,episodes)
    here=Path(__file__).resolve().parent
    producer={f.name:hashlib.sha256(f.read_bytes()).hexdigest()
              for f in sorted(here.glob("*.py"))}
    output={"schema":"junction.rokoko.action-necessity.v2.frozen",
            "completed_utc":datetime.now(timezone.utc).isoformat(),
            "source_sha256":producer,
            "source_commit_asserted_unverified":args.source_commit,
            "model_snapshot":fitted.snapshot(),
            "model_sha256":fitted.digest(),
            "fit":fit_stats,
            "evaluation":evaluation,
            "elapsed_seconds":round(time.monotonic()-start,3),
            "limits":["2D synthetic kinematics, NOT MuJoCo/MJWarp/Isaac or a physical robot",
                      "Fitted supervised policy, NOT reinforcement learning or a certified safety system",
                      "No provider bill attestations, signed runner receipt or authentic Rokoko data",
                      "No post-qualification parameter updates; preserve all negative OOD/counterexample evidence"]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,sort_keys=True,indent=2)+"\n")
    compact={key:value for key,value in output.items() if key not in ("model_snapshot","evaluation")}
    compact["evaluation"]={key:value for key,value in evaluation.items() if key!="per_world"}
    print(json.dumps(compact,sort_keys=True))


if __name__=="__main__":
    main()
