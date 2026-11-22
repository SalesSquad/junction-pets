#!/usr/bin/env python3
"""Source-bound developer campaign: Rust model + real 34-pet fixtures + benign Factory checks.

Never executes untrusted R or grants sandbox qualification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
MAX_CAPTURE = 128 * 1024


def run_step(label, command, cwd, timeout=180):
    started = time.monotonic()
    try:
        process = subprocess.run(
            command, cwd=cwd, capture_output=True, timeout=timeout, check=False,
            env={**os.environ, "CARGO_NET_OFFLINE": "true", "NO_COLOR": "1"},
        )
        output = (process.stdout + b"\n" + process.stderr)[:MAX_CAPTURE].decode("utf-8", "replace")
        return {"name": label, "status": "pass" if process.returncode == 0 else "fail",
                "exit_code": process.returncode, "seconds": round(time.monotonic() - started, 3),
                "output_sha256": hashlib.sha256(process.stdout + b"\n" + process.stderr).hexdigest(),
                "output_tail": output[-1800:]}
    except (subprocess.TimeoutExpired, OSError) as error:
        return {"name": label, "status": "fail", "error": type(error).__name__,
                "seconds": round(time.monotonic() - started, 3)}


def git_sha(path):
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True,
                                text=True, timeout=8, check=True)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return None


def verify_simulation(folder, results, seeds=4096, workers=8):
    crate = ROOT / "tools/rml1-sim"
    results.append(run_step("rust_sim_unit_tests", ["cargo", "test", "--offline"], crate))
    if results[-1]["status"] != "pass":
        return None
    with tempfile.TemporaryDirectory(prefix="rml1-campaign-") as temporary:
        first = Path(temporary) / "parallel.jsonl"
        second = Path(temporary) / "serial.jsonl"
        for label, workers, destination in [
            ("rust_sim_parallel", str(workers), first),
            ("rust_sim_serial_replay", "1", second),
        ]:
            results.append(run_step(label, ["cargo", "run", "--offline", "--release", "--",
                                            "--seeds", str(seeds), "--workers", workers,
                                            "--output", str(destination)], crate))
            if results[-1]["status"] != "pass":
                return None
        lhs, rhs = first.read_bytes(), second.read_bytes()
        rows = lhs.splitlines()
        try:
            summary = json.loads(rows[-1])
            valid = (lhs == rhs and len(rows) == seeds + 1 and
                     summary["kind"] == "summary" and
                     summary["scenarios"] == seeds and
                     summary["runtime_authorized"] is False and
                     all(json.loads(row)["runtime_authorized"] is False for row in rows[:-1]))
        except (ValueError, IndexError, KeyError, TypeError):
            valid = False
            summary = None
        results.append({"name": "rust_sim_byte_identical_replay", "status": "pass" if valid else "fail",
                        "jsonl_sha256": hashlib.sha256(lhs).hexdigest()})
        if valid and folder:
            destination = folder / "simulation.jsonl"
            destination.write_bytes(lhs)
        return summary if valid else None


def verify_factory(factory_root, results):
    if factory_root is None:
        results.append({"name": "factory_benign_broker", "status": "not_run",
                        "reason": "factory_root_not_supplied"})
        return
    crate = factory_root / "tools/factory_os/r_evaluator/linux_broker"
    if not (crate / "Cargo.toml").is_file():
        results.append({"name": "factory_benign_broker", "status": "fail",
                        "reason": "factory_crate_missing"})
        return
    results.append(run_step("factory_broker_unit_tests",
                            ["cargo", "test", "--offline", "--all-targets"], crate))
    if results[-1]["status"] != "pass":
        return
    if platform.system() != "Linux":
        results.append({"name": "factory_native_benign_canary", "status": "not_run",
                        "reason": "native_linux_required"})
        return
    results.append(run_step("factory_broker_build",
                            ["cargo", "build", "--offline", "--release"], crate))
    if results[-1]["status"] != "pass":
        return
    executable = crate / "target/release/rml1-broker-probe"
    script = crate / "cloud/test_broker_owned_canary.sh"
    results.append(run_step("factory_native_benign_canary",
                            ["sh", str(script), str(executable)], crate, timeout=25))


def verify_chibi(chibi_root, output, results, count):
    """Execute Chibi's actual source-pinned Rust market driver, not a duplicate model."""
    if chibi_root is None:
        return {"status": "not_run", "reason": "chibi_root_not_supplied"}
    if not (chibi_root / "tools/ci/seeded_factory.py").is_file():
        results.append({"name": "chibi_market_real_rust", "status": "fail",
                        "reason": "chibi_seeded_driver_missing"})
        return {"status": "fail", "reason": "driver_missing"}
    sha = git_sha(chibi_root)
    if sha is None:
        results.append({"name": "chibi_market_real_rust", "status": "fail",
                        "reason": "chibi_git_sha_missing"})
        return {"status": "fail", "reason": "source_sha_missing"}
    destination = output / "chibi-market"
    cache = output / "chibi-cache"
    # Chibi enforces clean HEAD, an external cache, a single-writer lock,
    # strict fixture source checks and real scenario receipts itself.
    # Chibi's campaign output directory must not exist before its own runner.
    step = run_step("chibi_market_real_rust",
                    ["python3", "tools/ci/seeded_factory.py", "--expected-head", sha,
                     "--cache-root", str(cache), "--out", str(destination),
                     "--lane", "market", "--campaign-start", "0",
                     "--campaign-count", str(count)], chibi_root, timeout=900)
    results.append(step)
    return {"status": step["status"], "source_sha": sha,
            "campaign_count": count, "output_dir": str(destination)}


def write_report(output, receipt):
    steps = receipt["steps"]
    rows = ["# RML1 development campaign", "",
            f"Overall: **{receipt['overall'].upper()}**",
            "Security: runtime authorization **false**; not an OCI or host attestation.",
            "",
            f"Junction source: \`{receipt['junction_source_sha']}\`",
            f"Factory source: \`{receipt['factory_source_sha']}\`",
            f"Chibi adapter: **{receipt['chibi_integration']['status']}**",
            "",
            "| Executed check | Status | Exit |",
            "|---|---|---|"]
    for step in steps:
        rows.append(f"| {step['name']} | {step['status']} | {step.get('exit_code', '—')} |")
    rows.extend(["", "## Synthetic simulator (not Chibi runtime)", ""])
    summary = receipt.get("simulation")
    if summary:
        for key in ("scenarios", "committed", "denied", "recovered",
                    "duplicate_prevented", "retries", "checksum"):
            rows.append(f"- {key}: {summary.get(key)}")
    else:
        rows.append("No validated synthetic simulator summary.")
    rows.extend(["", "A missing Factory or Linux canary makes overall INCOMPLETE.",
                 "Chibi is an opt-in real Rust integration; its absence is separately declared.",
                 "A Chibi adapter failure makes overall FAIL.",
                 ""])
    (output / "REPORT.md").write_text("\n".join(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-root", type=Path, help="local checkout of SalesSquad/factory")
    parser.add_argument("--chibi-root", type=Path, help="optional clean authorized SalesSquad/chibi checkout")
    parser.add_argument("--chibi-market-seeds", type=int, default=10000, help="Chibi real Rust scenario count")
    parser.add_argument("--out", type=Path, required=True, help="new or existing output directory")
    parser.add_argument("--seeds", type=int, default=4096, help="4096 by default, up to 1000000")
    parser.add_argument("--workers", type=int, default=8, help="parallel Rust simulation workers (1..64)")
    args = parser.parse_args()
    if not 1 <= args.seeds <= 1_000_000 or not 1 <= args.workers <= 64:
        parser.error("seeds must be 1..1000000 and workers must be 1..64")
    if not 1 <= args.chibi_market_seeds <= 100_000:
        parser.error("chibi-market-seeds must be 1..100000")
    output = args.out.resolve()
    if output.is_symlink():
        parser.error("output directory cannot be a symlink")
    output.mkdir(parents=True, exist_ok=True)
    factory = args.factory_root.resolve() if args.factory_root else None
    results = []
    simulation = verify_simulation(output, results, seeds=args.seeds, workers=args.workers)
    # This is the existing live fixture suite, which invokes all 34 actual offline analyzers.
    # A passing Node test process is NOT provider connectivity or Chibi host authorization.
    results.append(run_step("junction_34_real_offline_capability_fixtures",
                            ["node", "--test", "services/pet-adapters/registry.test.mjs"],
                            ROOT, timeout=240))
    verify_factory(factory, results)
    chibi = verify_chibi(args.chibi_root.resolve() if args.chibi_root else None,
                         output, results, args.chibi_market_seeds)
    # Never report a complete campaign when a required integration did not run.
    # A partial platform (macOS) is useful for development but not Linux acceptance.
    statuses = {r["status"] for r in results}
    overall = ("fail" if "fail" in statuses else
               "incomplete" if "not_run" in statuses else
               "pass" if results and statuses == {"pass"} else "fail")
    receipt = {
        "schema": "rml1.developer-integration/v1",
        "junction_source_sha": git_sha(ROOT),
        "factory_source_sha": git_sha(factory) if factory else None,
        "platform": platform.system().lower(),
        "simulation": simulation,
        "campaign_parameters": {"seeds": args.seeds, "workers": args.workers},
        "chibi_integration": chibi,
        "steps": results,
        "qualified": False,
        "runtime_authorized": False,
        "generated_r_executed": False,
        "overall": overall,
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    write_report(output, receipt)
    print(json.dumps({"overall": receipt["overall"], "steps": [
        {"name": step["name"], "status": step["status"]} for step in results
    ], "receipt": str(output / "receipt.json"), "runtime_authorized": False}))
    return {"pass": 0, "fail": 1, "incomplete": 2}[overall]


if __name__ == "__main__":
    sys.exit(main())
