#!/usr/bin/env python3
"""Run "<seed> <policy>" jobs with N workers via run_pair.py; skip jobs already in OUT.

    SPREAD_KEY=... python run_jobs.py <out.jsonl> <workers> <jobs.txt> [stopfile]

Unranked practice only (run_pair.py never uses --board or --final). Creating the
stop file lets running worlds finish and starts no new ones, so no world is left
open. Restart with another worker count: finished jobs are skipped.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    out, workers, jobs_path = os.path.abspath(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    stop = sys.argv[4] if len(sys.argv) > 4 else out + ".stop"
    if not 1 <= workers <= 8:
        raise SystemExit("workers must be 1..8 (practice slot limit)")
    done = set()
    if os.path.exists(out):
        for line in open(out):
            if line.strip():
                r = json.loads(line)
                done.add((r["seed"], r["policy"]))
    jobs = [tuple(l.split()) for l in open(jobs_path) if l.strip()]
    todo = [j for j in jobs if j not in done]
    logs = os.path.join(os.path.dirname(out), "logs")
    os.makedirs(logs, exist_ok=True)
    lock = threading.Lock()
    print(f"{len(todo)} of {len(jobs)} jobs to run with {workers} workers", flush=True)

    def run(job: tuple[str, str]) -> None:
        if os.path.exists(stop):
            return
        seed, policy = job
        log = os.path.join(logs, f"{seed}-{policy}.log")
        with open(log, "w") as fh:
            subprocess.run([sys.executable, "run_pair.py", seed, policy], stdout=fh,
                           stderr=subprocess.STDOUT, cwd=HERE, check=False)
        lines = [l[7:] for l in open(log) if l.startswith("RESULT ")]
        with lock:
            if lines:
                with open(out, "a") as fh:
                    fh.write(lines[-1])
            print(("done " if lines else "FAILED ") + seed + " " + policy, flush=True)

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(run, todo))
    print("JOBS_DONE", flush=True)


if __name__ == "__main__":
    main()
