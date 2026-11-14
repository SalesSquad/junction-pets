#!/usr/bin/env python3
"""Independent, source-bound SAME-WORLD comparison without winner promotion."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

V2 = "f96788807c262b2233f034c045df4373cb3c428c"
TD = "f7b512d93ca46e6ddf7204f62f118eee800f285b"
EXPERIMENT = "dc6fbe5434fbd28ccf5a50eafbe4c3c5fde36b7e"
SPLITS = (("locked_test", "test", 327000, 500), ("locked_ood", "ood", 427000, 300))


def verified_checkout(root: Path, expected: str) -> None:
    observed = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if observed != expected:
        raise RuntimeError("DUAL_SOURCE_COMMIT_MISMATCH")
    changed = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=no"], text=True).strip()
    if changed:
        raise RuntimeError("UNEXPECTED_TRACKED_SOURCE_OVERLAY")


def main() -> int:
    source = Path(os.environ["CRACI_SOURCE_ROOT"]).resolve()
    root = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    td = root / "comparator"
    experiment = root / "experiment"
    for src, expected in ((source, V2), (td, TD), (experiment, EXPERIMENT)):
        verified_checkout(src, expected)
    if os.environ["CRACI_SOURCE_SHA"] != V2:
        raise RuntimeError("PRIMARY_RECEIPT_SOURCE_PIN_MISMATCH")
    runner = experiment / "experiments/rokoko-headtohead/tournament.py"
    output = (Path(os.environ["CRACI_RECEIPT_DIR"]) / "artifacts" / "rokoko-shared").resolve()
    if output.exists():
        raise RuntimeError("REFUSE_OVERWRITE_TOURNAMENT_EVIDENCE")
    output.mkdir(parents=True)
    summary = {
        "schema": "junction.rokoko.headtohead.craci.qualification.v1",
        "exact_sources": {"v2": V2, "td": TD, "experiment": EXPERIMENT},
        "predeclared_worlds": True, "global_once_registry_enforced": False,
        "results": [], "provenance_passed": False,
        "interpretation": "descriptive paired contrast only, no model promotion",
    }
    for split, generator, first, count in SPLITS:
        destination = output / (split + ".json")
        try:
            subprocess.run(
                [sys.executable, str(runner), "--v2-root", str(source),
                 "--td-root", str(td), "--split", split,
                 "--episodes", str(count), "--confirm-lockbox",
                 "--output", str(destination)],
                check=True, cwd=str(experiment), env={**os.environ, "PYTHONHASHSEED": "0"},
            )
            value = json.loads(destination.read_text())
            data = value["result"]
            expected_seeds = list(range(first, first + count))
            valid = (
                value["schema"] == "junction.rokoko.shared-world-tournament.v1"
                and value["policy_sources"] == {"v2": V2, "td": TD}
                and value["weights_sha256"] == {
                    "v2": "1bab986c10be062cf87a4848916917cbab3a78b53e78cda8c2f8673f62d4cc55",
                    "td": "3868559e05f81e3148e34ebd99a7d874525e4ceba2ca942779628104d38fef28"}
                and value["frozen_split"] == split
                and data["generator"] == generator
                and data["seed_range"] == [first, first + count - 1]
                and data["episodes"] == count
                and [row["seed"] for row in data["world_fingerprints"]] == expected_seeds
                and all([row["seed"] for row in data["per_world"][policy]] == expected_seeds
                        for policy in ("v2", "td", "constant", "guarded_constant"))
                and data["v2_minus_td"]["success"]["units"] == "percentage_points"
            )
            summary["results"].append({
                "split": split, "episodes": count,
                "v2_success": data["summaries"]["v2"]["success"],
                "td_success": data["summaries"]["td"]["success"],
                "v2_unsafe": data["summaries"]["v2"]["unsafe"],
                "td_unsafe": data["summaries"]["td"]["unsafe"],
                "v2_minus_td_success_pp": data["v2_minus_td"]["success"]["a_minus_b_mean"],
                "v2_minus_td_paired95_pp": data["v2_minus_td"]["success"]["paired_bootstrap_95"],
                "same_world_provenance_verified": valid,
            })
        except Exception as exc:
            summary["results"].append({
                "split": split, "same_world_provenance_verified": False,
                "error_type": type(exc).__name__,
            })
            break
    summary["provenance_passed"] = (
        len(summary["results"]) == len(SPLITS)
        and all(row["same_world_provenance_verified"] for row in summary["results"])
    )
    with (output / "qualification.json").open("x") as handle:
        json.dump(summary, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["provenance_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
