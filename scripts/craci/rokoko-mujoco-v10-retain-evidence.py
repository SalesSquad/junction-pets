#!/usr/bin/env python3
"""Publish V10 fully verified private originals as collector-safe exact ZIP parts.

No >20 MiB original ever appears beneath CRACI_RECEIPT_DIR.  The independent
MuJoCo qualifier first reads BOTH complete original streams in private runner
temp, then calls this packer.  Original bytes remain in the private source
directory until ephemeral job exit.  No truncation, reduction or thresholds.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import zipfile


SCHEMA = "junction.rokoko.mujoco-v10-private-verified-evidence-parts.v1"
MANIFEST_SCHEMA = "junction.rokoko.mujoco-v10.prospective-train.v1.manifest"
QUALIFIED_SCHEMA = "junction.rokoko.mujoco-v10-prospective.craci.train.v1"
SOURCE_FILES = ("training.json", "full_transitions.jsonl.gz")
PROOF_FILES = ("manifest.json", "paired-readout.json",
               "independent-qualification.json", "independent-positive-replay.json")
CHUNK_BYTES = 6 * 1024 * 1024
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_COLLECTOR_BYTES = 63 * 1024 * 1024
MAX_PARTS = 64


def require(ok, code):
    if not ok:
        raise AssertionError(code)


def sha_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_sha(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True,
                                     separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def safe_dir(path: Path):
    require(path.is_dir() and not path.is_symlink(), "V10_PRIVATE_EVIDENCE_ROOT_UNSAFE")
    return path.resolve(strict=True)


def source_proof(private: Path):
    require(set(p.name for p in private.iterdir()) == set(SOURCE_FILES + PROOF_FILES),
            "V10_PRIVATE_EXPECTED_FULL_SOURCE_AND_QUALIFICATION_ONLY")
    for name in SOURCE_FILES + PROOF_FILES:
        require((private / name).is_file() and not (private / name).is_symlink(),
                "V10_PRIVATE_EVIDENCE_FILE_INVALID")
    manifest = json.loads((private / "manifest.json").read_text(encoding="utf8"))
    qualified = json.loads((private / "independent-qualification.json").read_text(
        encoding="utf8"))
    replay = json.loads((private / "independent-positive-replay.json").read_text(
        encoding="utf8"))
    readout = json.loads((private / "paired-readout.json").read_text(encoding="utf8"))
    require(manifest.get("schema") == MANIFEST_SCHEMA and
            set(manifest.get("file_sha256", {})) == set(SOURCE_FILES) and
            manifest.get("auxiliary_file_sha256", {}).get("paired-readout.json") ==
            sha_file(private / "paired-readout.json") and
            qualified.get("schema") == QUALIFIED_SCHEMA and
            qualified.get("decision") == "valid_source_bound_five_way_train_only_evidence" and
            qualified.get("experiment_complete") is True and
            qualified.get("producer_exit_code") == 0 and
            qualified.get("independent_full_trace_public_mask_replay") is True and
            qualified.get("promotion_authorized") is False and
            qualified.get("dev_cal_test_ood_opened") is False and
            qualified.get("trials") == 800 and
            qualified.get("actual_real_option_transitions", 0) > 0 and
            qualified.get("full_transition_archive_sha256") ==
            manifest["file_sha256"]["full_transitions.jsonl.gz"] and
            qualified.get("dataset_sha256") == readout.get("dataset_sha256") and
            replay == qualified.get("independent_true_physics_positive_replay") and
            replay.get("claim_verified") is True and
            replay.get("model_promotion_authorized") is False and
            readout.get("model_promotion_authorized") is False and
            readout.get("executed_head") == manifest.get("executed_head") and
            qualified.get("exact_source_sha") == manifest.get("executed_head"),
            "V10_PRIVATE_UNQUALIFIED_OR_MISMATCHED_FULL_EVIDENCE")
    for name in SOURCE_FILES:
        require(sha_file(private / name) == manifest["file_sha256"][name],
                "V10_PRIVATE_UNCHANGED_RAW_MANIFEST_SHA_MISMATCH")
    return manifest


def verify_archive_parts(published: Path, report):
    published = safe_dir(published)
    require(report.get("schema") == SCHEMA and
            set(p.name for p in published.iterdir()) ==
            set(PROOF_FILES + ("retention-manifest.json",)) |
            {part["archive"] for src in report.get("sources", [])
             for part in src.get("parts", [])},
            "V10_PUBLISHED_UNEXPECTED_OR_MISSING_FILE")
    manifest_path = published / "manifest.json"
    require(sha_file(manifest_path) == report.get("original_manifest_sha256"),
            "V10_PUBLISHED_MANIFEST_REBINDING_INVALID")
    manifest = json.loads(manifest_path.read_text(encoding="utf8"))
    require(manifest.get("schema") == MANIFEST_SCHEMA and
            manifest.get("executed_head") == report.get("exact_source_sha") and
            set(manifest.get("file_sha256", {})) == set(SOURCE_FILES) and
            sorted(src.get("name") for src in report.get("sources", [])) ==
            sorted(SOURCE_FILES),
            "V10_PUBLISHED_SOURCE_PIN_OR_RAW_SET_MISMATCH")
    require(all((published / name).stat().st_size < MAX_FILE_BYTES
                for name in PROOF_FILES), "V10_PUBLISHED_PROOF_TOO_LARGE")
    require(sha_file(published / "paired-readout.json") ==
            manifest["auxiliary_file_sha256"]["paired-readout.json"],
            "V10_PUBLISHED_PAIRED_READOUT_SHA_DRIFT")
    parts = 0
    total = sum((published / name).stat().st_size for name in PROOF_FILES)
    for src in report["sources"]:
        require(src["name"] in SOURCE_FILES and
                src["original_sha256"] == manifest["file_sha256"][src["name"]],
                "V10_PUBLISHED_ORIGINAL_SOURCE_SHA_DRIFT")
        rebuilt_sha = hashlib.sha256()
        raw_bytes = 0
        for part in src["parts"]:
            archive_name = part["archive"]
            require(Path(archive_name).name == archive_name and
                    archive_name.endswith(".zip"),
                    "V10_PUBLISHED_UNSAFE_ARCHIVE_PATH")
            archive = published / archive_name
            require(archive.is_file() and not archive.is_symlink() and
                    archive.stat().st_size == part["archive_bytes"] and
                    0 < part["archive_bytes"] < MAX_FILE_BYTES and
                    sha_file(archive) == part["archive_sha256"],
                    "V10_PUBLISHED_ARCHIVE_BYTES_OR_SHA_INVALID")
            with zipfile.ZipFile(archive, "r") as packed:
                require(packed.namelist() == [part["entry"]],
                        "V10_PUBLISHED_ARCHIVE_ENTRY_CHANGED")
                content = packed.read(part["entry"])
            require(len(content) == part["raw_bytes"] and
                    hashlib.sha256(content).hexdigest() == part["raw_sha256"],
                    "V10_PUBLISHED_RAW_CHUNK_CHANGED")
            rebuilt_sha.update(content)
            raw_bytes += len(content)
            total += archive.stat().st_size
            parts += 1
        require(raw_bytes == src["original_bytes"] and
                rebuilt_sha.hexdigest() == src["original_sha256"],
                "V10_PUBLISHED_LOSSLESS_REASSEMBLY_FAILED")
    total += (published / "retention-manifest.json").stat().st_size
    require(parts <= MAX_PARTS and total < MAX_COLLECTOR_BYTES,
            "V10_COLLECTOR_63M_TOTAL_OR_64_PARTS_BOUND_INVALID")
    return {"source_count": len(report["sources"]), "archives": parts,
            "collector_bytes": total}


def publish_private_source(private: Path, collector: Path):
    private = safe_dir(private)
    collector = collector.absolute()
    require(not collector.exists() and not collector.is_relative_to(private) and
            not private.is_relative_to(collector),
            "V10_COLLECTOR_MUST_BE_SEPARATE_FRESH_EVIDENCE_TREE")
    manifest = source_proof(private)
    source_sizes = {name: (private / name).stat().st_size for name in SOURCE_FILES}
    proof_sizes = sum((private / name).stat().st_size for name in PROOF_FILES)
    chunks = sum((size + CHUNK_BYTES - 1) // CHUNK_BYTES for size in source_sizes.values())
    require(chunks <= MAX_PARTS and
            sum(source_sizes.values()) + proof_sizes + chunks * 2048 <
            MAX_COLLECTOR_BYTES,
            "V10_PRIVATE_SOURCE_TOO_LARGE_FOR_ORIGINAL_COLLECTOR_CAP")
    collector.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name in PROOF_FILES:
        dest = collector / name
        shutil.copyfile(private / name, dest)
        require(dest.stat().st_size < MAX_FILE_BYTES and
                sha_file(dest) == sha_file(private / name),
                "V10_SMALL_INDEPENDENT_PROOF_PUBLISH_CHANGED")
    report = {"schema": SCHEMA,
              "original_manifest_sha256": sha_file(private / "manifest.json"),
              "exact_source_sha": manifest["executed_head"],
              "sources": []}
    for name in SOURCE_FILES:
        checksum = hashlib.sha256()
        parts = []
        with (private / name).open("rb") as source:
            index = 0
            while block := source.read(CHUNK_BYTES):
                checksum.update(block)
                archive_name = f"{name}.part{index:03d}.zip"
                entry_name = f"{name}.part{index:03d}"
                archive = collector / archive_name
                with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED,
                                     compresslevel=6, allowZip64=False) as file:
                    file.writestr(entry_name, block)
                require(archive.stat().st_size < MAX_FILE_BYTES,
                        "V10_ORIGINAL_COLLECTOR_FILE_CAP_VIOLATED")
                parts.append({"archive": archive_name, "entry": entry_name,
                              "archive_bytes": archive.stat().st_size,
                              "archive_sha256": sha_file(archive),
                              "raw_bytes": len(block),
                              "raw_sha256": hashlib.sha256(block).hexdigest()})
                index += 1
        require(checksum.hexdigest() == manifest["file_sha256"][name],
                "V10_PRIVATE_SOURCE_CHANGED_DURING_PACKAGING")
        report["sources"].append({"name": name,
                                  "original_bytes": source_sizes[name],
                                  "original_sha256": checksum.hexdigest(),
                                  "parts": parts})
    with (collector / "retention-manifest.json").open("x", encoding="utf8") as file:
        json.dump(report, file, sort_keys=True, indent=2)
        file.write("\n")
    check = verify_archive_parts(collector, report)
    # Both full originals remain in the private runner temp. Nothing is
    # renamed, deleted or mutated to fake a green collector outcome.
    require(all((private / name).is_file() and
                sha_file(private / name) == manifest["file_sha256"][name]
                for name in SOURCE_FILES),
            "V10_PRIVATE_SOURCE_NOT_RETAINED_AFTER_PACKAGING")
    return {"schema": SCHEMA, **check,
            "exact_source_sha": manifest["executed_head"],
            "original_sha256": manifest["file_sha256"]}
