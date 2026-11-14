#!/usr/bin/env python3
"""MuJoCo v3 frozen-policy independent 100-world calibration gate, separate from actual-physics smoke."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

SOURCE = "466c4264468b35c954242d8c3409a47c5ba3b4b8"


def main() -> int:
    src = Path(os.environ["CRACI_SOURCE_ROOT"]).resolve()
    evidence = (Path(os.environ["CRACI_RECEIPT_DIR"]) / "artifacts" / "rokoko-mujoco-v3-cal").resolve()
    if evidence.exists():
        raise RuntimeError("NO_OVERWRITE_MUJOCO_V3_CAL_PROOF")
    evidence.mkdir(parents=True)
    observed = subprocess.check_output(["git", "-C", str(src), "rev-parse", "HEAD"], text=True).strip()
    if observed != SOURCE or os.environ["CRACI_SOURCE_SHA"] != SOURCE:
        raise RuntimeError("MUJOCO_V3_PIN_MISMATCH")
    python = Path(os.environ["RUNNER_TEMP"]) / "mujoco-venv/bin/python"
    if not python.is_file():
        raise RuntimeError("MUJOCO_VENV_MISSING")
    module = src / "solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v3"
    subprocess.run(
        [str(python), "-m", "unittest", "discover", "-v", "-s", str(module), "-p", "test_contract.py"],
        check=True, cwd=str(src),
    )
    destination = evidence / "cal-physics-v3.json"
    execution = subprocess.run([
        str(python), str(module / "run.py"), "--split", "cal", "--episodes", "100",
        "--seed-offset", "0", "--max-options", "60", "--require-git", "--expected-head", SOURCE,
        "--output", str(destination),
    ], cwd=str(src), check=False)
    if not destination.is_file():
        raise RuntimeError("MUJOCO_POLICY_SOURCE_RECEIPT_MISSING")
    obj = json.loads(destination.read_text())
    rows = obj["paired_worlds"]
    gate = obj["qualification"]
    comparisons = obj["summaries"]["risk_v3"]
    source_ok = (
        obj["schema"] == "rokoko-mujoco-real-physics-risk-v3"
        and obj["actual_physics_engine"] == "mujoco-3.3.7"
        and obj["executed_head"] == SOURCE
        and obj["split"] == "cal" and obj["first_seed"] == 229000
        and obj["episodes"] == 100 and len(rows) == 100
        and all(
            len({record["world_hash"] for record in row.values()}) == 1
            and all(record["physics_steps"] > 0 for record in row.values())
            for row in rows
        )
    )
    science_ok = (
        execution.returncode == 0 and gate["scientifically_qualifies"] is True
        and gate["positive_gain"] is True
        and gate["no_unsafe_regression"] is True
        and gate["paired_lower_bound_positive"] is True
        and comparisons["candidate_success"] > comparisons["constant_success"]
        and comparisons["candidate_unsafe"] <= comparisons["constant_unsafe"]
    )
    # Post-hoc mechanism diagnosis only; the unconditional paired gate above
    # remains the sole scientific promotion criterion. No sample filtering.
    posthoc = {
        "exploratory_only": True,
        "do_not_promote_on_strata": True,
        "deadman_released": {"worlds": 0, "v3_success": 0, "constant_success": 0, "v3_unsafe": 0, "constant_unsafe": 0},
        "deadman_held": {"worlds": 0, "v3_success": 0, "constant_success": 0, "v3_unsafe": 0, "constant_unsafe": 0},
    }
    deadman_consistent = True
    for row in rows:
        releases = {row[k]["diagnostic_deadman_release_tick"]
                    for k in ("constant", "adaptive_v2", "risk_v3")}
        if len(releases) != 1:
            deadman_consistent = False
            continue
        group = posthoc["deadman_released" if next(iter(releases)) >= 0 else "deadman_held"]
        group["worlds"] += 1
        for target, policy in (("v3", "risk_v3"), ("constant", "constant")):
            group[f"{target}_success"] += int(row[policy]["success"])
            group[f"{target}_unsafe"] += int(row[policy]["unsafe"])
    source_ok = source_ok and deadman_consistent and (
        posthoc["deadman_released"]["worlds"] + posthoc["deadman_held"]["worlds"] == 100
    )
    summary = {
        "schema": "junction.rokoko.mujoco-v3.craci.cal.v1",
        "source_sha": SOURCE,
        "actual_physics_source_verified": source_ok,
        "posthoc_deadman_strata": posthoc,
        "policy_scientific_gate_passed": science_ok,
        "teacher_baseline_negative_historical_run": 43627944236,
        "v2_scientific_negative_run": 43628857595,
        "adaptive_success": comparisons["candidate_success"],
        "constant_success": comparisons["constant_success"],
        "unsafe_adaptive": comparisons["candidate_unsafe"],
        "unsafe_constant": comparisons["constant_unsafe"],
        "delta_success_pp": comparisons["delta_success_percentage_points"],
        "paired_bootstrap95_pp": comparisons["paired_bootstrap95_pp"],
        "decision": "qualified_on_independent_cal_only" if source_ok and science_ok else "failed_or_inconclusive_on_cal",
        "limits": "real MuJoCo CPU physics on independent 100 cal worlds 229000-229099; no controller retuning; test/OOD unopened",
    }
    with (evidence / "qualification.json").open("x") as handle:
        json.dump(summary, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print(json.dumps(summary, sort_keys=True))
    return 0 if source_ok and science_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
