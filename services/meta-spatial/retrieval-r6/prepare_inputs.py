#!/usr/bin/env python3
"""Prepare source-bound train/dev pixels; never send labels/catalog text to extraction."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent
WORK_ID = "META-LENS-R6-VERDA-20261114"
DATASET_SHA256 = "bd70decf437dd34dfa9e2866c2110b142d7e746ea66c6f1098ac81deb6cac59c"
R4_REPORT_SHA256 = "8eda9a3d532b931bc93a765e555bc9008ce9d3c781d1c9efef583e6db515ca80"
COUNTS = {"train": 3313, "dev": 727}
PUBLIC_BASE = "https://amazon-berkeley-objects.s3.amazonaws.com/"
PUBLIC_PATH = re.compile(r"source/images/small/[a-z0-9]{2}/[a-z0-9]+\.jpg")
R4_FEATURES = ("f_visual", "f_adapted", "f_text", "f_reverse_rank", "f_density", "f_gap")
R4_COLUMNS = ("split", "query_id", "query_family", "candidate_id", "candidate_family", "label",
              *R4_FEATURES, "baseline_rank", "visual_rank", "text_rank")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def is_sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def sha256(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "regular_input_file_required:" + path.name)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_field")
        result[key] = value
    return result


def bad_constant(value):
    raise ValueError("nonfinite_json_constant:" + value)


def read_json(path):
    sha256(path)
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_pairs,
                      parse_constant=bad_constant)


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")


def finite(value):
    require(not isinstance(value, bool), "finite_number_required")
    number = float(value)
    require(math.isfinite(number), "finite_number_required")
    return number


def source_binding(commit, names):
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
            "exact_source_commit_required")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(actual == commit, "source_head_mismatch")
    repo = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=ROOT, text=True).strip())
    hashes = {}
    for name in names:
        path = ROOT / name
        hashes[name] = sha256(path)
        raw = subprocess.check_output(["git", "show", commit + ":" + path.relative_to(repo).as_posix()], cwd=ROOT)
        require(hashlib.sha256(raw).hexdigest() == hashes[name], "source_bytes_differ_from_commit:" + name)
    return {"source_commit": commit, "source_sha256": hashes}


def new_output(path):
    path = Path(path)
    require(not path.exists() and not path.is_symlink(), "new_output_directory_required")
    require(not any(p.is_symlink() for p in path.parents), "output_symlink_ancestor_refused")
    path.mkdir(parents=True)


def load_r4_report(path):
    require(sha256(path) == R4_REPORT_SHA256, "pinned_r4_report_mismatch")
    report = read_json(path)
    require(report.get("work_id") == "META-LENS-R4-COVERAGE93-20261114", "r4_report_work_id_mismatch")
    require(is_sha(report.get("provenance", {}).get("input_sha256")), "r4_candidate_hash_binding_required")
    artifacts = {}
    for item in report.get("artifacts", []):
        require(item["path"] not in artifacts and is_sha(item.get("sha256")), "invalid_r4_artifact_binding")
        artifacts[item["path"]] = item["sha256"]
    require({"predictions.csv", "model.json"} <= set(artifacts), "r4_model_and_predictions_bindings_required")
    return report, artifacts


def project_dataset(dataset, *, expected_counts=COUNTS):
    """Validate all source split ownership, then emit only train/dev image slots."""
    require(dataset.get("kind") == "meta.public-abo-retrieval" and dataset.get("license") == "CC-BY-4.0",
            "public_dataset_contract_mismatch")
    rows = dataset.get("records")
    require(isinstance(rows, list) and bool(rows), "dataset_records_required")
    products, families, image_splits, path_hashes = {}, {}, {}, {}
    records, truths, images = [], [], {}
    counts = Counter()
    for row in rows:
        pid, family, split = row.get("product_id"), row.get("family_id"), row.get("split")
        require(isinstance(pid, str) and bool(pid) and pid not in products, "unique_product_id_required")
        require(isinstance(family, str) and bool(family), "family_id_required")
        require(split in {"train", "dev", "cal", "test", "ood"}, "invalid_dataset_split")
        require(family not in families or families[family] == split, "family_split_overlap")
        products[pid], families[family] = split, split
        counts[split] += 1
        views = row.get("views")
        require(isinstance(views, list) and len(views) == 2, "two_original_views_required")
        require(views[0].get("sha256") != views[1].get("sha256"), "distinct_query_gallery_images_required")
        for view in views:
            digest, path = view.get("sha256"), view.get("path")
            require(is_sha(digest) and isinstance(path, str) and PUBLIC_PATH.fullmatch(path) is not None,
                    "public_image_binding_required")
            require(digest not in image_splits or image_splits[digest] == split, "image_hash_split_overlap")
            require(path not in path_hashes or path_hashes[path] == digest, "image_path_hash_conflict")
            image_splits[digest], path_hashes[path] = split, digest
            if split in expected_counts:
                image = {"image_id": "img-" + digest, "sha256": digest, "path": path,
                         "url": PUBLIC_BASE + path.removeprefix("source/")}
                if digest not in images or path < images[digest]["path"]:
                    images[digest] = image
        if split in expected_counts:
            require(isinstance(row.get("metadata_text"), str), "candidate_catalog_text_required")
            records.append({"product_id": pid, "split": split,
                            "query_image_id": "img-" + views[1]["sha256"],
                            "gallery_image_id": "img-" + views[0]["sha256"],
                            "catalog_text": row["metadata_text"]})
            truths.append({"product_id": pid, "split": split, "family_id": family})
    require(dict(counts) == dataset.get("counts"), "dataset_split_counts_mismatch")
    require({s: counts[s] for s in expected_counts} == expected_counts, "expected_train_dev_counts_mismatch")
    admission = {"product_disjoint": True, "family_disjoint": True, "image_hash_disjoint": True,
                 "source_partitions_checked": sorted(counts), "extracted_partitions": ["train", "dev"],
                 "original_query_view_index": 1, "original_gallery_view_index": 0,
                 "image_slots": 2 * len(records), "unique_images": len(images),
                 "cal_test_ood_images_exported": 0}
    return records, truths, [images[h] for h in sorted(images)], admission


def csv_rows_with_bytes(path, required_columns):
    """Source CSV has one record per physical line; keep its original numeric bytes."""
    with Path(path).open("rb") as handle:
        header = handle.readline()
        columns = next(csv.reader([header.decode("utf-8")], strict=True), [])
        require(columns == list(required_columns), "csv_column_contract_mismatch")
        yield None, header
        for raw in handle:
            values = next(csv.reader([raw.decode("utf-8")], strict=True), [])
            require(len(values) == len(columns), "csv_record_width_mismatch")
            yield dict(zip(columns, values)), raw


def validate_pair(row, records, truths):
    split, query, candidate = row["split"], row["query_id"], row["candidate_id"]
    require(query in records and candidate in records and
            records[query]["split"] == records[candidate]["split"] == split, "candidate_record_split_mismatch")
    require(row["query_family"] == truths[query]["family_id"] and
            row["candidate_family"] == truths[candidate]["family_id"], "candidate_family_binding_mismatch")
    require(row["label"] in {"0", "1"} and int(row["label"]) == int(query == candidate), "candidate_label_binding_mismatch")
    for feature in R4_FEATURES:
        finite(row[feature])
    for rank in ("baseline_rank", "visual_rank", "text_rank"):
        require(re.fullmatch(r"[1-9][0-9]*", row[rank]) is not None, "positive_candidate_rank_required")
    return split, query, candidate


def copy_candidates(source, output, records, truths, *, candidate_limit=100):
    records = {row["product_id"]: row for row in records}
    truths = {row["product_id"]: row for row in truths}
    seen, rows, found = {pid: set() for pid in records}, Counter(), set()
    with Path(output).open("xb") as handle:
        for row, raw in csv_rows_with_bytes(source, R4_COLUMNS):
            if row is None:
                handle.write(raw)
                continue
            require(row["split"] in {"train", "dev", "cal", "test"}, "unexpected_candidate_split")
            if row["split"] not in {"train", "dev"}:
                continue
            split, query, candidate = validate_pair(row, records, truths)
            require(candidate not in seen[query], "duplicate_query_candidate")
            seen[query].add(candidate)
            require(len(seen[query]) <= candidate_limit, "candidate_limit_exceeded")
            if row["label"] == "1":
                found.add(query)
            rows[split] += 1
            handle.write(raw)
    require(all(len(values) == candidate_limit for values in seen.values()), "incomplete_original_candidate_pool")
    return {"rows": dict(rows), "candidate_limit": candidate_limit, "oracle_positive_injected": False,
            "queries_with_truth_candidate": len(found), "queries_missing_truth_candidate": len(records) - len(found),
            "original_numeric_bytes_preserved": True}


def prepare(dataset_path, candidates_path, report_path, output, binding):
    require(sha256(dataset_path) == DATASET_SHA256, "pinned_dataset_mismatch")
    report, artifacts = load_r4_report(report_path)
    input_hashes = {"dataset": sha256(dataset_path), "r4_report": sha256(report_path), "candidates": sha256(candidates_path)}
    require(input_hashes["candidates"] == report["provenance"]["input_sha256"], "r4_candidate_hash_mismatch")
    records, truths, images, admission = project_dataset(read_json(dataset_path))
    new_output(output)
    files = {name: Path(output) / name for name in ("inputs.json", "records.json", "truth.json", "train_dev_candidates.csv")}
    candidates = copy_candidates(candidates_path, files["train_dev_candidates.csv"], records, truths)
    common = {"schema_version": 1, "work_id": WORK_ID, **binding, "dataset_sha256": DATASET_SHA256}
    write_json(files["inputs.json"], {"schema": "meta_r6_images_v1", "source_commit": binding["source_commit"],
                                    "dataset_sha256": DATASET_SHA256, "images": images})
    write_json(files["records.json"], {**common, "kind": "meta.r6.train_dev_records", "records": records})
    write_json(files["truth.json"], {**common, "kind": "meta.r6.train_dev_truth", "records": truths})
    require(input_hashes == {"dataset": sha256(dataset_path), "r4_report": sha256(report_path), "candidates": sha256(candidates_path)},
            "input_changed_during_preparation")
    require(all(sha256(ROOT / name) == value for name, value in binding["source_sha256"].items()), "preparation_source_changed")
    manifest = {"schema_version": 1, "kind": "meta.r6.prepared_inputs", "work_id": WORK_ID, **binding,
                "input_hashes": input_hashes, "files_sha256": {name: sha256(path) for name, path in files.items()},
                "counts": COUNTS, "admission": admission, "candidates": candidates,
                "baseline_model_sha256": artifacts["model.json"], "baseline_predictions_sha256": artifacts["predictions.csv"],
                "query_metadata_sent_to_extraction": False, "truth_sent_to_extraction": False,
                "qualification": False, "action_authorized": False}
    write_json(Path(output) / "prepare_manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--r4-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    binding = source_binding(args.source_commit, ("prepare_inputs.py",))
    result = prepare(args.dataset, args.candidates, args.r4_report, args.output, binding)
    print(json.dumps({"status": "PREPARED_RESEARCH_ONLY", "counts": result["counts"],
                      "image_slots": result["admission"]["image_slots"], "unique_images": result["admission"]["unique_images"],
                      "inputs_sha256": result["files_sha256"]["inputs.json"]}), flush=True)


if __name__ == "__main__":
    main()
