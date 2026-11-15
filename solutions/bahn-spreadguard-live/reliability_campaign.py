#!/usr/bin/env python3
"""Bounded unranked campaign. Uses existing SDK credentials without copying them."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys

from official_study import atomic_json, provenance, resolve_configuration


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--partition", choices=["development", "blind"], required=True)
    parser.add_argument("--policies", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, choices=[1, 2, 3], default=2)
    parser.add_argument("--model")
    parser.add_argument("--late-threshold", type=float)
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text())
    allowed = {"baseline", "deadline", "capacity", "learned", "trust", "notes"}
    if len(set(args.policies)) != len(args.policies) or not set(args.policies) <= allowed:
        parser.error("Policies must be unique known opt-in ablations")
    if args.partition == "blind" and not plan.get("frozen_candidate"):
        parser.error("Blind evaluation requires a frozen_candidate in the plan")
    if args.partition == "blind" and set(args.policies) != {"baseline", plan["frozen_candidate"]["policy"]}:
        parser.error("Blind evaluation must compare baseline and the frozen candidate only")
    if args.partition == "blind":
        frozen = plan["frozen_candidate"]
        effective = argparse.Namespace(policy=frozen["policy"], model=args.model,
                                       late_threshold=args.late_threshold)
        resolve_configuration(effective)
        observed = provenance(effective.model)
        if observed["files_sha256"] != frozen.get("files_sha256") \
                or observed["model_sha256"] != frozen.get("model_sha256") \
                or effective.late_threshold != frozen.get("late_threshold"):
            parser.error("Candidate source/model/threshold differs from its predeclared freeze")
    seeds = plan["partitions"][args.partition]
    if len(set(seeds)) != len(seeds) or set(plan["partitions"]["development"]) & set(plan["partitions"]["blind"]):
        parser.error("Seed groups must be unique and development/blind must be disjoint")
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    jobs = [(seed, policy) for seed in seeds for policy in args.policies]

    def execute(job: tuple[str, str]) -> dict:
        seed, policy = job
        destination = root / seed / policy
        destination.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, str(Path(__file__).with_name("official_study.py")), "run",
                   "--seed", seed, "--policy", policy, "--partition", args.partition,
                   "--output", str(destination)]
        if policy == "learned":
            if not args.model:
                raise ValueError("Learned policy needs --model")
            command += ["--model", str(Path(args.model).resolve())]
            if args.late_threshold is not None:
                command += ["--late-threshold", str(args.late_threshold)]
        with open(destination / "runner.log", "a") as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
        receipt_path = destination / "run.json"
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
        summary = {"seed_group": seed, "policy": policy, "exit_code": result.returncode,
                   "world_id": receipt.get("world_id"), "state": receipt.get("state"),
                   "score": receipt.get("evidence", {}).get("score"),
                   "elapsed_seconds": receipt.get("elapsed_seconds")}
        print(json.dumps(summary, sort_keys=True), flush=True)
        return summary

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(execute, job) for job in jobs]
        for future in as_completed(futures):
            results.append(future.result())
            atomic_json(root / "campaign.json", {"schemaVersion": 1, "partition": args.partition,
                                                 "jobs": sorted(results, key=lambda row: (row["seed_group"], row["policy"]))})
    if any(row["exit_code"] != 0 or row["state"] != "completed" for row in results):
        raise SystemExit("Campaign has incomplete runs; preserve and reconcile their receipts")


if __name__ == "__main__":
    main()
