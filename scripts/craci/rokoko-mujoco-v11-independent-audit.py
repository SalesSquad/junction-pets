#!/usr/bin/env python3
"""Read-only independent V11 physics evidence reconstruction and science audit.

This neither trains nor executes a paid job. It checks the original 800 trial
rows and all original option transitions, including every public seven-action
mask and terminal 250-tick physical dwell goal.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import zipfile
import numpy as np


SOURCE = "ab6df4054ef6ed350b479469590a48046a0c0a68"
HARNESS = "b1938bee9dbca482f645b5dde3359de38e6c125e"
WORKLOAD = "rokoko-mujoco-v11-prospective"
ARTIFACT_ZIP_SHA256 = "bbf94c662fab3ac0efab3448c9e917dcce473a2644efc82a3f4835dd85792bae"
FIRST = 517000
ARMS = ("frozen_v5", "frozen_v6", "frozen_v8",
        "v10_loss_informed", "v11_goal_preserving")
PROOFS = ("manifest.json", "paired-readout.json", "source-integrity.json",
          "independent-qualification.json", "independent-positive-replay.json",
          "independent-clear-goal-replay.json")
ORIGINALS = ("training.json", "full_transitions.jsonl.gz")

class guard:
    """Independent, frozen replica of the public safety mask and sparse trace schema.

    Original ContactEnv.mask source blob:
    0ccf9bdf30571b8947bd0ab0cc14049a4b42008d.
    MovingContactEnv.mask source blob:
    80862713435a78443c524ae9374fd19140b23b46.
    This guard never receives private physics state or future actions.
    """

    @staticmethod
    def sparse_indices(n):
        return sorted(set(range(min(12, n))) |
                      set(range(max(0, n - 8), n)) |
                      set(range(0, n, 5)))

    @staticmethod
    def valid_obs(vec):
        return (isinstance(vec, list) and len(vec) == 18 and
                all(type(x) in (float, int) and math.isfinite(x) for x in vec))

    @staticmethod
    def public_mask(observation):
        o = np.asarray(observation, dtype=np.float32)
        goal = np.array([.16, 0.])
        allowed = np.ones(7, dtype=bool)
        if o[15] or not o[10] or not o[11] or o[8] > .1 or o[9] < .8:
            allowed[:6] = False
            return [int(x) for x in allowed]
        obj, obstacle = o[:2], o[6:8]
        v = goal - obj
        nearest = obj + np.clip(np.dot(obstacle - obj, v) /
                                max(np.dot(v, v), 1e-12), 0, 1) * v
        if np.linalg.norm(nearest - obstacle) < .060:
            allowed[:5] = False
        if np.linalg.norm(o[2:4] - obj) < .029:
            allowed[2] = False
        obj64 = np.asarray(o[:2], dtype=np.float64)
        obstacle64 = np.asarray(o[6:8], dtype=np.float64)
        to_goal = goal - obj64
        unit = to_goal / max(float(np.linalg.norm(to_goal)), 1e-9)
        nearest64 = obj64 + np.clip(np.dot(obstacle64 - obj64, to_goal) /
                                    max(np.dot(to_goal, to_goal), 1e-12), 0., 1.) * to_goal
        if float(np.linalg.norm(obstacle64 - nearest64)) < .060:
            lateral = np.array([-unit[1], unit[0]])
            for option in (0, 3, 4):
                destination = obj64 - (.041 if option == 0 else .024) * unit + (
                    0. if option == 0 else (.019 if option == 3 else -.019)) * lateral
                allowed[option] = bool(np.linalg.norm(destination - obstacle64) > .055)
        return [int(x) for x in allowed]


def demand(cond, reason):
    if not cond:
        raise AssertionError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def read(path):
    return json.loads(path.read_bytes())


def safe(row):
    return (row["success"] is True and row["unsafe"] is False and
            row["abstained"] is False)


def audit(extract: Path, artifact_zip: Path):
    demand(extract.is_dir() and artifact_zip.is_file(), "EXACT_RETAINED_DATA_MISSING")
    demand(sha(artifact_zip.read_bytes()) == ARTIFACT_ZIP_SHA256,
           "ORIGINAL_GITHUB_ARTIFACT_ZIP_SHA_DRIFT")
    receipt = read(extract / "receipt.json")
    capture = read(extract / "manifest.json")
    demand(receipt["status"] == "succeeded" and
           receipt["jobStatus"] == "success" and
           receipt["stageOutcome"] == "success" and
           receipt["sourceVerified"] is True and
           receipt["harnessVerified"] is True and
           receipt["binding"]["sourceSha"] == SOURCE and
           receipt["binding"]["harnessSha"] == HARNESS and
           receipt["binding"]["workload"] == WORKLOAD and
           receipt["command"]["exitCode"] == 0 and
           receipt.get("providerAttestationVerified") is False,
           "CRACI_SOURCE_BOUND_COMPLETE_PHYSICS_RECEIPT_REQUIRED")
    demand(sha((extract / "manifest.json").read_bytes()) ==
           receipt["manifest"]["sha256"] and capture["complete"] is True,
           "SIGNED_COLLECTOR_RECEIPT_NOT_CLAIMED")
    for f in capture["files"]:
        fpath = extract / f["path"]
        demand(fpath.is_file() and not fpath.is_symlink() and
               fpath.stat().st_size == f["bytes"] and
               sha(fpath.read_bytes()) == f["sha256"],
               "CAPTURED_FILE_BYTES_BAD_" + f["path"])

    product = extract / "artifacts" / WORKLOAD
    retention = read(product / "retention-manifest.json")
    original_manifest = read(product / "manifest.json")
    demand(retention["exact_source_sha"] ==
           original_manifest["executed_head"] == SOURCE and
           retention["original_manifest_sha256"] ==
           sha((product / "manifest.json").read_bytes()),
           "ORIGINAL_SOURCE_COMMIT_OR_MANIFEST_TAMPER")
    demand({x["name"] for x in retention["sources"]} == set(ORIGINALS) and
           set(retention["proof_sha256"]) == set(PROOFS) and
           set(original_manifest["file_sha256"]) ==
           set(ORIGINALS) | {"paired-readout.json"},
           "SOURCE_AND_PROOF_SET_NOT_COMPLETE")
    for name in PROOFS:
        demand(sha((product / name).read_bytes()) ==
               retention["proof_sha256"][name], "ORIGINAL_PROOF_HASH_BAD_" + name)
    total = sum((product / name).stat().st_size for name in PROOFS)
    raw = {}
    for original in retention["sources"]:
        pieces = []
        for part in original["parts"]:
            archive = product / part["archive"]
            packet = archive.read_bytes()
            demand(len(packet) == part["archive_bytes"] and
                   len(packet) < 20 * 1024 * 1024 and
                   sha(packet) == part["archive_sha256"],
                   "ZIP_PART_BAD_" + part["archive"])
            with zipfile.ZipFile(archive) as zipped:
                demand(zipped.namelist() == [part["entry"]],
                       "ZIP_MALFORMED_ENTRY")
                content = zipped.read(part["entry"])
            demand(len(content) == part["raw_bytes"] and
                   sha(content) == part["raw_sha256"],
                   "ZIP_CHUNK_HASH_INVALID")
            pieces.append(content)
            total += len(packet)
        full = b"".join(pieces)
        name = original["name"]
        demand(len(full) == original["original_bytes"] and
               sha(full) == original["original_sha256"] ==
               original_manifest["file_sha256"][name],
               "LOSSLESS_ORIGINAL_RECONSTRUCTION_BAD_" + name)
        raw[name] = full
    total += (product / "retention-manifest.json").stat().st_size
    demand(total < 63 * 1024 * 1024, "COLLECTOR_TOTAL_OVER_CAP")
    training = json.loads(raw["training.json"])
    readout = read(product / "paired-readout.json")
    qualification = read(product / "independent-qualification.json")
    integrity = read(product / "source-integrity.json")
    demand(training["executed_head"] == SOURCE and
           training["training_only"] is True and
           training["no_dev_test_ood"] is True and
           training["actual_physics_engine"] == "mujoco-3.3.7" and
           training["model_promotion_authorized"] is False and
           integrity["independent_physics_replay_complete"] is False and
           qualification["experiment_complete"] is True and
           qualification["independent_full_trace_public_mask_replay"] is True and
           qualification["all_512_real_initial_worlds_replayed"] is True and
           qualification["promotion_authorized"] is False and
           qualification["dev_cal_test_ood_opened"] is False and
           qualification["independent_true_physics_positive_replay"]["claim_verified"] is True and
           qualification["independent_true_physics_clear_goal_replay"]["claim_verified"] is True,
           "PHYSICAL_PROVENANCE_OR_PROMOTION_CLAIM_BAD")

    scans = training["all_512_public_initial_scans"]
    near, clear = [], []
    demand(len(scans) == 512, "FULL_512_PREOUTCOME_SCAN_MISSING")
    for i, scan in enumerate(scans):
        o = scan["observation"]
        demand(scan["seed"] == FIRST + i and guard.valid_obs(o) and
               scan["mask"] == guard.public_mask(o),
               "SOURCE_PUBLIC_INITIAL_SHIELD_SCAN_BAD")
        if abs(o[7]) < 0.122 and len(near) < 128:
            near.append(scan["seed"])
        if abs(o[7]) >= 0.122 and len(clear) < 32:
            clear.append(scan["seed"])
    demand(len(near) == 128 and len(clear) == 32, "CANDIDATE_COHORT_UNDERFILLED")
    cohort = {row["seed"]: row for row in training["cohort"]}
    demand(set(cohort) == set(near + clear) and
           [row["seed"] for row in training["cohort"]] == sorted(near + clear),
           "COHORT_CHERRYPICKED_OR_NOT_PUBLIC")
    rows = {}
    for row in training["trials"]:
        key = (row["seed"], row["strategy"])
        demand(key not in rows and key[0] in cohort and key[1] in ARMS and
               row["world_hash"] == cohort[key[0]]["world_hash"] and
               row["observed_corridor"] == cohort[key[0]]["observed_corridor"] and
               abs(row["initial_observed_obstacle_y"] -
                   cohort[key[0]]["initial_observed_obstacle_y"]) < 1e-5,
               "TRIALS_NOT_ON_IDENTICAL_PUBLIC_SOURCE_WORLDS")
        rows[key] = row
    demand(len(rows) == training["actual_trials"] == 800 and
           set(rows) == {(seed, arm) for seed in cohort for arm in ARMS},
           "FIVE_WAY_COMPLETE_PAIRED_800_REQUIRED")
    per = {name: Counter({"safe_goals": 0, "unsafe": 0,
                          "near_safe_goals": 0, "clear_safe_goals": 0})
           for name in ARMS}
    seen = set()
    option_count = 0
    with gzip.GzipFile(fileobj=__import__("io").BytesIO(
            raw["full_transitions.jsonl.gz"]), mode="rb") as original_stream:
        for line in original_stream:
            data = json.loads(line)
            key = (data["seed"], data["strategy"])
            demand(key in rows and key not in seen, "RAW_OPTION_DUPLICATE_OR_MISSING_KEY")
            seen.add(key)
            row = rows[key]
            events = data["transitions"]
            demand(1 <= len(events) <= 60 and
                   row["full_transition_count"] == row["option_steps"] == len(events) and
                   row["full_transition_sha256"] == sha(canonical(events)) and
                   row["sparse_transition_indices"] == guard.sparse_indices(len(events)) and
                   row["transitions"] ==
                   [events[i] for i in row["sparse_transition_indices"]],
                   "ORIGINAL_FULL_OPTION_DIGEST_OR_SPARSE_DRIFT")
            for j, ev in enumerate(events):
                o = ev["observation"]
                after = ev["next_observation"]
                demand(guard.valid_obs(o) and guard.valid_obs(after) and
                       ev["mask"] == guard.public_mask(o) and
                       0 <= ev["action"] < 7 and ev["mask"][ev["action"]] == 1 and
                       type(ev["cost"]) is int and ev["cost"] in (0, 1) and
                       ev["done"] is (j == len(events) - 1),
                       "FULL_18D_SEVEN_ACTION_SHIELD_OR_FINISH_DRIFT")
                if j:
                    demand(all(abs(float(a)-float(b)) < 1e-5 for a, b in
                               zip(events[j-1]["next_observation"], o)),
                           "PHYSICS_OBSERVATION_CHAIN_BROKEN")
            last = events[-1]
            demand(row["success"] == last["success_info"] and
                   row["unsafe"] == bool(any(e["cost"] for e in events)) and
                   row["contacts"] == last["contacts_cumulative"] and
                   abs(row["total_reward"] -
                       sum(e["reward"] for e in events)) < 1e-4,
                   "TRUE_MUJOCO_OUTCOME_NOT_FROM_RAW")
            if safe(row):
                o = last["next_observation"]
                demand(last["dwell_ticks_cumulative"] >= 250 and
                       last["contacts_cumulative"] > 0 and
                       math.hypot(o[0]-o[16], o[1]-o[17]) < 0.025 and
                       last["action"] != 6, "FAKE_PHYSICAL_250TICK_GOAL")
            per[key[1]]["safe_goals"] += int(safe(row))
            per[key[1]]["unsafe"] += int(row["unsafe"])
            per[key[1]]["near_safe_goals"] += int(safe(row) and row["observed_corridor"])
            per[key[1]]["clear_safe_goals"] += int(safe(row) and not row["observed_corridor"])
            option_count += len(events)
    demand(seen == set(rows) and
           option_count == training["actual_option_transitions"] ==
           qualification["actual_real_option_transitions"],
           "FULL_OPTION_STREAM_INCOMPLETE")
    for name in ARMS:
        demand(dict(per[name]) == readout["strategies"][name],
               "PER_ARM_SCIENCE_NOT_DERIVED_FROM_ORIGINAL_RAW_" + name)
    lost = sorted(seed for seed in cohort if safe(rows[seed, "frozen_v5"]) and
                  not safe(rows[seed, "v11_goal_preserving"]))
    novel = sorted(seed for seed in cohort if safe(rows[seed, "v11_goal_preserving"]) and
                   not safe(rows[seed, "frozen_v5"]))
    unsafe = sorted(seed for seed in cohort if rows[seed, "v11_goal_preserving"]["unsafe"])
    demand(lost == readout["lost_frozen_v5_goal_seed_ids"] and
           novel == readout["novel_v11_safe_goal_seed_ids"] and
           unsafe == readout["unsafe_v11_seed_ids"] and
           qualification["lost_v5_goal_seed_ids"] == lost and
           qualification["novel_v11_safe_goal_seed_ids"] == novel,
           "LEARNING_DELTA_NOT_FROM_ORIGINAL_PHYSICS")
    # Descriptive uncertainty only. Never use a TRAIN p-value to relabel a
    # negative result or turn a source-only hypothesis into a heldout win.
    discordant = len(lost) + len(novel)
    mcnemar_p = min(1.0, 2.0 * sum(math.comb(discordant, i)
                    for i in range(min(len(lost), len(novel)) + 1)) /
                    2 ** discordant) if discordant else 1.0
    public_seeds = sorted(cohort)
    paired_delta = {seed: int(safe(rows[seed, "v11_goal_preserving"])) -
                    int(safe(rows[seed, "frozen_v5"])) for seed in public_seeds}
    rng = random.Random(20261115)
    bootstrap = sorted(sum(paired_delta[public_seeds[rng.randrange(160)]]
                           for _ in range(160)) / 160 for _ in range(10_000))
    result = {
        "run_id": receipt["runId"], "artifact_zip_sha256": sha(artifact_zip.read_bytes()),
        "source_sha": SOURCE, "harness_sha": HARNESS, "worlds": len(cohort),
        "episodes": len(rows), "original_option_transitions": option_count,
        "losslessly_reassembled_original_sha256": {
            name: sha(raw[name]) for name in ORIGINALS},
        "per_arm": {name: dict(per[name]) for name in ARMS},
        "v11_novel_safe_goal_seeds": novel, "v11_lost_v5_goal_seeds": lost,
        "v11_unsafe_seed_ids": unsafe,
        "paired_safe_goal_delta_count": len(novel) - len(lost),
        "paired_safe_goal_delta_rate": (len(novel) - len(lost)) / 160,
        "paired_bootstrap_95pct_exploratory": [bootstrap[249], bootstrap[9749]],
        "mcnemar_exact_two_sided_exploratory_p": mcnemar_p,
        "science": ("NEW_TRAIN_CANDIDATE_FOR_INDEPENDENT_REVIEW" if
                    novel and not lost and not unsafe else
                    "NO_PROMOTION_NEGATIVE_TRAIN"),
        "provider_attestation_verified": False,
        "model_promotion_authorized": False,
        "physically_reexecuted_in_independent_scratch": False,
        "hosted_source_bound_physical_replay_reported": True,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("retained_extract", type=Path)
    parser.add_argument("original_artifact_zip", type=Path)
    arguments = parser.parse_args()
    audit(arguments.retained_extract, arguments.original_artifact_zip)
