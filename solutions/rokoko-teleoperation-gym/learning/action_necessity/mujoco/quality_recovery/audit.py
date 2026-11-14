#!/usr/bin/env python3
"""Read-only, exact-source Rokoko V8/V9 TRAIN action-degeneracy audit.

Does not fit models, step MuJoCo, modify a checkpoint, open heldouts, or
qualify safety. Accepts the pinned original GitHub evidence archive only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile

V8_ARCHIVE_SHA = "8e33c0b87a8e98cf3be2d4116a8bc4eca2e45efc3707e9fc8d385566319febb8"
V8_WEIGHTS_SHA = "07823dcc52ea85b64e18767e1b1af29e63e3236613598cb349610a6b4fd37dc1"
V9_CANDIDATE_SHA = "81734631d41428e029b3b308ca2e0d5cdf2485dd9ef3dae70794d69f4f5939ba"
V8_SOURCE_SHA = "87c91de52cef5c3e745115f737abc4ab8d654a32"
V8_HARNESS_SHA = "251f003b56b9eea1aff79568ad351f615acaee20"
V8_TRAINING_SHA = "af84ec8c6552383e29b8a8dd18ef237c8e3dfd3080729b16f445239618327965"
V8_RAW_SHA = "cbaeacd5a7a2a46a30e6b63afeb12614552da032b68e78a6a90fa7d75c49101a"
MODEL_SHA = "9dd1011cd267899da4b9205fb73bdd2f5a8453719b1003351a24a82a2743e0ea"
STRATEGIES = ("frozen_v5", "frozen_v6", "repeat_left", "v8_hierarchical")
PREFIX = "artifacts/rokoko-mujoco-v8-prospective/"
LIMITS = {"training.json": 19_922_944, "full_transitions.jsonl.gz": 8_000_000}


def require(ok: bool, label: str):
    if not ok:
        raise ValueError(label)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf8")


def _zip_member(archive: zipfile.ZipFile, name: str, limit: int) -> bytes:
    entry = archive.getinfo(name)
    require(0 < entry.file_size <= limit and not entry.is_dir(),
            "ARCHIVE_ENTRY_SIZE_OR_TYPE_INVALID")
    return archive.read(entry)


def read_original(archive_path: Path):
    require(sha(archive_path.read_bytes()) == V8_ARCHIVE_SHA,
            "ORIGINAL_GITHUB_ARTIFACT_SHA_MISMATCH")
    with zipfile.ZipFile(archive_path) as outer:
        manifest = json.loads(_zip_member(outer, PREFIX + "retention-manifest.json", 16_384))
        require(manifest.get("exact_source_sha") == V8_SOURCE_SHA,
                "RETAINED_SOURCE_SHA_MISMATCH")
        files = {}
        for record in manifest.get("sources", []):
            filename = record["name"]
            require(filename in LIMITS and filename not in files,
                    "UNEXPECTED_OR_DUPLICATE_RETAINED_SOURCE")
            chunks = []
            for part in record["parts"]:
                name = part["archive"]
                require(name.startswith(filename + ".part") and name.endswith(".zip"),
                        "UNEXPECTED_ZIP_PART")
                zipped = _zip_member(outer, PREFIX + name, LIMITS[filename])
                require(sha(zipped) == part["archive_sha256"],
                        "PART_ARCHIVE_SHA_MISMATCH")
                with zipfile.ZipFile(io.BytesIO(zipped)) as inner:
                    require(inner.namelist() == [part["entry"]],
                            "PART_ARCHIVE_ENTRY_INVALID")
                    chunk = _zip_member(inner, part["entry"], LIMITS[filename])
                require(len(chunk) == part["raw_bytes"] and sha(chunk) == part["raw_sha256"],
                        "PART_RAW_SHA_MISMATCH")
                chunks.append(chunk)
            raw = b"".join(chunks)
            require(len(raw) <= LIMITS[filename] and
                    len(raw) == record["original_bytes"] and
                    sha(raw) == record["original_sha256"],
                    "RESTORED_RAW_SHA_MISMATCH")
            files[filename] = raw
    require(set(files) == set(LIMITS) and
            sha(files["training.json"]) == V8_TRAINING_SHA and
            sha(files["full_transitions.jsonl.gz"]) == V8_RAW_SHA,
            "COMPLETE_EXACT_V8_EVIDENCE_REQUIRED")
    training = json.loads(files["training.json"])
    require(training["executed_head"] == V8_SOURCE_SHA and
            training["frozen_weights_sha256"] == MODEL_SHA and
            training["actual_transition_count"] == 29_923 and
            training["actual_trials"] == 640 and
            training["dev_cal_test_ood_opened"] is False and
            training["training_only"] is True and
            training["model_promotion_authorized"] is False,
            "ORIGINAL_TRAIN_ONLY_QUALIFICATION_INVALID")
    rows = training["trials"]
    require(len(rows) == 640 and len({(r["seed"], r["strategy"]) for r in rows}) == 640,
            "UNPAIRED_TRIAL_IDENTITIES")
    by_seed = defaultdict(dict)
    for row in rows:
        by_seed[row["seed"]][row["strategy"]] = row
    require(len(by_seed) == 160 and
            all(set(trials) == set(STRATEGIES) and
                len({row["world_hash"] for row in trials.values()}) == 1
                for trials in by_seed.values()),
            "PAIRED_WORLD_HASH_OR_STRATEGY_MISMATCH")
    return files["full_transitions.jsonl.gz"], rows


def load_weights(path: Path, expected_sha: str):
    data = path.read_bytes()
    require(sha(data) == expected_sha, "FROZEN_MODEL_FILE_SHA_MISMATCH")
    obj = json.loads(data)
    weights = obj["weights"]
    require(len(weights) == 4 and all(len(stage) == 41 and
            all(len(row) == 7 and all(type(x) in (int, float) and
            math.isfinite(x) for x in row) for row in stage)
            for stage in weights), "UNEXPECTED_MODEL_SHAPE_OR_NONFINITE")
    if expected_sha == V8_WEIGHTS_SHA:
        require(sha(canonical(obj)) == MODEL_SHA and
                obj["source_head"] == "4b91c64bc1a79bf630b1da6d12bea28e87c2990a",
                "V8_CHECKPOINT_MODEL_IDENTITY_MISMATCH")
    else:
        require(obj.get("ready_for_new_prospective_physics") is False and
                obj.get("deployment_authorized") is False,
                "V9_UNPROMOTED_RESEARCH_CHECKPOINT_REQUIRED")
    return weights


def action_from_weights(features, legal, weights):
    require(len(features) == 41 and len(legal) == 7 and
            all(type(x) in (int, float) and math.isfinite(x) for x in features) and
            all(type(x) is bool for x in legal) and any(legal),
            "INVALID_OBSERVATION_OR_LEGAL_MASK")
    require(len(weights) == 41 and
            all(len(row) == 7 and
                all(type(x) in (int, float) and math.isfinite(x) for x in row)
                for row in weights),
            "INVALID_MODEL_WEIGHT_MATRIX")
    scores = [
        sum(features[i] * weights[i][a] for i in range(41)) if legal[a] else -math.inf
        for a in range(7)
    ]
    require(all(math.isfinite(scores[a]) for a in range(7) if legal[a]),
            "NONFINITE_LEGAL_ACTION_SCORE")
    action = max(range(7), key=lambda i: scores[i])
    require(legal[action], "SCORER_SELECTED_MASKED_ACTION")
    return action


class PublicMemory:
    """Exact independent reconstruction of V8 PublicMemory public-state ABI."""
    def __init__(self):
        self.initial_y = None
        self.away_sign = 1.0
        self.ticks = 0
        self.side_steps = 0
        self.last = None

    def features(self, observation, mask):
        require(len(observation) == 18 and len(mask) == 7 and
                all(type(x) in (int, float) and math.isfinite(x)
                    for x in observation) and
                all(type(x) in (int, bool) and x in (0, 1) for x in mask),
                "INVALID_PUBLIC_18D_7MASK")
        legal = [bool(v) for v in mask]
        require(any(legal), "EMPTY_SAFETY_MASK")
        if self.initial_y is None:
            self.initial_y = float(observation[1])
            self.away_sign = -1.0 if observation[7] >= observation[1] else 1.0
        movement = (observation[1] - self.initial_y) * self.away_sign
        distance = math.hypot(observation[16] - observation[0],
                              observation[17] - observation[1])
        forward = legal[1] or legal[2]
        if distance < .035:
            stage = 3
        elif movement >= .010 and forward and self.side_steps:
            stage = 2
        elif movement >= .005 and self.side_steps:
            stage = 1
        else:
            stage = 0
        clip = lambda x, lo, hi: max(lo, min(hi, x))
        features = ([1.0] + [clip(float(x) * 4.0, -2.0, 2.0) for x in observation]
                    + [float(x) for x in legal]
                    + [float(self.last == j) for j in range(7)]
                    + [float(stage == j) for j in range(4)]
                    + [clip(movement * 20, -2.0, 2.0),
                       min(self.ticks, 60) / 60,
                       min(self.side_steps, 10) / 10,
                       clip(distance * 5, 0.0, 2.0)])
        require(len(features) == 41, "PUBLIC_MODEL_FEATURE_ABI_DRIFT")
        return stage, features, legal

    def remember(self, action):
        self.last = action
        self.side_steps += int(action in (3, 4))
        self.ticks += 1


def action_health(stage_counts, *, min_forward_legal=100):
    """Diagnostic only: not a proof of safety, utility, or scientific gain."""
    n = stage_counts["stage2_forward_legal"]
    selected = stage_counts["stage2_forward_selected"]
    return {"stage2_forward_legal": n,
            "stage2_forward_selected": selected,
            "stage2_left_selected": stage_counts["stage2_left_selected"],
            "degenerate_stage2": n >= min_forward_legal and selected == 0,
            "denominator": "observed public-option decisions on original V8 TRAIN traces"}


def audit(raw_gz: bytes, rows: list[dict], v8_weights, v9_weights=None):
    index = {(row["seed"], row["strategy"]): row for row in rows}
    seen = set()
    decisions = 0
    transitions = 0
    stats = {name: Counter() for name in ["v8", "v9_off_policy"]}
    stage_v8 = Counter()
    pair = defaultdict(dict)
    for row in rows:
        pair[row["seed"]][row["strategy"]] = row
    with gzip.GzipFile(fileobj=io.BytesIO(raw_gz)) as stream:
        for line in stream:
            doc = json.loads(line)
            key = (doc["seed"], doc["strategy"])
            require(key in index and key not in seen, "DUPLICATE_OR_UNKNOWN_RAW_TRIAL")
            seen.add(key)
            reference = index[key]
            events = doc["transitions"]
            require(len(events) == reference["full_transition_count"] and
                    sha(canonical(events)) == reference["full_transition_sha256"],
                    "ORIGINAL_OPTION_TRACE_SHA_MISMATCH")
            transitions += len(events)
            if doc["strategy"] != "v8_hierarchical":
                continue
            mem = PublicMemory()
            for event in events:
                stage, features, legal = mem.features(event["observation"], event["mask"])
                choice = action_from_weights(features, legal, v8_weights[stage])
                require(choice == event["action"],
                        "FROZEN_V8_ACTION_REPLAY_MISMATCH")
                stats["v8"][f"stage{stage}_actions"] += 1
                if stage == 2 and (legal[1] or legal[2]):
                    stats["v8"]["stage2_forward_legal"] += 1
                    stats["v8"]["stage2_forward_selected"] += int(choice in (1, 2))
                    stats["v8"]["stage2_left_selected"] += int(choice == 3)
                if v9_weights is not None:
                    projected = action_from_weights(features, legal, v9_weights[stage])
                    stats["v9_off_policy"][f"stage{stage}_actions"] += 1
                    if stage == 2 and (legal[1] or legal[2]):
                        stats["v9_off_policy"]["stage2_forward_legal"] += 1
                        stats["v9_off_policy"]["stage2_forward_selected"] += int(projected in (1, 2))
                        stats["v9_off_policy"]["stage2_left_selected"] += int(projected == 3)
                decisions += 1
                mem.remember(event["action"])
                stage_v8[stage] += 1
    require(len(seen) == 640 and transitions == 29_923 and decisions == 9_580,
            "FULL_EVIDENCE_REPLAY_COUNT_MISMATCH")
    near_seeds = [seed for seed, r in pair.items() if r["v8_hierarchical"]["observed_corridor"]]
    require(len(near_seeds) == 128, "NEAR_CORRIDOR_COUNT_MISMATCH")
    safe_v5 = {seed for seed in near_seeds if
               pair[seed]["frozen_v5"]["success"] and not pair[seed]["frozen_v5"]["unsafe"]}
    safe_v8 = {seed for seed in near_seeds if
               pair[seed]["v8_hierarchical"]["success"] and not pair[seed]["v8_hierarchical"]["unsafe"]}
    require(len(safe_v5) == 9 and not safe_v8, "HISTORICAL_V8_FAILURE_EVIDENCE_CHANGED")
    return {
        "schema": "rokoko.v8-v9.quality-recovery.audit.v1",
        "status": "SCIENCE_RED_DIAGNOSTIC_ONLY",
        "model_promotion_authorized": False,
        "physics_was_executed_by_this_audit": False,
        "new_training_or_heldout": False,
        "original_hosted_run": 43645486985,
        "original_harness_sha": V8_HARNESS_SHA,
        "original_product_sha": V8_SOURCE_SHA,
        "trials": len(seen),
        "full_option_transitions_verified": transitions,
        "frozen_v8_decisions_replayed": decisions,
        "v8_stages": {str(k): v for k, v in sorted(stage_v8.items())},
        "frozen_v5_safe_near_goals": len(safe_v5),
        "frozen_v8_safe_near_goals": len(safe_v8),
        "lost_v5_safe_goal_seeds": sorted(safe_v5 - safe_v8),
        "frozen_v8_action_health": action_health(stats["v8"]),
        "v9_on_v8_observations_off_policy_only":
            action_health(stats["v9_off_policy"]) if v9_weights is not None else None,
        "model_repair_required": action_health(stats["v8"])["degenerate_stage2"],
        "interpretation": (
            "A V9 projection on V8 observations reuses V8 action history; "
            "it is not a V9 closed-loop physics result or safety qualification."
        ),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifact", type=Path, required=True)
    p.add_argument("--v8-weights", type=Path, required=True)
    p.add_argument("--v9-weights", type=Path)
    p.add_argument("--output", type=Path, help="new JSON output path; will not overwrite")
    args = p.parse_args()
    raw, rows = read_original(args.artifact)
    v8_weights = load_weights(args.v8_weights, V8_WEIGHTS_SHA)
    v9_weights = (load_weights(args.v9_weights, V9_CANDIDATE_SHA)
                  if args.v9_weights else None)
    result = audit(raw, rows, v8_weights, v9_weights)
    data = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf8") as out:
            out.write(data)
    else:
        print(data, end="")


if __name__ == "__main__":
    main()
