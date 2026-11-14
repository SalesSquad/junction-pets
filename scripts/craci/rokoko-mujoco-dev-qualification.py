#!/usr/bin/env python3
"""Real MuJoCo 3.3.7 CRACI dev-only smoke; never opens heldout worlds."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

SOURCE_SHA = "cd7b2446c5f8d0e96761524f8a26a20ac4cbf44d"


def main() -> int:
    src = Path(os.environ["CRACI_SOURCE_ROOT"]).resolve()
    output = (Path(os.environ["CRACI_RECEIPT_DIR"]) / "artifacts" / "rokoko-mujoco").resolve()
    head = subprocess.check_output(["git", "-C", str(src), "rev-parse", "HEAD"], text=True).strip()
    if head != SOURCE_SHA or os.environ["CRACI_SOURCE_SHA"] != SOURCE_SHA:
        raise RuntimeError("MUJOCO_PINNED_SOURCE_MISMATCH")
    if output.exists():
        raise RuntimeError("REFUSE_TO_OVERWRITE_PHYSICS_EVIDENCE")
    output.mkdir(parents=True)
    python = Path(os.environ["RUNNER_TEMP"]) / "mujoco-venv/bin/python"
    if not python.is_file():
        raise RuntimeError("NO_ISOLATED_MUJOCO_VENV")
    module = src / "solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco"
    subprocess.run(
        [str(python), "-m", "unittest", "discover", "-v", "-s", str(module), "-p", "test_contract.py"],
        check=True, cwd=str(src),
    )
    subprocess.run([str(python), "-m", "pip", "freeze"], check=True)
    destination = output / "dev-physics.json"
    subprocess.run([
        str(python), str(module / "run.py"), "--split", "dev", "--episodes", "8",
        "--max-options", "60", "--require-git", "--expected-head", SOURCE_SHA,
        "--output", str(destination),
    ], check=True, cwd=str(src))
    result = json.loads(destination.read_text())
    rows = result["paired_worlds"]
    teacher = result["summaries"]["teacher"]
    paired = (
        result["schema"] == "rokoko-mujoco-cpu-action-necessity-v1"
        and result["actual_physics_engine"] == "mujoco-3.3.7"
        and result["executed_head"] == SOURCE_SHA
        and result["split"] == "dev"
        and result["first_seed"] == 129000
        and result["episodes"] == 8
        and len(rows) == 8
        and all(
            row["constant"]["world_hash"] == row["teacher"]["world_hash"]
            and row["constant"]["physics_steps"] > 0
            and row["teacher"]["physics_steps"] > 0
            for row in rows
        )
    )
    safe = teacher["candidate_unsafe"] <= teacher["constant_unsafe"]
    proof = {
        "schema": "junction.rokoko.mujoco.craci.dev.v1",
        "source_sha": SOURCE_SHA,
        "real_mujoco_3_3_7_confirmed": paired,
        "same_world_pairing_and_positive_mj_steps": paired,
        "teacher_unsafe_no_worse_than_constant": safe,
        "candidate_multi_action_episodes": teacher["candidate_multi_action_episodes"],
        "physics_steps": teacher["candidate_physics_steps"],
        "teacher_success": teacher["candidate_success"],
        "constant_success": teacher["constant_success"],
        "teacher_delta_pp": teacher["delta_success_percentage_points"],
        "result": "passed" if paired and safe else "failed",
        "scope": "8 synthetic dev worlds, true MuJoCo 2ms physics; not physical robot",
    }
    with (output / "qualification.json").open("x") as handle:
        json.dump(proof, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print(json.dumps(proof, sort_keys=True))
    return 0 if paired and safe else 1


if __name__ == "__main__":
    raise SystemExit(main())
