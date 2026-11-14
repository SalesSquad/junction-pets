#!/usr/bin/env python3
"""Single-use, preregistered v2 supervised-policy lockbox qualification on CRACI.

These world seeds must never be retuned against after this script runs.
Preserve negative results, raw per-world records, and exact source bindings.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

FROZEN_SOURCE = "f96788807c262b2233f034c045df4373cb3c428c"
FROZEN_MODEL = "1bab986c10be062cf87a4848916917cbab3a78b53e78cda8c2f8673f62d4cc55"
SPLITS = (("locked_test", "test", 326000, 300), ("locked_ood", "ood", 426000, 200))


def main() -> int:
    source = Path(os.environ["CRACI_SOURCE_ROOT"]).resolve()
    output = (Path(os.environ["CRACI_RECEIPT_DIR"]) / "artifacts" / "rokoko-v2").resolve()
    observed_source = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if observed_source != FROZEN_SOURCE or os.environ["CRACI_SOURCE_SHA"] != FROZEN_SOURCE:
        raise RuntimeError("FROZEN_V2_SOURCE_MISMATCH")
    if output.exists():
        raise RuntimeError("REFUSE_OVERWRITE_LOCKBOX_EVIDENCE")
    output.mkdir(parents=True)
    runner = source / "solutions/rokoko-teleoperation-gym/learning/action_necessity/v2_run.py"
    summary = {"schema": "junction.rokoko.v2.craci.qualification.v1",
               "source_sha": FROZEN_SOURCE, "model_sha256_expected": FROZEN_MODEL,
               "preregistered_seed_windows": True, "global_once_registry_enforced": False, "results": [], "all_criteria_passed": False}
    for split, underlying, first, count in SPLITS:
        destination = output / (split + ".json")
        try:
            subprocess.run(
                [sys.executable, str(runner), "--split", split, "--episodes", str(count),
                 "--output", str(destination), "--source-commit", FROZEN_SOURCE],
                check=True, cwd=str(runner.parent),
                env={**os.environ, "PYTHONHASHSEED": "0"},
            )
            result = json.loads(destination.read_text())
            evaluation = result["evaluation"]
            verified = (
                result["schema"] == "junction.rokoko.action-necessity.v2.frozen"
                and result["source_commit_asserted_unverified"] == FROZEN_SOURCE
                and result["model_sha256"] == FROZEN_MODEL
                and evaluation["split"] == split
                and evaluation["underlying_generator"] == underlying
                and evaluation["episodes"] == count
                and evaluation["world_seed_range"] == [first, first + count - 1]
                and len(evaluation["per_world"]["fitted"]) == count
                and len(evaluation["per_world"]["constant"]) == count
                and evaluation["model_minus_constant"]["delta_pp"] >= 15
                and evaluation["model_minus_constant"]["paired_bootstrap_95_pp"][0] > 0
                and evaluation["fitted"]["unsafe"] <= evaluation["unchanged_constant"]["unsafe"]
                and evaluation["toy_acceptance"] is True
            )
            summary["results"].append({
                "split": split, "seed_range": [first, first + count - 1],
                "episodes": count, "success_delta_pp": evaluation["model_minus_constant"]["delta_pp"],
                "paired_bootstrap_95_pp": evaluation["model_minus_constant"]["paired_bootstrap_95_pp"],
                "fitted_unsafe": evaluation["fitted"]["unsafe"],
                "constant_unsafe": evaluation["unchanged_constant"]["unsafe"],
                "model_sha256": result["model_sha256"],
                "locked_criterion_passed": verified,
            })
        except Exception as exc:
            summary["results"].append({
                "split": split, "locked_criterion_passed": False,
                "error_type": type(exc).__name__, "error_code": "RUN_OR_SCHEMA_FAILED"
            })
            break
    summary["all_criteria_passed"] = (
        len(summary["results"]) == len(SPLITS)
        and all(result["locked_criterion_passed"] for result in summary["results"])
    )
    summary_path = output / "qualification.json"
    with summary_path.open("x") as handle:
        json.dump(summary, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print(json.dumps({**summary, "note": "synthetic supervised 2D only, no real robot/MuJoCo safety claim"}, sort_keys=True))
    return 0 if summary["all_criteria_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
