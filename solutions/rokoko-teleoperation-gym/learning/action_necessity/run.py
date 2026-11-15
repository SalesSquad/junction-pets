#!/usr/bin/env python3
"""Reproducible paired teacher-vs-constant experiment; NO learned-policy claim."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from random import Random

from arena import RouteTeacher, SEEDS, constant_forward, make_world, run_episode


def paired_bootstrap(teacher: list[dict], null: list[dict],
                     reps: int = 4000) -> dict:
    """Predeclared paired percentile bootstrap, resampling *entire worlds*."""
    if len(teacher) != len(null) or not teacher:
        raise ValueError("paired nonempty results required")
    if any(t["seed"] != n["seed"] for t, n in zip(teacher, null)):
        raise ValueError("unpaired seed ordering")
    values = [int(t["success"]) - int(n["success"]) for t, n in zip(teacher, null)]
    rng = Random(0x4A554E4354494F4E)
    size = len(values)
    samples = sorted(sum(values[rng.randrange(size)] for _ in range(size))/size
                     for _ in range(reps))
    return {
        "delta_pp": round(100*statistics.mean(values), 3),
        "paired_bootstrap_95_pp": [round(100*samples[int(reps*.025)], 3),
                                   round(100*samples[min(reps-1, int(reps*.975))], 3)],
        "teacher_only_success": values.count(1),
        "null_only_success": values.count(-1),
        "ties": values.count(0),
        "method": "paired percentile bootstrap, 4000 world-level resamples; descriptive, not a safety certificate",
    }


def summarize(rows: list[dict]) -> dict:
    return {"episodes": len(rows), "success": sum(int(r["success"]) for r in rows),
            "unsafe": sum(int(r["unsafe"]) for r in rows),
            "abort": sum(int(r["aborted"]) for r in rows),
            "refusals": sum(r["refusals"] for r in rows),
            "holds": sum(r["holds"] for r in rows),
            "reobservations": sum(r["reobservations"] for r in rows)}


def evaluate(split: str, n: int) -> dict:
    if split not in SEEDS or not 1 <= n <= 1000:
        raise ValueError("unknown split or episodes outside 1..1000")
    teachers = []
    nulls = []
    for i in range(n):
        w = make_world(split, SEEDS[split]+i)
        teachers.append(run_episode(w, "observable_rule_teacher", RouteTeacher))
        nulls.append(run_episode(w, "shielded_constant_forward", lambda: constant_forward))
    paired = paired_bootstrap(teachers, nulls)
    t, b = summarize(teachers), summarize(nulls)
    # Qualification is strictly about this 2D toy baseline, NOT learning or MuJoCo.
    action_necessity_demo = (n >= 100 and paired["delta_pp"] >= 15.
                             and paired["paired_bootstrap_95_pp"][0] > 0
                             and t["unsafe"] <= b["unsafe"])
    return {"split": split, "world_range": [SEEDS[split], SEEDS[split]+n-1],
            "worlds": n, "teacher": t, "null": b, "paired": paired,
            "action_necessity_demo": action_necessity_demo,
            "criterion": "n>=100; teacher-minus-constant >=15pp; paired lower 95% >0; teacher unsafe no higher",
            "rows": {"teacher": teachers, "null": nulls}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=sorted(SEEDS), default="dev")
    parser.add_argument("--episodes", type=int, default=120)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", default=None,
                        help="Optional full 40-char SHA asserted by coordinator; never self-attested")
    args = parser.parse_args()
    if args.source_commit and not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        parser.error("source-commit must be a 40-char hexadecimal SHA")
    if args.output.exists():
        raise RuntimeError("output path exists; never overwrite prior experimental evidence")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    evidence = evaluate(args.split, args.episodes)
    base = Path(__file__).resolve().parent
    source_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(base.glob("*.py"))}
    receipt = {
        "schema": "junction.rokoko.action-necessity.v1",
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit_assertion": args.source_commit,
        "commit_binding": "UNVERIFIED_EXTERNAL_ASSERTION" if args.source_commit else "NONE",
        "source_sha256": source_hashes,
        "environment": "SYNTHETIC_2D_KINEMATICS_NOT_MUJOCO",
        "operator": "RULE_BASED_OBSERVED_STATE_TEACHER_NOT_TRAINED_MODEL",
        "shield": "IDENTICAL_LOCAL_TRUE_GEOMETRY_GUARD_FOR_BOTH_POLICIES",
        "frozen_world_design": "4 scenarios; randomized friction/drift; crossing obstacle; delayed/dropout readings; deadman release",
        "duration_s": round(time.monotonic()-began, 3),
        **evidence,
        "limits": ["No MuJoCo or MJWarp/Isaac simulation executed.",
                   "No Rokoko SDK, physical robot or actual actuation.",
                   "No RL model was trained, evaluated or shown to improve.",
                   "Shield sees ground truth and does not certify device safety.",
                   "Run locked test/OOD only after freezing algorithm and world generator; do not tune on these results."],
    }
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True)+"\n")
    compact = {k: v for k, v in receipt.items() if k != "rows"}
    print(json.dumps(compact, sort_keys=True))


if __name__ == "__main__":
    main()
