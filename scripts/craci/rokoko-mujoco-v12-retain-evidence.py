#!/usr/bin/env python3
"""V12 private-first original TRAIN archive: lossless 6MiB ZIP parts.

Publish an independently replayed 144-episode original or explicitly marked
INCOMPLETE early STOP. Never show partial source as a qualified full run.
Unchanged CRACI original collector limits: 20MiB/file, 63MiB aggregate.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import shutil
import zipfile


SCHEMA = "junction.rokoko.v12-pilot-private-retention.v1"
ORIGINAL_SCHEMA = "junction.rokoko.v12.fresh-518000-pilot.v1"
COMPLETE_SOURCES = ("training.json", "full_transitions.jsonl.gz")
COMPLETE_PROOFS = ("manifest.json", "paired-readout.json",
                   "independent-qualification.json")
PARTIAL_SOURCES = ("partial_training.json", "full_transitions.jsonl.gz")
PARTIAL_PROOFS = ("early_stop.json",)
CHUNK_BYTES = 6 * 1024 * 1024
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_COLLECTOR_BYTES = 63 * 1024 * 1024
MAX_PARTS = 64


def require(ok, code):
    if not ok:
        raise AssertionError(code)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def safe_root(root):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(),
            "V12_PRIVATE_OR_COLLECTOR_ROOT_UNSAFE")
    return root.resolve(strict=True)


def json_file(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size < MAX_FILE_BYTES,
            "V12_MISSING_OR_UNBOUNDED_SOURCE_PROOF")
    return json.loads(path.read_text(encoding="utf8"))


def complete_source_proof(private):
    require(set(p.name for p in private.iterdir()) ==
            set(COMPLETE_SOURCES + COMPLETE_PROOFS),
            "V12_COMPLETE_EXACT_ORIGINALS_AND_REPLAY_PROOF_REQUIRED")
    manifest = json_file(private / "manifest.json")
    readout = json_file(private / "paired-readout.json")
    qualified = json_file(private / "independent-qualification.json")
    require(manifest.get("schema") == ORIGINAL_SCHEMA + ".manifest" and
            set(manifest.get("file_sha256", {})) ==
            {"training.json", "full_transitions.jsonl.gz", "paired-readout.json"} and
            manifest.get("actual_trials") == 144 and
            manifest.get("promotion_authorized") is False and
            readout.get("totalOriginalRealEpisodes") == 144 and
            readout.get("modelPromotionAuthorized") is False and
            readout.get("devCalTestOodOpened") is False and
            qualified.get("schema") == ORIGINAL_SCHEMA + ".independent-qualification" and
            qualified.get("executed_head") == manifest.get("executed_head") and
            qualified.get("actual_trials") == 144 and
            qualified.get("new_model_promotion_authorized") is False and
            qualified.get("dev_cal_test_ood_opened") is False and
            qualified.get("original_sha256") == manifest["file_sha256"] and
            qualified.get("full_144_real_episode_physics_replay", {}).get(
                "all_512_public_initial_worlds_replayed") is True and
            qualified["full_144_real_episode_physics_replay"].get(
                "all_144_complete_real_episodes_replayed") is True and
            qualified["full_144_real_episode_physics_replay"].get(
                "claim_verified") is True,
            "V12_SOURCE_NOT_INDEPENDENTLY_TRUE_PHYSICS_QUALIFIED")
    require(all((private / n).is_file() and not (private / n).is_symlink()
                and sha(private / n) == expected
                for n, expected in manifest["file_sha256"].items()),
            "V12_COMPLETE_SOURCE_OR_READOUT_SHA_CHANGED")
    return manifest["executed_head"], manifest["file_sha256"]


def incomplete_source_proof(private):
    require(set(p.name for p in private.iterdir()) ==
            set(PARTIAL_SOURCES + PARTIAL_PROOFS),
            "V12_INCOMPLETE_PARTIAL_ORIGINALS_AND_STOP_ONLY")
    stop = json_file(private / "early_stop.json")
    partial = json_file(private / "partial_training.json")
    hashes = stop.get("raw_sha256", {})
    require(stop.get("schema") == ORIGINAL_SCHEMA + ".early-stop" and
            partial.get("schema") == ORIGINAL_SCHEMA + ".incomplete" and
            stop.get("status") == partial.get("status") == "INCOMPLETE_STOP" and
            stop.get("reason") == partial.get("stop_reason") and
            (stop.get("completed_episodes") != 144 or stop.get("reason") in (
                "CANDIDATE_LOST_ACTUAL_FROZEN_V5_GOAL",
                "OBSERVED_UNSAFE_ACTUAL_MUJOCO_COST")) and
            stop.get("executed_head") == partial.get("executed_head") and
            0 <= stop.get("completed_episodes", -1) <= 144 and
            stop.get("completed_episodes") ==
            partial.get("real_completed_episodes") ==
            len(partial.get("complete_real_trial_rows", [])) and
            stop.get("expected_episodes") == 144 and
            stop.get("promotion_authorized") is False and
            partial.get("promotion_authorized") is False and
            partial.get("no_automatic_retry_or_seed_fishing") is True and
            set(hashes) == set(PARTIAL_SOURCES) and
            all(sha(private / name) == hashes[name] for name in PARTIAL_SOURCES),
            "V12_PARTIAL_CANNOT_PRETEND_COMPLETE_ORIGINAL_RUN")
    # Every recorded completed option must remain exactly one distinct raw
    # trace even in an early STOP. No silently discarded failed-world row.
    rows = {(r["seed"], r["strategy"]): r for r in
            partial["complete_real_trial_rows"]}
    require(len(rows) == stop["completed_episodes"],
            "V12_INCOMPLETE_DUPLICATED_ORIGINAL_ROW")
    seen = set()
    count = 0
    with gzip.open(private / "full_transitions.jsonl.gz", "rt",
                   encoding="utf8") as stream:
        for line in stream:
            require(len(line) < 2 * 1024 * 1024,
                    "V12_INCOMPLETE_OVERSIZED_RAW_OPTION")
            data = json.loads(line)
            key = (data["seed"], data["strategy"])
            require(key in rows and key not in seen and
                    len(data["transitions"]) == rows[key]["full_transition_count"] and
                    all(len(t["mask"]) == 7 and t["mask"][t["action"]] == 1
                        for t in data["transitions"]),
                    "V12_INCOMPLETE_LOST_OR_SHIELD_ILLEGAL_REAL_EPISODE")
            seen.add(key)
            count += len(data["transitions"])
    require(seen == set(rows) and count == partial["raw_real_option_transitions"],
            "V12_INCOMPLETE_RAW_PARTIAL_TRACE_COUNT_DRIFT")
    return stop["executed_head"], hashes


def verify_reassembled(published, manifest):
    published = safe_root(published)
    require(manifest["schema"] == SCHEMA and
            manifest["status"] in ("COMPLETE_TRAIN_ONLY", "INCOMPLETE_STOP") and
            set(p.name for p in published.iterdir()) ==
            set(manifest["proof_sha256"]) | {"retention-manifest.json"} |
            {part["archive"] for src in manifest["sources"]
             for part in src["parts"]},
            "V12_COLLECTOR_EXACT_BOUNDED_SOURCE_SET_CHANGED")
    for name, expected in manifest["proof_sha256"].items():
        require(sha(published / name) == expected and
                (published / name).stat().st_size < MAX_FILE_BYTES,
                "V12_SMALL_SOURCE_PROOF_REBOUND_OR_OVERSIZED")
    require(len(manifest["sources"]) == 2 and
            set(src["name"] for src in manifest["sources"]) ==
            set(COMPLETE_SOURCES if manifest["status"] == "COMPLETE_TRAIN_ONLY"
                else PARTIAL_SOURCES),
            "V12_LOSSLESS_UNEXPECTED_PRIVATE_ORIGINAL_SET")
    size = sum((published / name).stat().st_size for name in
               manifest["proof_sha256"])
    parts = 0
    for src in manifest["sources"]:
        rebuilt = hashlib.sha256()
        raw_bytes = 0
        for part in src["parts"]:
            archive_name = part["archive"]
            require(Path(archive_name).name == archive_name and
                    archive_name.endswith(".zip"), "V12_UNSAFE_ZIP_PATH")
            archive = published / archive_name
            require(archive.is_file() and not archive.is_symlink() and
                    0 < archive.stat().st_size == part["archive_bytes"] < MAX_FILE_BYTES and
                    sha(archive) == part["archive_sha256"],
                    "V12_TAMPERED_OR_OVERLIMIT_ARCHIVE")
            with zipfile.ZipFile(archive, "r") as packed:
                require(packed.namelist() == [part["entry"]],
                        "V12_ZIP_UNEXPECTED_EXTRA_ORIGINAL_ENTRY")
                raw = packed.read(part["entry"])
            require(len(raw) == part["raw_bytes"] and
                    hashlib.sha256(raw).hexdigest() == part["raw_sha256"],
                    "V12_ZIP_PART_NOT_EXACT_RAW_BYTES")
            rebuilt.update(raw)
            raw_bytes += len(raw)
            parts += 1
            size += archive.stat().st_size
        require(raw_bytes == src["original_bytes"] and
                rebuilt.hexdigest() == src["original_sha256"] ==
                manifest["original_sha256"][src["name"]],
                "V12_ORIGINAL_SOURCE_SHA_LOSSLESS_REASSEMBLY_FAILED")
    size += (published / "retention-manifest.json").stat().st_size
    require(parts <= MAX_PARTS and size < MAX_COLLECTOR_BYTES,
            "V12_ORIGINAL_63M_64PARTS_COLLECTOR_CAP")
    return {"original_sha256": manifest["original_sha256"],
            "exact_source_sha": manifest["exact_source_sha"],
            "collector_bytes": size, "archives": parts}


def _publish(private, collector, status, sources, proofs, identity):
    private = safe_root(private)
    # Canonicalize existing parent aliases (/var -> /private/var on macOS) and
    # symlinks *before* enforcing source/collector directory separation.
    collector = Path(collector).resolve(strict=False)
    require(not collector.exists() and
            not collector.is_relative_to(private) and
            not private.is_relative_to(collector),
            "V12_COLLECTOR_MUST_BE_NEW_SEPARATE_PRIVATE_ORIGINAL_ROOT")
    source, hashes = identity(private)
    sizes = {(name): (private / name).stat().st_size for name in sources}
    chunks = sum((n + CHUNK_BYTES - 1) // CHUNK_BYTES for n in sizes.values())
    require(chunks <= MAX_PARTS and
            sum(sizes.values()) + sum((private / p).stat().st_size for p in proofs) +
            chunks * 2048 < MAX_COLLECTOR_BYTES,
            "V12_ORIGINAL_TOO_LARGE_FOR_UNCHANGED_COLLECTOR_CAP")
    collector.mkdir(parents=True, mode=0o700, exist_ok=False)
    for name in proofs:
        shutil.copyfile(private / name, collector / name)
        require(sha(collector / name) == sha(private / name) and
                (collector / name).stat().st_size < MAX_FILE_BYTES,
                "V12_SMALL_PROOF_BYTES_CHANGED_ON_COPY")
    retention = {"schema": SCHEMA, "status": status,
                 "exact_source_sha": source,
                 "original_sha256": hashes,
                 "proof_sha256": {name: sha(private / name) for name in proofs},
                 "sources": []}
    for name in sources:
        original_hash = hashlib.sha256()
        archive_parts = []
        with (private / name).open("rb") as stream:
            index = 0
            while raw := stream.read(CHUNK_BYTES):
                original_hash.update(raw)
                entry = f"{name}.part{index:03d}"
                archive_name = entry + ".zip"
                archive = collector / archive_name
                with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED,
                                     compresslevel=6, allowZip64=False) as packed:
                    packed.writestr(entry, raw)
                require(archive.stat().st_size < MAX_FILE_BYTES,
                        "V12_ARCHIVE_EXCEEDED_UNCHANGED_COLLECTOR_FILE_CAP")
                archive_parts.append({"archive": archive_name, "entry": entry,
                                      "archive_bytes": archive.stat().st_size,
                                      "archive_sha256": sha(archive),
                                      "raw_bytes": len(raw),
                                      "raw_sha256": hashlib.sha256(raw).hexdigest()})
                index += 1
        require(original_hash.hexdigest() == hashes[name],
                "V12_ORIGINAL_CHANGED_BEFORE_PACKING")
        retention["sources"].append({
            "name": name, "original_bytes": sizes[name],
            "original_sha256": original_hash.hexdigest(), "parts": archive_parts})
    with (collector / "retention-manifest.json").open("x", encoding="utf8") as file:
        json.dump(retention, file, sort_keys=True, indent=2)
        file.write("\n")
    checked = verify_reassembled(collector, retention)
    require(all(sha(private / name) == hashes[name] for name in sources),
            "V12_ORIGINAL_CHANGED_AFTER_PACKING")
    return checked


def publish_qualified(private, collector):
    return _publish(private, collector, "COMPLETE_TRAIN_ONLY",
                    COMPLETE_SOURCES, COMPLETE_PROOFS, complete_source_proof)


def publish_early_stop(private, collector):
    return _publish(private, collector, "INCOMPLETE_STOP",
                    PARTIAL_SOURCES, PARTIAL_PROOFS, incomplete_source_proof)
