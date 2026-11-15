#!/usr/bin/env python3
"""Read-only retrospective V14 veto-count audit of SHA-pinned V12 TRAIN traces.

This does not run original physics, replay worlds, or produce counterfactual
outcomes.  It prints aggregate JSON only and does not persist raw observations.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile

from guard import decide


ORIGINAL_WORKFLOW_ARTIFACT_SHA = "f2bed411c74bd99a4a622bd3ed1853a2542313ede8acc219b9f1d57c08729311"
RAW_TRACE_SHA = "7e8d7c80cb8d035d904338e1a544662181a93933cc5c324458f7195c56f90b91"
RAW_TRAINING_SHA = "cdc4d9d8729d61c730048c802579d25813dc45b55cf4e68d61d680840b7e7a2d"
V5 = "frozen_v5"
ARM_NAMES = (
    V5, "v12_phase_dwell_supported_actions", "v12_right_side_action4_exploration_train_only",
)
ROOT = "artifacts/rokoko-mujoco-v12-pilot/"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_member(outer: zipfile.ZipFile, name: str, expected_sha: str) -> bytes:
    member = ROOT + name + ".part000.zip"
    if member not in outer.namelist():
        raise ValueError("V12_SOURCE_PINNED_PART_MISSING")
    part = outer.getinfo(member)
    if part.file_size > 10 * 1024 * 1024:
        raise ValueError("V12_PART_OUTER_UNEXPECTED_SIZE")
    with zipfile.ZipFile(io.BytesIO(outer.read(member))) as inner:
        entries = inner.infolist()
        entry_name = name + ".part000"
        if len(entries) != 1 or entries[0].filename != entry_name or entries[0].file_size > 10 * 1024 * 1024:
            raise ValueError("V12_PART_INNER_MEMBER_OR_SIZE_DRIFT")
        raw = inner.read(entry_name)
    if _digest(raw) != expected_sha:
        raise ValueError("V12_SOURCE_RAW_SHA_DRIFT")
    return raw


def load_original(archive: Path):
    archive = archive.resolve(strict=True)
    if not archive.is_file() or archive.is_symlink() or archive.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("V12_UNEXPECTED_ARTIFACT_SOURCE_OR_SIZE")
    if _digest(archive.read_bytes()) != ORIGINAL_WORKFLOW_ARTIFACT_SHA:
        raise ValueError("V12_WORKFLOW_ARTIFACT_SHA_DRIFT")
    with zipfile.ZipFile(archive) as outer:
        raw_trace = _safe_member(outer, "full_transitions.jsonl.gz", RAW_TRACE_SHA)
        raw_training = _safe_member(outer, "training.json", RAW_TRAINING_SHA)
    decompressed = gzip.decompress(raw_trace)
    if len(decompressed) > 32 * 1024 * 1024:
        raise ValueError("V12_TRACE_DECOMPRESSED_TOO_LARGE")
    episodes = [json.loads(line) for line in decompressed.splitlines()]
    training = json.loads(raw_training)
    if len(episodes) != 144 or len(training["trials"]) != 144 or training["actual_option_transitions"] != 4228:
        raise ValueError("V12_ORIGINAL_144x4228_COHORT_DRIFT")
    return episodes, training["trials"]


def summarize(episodes, metadata):
    source = {(e["seed"], e["strategy"]): e for e in episodes}
    rows = {(r["seed"], r["strategy"]): r for r in metadata}
    if set(source) != set(rows) or len(source) != 144:
        raise ValueError("V12_TRIAL_IDENTITY_DRIFT")
    for arm in ARM_NAMES:
        if sum(strategy == arm for seed, strategy in source) != 48:
            raise ValueError("V12_ARM_WORLDS_DRIFT")
    results = {}
    total_options = 0
    for arm in ARM_NAMES:
        tally = collections.Counter()
        causes = collections.Counter()
        for key, episode in source.items():
            if key[1] != arm:
                continue
            tally["worlds"] += 1
            originally_won = bool(rows[key]["success"])
            tally["original_winning_worlds"] += int(originally_won)
            decisions = []
            prior = None
            for step in episode["transitions"]:
                act = step["action"]
                if type(act) is not int or not 0 <= act <= 6 or step["mask"][act] != 1:
                    raise ValueError("V12_ORIGINAL_MASK_OR_ACTION_DRIFT")
                outcome = decide(step["observation"], step["mask"], act,
                                 previous_public18d=prior)
                prior = step["observation"]
                tally["original_options"] += 1
                total_options += 1
                if act == 6:
                    tally["original_abstains"] += 1
                else:
                    tally["original_motor_options"] += 1
                    veto = outcome.would_veto_requested
                    tally["shadow_motor_vetoes"] += int(veto)
                    if originally_won:
                        tally["winner_motor_options"] += 1
                        tally["winner_motor_vetoes"] += int(veto)
                    if veto:
                        causes.update(outcome.action_risks[act].causes)
                    decisions.append(veto)
            if any(decisions):
                tally["worlds_with_any_motor_veto"] += 1
                if originally_won:
                    tally["winning_worlds_with_any_motor_veto"] += 1
        results[arm] = {
            **{name: int(tally[name]) for name in (
                "worlds", "original_winning_worlds", "original_options",
                "original_abstains", "original_motor_options", "shadow_motor_vetoes",
                "worlds_with_any_motor_veto", "winner_motor_options", "winner_motor_vetoes",
                "winning_worlds_with_any_motor_veto")},
            "veto_reasons": dict(sorted(causes.items())),
        }
    if total_options != 4228 or results[V5]["original_winning_worlds"] != 12:
        raise ValueError("V12_OPTION_COUNTS_OR_WINNERS_DRIFT")
    return {
        "scope": "RETROSPECTIVE_PUBLIC18D_SHADOW_NO_COUNTERFACTUAL_PHYSICS_OR_EFFICACY",
        "cohort": "original V12 seen TRAIN 48 worlds x 3 original arms",
        "original_workflow_run": 43657058944,
        "original_artifact_sha256": ORIGINAL_WORKFLOW_ARTIFACT_SHA,
        "source_binding": "V13 product 0751d78b93855bf70820b03b0a543e123d218baf",
        "v14_candidate": "OOD-wide swept veto, no runtime bound overrides",
        "by_arm": results,
        "science_decision": "NOT_QUALIFIED_NO_NEW_PHYSICS",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path,
                        help="Local SHA-pinned original V12 GitHub retained artifact ZIP")
    args = parser.parse_args()
    episodes, metadata = load_original(args.artifact)
    print(json.dumps(summarize(episodes, metadata), sort_keys=True,
                     separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
