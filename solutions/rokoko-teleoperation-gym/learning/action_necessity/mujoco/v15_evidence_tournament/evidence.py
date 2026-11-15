"""Read-only, SHA-pinned original V12 MuJoCo evidence for an offline tournament.

All three *whole policies* were really executed in each original TRAIN world.
The reader never synthesizes an unexecuted option or interprets incomplete V13
as training data. This module cannot run physics, call an API, or send commands.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile


ORIGINAL_RUN = 43657058944
ORIGINAL_ARTIFACT = 14139070947
ORIGINAL_ZIP_SHA256 = "f2bed411c74bd99a4a622bd3ed1853a2542313ede8acc219b9f1d57c08729311"
ORIGINAL_PRODUCT_HEAD = "78f1b9de566dedf9ba3800ebee60fffa8ed0cc4f"
ORIGINAL_HARNESS_HEAD = "4874d15dd68d3a809aaf7d769d6b5bef85d378bd"
ORIGINAL_MODEL_SHA256 = "82cfa42ba2240aff6d00ec3e2b15c06d78386d3c0682986a23e478977f2dbf9e"
ORIGINAL_RAW_SHA256 = {
    "training.json": "cdc4d9d8729d61c730048c802579d25813dc45b55cf4e68d61d680840b7e7a2d",
    "full_transitions.jsonl.gz": "7e8d7c80cb8d035d904338e1a544662181a93933cc5c324458f7195c56f90b91",
}
V13_SHA_ONLY_MANIFEST_SHA256 = "5c3eae39e3a3bf6250c4713c42894034b1d27b64982b3e68c9c17e7f9d8c4d3a"
V13_UNSAFE_EVENT_SHA256 = "4702034192e3877e42278a1b297e9b8c787955fbe2a30e411dd06fd9a7fee4ba"
V5 = "frozen_v5"
PHASE = "v12_phase_dwell_supported_actions"
EXPLORATORY = "v12_right_side_action4_exploration_train_only"
STRATEGIES = (V5, PHASE, EXPLORATORY)
PREFIX = "artifacts/rokoko-mujoco-v12-pilot/"


def require(condition: bool, label: str) -> None:
    if not condition:
        raise ValueError(label)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: bytes, label: str):
    try:
        return json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"V15_INVALID_{label}_JSON") from exc


def _nested_original(outer: zipfile.ZipFile, source: dict) -> bytes:
    name = source["name"]
    require(name in ORIGINAL_RAW_SHA256, "V15_UNREVIEWED_RAW_NAME")
    parts = source["parts"]
    require(len(parts) == 1, "V15_UNEXPECTED_ORIGINAL_PART_COUNT")
    part = parts[0]
    require(part["archive"] == name + ".part000.zip" and
            part["entry"] == name + ".part000", "V15_ORIGINAL_PART_ENTRY_CHANGED")
    binary = outer.read(PREFIX + part["archive"])
    require(len(binary) == part["archive_bytes"] and
            sha256(binary) == part["archive_sha256"], "V15_ORIGINAL_PART_SHA_CHANGED")
    with zipfile.ZipFile(io.BytesIO(binary)) as inner:
        require(inner.namelist() == [part["entry"]], "V15_NESTED_ZIP_ENTRY_CHANGED")
        raw = inner.read(part["entry"])
    require(len(raw) == part["raw_bytes"] == source["original_bytes"] and
            sha256(raw) == part["raw_sha256"] == source["original_sha256"] ==
            ORIGINAL_RAW_SHA256[name], "V15_ORIGINAL_RAW_SHA_CHANGED")
    return raw


def _valid_observation(obs) -> bool:
    return (isinstance(obs, list) and len(obs) == 18 and
            all(type(x) in (float, int) and math.isfinite(x) for x in obs))


def _valid_mask(mask) -> bool:
    return (isinstance(mask, list) and len(mask) == 7 and
            all(type(x) is int and x in (0, 1) for x in mask) and any(mask))


def read_v12(archive: Path) -> dict:
    """Return exactly 48 paired TRAIN worlds and source hashes, no raw export.

    For inference, only `public_initial_observation` and original legal mask
    are allowed. `seed` and `outcomes` are provenance/training targets, never
    policy features. All outcomes are factual whole-policy physics runs.
    """
    archive = Path(archive)
    require(archive.is_file() and not archive.is_symlink(), "V15_ORIGINAL_ZIP_MISSING")
    require(sha256(archive.read_bytes()) == ORIGINAL_ZIP_SHA256,
            "V15_ORIGINAL_OUTER_ZIP_SHA_CHANGED")
    with zipfile.ZipFile(archive) as z:
        manifest = _json(z.read(PREFIX + "manifest.json"), "MANIFEST")
        retention = _json(z.read(PREFIX + "retention-manifest.json"), "RETENTION")
        receipt = _json(z.read("receipt.json"), "RECEIPT")
        qualification = _json(z.read(PREFIX + "independent-qualification.json"), "QUAL")
        readout = _json(z.read(PREFIX + "paired-readout.json"), "READOUT")
        require(retention["status"] == "COMPLETE_TRAIN_ONLY" and
                len(retention["sources"]) == 2 and
                {s["name"] for s in retention["sources"]} == set(ORIGINAL_RAW_SHA256) and
                retention["exact_source_sha"] == ORIGINAL_PRODUCT_HEAD and
                manifest["file_sha256"]["full_transitions.jsonl.gz"] ==
                ORIGINAL_RAW_SHA256["full_transitions.jsonl.gz"] and
                manifest["file_sha256"]["training.json"] ==
                ORIGINAL_RAW_SHA256["training.json"] and
                manifest["executed_head"] == ORIGINAL_PRODUCT_HEAD and
                manifest["model_sha256"] == ORIGINAL_MODEL_SHA256 and
                manifest["actual_trials"] == 144 and
                manifest["actual_option_transitions"] == 4228 and
                manifest["training_only"] is True and
                manifest["promotion_authorized"] is False,
                "V15_V12_MANIFEST_SOURCE_CHANGED")
        binding = receipt["binding"]
        require(receipt["status"] == "succeeded" and
                receipt["jobStatus"] == "success" and
                receipt["sourceVerified"] is True and
                receipt["harnessVerified"] is True and
                receipt["command"]["exitCode"] == 0 and
                binding["sourceSha"] == ORIGINAL_PRODUCT_HEAD and
                binding["harnessSha"] == ORIGINAL_HARNESS_HEAD and
                binding["workload"] == "rokoko-mujoco-v12-pilot" and
                qualification["experiment_complete"] is True and
                qualification["full_144_real_episode_physics_replay"]
                ["all_144_complete_real_episodes_replayed"] is True and
                qualification["original_sha256"]["training.json"] ==
                ORIGINAL_RAW_SHA256["training.json"] and
                readout["scienceDecision"] == "STOP" and
                readout["hardStopNoFurtherPhysics"] is True and
                readout["modelPromotionAuthorized"] is False,
                "V15_V12_QUALIFICATION_CHANGED")
        raws = {s["name"]: _nested_original(z, s) for s in retention["sources"]}
    data = _json(raws["training.json"], "TRAINING")
    raw_lines = gzip.decompress(raws["full_transitions.jsonl.gz"]).splitlines()
    traces = [_json(line, "TRANSITION") for line in raw_lines]
    require(data["actual_trials"] == len(data["trials"]) == len(traces) == 144 and
            data["actual_option_transitions"] == 4228 and
            data["executed_head"] == ORIGINAL_PRODUCT_HEAD and
            data["model_sha256"] == ORIGINAL_MODEL_SHA256 and
            data["training_only"] is True and
            data["no_dev_test_ood"] is True and
            data["model_promotion_authorized"] is False and
            tuple(data["strategies"]) == STRATEGIES and
            len(data["all_512_public_initial_scans"]) == 512 and
            len(data["cohort"]) == 48, "V15_V12_REAL_TRAINING_DRIFT")
    scans = {r["seed"]: r for r in data["all_512_public_initial_scans"]}
    require(len(scans) == 512, "V15_INITIAL_SCAN_DUPLICATES")
    cohort = {r["seed"]: r for r in data["cohort"]}
    require(len(cohort) == 48, "V15_COHORT_DUPLICATES")
    raw_trace_map = {}
    valid_options = 0
    for trace in traces:
        key = (trace["seed"], trace["strategy"])
        require(key not in raw_trace_map and trace["seed"] in cohort and
                trace["strategy"] in STRATEGIES, "V15_ORIGINAL_TRACE_DUPLICATE_OR_OOD")
        options = trace["transitions"]
        for step in options:
            obs, nobs, mask, action = (step["observation"],
                                      step["next_observation"],step["mask"],step["action"])
            require(_valid_observation(obs) and _valid_observation(nobs) and
                    _valid_mask(mask) and type(action) is int and
                    0 <= action < 7 and mask[action] == 1 and
                    type(step["cost"]) is int and step["cost"] >= 0,
                    "V15_NONPUBLIC_OR_ILLEGAL_ORIGINAL_OPTION")
        valid_options += len(options)
        raw_trace_map[key] = options
    require(len(raw_trace_map) == 144 and valid_options == 4228,
            "V15_ORIGINAL_OPTION_COUNT_DRIFT")
    trial_map = {}
    for row in data["trials"]:
        key = (row["seed"], row["strategy"])
        require(key not in trial_map and key in raw_trace_map and
                row["world_hash"] == cohort[row["seed"]]["world_hash"] and
                row["full_transition_count"] == len(raw_trace_map[key]) ==
                row["option_steps"] and
                type(row["success"]) is bool and type(row["unsafe"]) is bool and
                type(row["physics_steps"]) is int and row["physics_steps"] >= 0 and
                not row["unsafe"] and
                all(step["cost"] == 0 for step in raw_trace_map[key]),
                "V15_ORIGINAL_TRIAL_OR_SAFETY_DRIFT")
        trial_map[key] = row
    require(len(trial_map) == 144, "V15_INCOMPLETE_THREE_ARM_COHORT")
    worlds = []
    for seed, meta in sorted(cohort.items()):
        scan = scans[seed]
        obs, mask = scan["observation"], scan["mask"]
        require(_valid_observation(obs) and _valid_mask(mask) and
                scan["world_hash"] == meta["world_hash"] and
                mask == meta["initial_mask"] and
                abs(obs[7] - meta["initial_public_obstacle_y"]) < 1e-10 and
                bool(abs(obs[7]) < 0.122) == meta["observed_corridor"],
                "V15_INITIAL_PUBLIC_COHORT_MISMATCH")
        outcomes = {arm: {"safe_goal": bool(trial_map[seed, arm]["success"]),
                          "unsafe": bool(trial_map[seed, arm]["unsafe"]),
                          "options": int(trial_map[seed, arm]["option_steps"]),
                          "physics_ticks": int(trial_map[seed, arm]["physics_steps"])}
                    for arm in STRATEGIES}
        worlds.append({"seed": seed, "world_hash": meta["world_hash"],
                       "public_initial_observation": obs, "original_mask": mask,
                       "outcomes": outcomes})
    require(len(worlds) == 48, "V15_INCOMPLETE_ORIGINAL_WORLDS")
    return {"worlds": worlds, "actual_real_episodes": 144,
            "actual_mask_legal_options": valid_options,
            "original_zip_sha256": ORIGINAL_ZIP_SHA256,
            "original_training_sha256": ORIGINAL_RAW_SHA256["training.json"],
            "original_full_transitions_sha256": ORIGINAL_RAW_SHA256["full_transitions.jsonl.gz"],
            "original_product_head": ORIGINAL_PRODUCT_HEAD,
            "original_harness_head": ORIGINAL_HARNESS_HEAD}


def read_unsafe_v13_manifest(path: Path) -> dict:
    """The incomplete V13 run is a quarantine signature, NEVER a label source."""
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "V15_V13_PACKET_MISSING")
    raw = path.read_bytes()
    require(sha256(raw) == V13_SHA_ONLY_MANIFEST_SHA256,
            "V15_V13_PACKET_SHA_CHANGED")
    m = _json(raw, "V13_PACKET")
    bad = m["unsafe_terminal"]
    require(m["status"] == "INCOMPLETE_STOP" and
            m["safety_decision"] == "STOP_UNSAFE" and
            m["efficacy_qualified"] is False and
            m["model_promotion_authorized"] is False and
            m["unsafe_events"] == 1 and m["original_recorded_options"] == 394 and
            bad["transition_sha256"] == V13_UNSAFE_EVENT_SHA256 and
            bad["cost"] == 1 and bad["done"] is True,
            "V15_V13_UNSAFE_QUARANTINE_DRIFT")
    return {"source": "V13_INCOMPLETE_QUARANTINED",
            "manifest_sha256": V13_SHA_ONLY_MANIFEST_SHA256,
            "unsafe_transition_sha256": V13_UNSAFE_EVENT_SHA256,
            "training_rows_accepted": 0, "efficacy_rows_accepted": 0,
            "physics_dispatch_allowed": False}
