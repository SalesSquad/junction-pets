#!/usr/bin/env python3
"""Bind full hybrid raw data to *existing* CRACI safe ZIP-part packaging.

The already-reviewed V7 packer keeps its 6MiB chunks, 20MiB per artifact,
63MiB total budget and immutable original SHA reassembly. This adapter only
declares the hybrid's exact three source files and distinct evidence schema.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


NAME = "rokoko-mujoco-v10-hybrid-prospective"
SCHEMA = "junction.rokoko.mujoco-v10-hybrid-evidence-parts.v1"
FILES = ("training.json", "full_transitions.jsonl.gz", "paired-readout.json")
QUALIFICATION_SCHEMA = "junction.rokoko.mujoco-v10-hybrid-prospective.v1.independent-qualification"


def require(condition, reason):
    if not condition:
        raise AssertionError(reason)


def import_original_packer(harness_root: Path):
    path = harness_root / "scripts/craci/rokoko-mujoco-v7-retain-evidence.py"
    require(path.is_file() and not path.is_symlink(),
            "HYBRID_MISSING_ORIGINAL_BOUNDED_PACKER")
    spec = importlib.util.spec_from_file_location("hybrid_original_v7_bounded_packer", path)
    require(spec is not None and spec.loader is not None,
            "HYBRID_ORIGINAL_PACKER_IMPORT_FAILURE")
    packer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(packer)
    # Never change the source's limits/chunking/validators. Only teach the
    # reviewed generic packer about this one exact schema and file set.
    require(packer.CHUNK_BYTES == 6 * 1024 * 1024 and
            packer.MAX_FILE_BYTES == 20 * 1024 * 1024 and
            packer.MAX_COLLECTOR_BYTES == 63 * 1024 * 1024,
            "HYBRID_ORIGINAL_SAFE_PACKER_LIMIT_CHANGED")
    packer.SOURCE_FILES = FILES
    packer.ARTIFACT_SCHEMAS = {NAME: SCHEMA}
    return packer


def prereview_artifacts(folder: Path, packer):
    require(folder.is_dir() and not folder.is_symlink(),
            "HYBRID_MISSING_INDEPENDENT_RAW_EVIDENCE")
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf8"))
    original_plan = json.loads((folder / "evidence-parts-plan.json").read_text(
        encoding="utf8"))
    check = json.loads((folder / "independent-qualification.json").read_text(
        encoding="utf8"))
    positive = json.loads((folder / "independent-positive-replay.json").read_text(
        encoding="utf8"))
    require(set(manifest.get("file_sha256", {})) == set(FILES) and
            original_plan.get("schema") == SCHEMA and
            original_plan.get("archive_created_by_this_runner") is False and
            original_plan.get("manifest_sha256") ==
            packer.sha_file(folder / "manifest.json") and
            check.get("schema") == QUALIFICATION_SCHEMA and
            check.get("experiment_complete") is True and
            check.get("source_head") == manifest.get("executed_head") and
            check.get("harness_head") == manifest.get("harness_expected_head") and
            check.get("real_original_mujoco_episodes") == 640 and
            check.get("all_original_full_traces_and_masks_verified") is True and
            check.get("independent_true_physics_positive_replay") is True and
            check.get("promotion_authorized") is False and
            check.get("dev_cal_test_ood_opened") is False and
            positive.get("claim_verified") is True,
            "HYBRID_INCOMPLETE_OR_UNREVIEWED_SOURCE_EVIDENCE")
    declared = original_plan.get("part_files_for_independent_external_packager", [])
    require(sorted(p.get("name") for p in declared) == sorted(FILES),
            "HYBRID_INCOMPLETE_OR_DUPLICATE_PARTS_PLAN")
    for declaration in declared:
        name = declaration.get("name")
        require(name in FILES and declaration.get("sha256") ==
                manifest["file_sha256"][name] and
                declaration.get("bytes") == (folder / name).stat().st_size,
                "HYBRID_UNBOUND_ORIGINAL_PARTS_PLAN")
    require(len(original_plan.get("part_files_for_independent_external_packager", [])) ==
            len(FILES), "HYBRID_INCOMPLETE_EVIDENCE_PARTS_PLAN")
    for name in FILES:
        require(packer.sha_file(folder / name) == manifest["file_sha256"][name],
                "HYBRID_ORIGINAL_FILE_SHA_DRIFT_" + name)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("pack", "restore"), default="pack")
    parser.add_argument("--harness-root", type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--private-staging", type=Path)
    parser.add_argument("--restore-output", type=Path)
    args = parser.parse_args()
    # Installed location: <harness>/scripts/craci/<this file>. Three parent
    # steps from the file, not two, reach the actual checked-out repo root.
    harness_root = args.harness_root or Path(__file__).resolve().parent.parent.parent
    packer = import_original_packer(harness_root.resolve(strict=True))
    evidence = args.evidence_root.resolve(strict=True)
    if args.mode == "pack":
        require(args.private_staging is not None and args.restore_output is None,
                "HYBRID_PACK_PRIVATE_STAGING_REQUIRED")
        prereview_artifacts(evidence / "artifacts" / NAME, packer)
        report = packer.package_evidence(
            evidence, args.private_staging, artifact_name=NAME)
    else:
        require(args.restore_output is not None and args.private_staging is None,
                "HYBRID_RESTORE_OUTPUT_REQUIRED")
        report = packer.restore_parts(evidence, args.restore_output)
    print(json.dumps({"schema": SCHEMA,
                      "retained_exact_original_files": len(report["sources"]),
                      "chunk_zip_parts": sum(len(x["parts"]) for x in report["sources"]),
                      "original_sha256": {x["name"]: x["original_sha256"]
                                          for x in report["sources"]}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
