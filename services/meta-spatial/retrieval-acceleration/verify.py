#!/usr/bin/env python3
"""Run only this subtree's focused checks and bind results to executed sources."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import io
import json
import os
from pathlib import Path
import platform
import time
import unittest

from cli import write_new_json

ROOT = Path(__file__).resolve().parent


def source_hashes():
    files = sorted(ROOT.glob("*.py")) + [ROOT / "output.schema.json", ROOT / "requirements.txt",
                                          ROOT / "requirements-dev.txt"]
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path, log_path = args.output_dir / "verification.json", args.output_dir / "test-output.txt"
    if report_path.exists() or log_path.exists():
        parser.error("verification outputs must be new; preserve previous evidence")
    before = source_hashes()
    started = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT), pattern="test_*.py")
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    elapsed = time.perf_counter() - start
    after = source_hashes()
    raw_log = stream.getvalue().encode("utf-8")
    with log_path.open("xb") as handle:
        handle.write(raw_log)
    passed = result.wasSuccessful() and not result.skipped and before == after
    report = {
        "schema_version": 1, "work_id": "META-LENS-ACCEL-20261114",
        "kind": "meta.retrieval-acceleration.focused-verification",
        "status": "PASS" if passed else "FAIL",
        "source_base_commit": "3e2aeaf69cb7a54c79ba3a35c06dfd9ade89d3e1",
        "started_utc": started, "ended_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": elapsed,
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "unexpected_successes": len(result.unexpectedSuccesses),
        "source_sha256": before, "source_stable_during_execution": before == after,
        "post_execution_source_sha256": after,
        "test_output_sha256": hashlib.sha256(raw_log).hexdigest(),
        "reference_source_sha256": {name: hashlib.sha256((ROOT.parent / "retrieval-r3" / name).read_bytes()).hexdigest()
                                    for name in ("runtime.py", "visual_adapter.py")},
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "packages": {name: version(name) for name in ("numpy", "jsonschema", "safetensors", "threadpoolctl")},
                        "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS")},
        "provider_calls": 0, "gpu_instances": 0, "new_provider_compute_cost_usd": 0,
        "tool_and_llm_cost_usd": None, "qualification": False,
        "action_authorized": False, "physical_identity_verified": False,
        "scope": "Portable synthetic contract, numeric parity, artifact integrity and real local CLI checks",
        "limitations": ["Not hosted CI, a signed execution attestation or product qualification",
                        "No real R5 pilot artifacts or image pixels were supplied to this verification",
                        "No measured improvement in model recall, accepted coverage or glasses end-to-end latency"],
    }
    write_new_json(report_path, report)
    print(json.dumps({"status": report["status"], "tests_run": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors),
                      "skipped": len(result.skipped), "elapsed_seconds": elapsed,
                      "source_stable_during_execution": before == after}))
    if not passed:
        print(stream.getvalue())
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
