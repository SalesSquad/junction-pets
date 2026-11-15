#!/usr/bin/env python3
"""Describe actual RIGHT4 coverage in the pinned TRAIN archive; no physics."""

import argparse
import gzip
import hashlib
import io
import json
import zipfile
from pathlib import Path

ZIP_SHA = "45ff6ba157771a2a56c6139ec124a30f0fc0f26674fe97f00dd5d4c996e404e2"
PREFIX = "artifacts/rokoko-mujoco-v13-original/"
BASE = "frozen_v5"
ARMS = (
    BASE,
    "v12_phase_dwell_supported_actions",
    "train_only_right4_burst2",
    "train_only_right4_burst4",
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def audit(path):
    raw = path.read_bytes()
    require(digest(raw) == ZIP_SHA, "OUTER_SHA")
    originals = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        retention = json.loads(archive.read(PREFIX + "retention-manifest.json"))
        proof = json.loads(archive.read(PREFIX + "independent-qualification.json"))
        for source in retention["sources"]:
            chunks = []
            for part in source["parts"]:
                data = archive.read(PREFIX + part["archive"])
                require(digest(data) == part["archive_sha256"], "PART_ARCHIVE_SHA")
                with zipfile.ZipFile(io.BytesIO(data)) as nested:
                    chunk = nested.read(part["entry"])
                require(digest(chunk) == part["raw_sha256"], "PART_RAW_SHA")
                chunks.append(chunk)
            data = b"".join(chunks)
            require(
                digest(data) == source["original_sha256"]
                == retention["original_sha256"][source["name"]],
                "ORIGINAL_SHA",
            )
            originals[source["name"]] = data

    training = json.loads(originals["training.json"])
    traces = [
        json.loads(line)
        for line in gzip.decompress(originals["full_transitions.jsonl.gz"]).splitlines()
    ]
    rows = {(row["seed"], row["strategy"]): row for row in training["trials"]}
    by_arm = {(row["seed"], row["strategy"]): row["transitions"] for row in traces}
    require(
        len(training["trials"]) == len(traces) == len(rows) == len(by_arm) == 192
        and rows.keys() == by_arm.keys(),
        "PAIR_COUNT",
    )
    for key, trace in by_arm.items():
        data = json.dumps(
            trace, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
        require(digest(data) == rows[key]["full_transition_sha256"], "TRACE_SHA")

    worlds = {row["seed"]: row for row in training["cohort"]}
    instances = proof["full_192_real_episode_physics_replay"][
        "untrained_right4_actual_legal_instances"
    ]
    require(
        instances == training["observed_exploration_action4_instances"]
        and len(instances) == 149,
        "BURST_EVIDENCE",
    )
    active = {
        arm: {row["seed"] for row in instances if row["strategy"] == arm}
        for arm in ARMS
    }
    winners = {
        row["seed"]
        for row in training["trials"]
        if row["strategy"] == BASE and row["success"]
    }
    counts = {}
    for arm in ARMS:
        arm_rows = [row for row in training["trials"] if row["strategy"] == arm]
        changed = sum(
            [step["action"] for step in by_arm[(row["seed"], arm)]]
            != [step["action"] for step in by_arm[(row["seed"], BASE)]]
            for row in arm_rows
        )
        counts[arm] = {
            "worlds_with_active_right4": len(active[arm]),
            "active_right4_options": sum(row["strategy"] == arm for row in instances),
            "changed_action_sequence_worlds_vs_v5": changed,
            "abstained_episodes": sum(row["abstained"] for row in arm_rows),
            "abstained_near_episodes": sum(
                row["abstained"] and row["observed_corridor"] for row in arm_rows
            ),
        }

    active_worlds = active[ARMS[2]] | active[ARMS[3]]
    return {
        "run": 43666894721,
        "scope": "retrospective fixed TRAIN cohort; descriptive, not causal or safety qualification",
        "distinct_active_right4_worlds": len(active_worlds),
        "active_right4_near_worlds": sum(
            worlds[seed]["observed_corridor"] for seed in active_worlds
        ),
        "active_right4_clear_worlds": sum(
            not worlds[seed]["observed_corridor"] for seed in active_worlds
        ),
        "active_worlds_that_v5_won": len(active_worlds & winners),
        "burst_arms_active_in_same_worlds": active[ARMS[2]] == active[ARMS[3]],
        "by_arm": counts,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.archive)
    with args.output.open("x") as output:
        json.dump(result, output, sort_keys=True, indent=2)
        output.write("\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
