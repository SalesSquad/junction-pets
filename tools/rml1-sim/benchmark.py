#!/usr/bin/env python3
"""Reproducible Rust simulation performance sweep. Model only; never RML1 authorization."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
import time

CRATE = Path(__file__).resolve().parent

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def sweep(binary, *, seeds, workers, repeats, output):
    baseline = None
    results = []
    with tempfile.TemporaryDirectory(prefix="rml1-perf-") as temporary:
        for worker_count in workers:
            times = []
            digest = None
            for attempt in range(repeats):
                destination = Path(temporary) / f"{worker_count}-{attempt}.jsonl"
                started = time.perf_counter()
                run = subprocess.run([str(binary), "--seeds", str(seeds),
                                      "--workers", str(worker_count),
                                      "--output", str(destination)], capture_output=True,
                                     check=False, timeout=180)
                elapsed = time.perf_counter() - started
                if run.returncode != 0 or not destination.is_file():
                    raise RuntimeError(f"simulation failed workers={worker_count} exit={run.returncode}")
                candidate = sha256(destination)
                if baseline is None:
                    baseline = candidate
                if candidate != baseline:
                    raise RuntimeError(f"non-deterministic bytes workers={worker_count} attempt={attempt}")
                digest = candidate
                times.append(elapsed)
                destination.unlink()
            median = statistics.median(times)
            results.append({"workers": worker_count, "repeats": repeats, "seconds": times,
                            "median_seconds": median, "scenarios_per_second": round(seeds / median),
                            "byte_identical": True, "sha256": digest})
    serial = next(row["median_seconds"] for row in results if row["workers"] == 1)
    for row in results:
        row["speedup_vs_serial"] = round(serial / row["median_seconds"], 3)
    receipt = {"schema": "rml1.synthetic-performance/v1",
               "simulation_only": True, "runtime_authorized": False,
               "seeds": seeds, "platform": platform.platform(),
               "python": platform.python_version(), "results": results}
    output.mkdir(parents=True, exist_ok=True)
    (output / "perf.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    report = ["# RML1 synthetic Rust simulation benchmark", "",
              f"Scenarios: {seeds}; repetitions: {repeats}",
              "Never an OCI, Factory sandbox or real Chibi performance measurement.",
              "", "| Workers | Median seconds | Seeds/s | Speedup vs 1 |",
              "|---:|---:|---:|---:|"]
    for row in results:
        report.append(f"| {row['workers']} | {row['median_seconds']:.4f} | "
                      f"{row['scenarios_per_second']} | {row['speedup_vs_serial']:.3f}× |")
    report.extend(["", "All outputs must match byte-for-byte; a mismatch exits nonzero.",
                   "Small scenarios may run slower with many threads because of scheduling overhead.", ""])
    (output / "PERF.md").write_text("\n".join(report))
    print(json.dumps({"status": "pass", "sha256": baseline,
                      "workers": [r["workers"] for r in results],
                      "output": str(output / "perf.json"),
                      "runtime_authorized": False}))
    return receipt

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=100000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--binary", type=Path, default=CRATE / "target/release/rml1-sim")
    args = parser.parse_args()
    if not 1 <= args.seeds <= 1000000 or not 1 <= args.repeats <= 10:
        parser.error("seeds must be 1..1000000, repeats 1..10")
    if not args.binary.is_file():
        parser.error("compiled release binary missing: cargo build --offline --release")
    sweep(args.binary.resolve(), seeds=args.seeds, workers=(1,2,4,8,16),
          repeats=args.repeats, output=args.out.resolve())

if __name__ == "__main__":
    main()
