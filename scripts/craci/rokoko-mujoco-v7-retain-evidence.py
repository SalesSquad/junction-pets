#!/usr/bin/env python3
"""Pack exact MuJoCo V7 raw evidence into collector-safe, independently checkable ZIP parts.

The generic CRACI collector deliberately admits only known extensions and caps
each artifact at 20 MiB and the entire payload at 63 MiB. Neither guard is
changed. This helper runs AFTER independent physics qualification but BEFORE
the collector; it retains both entire original raw files byte-for-byte in
small valid ZIP archives. Only verified originals are relocated to the
ephemeral same-job private directory; no user repository data is deleted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile

SOURCE_FILES = ("training.json", "full_transitions.jsonl.gz")
CHUNK_BYTES = 6 * 1024 * 1024
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_COLLECTOR_BYTES = 63 * 1024 * 1024
SCHEMA = "junction.rokoko.mujoco-v7-evidence-parts.v1"


def require(condition, reason):
    if not condition:
        raise AssertionError(reason)


def sha_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_root(folder: Path):
    folder = folder.resolve(strict=True)
    require(folder.is_dir() and not folder.is_symlink(), "EVIDENCE_ROOT_UNSAFE")
    return folder


def verify_parts(folder: Path, report: dict):
    require(report.get("schema") == SCHEMA, "EVIDENCE_PACK_SCHEMA")
    for source in report["sources"]:
        digest = hashlib.sha256()
        expected_total = 0
        for part in source["parts"]:
            name = part["archive"]
            require(Path(name).name == name and name.endswith(".zip"),
                    "EVIDENCE_PACK_PART_PATH")
            archive = folder / name
            require(archive.stat().st_size == part["archive_bytes"] and
                    sha_file(archive) == part["archive_sha256"],
                    "EVIDENCE_PACK_ARCHIVE_TAMPERED")
            with zipfile.ZipFile(archive, "r") as source_zip:
                require(source_zip.namelist() == [part["entry"]],
                        "EVIDENCE_PACK_ENTRY_MISMATCH")
                contents = source_zip.read(part["entry"])
            require(len(contents) == part["raw_bytes"] and
                    hashlib.sha256(contents).hexdigest() == part["raw_sha256"],
                    "EVIDENCE_PACK_RAW_CHUNK_TAMPERED")
            digest.update(contents)
            expected_total += len(contents)
        require(expected_total == source["original_bytes"] and
                digest.hexdigest() == source["original_sha256"],
                "EVIDENCE_PACK_REASSEMBLY_MISMATCH")
    return True


def restore_parts(archive_folder: Path, output_folder: Path):
    """Restore exact original byte streams for a later train-only learner.

    This never overwrites a file and does not relax the frozen source digest.
    It is intentionally separate from the evidence-producing CRACI workflow.
    """
    archive_folder = safe_root(archive_folder)
    report = json.loads((archive_folder / "retention-manifest.json").read_text(
        encoding="utf8"))
    require(verify_parts(archive_folder, report), "EVIDENCE_RESTORE_VERIFICATION_FAILED")
    require(not output_folder.exists(), "EVIDENCE_RESTORE_TARGET_EXISTS")
    output_folder.mkdir(mode=0o700, parents=True)
    for source in report["sources"]:
        filename = source["name"]
        require(filename in SOURCE_FILES, "EVIDENCE_RESTORE_UNKNOWN_SOURCE")
        with (output_folder / filename).open("xb") as dest:
            for part in source["parts"]:
                with zipfile.ZipFile(archive_folder / part["archive"], "r") as archive:
                    dest.write(archive.read(part["entry"]))
        require(sha_file(output_folder / filename) == source["original_sha256"],
                "EVIDENCE_RESTORE_SHA_MISMATCH")
    return report


def package_evidence(evidence_root: Path, staging_root: Path,
                     chunk_bytes: int = CHUNK_BYTES):
    root = safe_root(evidence_root)
    artifacts = safe_root(root / "artifacts" / "rokoko-mujoco-v7-feasibility")
    staging_root = staging_root.absolute()
    require(staging_root != root and not staging_root.is_relative_to(root),
            "PRIVATE_STAGING_MUST_BE_OUTSIDE_RECEIPT")
    require(0 < chunk_bytes <= CHUNK_BYTES, "CHUNK_BOUND_INVALID")
    manifest = json.loads((artifacts / "manifest.json").read_text(encoding="utf8"))
    expected = manifest["file_sha256"]
    require(set(expected) == set(SOURCE_FILES), "SOURCE_EVIDENCE_MANIFEST_FILES")
    require(not (artifacts / "retention-manifest.json").exists(),
            "EVIDENCE_ALREADY_PACKAGED")
    inputs = []
    for filename in SOURCE_FILES:
        file = artifacts / filename
        require(file.is_file() and not file.is_symlink(), "SOURCE_EVIDENCE_MISSING")
        actual = sha_file(file)
        require(actual == expected[filename], "SOURCE_EVIDENCE_SHA_MISMATCH")
        inputs.append((filename, file, file.stat().st_size, actual))
    # Conservative preflight: retained archive data plus existing small files
    # must fit under the current collector's global payload and count limits.
    original_sum = sum(item[2] for item in inputs)
    other = sum(p.stat().st_size for p in artifacts.iterdir()
                if p.is_file() and p.name not in SOURCE_FILES)
    chunks = sum((size + chunk_bytes - 1) // chunk_bytes for _, _, size, _ in inputs)
    require(chunks <= 64 and original_sum + other + chunks * 2048 <
            MAX_COLLECTOR_BYTES, "EVIDENCE_PACK_EXCEEDS_COLLECTOR_CAP")
    require(not staging_root.exists(), "PRIVATE_STAGING_EXISTS")
    staging_root.mkdir(mode=0o700, parents=True)
    report = {"schema": SCHEMA, "original_manifest_sha256":
              sha_file(artifacts / "manifest.json"),
              "exact_source_sha": manifest["executed_head"], "sources": []}
    for filename, path, original_bytes, checksum in inputs:
        parts = []
        with path.open("rb") as data:
            index = 0
            while segment := data.read(chunk_bytes):
                archive_name = f"{filename}.part{index:03d}.zip"
                archive = artifacts / archive_name
                entry = f"{filename}.part{index:03d}"
                require(not archive.exists(), "EVIDENCE_PACK_ARCHIVE_EXISTS")
                with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_STORED,
                                     allowZip64=False) as output:
                    output.writestr(entry, segment)
                actual_bytes = archive.stat().st_size
                require(actual_bytes < MAX_FILE_BYTES, "EVIDENCE_PACK_PART_TOO_LARGE")
                parts.append({"archive": archive_name, "entry": entry,
                              "archive_bytes": actual_bytes,
                              "archive_sha256": sha_file(archive),
                              "raw_bytes": len(segment),
                              "raw_sha256": hashlib.sha256(segment).hexdigest()})
                index += 1
        report["sources"].append({"name": filename, "original_bytes": original_bytes,
                                  "original_sha256": checksum, "parts": parts})
    verify_parts(artifacts, report)
    # Integrity has been verified *before* moving originals. If any subsequent
    # publication step fails, the original bytes remain available in staging
    # until this isolated job ends. Only collector-accepted ZIPs are published.
    for filename, path, _, _ in inputs:
        os.replace(path, staging_root / filename)
    (artifacts / "retention-manifest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    verify_parts(artifacts, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("pack", "restore"), default="pack")
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--private-staging", type=Path)
    parser.add_argument("--restore-output", type=Path)
    args = parser.parse_args()
    if args.mode == "pack":
        require(args.private_staging is not None and args.restore_output is None,
                "EVIDENCE_PACK_REQUIRED_STAGING")
        report = package_evidence(args.evidence_root, args.private_staging)
    else:
        require(args.restore_output is not None and args.private_staging is None,
                "EVIDENCE_RESTORE_REQUIRED_OUTPUT")
        report = restore_parts(args.evidence_root, args.restore_output)
    print(json.dumps({"retained_sources": len(report["sources"]),
                      "archive_parts": sum(len(item["parts"]) for item in report["sources"]),
                      "original_shas": {item["name"]: item["original_sha256"]
                                        for item in report["sources"]}}, sort_keys=True))


if __name__ == "__main__":
    main()
