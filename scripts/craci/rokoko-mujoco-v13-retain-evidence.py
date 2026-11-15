#!/usr/bin/env python3
"""V13 original TRAIN-only forensic retention; exact SHA, 6MiB lossless parts.

This packer cannot turn a finite retrospective diagnostic into prospective
model qualification. It preserves all actually completed original MuJoCo
branches, and explicit incomplete STOPs, within unchanged CRACI collector caps.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import shutil
import zipfile


SCHEMA = "junction.rokoko.v13-private-lossless-retention.v1"
ORIGINAL_SCHEMA = "junction.rokoko.v13.actual-physics-causal-diagnostic.v1"
COMPLETE_SOURCES = ("training.json", "full_transitions.jsonl.gz",
                    "option_journal.jsonl.gz")
COMPLETE_PROOFS = ("manifest.json", "diagnostic-readout.json",
                   "independent-qualification.json")
PARTIAL_SOURCES = ("partial_training.json", "full_transitions.jsonl.gz",
                   "option_journal.jsonl.gz")
PARTIAL_PROOFS = ("early_stop.json",)
CHUNK_BYTES = 6 * 1024 * 1024
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_COLLECTOR_BYTES = 63 * 1024 * 1024
MAX_PARTS = 64
MAX_BRANCHES = 720
MAX_OPTION_EVENTS = MAX_BRANCHES * 60


def require(ok, code):
    if not ok:
        raise ValueError(code)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def safe_root(root):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "V13_RETENTION_UNSAFE_PRIVATE_OR_COLLECTOR_ROOT")
    return root.resolve(strict=True)


def read_json(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size < MAX_FILE_BYTES,
            "V13_RETENTION_SOURCE_PROOF_MISSING_OR_UNBOUNDED")
    return json.loads(path.read_text(encoding="utf8"))


def verify_original_evidence(private, complete):
    sources = COMPLETE_SOURCES if complete else PARTIAL_SOURCES
    proofs = COMPLETE_PROOFS if complete else PARTIAL_PROOFS
    require({p.name for p in private.iterdir()} == set(sources + proofs),
            "V13_RETENTION_EXACT_ORIGINALS_AND_PROOFS_ONLY")
    training = read_json(private / sources[0])
    require(training.get("schema") == ORIGINAL_SCHEMA + (
                ".training" if complete else ".incomplete") and
            training.get("training_only") is True and
            training.get("dev_cal_test_ood_opened") is False and
            training.get("model_promotion_authorized") is False and
            training.get("novel_prospective_goal_claim") is False and
            training.get("no_automatic_retry_or_seed_fishing") is True and
            training.get("source_v12_head") ==
                "78f1b9de566dedf9ba3800ebee60fffa8ed0cc4f" and
            training.get("source_v12_original_sha256") ==
                "7e8d7c80cb8d035d904338e1a544662181a93933cc5c324458f7195c56f90b91" and
            isinstance(training.get("recorded_branches"), int) and
            0 <= training["recorded_branches"] <= MAX_BRANCHES,
            "V13_RETENTION_TRAIN_ONLY_OR_PINNED_ORIGINAL_V12_SHA_CHANGED")
    require(training.get("status") == (
                "COMPLETE_TRAIN_DIAGNOSTIC_ONLY" if complete else "INCOMPLETE_STOP"),
            "V13_RETENTION_CANNOT_MISLABEL_PARTIAL_AS_COMPLETE")
    if complete:
        manifest = read_json(private / "manifest.json")
        readout = read_json(private / "diagnostic-readout.json")
        qualified = read_json(private / "independent-qualification.json")
        require(manifest.get("schema") == ORIGINAL_SCHEMA + ".manifest" and
                manifest.get("executed_head") == readout.get("executed_head") ==
                    training["executed_head"] and
                manifest.get("harness_head") == training["harness_head"] and
                manifest.get("actual_branch_episodes") ==
                    readout.get("raw_branch_count") == training["recorded_branches"] and
                manifest.get("actual_option_transitions") ==
                    training["recorded_real_options"] and
                manifest.get("complete_36_failed_seen_train_worlds") is True and
                manifest.get("no_prospective_goal_promotion") is True and
                qualified.get("schema") == ORIGINAL_SCHEMA +
                    ".independent-qualification" and
                qualified.get("all_36_seen_train_failure_worlds_physically_replayed") is True and
                qualified.get("all_raw_branches_independently_replayed") ==
                    training["recorded_branches"] and
                qualified.get("all_raw_original_physics_option_steps_replayed") ==
                    training["recorded_real_options"] and
                qualified.get("all_source_step_journal_events_matched_exact") ==
                    training["durably_journaled_all_executed_option_events"] ==
                    training["recorded_real_options"] and
                qualified.get("any_unsafe_actual_cost") is False and
                qualified.get("no_new_fresh_worlds_opened") is True and
                qualified.get("model_promotion_authorized") is False and
                set(manifest.get("file_sha256", {})) ==
                    {"training.json", "full_transitions.jsonl.gz",
                     "option_journal.jsonl.gz", "diagnostic-readout.json"} and
                all(sha(private / name) == expected for name, expected
                    in manifest["file_sha256"].items()),
                "V13_RETENTION_INDEPENDENT_FULL_PHYSICS_QUALIFICATION_NOT_PROVEN")
        expected_hashes = manifest["file_sha256"]
    else:
        stop = read_json(private / "early_stop.json")
        require(stop.get("schema") == ORIGINAL_SCHEMA + ".early-stop" and
                stop.get("status") == training["status"] and
                stop.get("recorded_branches") == training["recorded_branches"] and
                stop.get("recorded_real_options") == training["recorded_real_options"] and
                stop.get("durably_journaled_all_executed_option_events") ==
                    training["durably_journaled_all_executed_option_events"] and
                stop.get("model_promotion_authorized") is False and
                stop.get("reason") is not None and
                set(stop.get("raw_sha256", {})) == set(sources) and
                all(sha(private / name) == expected for name, expected in
                    stop["raw_sha256"].items()),
                "V13_RETENTION_INCOMPLETE_EVIDENCE_OR_STOP_CODE_MISSING")
        expected_hashes = stop["raw_sha256"]
    count = 0
    options = 0
    with gzip.open(private / "full_transitions.jsonl.gz", "rt", encoding="utf8") as stream:
        for line in stream:
            require(len(line) < 2 * 1024 * 1024 and count < MAX_BRANCHES,
                    "V13_RETENTION_OVERSIZE_OR_EXTRA_BRANCH")
            row = json.loads(line)
            require(row.get("branch_id") == count and
                    isinstance(row.get("seed"), int) and
                    518000 <= row["seed"] <= 518511 and
                    isinstance(row.get("actions"), list) and
                    isinstance(row.get("transitions"), list) and
                    len(row["actions"]) == len(row["transitions"]) and
                    0 < len(row["actions"]) <= 60 and
                    all(type(t.get("action")) is int and
                        len(t.get("mask", [])) == 7 and
                        t["mask"][t["action"]] == 1
                        for t in row["transitions"]),
                    "V13_RETENTION_LOST_OR_ILLEGAL_SEVEN_MASK_BRANCH")
            count += 1
            options += len(row["actions"])
    require(count == training["recorded_branches"] and
            options == training["recorded_real_options"] and
            0 <= options <= training["durably_journaled_all_executed_option_events"] <=
                MAX_OPTION_EVENTS and
            all(sha(private / name) == h for name, h in expected_hashes.items()),
            "V13_RETENTION_RAW_BRANCH_JOURNAL_COUNT_OR_SHA_DRIFT")
    step_count = 0
    step_branches = {}
    with gzip.open(private / "option_journal.jsonl.gz", "rt", encoding="utf8") as stream:
        for line in stream:
            require(len(line) < 2 * 1024 * 1024 and step_count < MAX_OPTION_EVENTS,
                    "V13_RETENTION_ORIGINAL_STEP_EVENT_TOO_LARGE_OR_OVER_BOUND")
            event = json.loads(line)
            require(event.get("schema") ==
                        "junction.rokoko.v13.finite-original-mujoco-causal-replay.v1.option-journal.v1" and
                    event.get("sourceOnlyUnattestedExecution") is True and
                    event.get("physicsQualificationPending") is True and
                    type(event.get("seed")) is int and
                    518000 <= event["seed"] <= 518511 and
                    type(event.get("branchId")) is str and
                    event["branchId"].startswith(f'v13-seen-train-{event["seed"]}-') and
                    event.get("optionIndexZeroBased") ==
                        step_branches.get(event["branchId"], 0) and
                    event.get("phase") in ("ORIGINAL_PREFIX", "COUNTERFACTUAL") and
                    isinstance(event.get("transition"), dict),
                    "V13_RETENTION_ORIGINAL_STEP_JOURNAL_CONTEXT_OR_ORDER_INVALID")
            step_branches[event["branchId"]] = (
                step_branches.get(event["branchId"], 0) + 1)
            require(step_branches[event["branchId"]] <= 60 and
                    event["transitionSha256"] == hashlib.sha256(
                        json.dumps(event["transition"], sort_keys=True,
                                   separators=(",", ":"), ensure_ascii=False,
                                   allow_nan=False).encode()).hexdigest() and
                    type(event["transition"].get("action")) is int and
                    len(event["transition"].get("mask", [])) == 7 and
                    event["transition"]["mask"][event["transition"]["action"]] == 1,
                    "V13_RETENTION_ORIGINAL_PER_OPTION_SHA_OR_SHIELD_INVALID")
            step_count += 1
    require(step_count == training["durably_journaled_all_executed_option_events"] and
            (not complete or step_count == options),
            "V13_RETENTION_MIDBRANCH_OPTIONS_OMITTED_OR_INVENTED")
    return training["executed_head"], {name: sha(private / name) for name in sources}


def verify_reassembled(collector, manifest):
    collector = safe_root(collector)
    require(manifest["schema"] == SCHEMA and
            manifest["status"] in ("COMPLETE_TRAIN_DIAGNOSTIC_ONLY", "INCOMPLETE_STOP") and
            {p.name for p in collector.iterdir()} ==
                set(manifest["proof_sha256"]) | {"retention-manifest.json"} |
                {part["archive"] for source in manifest["sources"]
                 for part in source["parts"]},
            "V13_RETENTION_COLLECTOR_UNKNOWN_OR_MISSING_PART")
    size = 0
    parts = 0
    for name, expected in manifest["proof_sha256"].items():
        file = collector / name
        require(file.is_file() and not file.is_symlink() and
                0 < file.stat().st_size < MAX_FILE_BYTES and sha(file) == expected,
                "V13_RETENTION_PROOF_SHA_CHANGED")
        size += file.stat().st_size
    require(len(manifest["sources"]) == 3 and
            {entry["name"] for entry in manifest["sources"]} ==
            set(COMPLETE_SOURCES if manifest["status"] ==
                "COMPLETE_TRAIN_DIAGNOSTIC_ONLY" else PARTIAL_SOURCES),
            "V13_RETENTION_SOURCE_SET_NOT_LOSSLESS")
    for source in manifest["sources"]:
        combined = hashlib.sha256()
        raw_bytes = 0
        require(source["parts"], "V13_RETENTION_EMPTY_ORIGINAL_PARTS")
        for part in source["parts"]:
            filename = part["archive"]
            require(Path(filename).name == filename and filename.endswith(".zip"),
                    "V13_RETENTION_ARCHIVE_PATH_TRAVERSAL")
            archive = collector / filename
            require(archive.is_file() and not archive.is_symlink() and
                    0 < archive.stat().st_size == part["archive_bytes"] < MAX_FILE_BYTES and
                    sha(archive) == part["archive_sha256"],
                    "V13_RETENTION_ARCHIVE_SHA_OR_SIZE_DRIFT")
            with zipfile.ZipFile(archive, "r") as package:
                require(package.namelist() == [part["entry"]],
                        "V13_RETENTION_EXTRA_PRIVATE_ZIP_MEMBER")
                data = package.read(part["entry"])
            require(len(data) == part["raw_bytes"] and
                    hashlib.sha256(data).hexdigest() == part["raw_sha256"],
                    "V13_RETENTION_CHUNK_BYTES_NOT_ORIGINAL")
            combined.update(data)
            raw_bytes += len(data)
            size += archive.stat().st_size
            parts += 1
        require(raw_bytes == source["original_bytes"] and
                combined.hexdigest() == source["original_sha256"] ==
                manifest["original_sha256"][source["name"]],
                "V13_RETENTION_PRIVATE_ORIGINAL_NOT_RECONSTRUCTIBLE_EXACT")
    size += (collector / "retention-manifest.json").stat().st_size
    require(parts <= MAX_PARTS and size < MAX_COLLECTOR_BYTES,
            "V13_RETENTION_UNCHANGED_63M_64PARTS_CAP")
    return {"exact_source_sha": manifest["exact_source_sha"],
            "original_sha256": manifest["original_sha256"],
            "collector_bytes": size, "archives": parts}


def publish(private_root, collector_root, *, complete):
    private = safe_root(private_root)
    collector = Path(collector_root).absolute()
    require(not collector.exists() and not collector.is_relative_to(private) and
            not private.is_relative_to(collector),
            "V13_RETENTION_PRIVATE_AND_COLLECTOR_SEPARATE_FRESH_ROOTS")
    source_sha, source_hashes = verify_original_evidence(private, complete)
    sources = COMPLETE_SOURCES if complete else PARTIAL_SOURCES
    proofs = COMPLETE_PROOFS if complete else PARTIAL_PROOFS
    count = sum(((private / name).stat().st_size + CHUNK_BYTES - 1) // CHUNK_BYTES
                for name in sources)
    require(count <= MAX_PARTS and
            sum((private / p).stat().st_size for p in (*sources, *proofs)) +
            count * 2048 < MAX_COLLECTOR_BYTES,
            "V13_RETENTION_ORIGINAL_LOSSLESS_SIZE_EXCEEDS_COLLECTOR")
    collector.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name in proofs:
        shutil.copyfile(private / name, collector / name)
        require(sha(private / name) == sha(collector / name),
                "V13_RETENTION_REBOUND_PROOF_BYTES")
    manifest = {"schema": SCHEMA,
                "status": "COMPLETE_TRAIN_DIAGNOSTIC_ONLY" if complete else
                          "INCOMPLETE_STOP",
                "exact_source_sha": source_sha, "original_sha256": source_hashes,
                "proof_sha256": {name: sha(private / name) for name in proofs},
                "sources": []}
    for name in sources:
        original_sha = hashlib.sha256()
        parts = []
        with (private / name).open("rb") as stream:
            index = 0
            while raw := stream.read(CHUNK_BYTES):
                original_sha.update(raw)
                entry = f"{name}.part{index:03d}"
                archive_name = entry + ".zip"
                target = collector / archive_name
                with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED,
                                     compresslevel=6, allowZip64=False) as zipf:
                    zipf.writestr(entry, raw)
                require(target.stat().st_size < MAX_FILE_BYTES,
                        "V13_RETENTION_CHUNK_BREACHED_20M_ORIGINAL_GATE")
                parts.append({"archive": archive_name, "entry": entry,
                              "archive_bytes": target.stat().st_size,
                              "archive_sha256": sha(target), "raw_bytes": len(raw),
                              "raw_sha256": hashlib.sha256(raw).hexdigest()})
                index += 1
        require(original_sha.hexdigest() == source_hashes[name],
                "V13_RETENTION_ORIGINAL_CHANGED_DURING_PACK")
        manifest["sources"].append({"name": name,
                                    "original_bytes": (private / name).stat().st_size,
                                    "original_sha256": source_hashes[name],
                                    "parts": parts})
    with (collector / "retention-manifest.json").open("x", encoding="utf8") as out:
        json.dump(manifest, out, sort_keys=True, indent=2)
        out.write("\n")
    result = verify_reassembled(collector, manifest)
    require(all(sha(private / name) == h for name, h in source_hashes.items()),
            "V13_RETENTION_ORIGINAL_CHANGED_AFTER_VERIFIED_LOSSLESS_PACK")
    return result
