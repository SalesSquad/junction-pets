#!/usr/bin/env python3
"""Join actual, complete image observations to frozen train/dev candidate pairs."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import numpy as np

from prepare_inputs import (COUNTS, DATASET_SHA256, PUBLIC_BASE, PUBLIC_PATH, R4_COLUMNS,
                            R4_FEATURES, R4_REPORT_SHA256, ROOT, WORK_ID, bad_constant,
                            csv_rows_with_bytes, finite, is_sha, load_r4_report, new_output,
                            read_json, require, sha256, source_binding, unique_pairs,
                            validate_pair, write_json)

NEW_FEATURES = ("f_radio", "f_ocr_visual_match", "f_ocr_catalog_match", "f_ocr_digit_match", "f_ocr_digit_conflict")
FEATURE_NAMES = (*R4_FEATURES, *NEW_FEATURES)
MODEL_PINS = {
    "ocr": {"model_id": "nvidia/nemotron-ocr-v2", "revision": "0e83e83f17943524b90afa6c0fd82ac2bc1a40ca"},
    "radio": {"model_id": "nvidia/C-RADIOv4-SO400M", "revision": "c0457f5dc26ca145f954cd4fc5bb6114e5705ad8"},
}
FEATURE_DEFINITIONS = {
    "f_radio": "Cosine of actual RADIO query view1 and candidate gallery view0 embeddings; each input norm within 0.001 of one.",
    "f_ocr_visual_match": "Set Jaccard of query OCR word tokens and candidate gallery OCR word tokens; empty union gives zero.",
    "f_ocr_catalog_match": "Set Jaccard of query OCR word tokens and candidate-side published metadata_text tokens; empty union gives zero.",
    "f_ocr_digit_match": "Fraction of distinct query OCR digit sequences present in candidate gallery OCR OR candidate catalog text; no query digits gives zero.",
    "f_ocr_digit_conflict": "Fraction of distinct query OCR digit sequences absent from BOTH candidate gallery OCR and candidate catalog text; no query digits gives zero. Lexical absence, not verified physical contradiction.",
    "tokenization": "Unicode NFKC then casefold; words match [^\\W_]+, digit sequences match \\d+; unique tokens, no confidence filtering.",
    "r4_score": "Exact numeric token copied from pinned R4 predictions; frozen audit baseline only, never a learned feature.",
}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def tokens(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return set(re.findall(r"[^\W_]+", normalized)), set(re.findall(r"\d+", normalized))


def jaccard(left, right):
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def pair_features(query, gallery, catalog):
    """Only measured query pixels and candidate-side data are accepted here."""
    cosine = float(np.dot(query["embedding"], gallery["embedding"]) / (query["norm"] * gallery["norm"]))
    require(np.isfinite(cosine) and -1.00000001 <= cosine <= 1.00000001, "invalid_radio_cosine")
    query_digits, candidate_digits = query["digits"], gallery["digits"] | catalog[1]
    return {"f_radio": min(1.0, max(-1.0, cosine)),
            "f_ocr_visual_match": jaccard(query["tokens"], gallery["tokens"]),
            "f_ocr_catalog_match": jaccard(query["tokens"], catalog[0]),
            "f_ocr_digit_match": len(query_digits & candidate_digits) / len(query_digits) if query_digits else 0.0,
            "f_ocr_digit_conflict": len(query_digits - candidate_digits) / len(query_digits) if query_digits else 0.0}


def prepared_inputs(directory, report, artifacts):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), "regular_prepared_directory_required")
    manifest = read_json(directory / "prepare_manifest.json")
    require(manifest.get("kind") == "meta.r6.prepared_inputs" and manifest.get("work_id") == WORK_ID,
            "prepared_manifest_contract_mismatch")
    expected_files = {"inputs.json", "records.json", "truth.json", "train_dev_candidates.csv"}
    require(set(manifest.get("files_sha256", {})) == expected_files, "prepared_file_bindings_required")
    for name, digest in manifest["files_sha256"].items():
        require(is_sha(digest) and sha256(directory / name) == digest, "prepared_file_hash_mismatch:" + name)
    require(manifest.get("input_hashes") == {"dataset": DATASET_SHA256, "r4_report": R4_REPORT_SHA256,
            "candidates": report["provenance"]["input_sha256"]}, "prepared_original_input_binding_mismatch")
    require(manifest.get("counts") == COUNTS and manifest.get("candidates", {}).get("candidate_limit") == 100,
            "prepared_counts_or_pool_mismatch")
    require(manifest.get("baseline_model_sha256") == artifacts["model.json"] and
            manifest.get("baseline_predictions_sha256") == artifacts["predictions.csv"], "prepared_baseline_binding_mismatch")
    inputs = read_json(directory / "inputs.json")
    require(set(inputs) == {"schema", "source_commit", "dataset_sha256", "images"} and
            inputs.get("schema") == "meta_r6_images_v1" and inputs.get("dataset_sha256") == DATASET_SHA256 and
            inputs.get("source_commit") == manifest.get("source_commit"), "image_manifest_contract_mismatch")
    images = {}
    for image in inputs.get("images", []):
        require(set(image) == {"image_id", "sha256", "path", "url"}, "image_fields_allowlist_violation")
        digest, path = image["sha256"], image["path"]
        require(is_sha(digest) and image["image_id"] == "img-" + digest and image["image_id"] not in images,
                "duplicate_or_invalid_image_identity")
        require(isinstance(path, str) and PUBLIC_PATH.fullmatch(path) is not None and
                image["url"] == PUBLIC_BASE + path.removeprefix("source/"), "public_image_source_mismatch")
        images[image["image_id"]] = image
    records_doc, truths_doc = read_json(directory / "records.json"), read_json(directory / "truth.json")
    for doc in (records_doc, truths_doc):
        require(doc.get("source_commit") == manifest.get("source_commit") and
                doc.get("source_sha256") == manifest.get("source_sha256") and
                doc.get("dataset_sha256") == DATASET_SHA256 and doc.get("work_id") == WORK_ID,
                "prepared_document_source_mismatch")
    records, truths, family_splits, image_splits = {}, {}, {}, {}
    for truth in truths_doc.get("records", []):
        pid, family, split = truth["product_id"], truth["family_id"], truth["split"]
        require(isinstance(pid, str) and pid and pid not in truths and split in COUNTS, "truth_identity_or_split_mismatch")
        require(isinstance(family, str) and family and (family not in family_splits or family_splits[family] == split),
                "family_split_overlap")
        truths[pid], family_splits[family] = truth, split
    for row in records_doc.get("records", []):
        pid, split = row["product_id"], row["split"]
        require(pid not in records and pid in truths and split in COUNTS and truths[pid]["split"] == split,
                "record_truth_identity_mismatch")
        require(isinstance(row.get("catalog_text"), str), "candidate_catalog_text_required")
        require(row["query_image_id"] != row["gallery_image_id"], "distinct_query_gallery_images_required")
        for image_id in (row["query_image_id"], row["gallery_image_id"]):
            require(image_id in images and (image_id not in image_splits or image_splits[image_id] == split),
                    "record_image_binding_or_split_mismatch")
            image_splits[image_id] = split
        records[pid] = row
    require(set(records) == set(truths) and dict(Counter(r["split"] for r in records.values())) == COUNTS,
            "complete_train_dev_records_required")
    require(set(image_splits) == set(images) and len(images) == manifest.get("admission", {}).get("unique_images") and
            manifest.get("admission", {}).get("image_slots") == 2 * sum(COUNTS.values()), "image_manifest_coverage_mismatch")
    require(all(manifest.get("admission", {}).get(k) is True for k in
                ("product_disjoint", "family_disjoint", "image_hash_disjoint")), "prepared_split_admission_required")
    return manifest, images, records, truths


def validate_extraction(summary, expected_images, inputs_hash, observations_hash):
    require(summary.get("status") == "complete" and summary.get("complete") is True, "complete_extraction_required")
    require(summary.get("input_sha256") == inputs_hash and summary.get("observations_sha256") == observations_hash,
            "extraction_artifact_binding_mismatch")
    counts = summary.get("counts", {})
    require(counts.get("expected_images") == counts.get("observed_images") == expected_images and
            counts.get("failed_images") == 0, "extraction_counts_mismatch")
    require(isinstance(summary.get("source_commit"), str) and
            re.fullmatch(r"[0-9a-f]{40}", summary["source_commit"]) is not None, "extractor_source_commit_required")
    require(is_sha(summary.get("source_sha256")), "extractor_source_hash_required")
    for name, pin in MODEL_PINS.items():
        model = summary.get("models", {}).get(name, {})
        require(all(model.get(k) == value for k, value in pin.items()), "extractor_model_pin_mismatch:" + name)
        files = model.get("files")
        require(isinstance(files, list) and bool(files), "model_weight_files_required")
        paths = []
        for file in files:
            require(set(file) == {"path", "sha256", "size_bytes"} and is_sha(file["sha256"]) and
                    isinstance(file["path"], str) and file["path"] and type(file["size_bytes"]) is int and
                    file["size_bytes"] > 0, "invalid_model_weight_file_binding")
            paths.append(file["path"])
        require(paths == sorted(set(paths)) and model.get("weights_sha256") == canonical_hash(files),
                "model_weights_aggregate_mismatch")


def parse_observation(row, image, dimension=None):
    require(row.get("image_id") == image["image_id"] and row.get("sha256") == image["sha256"], "observation_image_hash_mismatch")
    ocr, radio = row.get("ocr", {}), row.get("radio", {})
    require(ocr.get("status") == "ok" and isinstance(ocr.get("spans"), list), "complete_ocr_observation_required")
    texts = []
    for span in ocr["spans"]:
        require(isinstance(span, dict) and isinstance(span.get("text"), str), "ocr_text_required")
        confidence = span.get("confidence")
        require(isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and 0 <= finite(confidence) <= 1,
                "ocr_confidence_out_of_bounds")
        box = span.get("box_normalized")
        require(isinstance(box, list) and len(box) == 4 and all(isinstance(x, (int, float)) and
                not isinstance(x, bool) and 0 <= finite(x) <= 1 for x in box) and
                box[0] <= box[2] and box[1] <= box[3], "ocr_box_out_of_bounds")
        texts.append(span["text"])
    size, embedding = radio.get("dimension"), radio.get("embedding")
    require(type(size) is int and 1 <= size <= 65536 and (dimension is None or size == dimension), "radio_dimension_mismatch")
    require(isinstance(embedding, list) and len(embedding) == size and
            all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in embedding), "radio_embedding_contract_mismatch")
    vector = np.asarray(embedding, dtype=np.float64)
    require(np.isfinite(vector).all(), "radio_nonfinite_embedding")
    norm = float(np.linalg.norm(vector))
    require(abs(norm - 1.0) <= 0.001, "radio_unit_normalized_embedding_required")
    words, digits = tokens(" ".join(texts))
    return {"embedding": vector, "norm": norm, "tokens": words, "digits": digits,
            "span_count": len(texts), "observed_text": any(text.strip() for text in texts)}


def load_observations(path, images):
    observed, dimension = {}, None
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            require(bool(line.strip()), "blank_observation_record")
            row = json.loads(line, object_pairs_hook=unique_pairs, parse_constant=bad_constant)
            image_id = row.get("image_id")
            require(image_id in images and image_id not in observed, "unexpected_or_duplicate_observation")
            observed[image_id] = parse_observation(row, images[image_id], dimension)
            dimension = row["radio"]["dimension"]
    require(set(observed) == set(images), "missing_image_observations")
    return observed, dimension


def selected_predictions(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == ["split", "query_id", "candidate_id", "rank_score"], "r4_prediction_columns_mismatch")
        for row in reader:
            require(None not in row and all(value is not None for value in row.values()), "invalid_prediction_record")
            require(row["split"] in {"train", "dev", "cal", "test"}, "invalid_prediction_split")
            if row["split"] in COUNTS:
                finite(row["rank_score"])
                yield row


def export_features(candidate_path, predictions_path, output, records, truths, observations, *, candidate_limit=100):
    prediction_rows = iter(selected_predictions(predictions_path))
    seen, counts = {pid: set() for pid in records}, Counter()
    catalog = {pid: tokens(row["catalog_text"]) for pid, row in records.items()}
    with Path(output).open("xb") as handle:
        for row, raw in csv_rows_with_bytes(candidate_path, R4_COLUMNS):
            if row is None:
                handle.write(raw.rstrip(b"\r\n") + ("," + ",".join((*NEW_FEATURES, "r4_score")) + "\n").encode("ascii"))
                continue
            require(row["split"] in COUNTS, "train_dev_candidates_only")
            split, query, candidate = validate_pair(row, records, truths)
            require(candidate not in seen[query], "duplicate_query_candidate")
            seen[query].add(candidate)
            require(len(seen[query]) <= candidate_limit, "candidate_limit_exceeded")
            prediction = next(prediction_rows, None)
            require(prediction is not None and all(prediction[k] == row[k] for k in ("split", "query_id", "candidate_id")),
                    "frozen_r4_prediction_identity_or_order_mismatch")
            values = pair_features(observations[records[query]["query_image_id"]],
                                   observations[records[candidate]["gallery_image_id"]], catalog[candidate])
            suffix = [format(values[name], ".17g") for name in NEW_FEATURES] + [prediction["rank_score"]]
            handle.write(raw.rstrip(b"\r\n") + ("," + ",".join(suffix) + "\n").encode("ascii"))
            counts[split] += 1
    require(next(prediction_rows, None) is None, "unmatched_frozen_r4_predictions")
    require(all(len(values) == candidate_limit for values in seen.values()), "incomplete_original_candidate_pool")
    return dict(counts)


def build(args, binding):
    report, artifacts = load_r4_report(args.r4_report)
    require(sha256(args.r4_predictions) == artifacts["predictions.csv"], "frozen_r4_predictions_hash_mismatch")
    manifest, images, records, truths = prepared_inputs(args.prepared, report, artifacts)
    paths = {"prepared_manifest": args.prepared / "prepare_manifest.json", "extraction_manifest": args.extraction_manifest,
             "observations": args.observations, "r4_predictions": args.r4_predictions, "r4_report": args.r4_report}
    input_hashes = {name: sha256(path) for name, path in paths.items()}
    extraction = read_json(args.extraction_manifest)
    validate_extraction(extraction, len(images), manifest["files_sha256"]["inputs.json"], input_hashes["observations"])
    observations, dimension = load_observations(args.observations, images)
    new_output(args.output)
    output_csv = args.output / "candidates.csv"
    rows = export_features(args.prepared / "train_dev_candidates.csv", args.r4_predictions, output_csv, records, truths, observations)
    require(rows == {split: count * 100 for split, count in COUNTS.items()}, "feature_row_count_mismatch")
    require(input_hashes == {name: sha256(path) for name, path in paths.items()}, "input_changed_during_feature_build")
    require(all(sha256(args.prepared / name) == digest for name, digest in manifest["files_sha256"].items()),
            "prepared_file_changed_during_build")
    require(all(sha256(ROOT / name) == digest for name, digest in binding["source_sha256"].items()), "feature_source_changed")
    result = {"schema_version": 1, "kind": "meta.r6.actual_candidate_features", "work_id": WORK_ID, **binding,
              "input_file": "candidates.csv", "input_sha256": sha256(output_csv), "input_hashes": input_hashes,
              "prepared_files_sha256": manifest["files_sha256"], "feature_names": list(FEATURE_NAMES),
              "columns": [*R4_COLUMNS, *NEW_FEATURES, "r4_score"], "feature_definitions": FEATURE_DEFINITIONS,
              "counts": COUNTS, "rows": rows, "admission": manifest["admission"],
              "baseline_model_sha256": artifacts["model.json"], "baseline_predictions_sha256": artifacts["predictions.csv"],
              "models": extraction["models"], "extractor_source_commit": extraction["source_commit"],
              "extractor_source_sha256": extraction["source_sha256"], "radio_dimension": dimension,
              "observed_images": len(observations), "images_with_ocr_text": sum(o["observed_text"] for o in observations.values()),
              "ocr_spans": sum(o["span_count"] for o in observations.values()),
              "ocr_accuracy": None, "transcription_ground_truth_available": False,
              "oracle_positive_injected": False, "query_metadata_features": False,
              "candidate_catalog_metadata_used": True, "original_r4_numeric_tokens_preserved": True,
              "cal_test_images_or_rows_used": False, "qualification": False, "action_authorized": False,
              "physical_identity_verified": False}
    write_json(args.output / "data_manifest.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--extraction-manifest", type=Path, required=True)
    parser.add_argument("--r4-predictions", type=Path, required=True)
    parser.add_argument("--r4-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    result = build(args, source_binding(args.source_commit, ("prepare_inputs.py", "build_features.py")))
    print(json.dumps({"status": "FEATURES_BUILT_RESEARCH_ONLY", "input_sha256": result["input_sha256"],
                      "rows": result["rows"], "images_with_ocr_text": result["images_with_ocr_text"]}), flush=True)


if __name__ == "__main__":
    main()
