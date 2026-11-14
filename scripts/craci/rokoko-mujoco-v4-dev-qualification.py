#!/usr/bin/env python3
"""MuJoCo v4 swept-lane safety on 70 fresh development worlds, separate from actual-physics smoke."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

SOURCE = "5be248192d6eb09d54068d5509784644d763006f"


def main() -> int:
    src = Path(os.environ["CRACI_SOURCE_ROOT"]).resolve()
    evidence = (Path(os.environ["CRACI_RECEIPT_DIR"]) / "artifacts" / "rokoko-mujoco-v4-dev").resolve()
    if evidence.exists():
        raise RuntimeError("NO_OVERWRITE_MUJOCO_V4_PROOF")
    evidence.mkdir(parents=True)
    observed = subprocess.check_output(["git", "-C", str(src), "rev-parse", "HEAD"], text=True).strip()
    if observed != SOURCE or os.environ["CRACI_SOURCE_SHA"] != SOURCE:
        raise RuntimeError("MUJOCO_V4_PIN_MISMATCH")
    python = Path(os.environ["RUNNER_TEMP"]) / "mujoco-venv/bin/python"
    if not python.is_file():
        raise RuntimeError("MUJOCO_VENV_MISSING")
    module = src / "solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v4"
    subprocess.run(
        [str(python), "-m", "unittest", "discover", "-v", "-s", str(module), "-p", "test_contract.py"],
        check=True, cwd=str(src),
    )
    destination = evidence / "dev-physics-v4.json"
    execution = subprocess.run([
        str(python), str(module / "run.py"), "--split", "dev", "--episodes", "70",
        "--seed-offset", "100", "--max-options", "60", "--require-git", "--expected-head", SOURCE,
        "--output", str(destination),
    ], cwd=str(src), check=False)
    if not destination.is_file():
        raise RuntimeError("MUJOCO_POLICY_SOURCE_RECEIPT_MISSING")
    obj = json.loads(destination.read_text())
    rows = obj["paired_worlds"]
    gate = obj["qualification"]
    comparisons = obj["summaries"]["safe_v4"]
    source_ok = (
        obj["schema"] == "rokoko-mujoco-real-physics-swept-lane-v4"
        and obj["actual_physics_engine"] == "mujoco-3.3.7"
        and obj["executed_head"] == SOURCE
        and obj["split"] == "dev" and obj["first_seed"] == 129100
        and obj["episodes"] == 70 and len(rows) == 70
        and all(
            len({record["world_hash"] for record in row.values()}) == 1
            and all(
                (record["physics_steps"] > 0 and record["zero_physics_abstain"] is False)
                or (
                    policy == "safe_v4"
                    and record["zero_physics_abstain"] is True
                    and record["physics_steps"] == 0
                    and record["option_steps"] == 1
                    and record["abstained"] is True
                    and record["success"] is False
                    and record["unsafe"] is False
                    and record["proposal_counts"] == {"ABSTAIN": 1}
                    and record["option_trace"] == [{
                        "option": 1, "proposed": "ABSTAIN", "allowed": True,
                        "progress_m": 0., "contacts_added": 0, "refusals_added": 0,
                    }]
                )
                for policy, record in row.items()
            )
            for row in rows
        )
        and all(
            obj["abstention_accounting"][policy]["zero_physics_abstained"] ==
            sum(int(row[policy]["zero_physics_abstain"]) for row in rows)
            for policy in ("constant", "risk_v3", "safe_v4")
        )
        and all(
            obj["abstention_accounting"][policy]["zero_physics_abstained"] == 0
            for policy in ("constant", "risk_v3")
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
    summary = {
        "schema": "junction.rokoko.mujoco-v4.craci.dev.v2",
        "source_sha": SOURCE,
        "actual_physics_source_verified": source_ok,
        "zero_physics_explicit_safe_abstentions": obj["abstention_accounting"]["safe_v4"]["zero_physics_abstained"],
        "zero_physics_refusals_are_not_physical_safety_proofs": True,
        "policy_scientific_gate_passed": science_ok,
        "teacher_baseline_negative_historical_run": 43627944236,
        "risk_v3_cal_negative_run": 43630816368,
        "v2_scientific_negative_run": 43628857595,
        "safe_v4_success": comparisons["candidate_success"],
        "constant_success": comparisons["constant_success"],
        "unsafe_v4": comparisons["candidate_unsafe"],
        "unsafe_constant": comparisons["constant_unsafe"],
        "unsafe_risk_v3": obj["summaries"]["risk_v3"]["candidate_unsafe"],
        "delta_success_pp": comparisons["delta_success_percentage_points"],
        "paired_bootstrap95_pp": comparisons["paired_bootstrap95_pp"],
        "decision": "qualified_on_dev_only" if source_ok and science_ok else "failed_or_inconclusive_on_dev",
        "limits": "real MuJoCo CPU physics on fresh 70 dev worlds 129100-129169; prior v4 attempt 129030-129099 exposed; exposed v3 calibration 229000-229099 excluded; test/OOD untouched",
    }
    with (evidence / "qualification.json").open("x") as handle:
        json.dump(summary, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print(json.dumps(summary, sort_keys=True))
    return 0 if source_ok and science_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
