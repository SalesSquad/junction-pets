#!/usr/bin/env python3
"""One-use independent source-pinned reward-driven Expected SARSA qualification.

Only CRACI may open these predeclared test/OOD windows. The frozen model
SHA comes from *prior* dev/cal runs, not this script's sealed outcomes.
All red evidence and per-world rows are preserved without tuning.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

SOURCE_SHA = "f7b512d93ca46e6ddf7204f62f118eee800f285b"
MODEL_SHA = "3868559e05f81e3148e34ebd99a7d874525e4ceba2ca942779628104d38fef28"
SPLITS = (("test", 325000, 300), ("ood", 425000, 200))


def main() -> int:
    src = Path(os.environ["CRACI_SOURCE_ROOT"]).resolve()
    output = (Path(os.environ["CRACI_RECEIPT_DIR"]) / "artifacts" / "rokoko-td").resolve()
    observed = subprocess.check_output(["git", "-C", str(src), "rev-parse", "HEAD"], text=True).strip()
    if observed != SOURCE_SHA or os.environ["CRACI_SOURCE_SHA"] != SOURCE_SHA:
        raise RuntimeError("FROZEN_REWARD_TD_SOURCE_MISMATCH")
    if output.exists():
        raise RuntimeError("REFUSE_OVERWRITE_LOCKBOX_EVIDENCE")
    output.mkdir(parents=True)
    runner = src / "solutions/rokoko-teleoperation-gym/learning/action_necessity/rl/td_agent.py"
    summary = {"schema": "junction.rokoko.td.craci.qualification.v1",
               "source_sha": SOURCE_SHA, "expected_weights_sha256": MODEL_SHA,
               "preregistered_seed_windows": True, "global_once_registry_enforced": False, "results": [], "all_criteria_passed": False}
    for split, first, count in SPLITS:
        destination = output / (split + ".json")
        try:
            subprocess.run(
                [sys.executable, str(runner), "--train-episodes", "6000",
                 "--eval-split", split, "--eval-episodes", str(count),
                 "--confirm-locked", "--output", str(destination)],
                check=True, cwd=str(src), env={**os.environ, "PYTHONHASHSEED": "0"},
            )
            result = json.loads(destination.read_text())
            evaluation = result["test"]
            comparison = result["comparison"]
            valid = (
                result["schema"] == "junction.rokoko.reward-driven-td.v1"
                and result["environment"] == "SYNTHETIC_2D_KINEMATICS_NOT_MUJOCO"
                and result["weights_sha256"] == MODEL_SHA
                and result["train"]["teacher_actions_seen"] == 0
                and result["train"]["worlds"] == 6000
                and result["train"]["train_seed_range"] == [122000, 127999]
                and evaluation["split"] == split
                and evaluation["seed_range"] == [first, first + count - 1]
                and len(evaluation["rows"]["learned"]) == count
                and len(evaluation["rows"]["constant"]) == count
                and len(evaluation["rows"]["guarded_constant"]) == count
                and comparison["predeclared_delta_pp"] == 15
                and all(value is True for key, value in comparison.items() if key != "predeclared_delta_pp")
                and evaluation["paired"]["delta_pp"] >= 15
                and evaluation["paired_guarded"]["delta_pp"] >= 15
                and evaluation["paired"]["paired_bootstrap_95_pp"][0] > 0
                and evaluation["paired_guarded"]["paired_bootstrap_95_pp"][0] > 0
                and evaluation["learned"]["unsafe"] <= evaluation["constant"]["unsafe"]
                and evaluation["learned"]["unsafe"] <= evaluation["guarded_constant"]["unsafe"]
            )
            summary["results"].append({
                "split": split, "seed_range": [first, first + count - 1],
                "episodes": count, "learned_success": evaluation["learned"]["success"],
                "null_success": evaluation["constant"]["success"],
                "same_guard_null_success": evaluation["guarded_constant"]["success"],
                "success_delta_pp": evaluation["paired"]["delta_pp"],
                "same_guard_delta_pp": evaluation["paired_guarded"]["delta_pp"],
                "learned_unsafe": evaluation["learned"]["unsafe"],
                "null_unsafe": evaluation["constant"]["unsafe"],
                "same_guard_null_unsafe": evaluation["guarded_constant"]["unsafe"],
                "weights_sha256": result["weights_sha256"], "locked_criterion_passed": valid,
            })
        except Exception as exc:
            summary["results"].append({
                "split": split, "locked_criterion_passed": False,
                "error_type": type(exc).__name__, "error_code": "RUN_OR_SCHEMA_FAILED",
            })
            break
    summary["all_criteria_passed"] = (
        len(summary["results"]) == len(SPLITS)
        and all(result["locked_criterion_passed"] for result in summary["results"])
    )
    with (output / "qualification.json").open("x") as handle:
        json.dump(summary, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print(json.dumps({**summary, "limit": "reward RL trained on synthetic 2D; no MuJoCo or hardware"}))
    return 0 if summary["all_criteria_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
