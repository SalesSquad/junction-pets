#!/usr/bin/env python3
"""Independent source/CSV/paired-shard verification for synthetic MuJoCo runs."""
from __future__ import annotations
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
PRODUCT = HERE.parent
REPO = PRODUCT.parent.parent
RESULTS = HERE / "results"
REPORT = HERE / "report"
POLICIES = {
    "aligned_replay", "contact_feedback", "guarded_feedback", "safe_abstain"
}
PINNED_ADDITIONAL_SOURCE = (
    "src/retarget.mjs", "src/csv.mjs", "src/engine.mjs",
    "sim/experiment.py", "sim/scene.xml",
    "fixtures/synthetic-retarget.csv", "fixtures/retarget-map.json",
    "mega/experiment.py"
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked_file(rel, expected):
    if rel.startswith("/") or ".." in Path(rel).parts:
        raise ValueError("Unsafe source path")
    target = (PRODUCT / rel).resolve()
    if not target.is_relative_to(PRODUCT.resolve()):
        raise ValueError("Source path leaves product scope")
    actual = sha(target.read_bytes())
    if actual != expected:
        raise ValueError(f"Source bytes differ for {rel}")


def main():
    manifests = sorted(RESULTS.glob("campaign-shard-*.manifest.json"))
    if not manifests:
        raise RuntimeError("No completed physics manifests")
    meta = [json.loads(p.read_text()) for p in manifests]
    expected_count = meta[0]["total_case_plan"]
    n_shards = meta[0]["shards"]
    seed_base = meta[0]["seed_base"]
    source_commit = meta[0]["source_commit"]
    assert len(meta) == n_shards
    assert sorted(m["local_shard"] for m in meta) == list(range(n_shards))
    assert all(
        m["source_commit"] == source_commit and
        m["total_case_plan"] == expected_count and
        m["shards"] == n_shards and
        m["seed_base"] == seed_base and
        m["source_sha256"] == meta[0]["source_sha256"]
        for m in meta
    )
    for rel, expected in meta[0]["source_sha256"].items():
        checked_file(rel, expected)
    ledger = {}
    for rel in PINNED_ADDITIONAL_SOURCE:
        current = (PRODUCT / rel).read_bytes()
        archived = subprocess.check_output(
            ["git", "show", f"{source_commit}:solutions/rokoko-teleoperation-gym/{rel}"],
            cwd=REPO
        )
        if current != archived:
            raise RuntimeError(f"Source changed from pinned Git commit: {rel}")
        ledger[rel] = sha(current)
    all_cases = set()
    total_rows = 0
    raw_hashes = {}
    for m in meta:
        idx = m["local_shard"]
        p = RESULTS / f"campaign-shard-{idx}.csv"
        assert p.exists() and sha(p.read_bytes()) == m["raw_csv_sha256"]
        raw_hashes[p.name] = m["raw_csv_sha256"]
        local_cases: dict[int, set[str]] = {}
        with p.open(newline="", encoding="utf8") as f:
            for row in csv.DictReader(f):
                case = int(row["case_id"])
                seed = int(row["seed"])
                if case % n_shards != idx or seed != seed_base + case:
                    raise RuntimeError(f"Unpaired seed/shard in {p.name}")
                if case in all_cases:
                    raise RuntimeError("Cross-shard case collision")
                local_cases.setdefault(case, set()).add(row["policy"])
                total_rows += 1
        if any(v != POLICIES for v in local_cases.values()):
            raise RuntimeError(f"Missing/duplicated policy in {p.name}")
        assert len(local_cases) == m["actual_independent_scenarios"]
        assert total_rows <= expected_count * len(POLICIES)
        all_cases.update(local_cases)
    if all_cases != set(range(expected_count)):
        raise RuntimeError("Missing or unexpected physics scenario IDs")
    assert total_rows == expected_count * len(POLICIES)
    receipt = {
        "schema": "motionbridge.megasim.source-verified.v1",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit_during_run": source_commit,
        "actual_unique_scenarios": len(all_cases),
        "actual_physics_episodes": total_rows,
        "actual_solver_steps": total_rows * 3000,
        "all_shards_complete": True,
        "all_source_bytes_equal_pinned_commit": True,
        "model_inference_calls_during_physics": 0,
        "physical_hardware_calls": 0,
        "input_truth_label": "UNVERIFIED_REPLAY_SYNTHETIC",
        "source_sha256_ledger": ledger,
        "raw_csv_sha256": raw_hashes,
        "qualification": "SYNTHETIC_MUJOCO_ONLY_NOT_HARDWARE_OR_RL"
    }
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "source_verification.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf8"
    )
    print(json.dumps({
        k: receipt[k] for k in (
            "source_commit_during_run", "actual_unique_scenarios",
            "actual_physics_episodes", "actual_solver_steps",
            "all_source_bytes_equal_pinned_commit"
        )
    }))


if __name__ == "__main__":
    main()
