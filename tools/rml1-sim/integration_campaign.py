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


def verify_simulation(folder, results):
    crate = ROOT / "tools/rml1-sim"
    results.append(run_step("rust_sim_unit_tests", ["cargo", "test", "--offline"], crate))
    if results[-1]["status"] != "pass":
        return None
    with tempfile.TemporaryDirectory(prefix="rml1-campaign-") as temporary:
        first = Path(temporary) / "parallel.jsonl"
        second = Path(temporary) / "serial.jsonl"
        for label, workers, destination in [
            ("rust_sim_4096_parallel", "8", first),
            ("rust_sim_4096_serial_replay", "1", second),
        ]:
            results.append(run_step(label, ["cargo", "run", "--offline", "--release", "--",
                                            "--seeds", "4096", "--workers", workers,
                                            "--output", str(destination)], crate))
            if results[-1]["status"] != "pass":
                return None
        lhs, rhs = first.read_bytes(), second.read_bytes()
        rows = lhs.splitlines()
        try:
            summary = json.loads(rows[-1])
            valid = (lhs == rhs and len(rows) == 4097 and
                     summary["kind"] == "summary" and
                     summary["scenarios"] == 4096 and
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-root", type=Path, help="local checkout of SalesSquad/factory")
    parser.add_argument("--out", type=Path, required=True, help="new or existing output directory")
    args = parser.parse_args()
    output = args.out.resolve()
    if output.is_symlink():
        parser.error("output directory cannot be a symlink")
    output.mkdir(parents=True, exist_ok=True)
    factory = args.factory_root.resolve() if args.factory_root else None
    results = []
    simulation = verify_simulation(output, results)
    # This is the existing live fixture suite, which invokes all 34 actual offline analyzers.
    # A passing Node test process is NOT provider connectivity or Chibi host authorization.
    results.append(run_step("junction_34_real_offline_capability_fixtures",
                            ["node", "--test", "services/pet-adapters/registry.test.mjs"],
                            ROOT, timeout=240))
    verify_factory(factory, results)
    mandatory = [r for r in results if r["status"] != "not_run"]
    passed = bool(mandatory) and all(r["status"] == "pass" for r in mandatory)
    receipt = {
        "schema": "rml1.developer-integration/v1",
        "junction_source_sha": git_sha(ROOT),
        "factory_source_sha": git_sha(factory) if factory else None,
        "platform": platform.system().lower(),
        "simulation": simulation,
        "steps": results,
        "qualified": False,
        "runtime_authorized": False,
        "generated_r_executed": False,
        "overall": "pass" if passed else "fail",
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"overall": receipt["overall"], "steps": [
        {"name": step["name"], "status": step["status"]} for step in results
    ], "receipt": str(output / "receipt.json"), "runtime_authorized": False}))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
