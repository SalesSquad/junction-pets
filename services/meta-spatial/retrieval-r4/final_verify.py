#!/usr/bin/env python3
"""Reverify preserved experiments with repaired admission; never refit or overwrite."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from run_experiment import ROOT, digest, source_binding, verify_scores, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--rscript", required=True)
    args = parser.parse_args()
    before = source_binding(args.source_commit)
    if args.output.exists():
        raise ValueError("new_final_verification_path_required")
    started = time.monotonic()
    result = {"schema_version": 1, "source_commit": args.source_commit,
              "source_sha256": before, "status": "RUNNING", "runs": {},
              "checks": [], "qualification": False, "hosted_ci": False}
    try:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="2",
                   OMP_NUM_THREADS="2", VECLIB_MAXIMUM_THREADS="2")
        for name, command in (
            ("python_focused_checks", [sys.executable, "-B", "-m", "unittest", "discover",
                                       "-s", str(ROOT), "-p", "test_*.py", "-v"]),
            ("r_focused_checks", [args.rscript, str(ROOT / "test_reranker.R")]),
        ):
            checked = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                     text=True, timeout=180)
            result["checks"].append({"name": name, "exit_code": checked.returncode,
                                     "stdout": checked.stdout, "stderr": checked.stderr})
            if checked.returncode:
                raise RuntimeError(name + "_failed")
        for name in ("run-01", "run-02"):
            run = args.runs_root / name
            execution = json.loads((run / "execution.json").read_text())
            if execution.get("status") != "TRAINED_AND_VERIFIED_RESEARCH_ONLY":
                raise ValueError("original_experiment_did_not_finish")
            for artifact in execution["artifacts"]:
                path = run / artifact["path"]
                if not path.resolve().is_relative_to(run.resolve()):
                    raise ValueError("artifact_escaped_own_run")
                if digest(path) != artifact["sha256"] or path.stat().st_size != artifact["bytes"]:
                    raise ValueError("original_artifact_hash_mismatch:" + name + ":" + artifact["path"])
            numeric = json.loads((run / "independent_numerics.json").read_text())
            if numeric.get("status") != "PASS" or numeric.get("pairs_checked") != 128:
                raise ValueError("independent_numeric_check_failed")
            training = run / "training"
            report = json.loads((training / "report.json").read_text())
            for artifact in report["artifacts"]:
                path = training / artifact["path"]
                if not path.resolve().is_relative_to(training.resolve()) or digest(path) != artifact["sha256"]:
                    raise ValueError("training_artifact_hash_mismatch")
            parity = verify_scores(run / "candidates/candidates.csv", training)
            result["runs"][name] = {"original_source_commit": execution["source_commit"],
                                    "execution_sha256": digest(run / "execution.json"),
                                    "model_sha256": digest(training / "model.json"),
                                    "report_sha256": digest(training / "report.json"),
                                    "independent_numerics_sha256": digest(run / "independent_numerics.json"),
                                    "original_artifacts_verified": len(execution["artifacts"]),
                                    "parity": parity}
        if source_binding(args.source_commit) != before:
            raise ValueError("source_changed_during_final_verification")
        result["status"] = "PASS"
    except BaseException as error:
        result["status"] = "FAIL"
        result["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        result["elapsed_seconds"] = time.monotonic() - started
        write_json(args.output, result)
        print(json.dumps({"status": result["status"], "elapsed_seconds": result["elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
