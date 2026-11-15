#!/usr/bin/env python3
"""R8: the frozen four CPU histogram-tree configurations on eleven real features.

Fit consumes train only. Development selects a completed candidate; it does not
control training/stopping. Private rows and joblib files stay under private/.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import importlib.metadata
import inspect
from itertools import zip_longest
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time

WORK_ID = "META-LENS-R8-NONLINEAR-20261115"
EXPERIMENT = "cpu_hist_gradient_boosting11"
BASE_FEATURES = ["f_visual", "f_adapted", "f_text", "f_reverse_rank", "f_density", "f_gap"]
NEW_FEATURES = ["f_radio", "f_ocr_visual_match", "f_ocr_catalog_match", "f_ocr_digit_match", "f_ocr_digit_conflict"]
FEATURES = BASE_FEATURES + NEW_FEATURES
COUNTS = {"train": 3313, "dev": 727}
ROW_COUNTS = {"train": 331300, "dev": 72700}
GRID = [{"max_leaf_nodes": leaves, "l2_regularization": ridge}
        for leaves in (15, 31) for ridge in (1.0, 10.0)]
FIXED = {"loss": "log_loss", "learning_rate": 0.05, "max_iter": 150,
         "min_samples_leaf": 100, "max_bins": 127, "early_stopping": False,
         "categorical_features": None, "class_weight": None, "random_state": 20261115}
RUNTIME = {"threads": 4, "max_wall_seconds": 600}
PROTOCOL_SHA = '0b88c1bb51bb6aef93fa2a7eb384c187e5fc30bbed7aea59f0ab6568ab417efa'
PINS = {
    "prepared_manifest_sha256": "817435715686cc2d98eea94ea5d4fa95450fb803be3328eb66feb53185b631d0",
    "candidates_sha256": "8879394491a3bbbb576c616dcf93a7d0fe2642f0623dddc08a4a2f159ba8cc21",
    "truth_sha256": "114ae227c2095be5b43c43d47c692aab8da5547d4818885855ca0b64bfc1370f",
    "baseline_model_sha256": "4f6db7b937a244b2a6cdf5298d6087bcd84d01445219882c2b7d041986a3a0b6",
    "prepared_source_commit": "8948b44454f1a5dd174395e6d69e1ae8b533688b",
}
ORIGINS = {"dataset_sha256": "bd70decf437dd34dfa9e2866c2110b142d7e746ea66c6f1098ac81deb6cac59c",
           "r4_report_sha256": "8eda9a3d532b931bc93a765e555bc9008ce9d3c781d1c9efef583e6db515ca80"}
FLAGS = {"qualification": False, "action_authorized": False, "physical_identity_verified": False}
BASE_COLUMNS = ["split", "query_id", "query_family", "candidate_id", "candidate_family", "label",
                *BASE_FEATURES, "baseline_rank", "visual_rank", "text_rank"]
COLUMNS = BASE_COLUMNS + NEW_FEATURES + ["r4_score"]
SOURCE_HASHES = {'build_features.py': '90b726bd2aae727168d1605681a5ea9b7ae7c7e4559cbb5658a8ca32e3dc0fa1', 'extract_nvidia.py': 'a31e08d925b439b5d9e01d75dc9eb8a4397696425c2908853a96f6809421da11', 'prepare_inputs.py': '9d3a7a931be628f93ccb3c1a900aadc04cdec3aab3954fde232f011d2b35f2a8', 'train_reranker.R': '4dcd524d7ea1ab5df2574bffaa6871c26c31c67ed22c00e92619e987e7e29ad5'}
POSTPROCESSOR_SHA = '2b76f151830fd66590f2fd27352800659e21b6bfec992d20dc083223f3d2072b'
IMAGE_INPUT_SHA = "47a015b6cf7f2ef10ff246fbf325e3f63459aa277d8ab3bd4bd6f61b4e0ce25f"
MODEL_PINS = {"ocr": ("nvidia/nemotron-ocr-v2", "0e83e83f17943524b90afa6c0fd82ac2bc1a40ca"),
              "radio": ("nvidia/C-RADIOv4-SO400M", "c0457f5dc26ca145f954cd4fc5bb6114e5705ad8")}


def require(ok, code):
    if not ok:
        raise ValueError(code)


def unique_pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def bad_constant(value):
    raise ValueError("nonfinite_json_constant")


def read_json(path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique_pairs, parse_constant=bad_constant)


def sha(path):
    require(path.is_file() and not path.is_symlink(), "regular_file_required")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")


def finite(value):
    require(type(value) in (float, int) and math.isfinite(value), "nonfinite_numeric_value")
    return value


def identity(value):
    require(type(value) is str and value and not any(c in value for c in "\r\n\t\x1f"), "invalid_identity")
    return value


def validate_protocol(value):
    require(value.get("schema_version") == 1 and value.get("kind") == "meta.r8.nonlinear_feature_protocol"
            and value.get("work_id") == WORK_ID and value.get("experiment") == EXPERIMENT, "protocol_schema_mismatch")
    require(value.get("feature_names") == FEATURES and value.get("grid") == GRID
            and value.get("fixed_parameters") == FIXED and value.get("runtime") == RUNTIME
            and value.get("input_pins") == PINS and value.get("preparation_origins") == ORIGINS
            and value.get("feature_source_sha256") == SOURCE_HASHES
            and value.get("postprocessor_sha256") == POSTPROCESSOR_SHA,
            "preregistered_configuration_mismatch")
    require(all(value.get(k) is False for k in FLAGS), "qualification_flag_not_false")


def bind_source(protocol, commit):
    script = Path(__file__).resolve()
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None and commit != PINS["prepared_source_commit"],
            "new_full_source_commit_required")

    def git(*args):
        return subprocess.check_output(["git", "-C", str(script.parent), *args], stderr=subprocess.DEVNULL, timeout=30)

    root = Path(git("rev-parse", "--show-toplevel").decode().strip())
    require(git("rev-parse", "HEAD").decode().strip() == commit, "source_head_mismatch")
    require(not git("status", "--porcelain", "--untracked-files=all"), "clean_source_required")
    files = {"training_script_sha256": script, "protocol_sha256": protocol.resolve()}
    hashes = {}
    for name, path in files.items():
        require(path.is_relative_to(root), "source_file_outside_checkout")
        require(path.read_bytes() == git("show", commit + ":" + path.relative_to(root).as_posix()),
                "source_bytes_differ_from_commit")
        hashes[name] = sha(path)
    require(hashes["protocol_sha256"] == PROTOCOL_SHA, "protocol_digest_mismatch")
    validate_protocol(read_json(protocol))
    return root, {"source_commit": commit, "source_clean": True, **hashes}


def bind_prepared(prepared, baseline_path):
    paths = {"prepared_manifest_sha256": prepared/"prepare_manifest.json",
             "candidates_sha256": prepared/"train_dev_candidates.csv",
             "truth_sha256": prepared/"truth.json", "baseline_model_sha256": baseline_path}
    hashes = {name: sha(path) for name, path in paths.items()}
    require(all(hashes[name] == PINS[name] for name in paths), "pinned_input_digest_mismatch")
    manifest, truth_doc, baseline = [read_json(path) for path in
                                   (paths["prepared_manifest_sha256"], paths["truth_sha256"], baseline_path)]
    require(manifest["kind"] == "meta.r6.prepared_inputs" and manifest["source_commit"] == PINS["prepared_source_commit"]
            and manifest["counts"] == COUNTS, "prepared_manifest_mismatch")
    require(manifest["files_sha256"]["train_dev_candidates.csv"] == hashes["candidates_sha256"] and
            manifest["files_sha256"]["truth.json"] == hashes["truth_sha256"] and
            manifest["baseline_model_sha256"] == hashes["baseline_model_sha256"], "prepared_artifact_binding_mismatch")
    require(manifest["input_hashes"]["dataset"] == ORIGINS["dataset_sha256"] and
            manifest["input_hashes"]["r4_report"] == ORIGINS["r4_report_sha256"], "preparation_origin_mismatch")
    require(all(manifest["admission"].get(k) is True for k in
                ("family_disjoint", "product_disjoint", "image_hash_disjoint")) and
            manifest["admission"]["extracted_partitions"] == ["train", "dev"] and
            manifest["admission"]["cal_test_ood_images_exported"] == 0, "train_dev_admission_mismatch")
    require(truth_doc["kind"] == "meta.r6.train_dev_truth" and truth_doc["source_commit"] == manifest["source_commit"] and
            truth_doc["source_sha256"] == manifest["source_sha256"], "truth_source_mismatch")
    truth, families = {}, {}
    for row in truth_doc["records"]:
        query, family, split = identity(row["product_id"]), identity(row["family_id"]), row["split"]
        require(query not in truth and split in COUNTS and (family not in families or families[family] == split),
                "truth_identity_or_split_overlap")
        truth[query] = (split, family)
        families[family] = split
    require(dict(Counter(s for s, _ in truth.values())) == COUNTS, "truth_query_count_mismatch")
    require(baseline["kind"] == "ridge_pairwise_logistic" and baseline["feature_names"] == BASE_FEATURES and
            baseline["intercept"] == 0, "baseline_numeric_contract_mismatch")
    for values in (baseline["coefficients"], baseline["scaler"]["center"], baseline["scaler"]["scale"]):
        require(type(values) is list and len(values) == len(BASE_FEATURES), "baseline_numeric_shape_mismatch")
        for value in values:
            finite(value)
    require(all(value > 0 for value in baseline["scaler"]["scale"]), "baseline_scale_not_positive")
    return paths, hashes, truth, baseline


def bind_inputs(control, prepared, baseline_path, verification_sha):
    require(re.fullmatch(r"[0-9a-f]{64}", verification_sha) is not None, "verification_digest_required")
    paths, hashes, truth, baseline = bind_prepared(prepared, baseline_path)
    prepared_manifest = read_json(paths["prepared_manifest_sha256"])
    require(prepared_manifest["source_sha256"] == {"prepare_inputs.py": SOURCE_HASHES["prepare_inputs.py"]},
            "prepared_source_digest_mismatch")
    extra = {"feature_csv_sha256": control/"features-01/candidates.csv",
             "feature_manifest_sha256": control/"features-01/data_manifest.json",
             "training_verification_sha256": control/"training-verification.json",
             "linear_report_sha256": control/"training-01/report.json",
             "linear_model_sha256": control/"training-01/model.json",
             "extraction_summary_sha256": control/"gpu-output-01/extraction-01/summary.json",
             "observations_sha256": control/"gpu-output-01/extraction-01/observations.jsonl",
             "prepared_records_sha256": prepared/"records.json", "image_inputs_sha256": prepared/"inputs.json"}
    paths.update(extra)
    hashes.update({name: sha(path) for name, path in extra.items()})
    require(hashes["training_verification_sha256"] == verification_sha, "verification_digest_mismatch")
    verified = read_json(paths["training_verification_sha256"])
    require(verified["schema"] == "meta_r8_training_verification_v1" and
            verified["source_commit"] == PINS["prepared_source_commit"] and
            verified["source_files_sha256"] == SOURCE_HASHES and
            verified["postprocessor_sha256"] == POSTPROCESSOR_SHA and
            verified["source_clean_after_training"] is True, "verified_execution_source_mismatch")
    for name, count in {"verified_images": 6993, "baseline_dev_correct_at_1": 466,
                        "dev_queries": 727, "candidate_recall_correct": 719, "training_fits": 12,
                        "converged_fits": 12, "prediction_rows": 404000, "query_metrics_rows": 20200}.items():
        require(type(verified[name]) is int and verified[name] == count, "verified_execution_count_mismatch")
    require(verified["all_fits_updated_weights"] is True and verified["all_fits_reduced_objective"] is True,
            "verified_linear_training_incomplete")
    require(all(verified.get(k) is False for k in (*FLAGS, "accepted_coverage_measured", "ocr_transcription_accuracy_measured")),
            "verified_qualification_flag_not_false")
    for key, receipt_key in (("feature_csv_sha256", "feature_csv_sha256"),
                             ("feature_manifest_sha256", "feature_manifest_sha256"),
                             ("linear_report_sha256", "report_sha256"), ("linear_model_sha256", "model_sha256")):
        require(hashes[key] == verified[receipt_key], "verified_artifact_digest_mismatch")
    inputs = verified["input_artifacts_sha256"]
    require(inputs["prepared_manifest"] == PINS["prepared_manifest_sha256"] and
            inputs["r4_model.json"] == PINS["baseline_model_sha256"] and
            inputs["r4_report"] == ORIGINS["r4_report_sha256"] and
            inputs["r4_predictions.csv"] == prepared_manifest["baseline_predictions_sha256"],
            "verified_original_input_mismatch")
    actual_prepared = {"inputs.json": hashes["image_inputs_sha256"], "records.json": hashes["prepared_records_sha256"],
                       "truth.json": hashes["truth_sha256"], "train_dev_candidates.csv": hashes["candidates_sha256"]}
    require(actual_prepared == prepared_manifest["files_sha256"] and
            all(inputs[k] == v for k, v in actual_prepared.items()) and
            hashes["image_inputs_sha256"] == IMAGE_INPUT_SHA, "verified_prepared_file_mismatch")
    features = read_json(paths["feature_manifest_sha256"])
    require(features["schema_version"] == 1 and features["kind"] == "meta.r6.actual_candidate_features" and
            features["work_id"] == "META-LENS-R6-VERDA-20261114" and
            features["source_commit"] == PINS["prepared_source_commit"] and
            features["source_sha256"] == {k: SOURCE_HASHES[k] for k in ("prepare_inputs.py", "build_features.py")},
            "feature_source_contract_mismatch")
    require(features["feature_names"] == FEATURES and features["columns"] == COLUMNS and
            features["counts"] == COUNTS and features["rows"] == ROW_COUNTS and
            features["input_file"] == "candidates.csv" and features["input_sha256"] == hashes["feature_csv_sha256"],
            "feature_matrix_contract_mismatch")
    require(features["prepared_files_sha256"] == actual_prepared and
            features["admission"] == prepared_manifest["admission"] and
            features["baseline_model_sha256"] == PINS["baseline_model_sha256"] and
            features["baseline_predictions_sha256"] == prepared_manifest["baseline_predictions_sha256"],
            "feature_original_data_mismatch")
    require(features["input_hashes"] == {
        "prepared_manifest": PINS["prepared_manifest_sha256"],
        "extraction_manifest": hashes["extraction_summary_sha256"],
        "observations": hashes["observations_sha256"], "r4_predictions": prepared_manifest["baseline_predictions_sha256"],
        "r4_report": ORIGINS["r4_report_sha256"]}, "feature_input_binding_mismatch")
    require(features["observed_images"] == 6993 and type(features["radio_dimension"]) is int and
            features["radio_dimension"] > 0 and features["original_r4_numeric_tokens_preserved"] is True and
            features["candidate_catalog_metadata_used"] is True, "measured_image_features_required")
    require(all(features.get(k) is False for k in (*FLAGS, "oracle_positive_injected", "query_metadata_features",
                "cal_test_images_or_rows_used", "transcription_ground_truth_available")) and
            features["ocr_accuracy"] is None, "feature_admission_flag_mismatch")
    extraction = read_json(paths["extraction_summary_sha256"])
    require(extraction["schema"] == "meta_r6_extraction_v1" and extraction["status"] == "complete" and
            extraction["complete"] is True and extraction["source_commit"] == PINS["prepared_source_commit"] and
            extraction["source_sha256"] == SOURCE_HASHES["extract_nvidia.py"] and
            extraction["input_sha256"] == IMAGE_INPUT_SHA and extraction["dataset_sha256"] == ORIGINS["dataset_sha256"] and
            extraction["counts"] == {"manifest_images": 6993, "expected_images": 6993, "observed_images": 6993, "failed_images": 0},
            "complete_pinned_extraction_required")
    require(verified["extraction_artifacts_sha256"]["summary"] == hashes["extraction_summary_sha256"] and
            verified["extraction_artifacts_sha256"]["observations_sha256"] == hashes["observations_sha256"] and
            extraction["observations_sha256"] == hashes["observations_sha256"] and
            features["extractor_source_commit"] == PINS["prepared_source_commit"] and
            features["extractor_source_sha256"] == SOURCE_HASHES["extract_nvidia.py"] and
            features["models"] == extraction["models"] and all(extraction.get(k) is False for k in FLAGS),
            "extraction_feature_binding_mismatch")
    require(set(extraction["models"]) == set(MODEL_PINS), "foundation_model_set_mismatch")
    for key, (model_id, revision) in MODEL_PINS.items():
        require(extraction["models"][key]["model_id"] == model_id and
                extraction["models"][key]["revision"] == revision, "foundation_model_revision_mismatch")
    for key in ("linear_report_sha256", "linear_model_sha256"):
        doc = read_json(paths[key])
        require(all(doc.get(k) is False for k in FLAGS) and
                doc["provenance"]["source_commit"] == PINS["prepared_source_commit"] and
                doc["provenance"]["training_script_sha256"] == SOURCE_HASHES["train_reranker.R"] and
                doc["provenance"]["input_sha256"] == hashes["feature_csv_sha256"] and
                doc["provenance"]["manifest_sha256"] == hashes["feature_manifest_sha256"] and
                doc["provenance"]["baseline_model_sha256"] == PINS["baseline_model_sha256"],
                "linear_evidence_binding_mismatch")
        if key == "linear_report_sha256":
            require(doc["status"] == "trained_research_only" and doc["counts"] == COUNTS and
                    doc["rows"] == ROW_COUNTS and doc["consumed_partitions"] == ["train", "dev"] and
                    doc["training"]["fits"] == len(doc["optimizer_candidates"]) == 12,
                    "completed_linear_experiment_required")
    return paths, hashes, truth, baseline


def validate_row(row, truth):
    require(None not in row and all(value is not None for value in row.values()), "malformed_candidate_row")
    split, query, candidate = row["split"], identity(row["query_id"]), identity(row["candidate_id"])
    require(query in truth and candidate in truth and truth[query] == (split, row["query_family"]) and
            truth[candidate] == (split, row["candidate_family"]) and split in COUNTS, "candidate_truth_or_split_mismatch")
    require(row["label"] in ("0", "1") and int(row["label"]) == int(query == candidate), "exact_label_mismatch")
    values = [float(row[name]) for name in FEATURES]
    for value in values:
        finite(value)
    require(-1.00001 <= values[6] <= 1.00001 and all(0 <= value <= 1 for value in values[7:]),
            "measured_feature_range_mismatch")
    finite(float(row["r4_score"]))
    require(all(re.fullmatch(r"[1-9][0-9]*", row[k]) is not None for k in
                ("baseline_rank", "visual_rank", "text_rank")), "invalid_candidate_rank")
    return split, query, candidate, values


def read_candidates(path, original_path, truth, np):
    n = sum(ROW_COUNTS.values())
    x, y = np.empty((n, len(FEATURES)), dtype=np.float64), np.empty(n, dtype=np.int8)
    frozen = np.empty(n, dtype=np.float64)
    groups = {query: [] for query in truth}
    seen, ranks = {q: set() for q in truth}, {q: set() for q in truth}
    queries, candidates, splits, counts = [], [], [], Counter()
    with path.open(newline="", encoding="utf-8") as handle, original_path.open(newline="", encoding="utf-8") as original:
        reader, original_reader = csv.DictReader(handle), csv.DictReader(original)
        require(reader.fieldnames == COLUMNS and original_reader.fieldnames == BASE_COLUMNS, "eleven_real_feature_csv_required")
        for i, (row, frozen_row) in enumerate(zip_longest(reader, original_reader)):
            require(i < n and row is not None and frozen_row is not None, "candidate_row_count_mismatch")
            split, query, candidate, values = validate_row(row, truth)
            require(None not in frozen_row and all(frozen_row.get(k) == row[k] for k in BASE_COLUMNS),
                    "original_candidate_tokens_changed")
            require(candidate not in seen[query] and row["baseline_rank"] not in ranks[query] and
                    len(groups[query]) < 100, "duplicate_or_excess_candidate")
            seen[query].add(candidate)
            ranks[query].add(row["baseline_rank"])
            groups[query].append(i)
            x[i], y[i], frozen[i] = values, int(row["label"]), float(row["r4_score"])
            queries.append(query)
            candidates.append(candidate)
            splits.append(split)
            counts[split] += 1
    require(dict(counts) == ROW_COUNTS and all(len(v) == 100 for v in groups.values()), "incomplete_train_dev_pool")
    require(bool(np.isfinite(x).all()) and bool(np.isfinite(frozen).all()), "nonfinite_candidate_matrix")
    return {"x": x, "y": y, "frozen_scores": frozen, "groups": groups, "queries": queries, "candidates": candidates,
            "splits": splits, "truth": truth}


def training_rows(data, np):
    truth, groups, y = data["truth"], data["groups"], data["y"]
    usable = [q for q in sorted(truth) if truth[q][0] == "train" and int(y[groups[q]].sum()) == 1]
    require(len(usable) == 3280, "trainable_query_count_mismatch")
    family_queries = Counter(truth[q][1] for q in usable)
    indices, weights = [], []
    for query in usable:
        ids = groups[query]
        mass = 1.0 / family_queries[truth[query][1]]
        indices.extend(ids)
        weights.extend(mass if y[i] == 1 else mass/99 for i in ids)
    indices, weights = np.asarray(indices, dtype=np.int64), np.asarray(weights, dtype=np.float64)
    weights *= len(weights)/float(weights.sum())
    require(len(indices) == 328000 and bool(np.isfinite(weights).all()) and bool((weights > 0).all()),
            "invalid_training_weights")
    require(math.isclose(float(weights[y[indices] == 1].sum()), float(weights[y[indices] == 0].sum()), rel_tol=1e-12),
            "positive_negative_weight_mismatch")
    return indices, weights, len(family_queries)


def query_scores(data, score):
    require(len(score) == len(data["queries"]) and all(math.isfinite(float(v)) for v in score), "invalid_rank_scores")
    result = {split: {} for split in COUNTS}
    for query in sorted(data["groups"]):
        split, family = data["truth"][query]
        order = sorted(data["groups"][query], key=lambda i: (-float(score[i]), data["candidates"][i]))
        positive = [rank for rank, i in enumerate(order, 1) if data["y"][i] == 1]
        top = order[0]
        result[split][query] = {"rank": positive[0] if positive else None,
            "correct": bool(data["y"][top]), "family": family,
            "family_correct": data["truth"][data["candidates"][top]][1] == family,
            "top_candidate": data["candidates"][top], "top_score": float(score[top]), "candidates": len(order)}
    return result


def retrieval_metrics(table):
    n = len(table)
    require(n > 0, "empty_query_denominator")
    ranks = [r["rank"] for r in table.values() if r["rank"] is not None]
    metrics = {"queries": n, "families": len({r["family"] for r in table.values()}),
        "candidate_recall": len(ranks)/n, "candidate_recall_count": len(ranks),
        "missing_positive_queries": n-len(ranks), "mrr": math.fsum(1/r for r in ranks)/n,
        "family_recall_at_1": sum(r["family_correct"] for r in table.values())/n}
    for k in (1, 5, 10, 50, 100):
        correct = sum(rank <= k for rank in ranks)
        metrics["correct_at_" + str(k)], metrics["recall_at_" + str(k)] = correct, correct/n
    return metrics


def paired_changes(table, baseline):
    require(table.keys() == baseline.keys(), "paired_query_cohort_mismatch")
    pairs = {"corrected_errors": 0, "new_errors": 0, "unchanged_correct": 0, "unchanged_incorrect": 0}
    for query, row in table.items():
        old, new = baseline[query]["correct"], row["correct"]
        key = ("unchanged_correct" if old else "corrected_errors") if new else (
            "new_errors" if old else "unchanged_incorrect")
        pairs[key] += 1
    delta = sum(r["correct"] for r in table.values()) - sum(r["correct"] for r in baseline.values())
    require(sum(pairs.values()) == len(table) and delta == pairs["corrected_errors"]-pairs["new_errors"],
            "paired_count_inconsistency")
    return {"queries": len(table), **pairs, "net_correct_change": delta}


def selection_key(candidate):
    return (-candidate["dev"]["correct_at_1"], -candidate["dev"]["mrr"],
            candidate["parameters"]["max_leaf_nodes"], -candidate["parameters"]["l2_regularization"])


def weighted_logloss(y, score, weights, np):
    return float(np.sum(weights*(np.logaddexp(0.0, score)-y*score))/weights.sum())


def export_private_rows(directory, data, scores, query_tables, selected):
    methods = list(scores)
    with (directory/"predictions.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["split", "query_id", "candidate_id", *methods, "selected_rank_score"])
        for i, query in enumerate(data["queries"]):
            writer.writerow([data["splits"][i], query, data["candidates"][i],
                             *[format(float(scores[m][i]), ".17g") for m in methods],
                             format(float(scores[selected][i]), ".17g")])
    with (directory/"query_metrics.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["method", "split", "query_id", "query_family", "top_candidate", "exact_correct",
                         "family_correct", "positive_rank", "candidates", "top_score", "selected"])
        for method, partitions in query_tables.items():
            for split, table in partitions.items():
                for query, row in table.items():
                    writer.writerow([method, split, query, row["family"], row["top_candidate"], int(row["correct"]),
                                     int(row["family_correct"]), "" if row["rank"] is None else row["rank"],
                                     row["candidates"], format(row["top_score"], ".17g"), int(method == selected)])


def run(args, started, state):
    root, source = bind_source(args.protocol, args.source_commit)
    output = args.output.resolve()
    require(not args.output.exists() and not args.output.is_symlink() and not output.is_relative_to(root),
            "new_output_outside_checkout_required")
    require(all(not p.is_symlink() for p in args.output.parents), "output_parent_symlink_refused")
    paths, hashes, truth, baseline = bind_inputs(args.control, args.prepared, args.baseline_model, args.verification_sha256)
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = "4"
    import joblib
    import numpy as np
    import scipy
    import sklearn
    from sklearn.ensemble import HistGradientBoostingClassifier
    from threadpoolctl import threadpool_limits, threadpool_info

    require(sklearn.__version__ == "1.9.1" and np.__version__ == "2.5.4" and scipy.__version__ == "1.18.1",
            "runtime_package_version_changed")
    require(platform.machine() == "arm64" and sys.version_info[:3] == (3, 15, 2), "runtime_platform_changed")
    dependency_path = Path(inspect.getsourcefile(HistGradientBoostingClassifier))
    dependency_hash = sha(dependency_path)
    runtime = {"python": platform.python_version(), "machine": platform.machine(), "numpy": np.__version__,
               "scipy": scipy.__version__, "scikit_learn": sklearn.__version__, "joblib": joblib.__version__,
               "hist_gradient_boosting_source_sha256": dependency_hash, **RUNTIME}
    data = read_candidates(paths["feature_csv_sha256"], paths["candidates_sha256"], truth, np)
    indices, weights, fitted_families = training_rows(data, np)
    reconstructed = ((data["x"][:, :len(BASE_FEATURES)] - np.asarray(baseline["scaler"]["center"])) /
                     np.asarray(baseline["scaler"]["scale"])) @ np.asarray(baseline["coefficients"])
    frozen = data["frozen_scores"]
    require(bool(np.allclose(frozen, reconstructed, atol=1e-10, rtol=1e-10)), "frozen_score_reconstruction_mismatch")
    baseline_score_error = float(np.max(np.abs(frozen-reconstructed)))
    query_tables = {"frozen_r4": query_scores(data, frozen)}
    baseline_metrics = {s: retrieval_metrics(t) for s, t in query_tables["frozen_r4"].items()}
    base_dev = baseline_metrics["dev"]
    require(base_dev["queries"] == 727 and base_dev["correct_at_1"] == 466 and
            base_dev["candidate_recall_count"] == 719 and base_dev["missing_positive_queries"] == 8 and
            math.isclose(base_dev["mrr"], 0.74328496725491622, abs_tol=1e-12, rel_tol=0), "frozen_baseline_drift")
    output.mkdir(parents=True, exist_ok=False)
    state["output_created"] = True
    private = output/"private"
    private.mkdir()
    scores, candidates, models = {"frozen_r4": frozen}, [], {}
    x_train, y_train = data["x"][indices], data["y"][indices]
    positive_weight = float(weights[y_train == 1].sum())
    negative_weight = float(weights[y_train == 0].sum())
    initial_bias = math.log(positive_weight/negative_weight)
    initial_loss = weighted_logloss(y_train, initial_bias, weights, np)
    print(json.dumps({"stage": "admitted", "experiment": EXPERIMENT, "training_rows": len(indices),
                      "training_queries": 3280, "dev_queries": 727, "baseline_correct_at_1": 466}), flush=True)
    with threadpool_limits(limits=4):
        runtime["observed_threadpools"] = [{k: p.get(k) for k in ("user_api", "internal_api", "num_threads")}
                                           for p in threadpool_info()]
        require(all(p["num_threads"] <= 4 for p in runtime["observed_threadpools"]), "thread_limit_not_applied")
        for grid in GRID:
            method = "hgb_leaves%d_l2_%d" % (grid["max_leaf_nodes"], grid["l2_regularization"])
            fit_started = time.monotonic()
            estimator = HistGradientBoostingClassifier(**FIXED, **grid, max_depth=None, max_features=1.0,
                monotonic_cst=None, interaction_cst=None, warm_start=False, validation_fraction=None)
            estimator.fit(x_train, y_train, sample_weight=weights)
            # Evaluate only completed fixed-length models; no validation arguments or dev stopping.
            all_scores = estimator.decision_function(data["x"])
            final_loss = weighted_logloss(y_train, all_scores[indices], weights, np)
            require(int(estimator.n_iter_) == 150 and int(estimator.n_trees_per_iteration_) == 1 and
                    bool(np.isfinite(all_scores).all()) and math.isfinite(final_loss) and final_loss < initial_loss,
                    "fit_did_not_complete_or_reduce_training_loss")
            update = float(np.max(np.abs(all_scores[indices] - initial_bias)))
            require(update > 0 and math.isfinite(update), "model_scores_did_not_change")
            scores[method] = all_scores
            query_tables[method] = query_scores(data, all_scores)
            per_split = {s: retrieval_metrics(t) for s, t in query_tables[method].items()}
            model_path = private/(method + ".joblib")
            joblib.dump(estimator, model_path, compress=3)
            model_sha = sha(model_path)
            models[method] = model_path
            candidate = {"method": method, "parameters": {**FIXED, **grid}, **per_split,
                "paired_dev_against_frozen": paired_changes(query_tables[method]["dev"], query_tables["frozen_r4"]["dev"]),
                "optimization": {"completed_trees": int(estimator.n_iter_), "initial_weighted_logloss": initial_loss,
                    "final_weighted_logloss": final_loss, "training_score_update_max_abs": update,
                    "elapsed_seconds": time.monotonic()-fit_started, "completed": True}, "model_sha256": model_sha}
            candidates.append(candidate)
            print(json.dumps({"stage": "fit_complete", "method": method, "dev": candidate["dev"],
                              "optimization": candidate["optimization"]}, sort_keys=True), flush=True)
    best = min(candidates, key=selection_key)
    improves = (best["dev"]["correct_at_1"], best["dev"]["mrr"]) > (base_dev["correct_at_1"], base_dev["mrr"])
    selected = best["method"] if improves else "frozen_r4"
    best_path = private/"best-trained.joblib"
    with best_path.open("xb") as handle:
        handle.write(models[best["method"]].read_bytes())
    require(sha(best_path) == best["model_sha256"], "best_model_copy_mismatch")
    # Load only our just-written, hash-bound model; never accept an external pickle.
    restored = joblib.load(best_path)
    with threadpool_limits(limits=4):
        require(bool(np.array_equal(restored.decision_function(data["x"]), scores[best["method"]])), "model_serialization_parity_failed")
    export_private_rows(private, data, scores, query_tables, selected)
    _, final_source = bind_source(args.protocol, args.source_commit)
    require(final_source == source and all(sha(path) == hashes[name] for name, path in paths.items()) and
            sha(dependency_path) == dependency_hash, "source_or_input_changed_during_run")
    provenance = {**source, **hashes, "prepared_source_commit": PINS["prepared_source_commit"]}
    common = {"schema_version": 1, "work_id": WORK_ID, "experiment": EXPERIMENT, "provenance": provenance,
              **FLAGS, "accepted_coverage_measured": False, "ocr_transcription_accuracy_measured": False,
              "new_image_features": True, "provider_inference_calls": 0, "provider_inference_calls_scope": "this CPU trainer",
              "new_foundation_weights_trained": False, "ranking_weights_optimized": True}
    model_summary = {**common, "best_trained_method": best["method"], "best_trained_model_sha256": best["model_sha256"],
        "selected_method": selected, "baseline_retained": not improves, "feature_names": FEATURES,
        "selected_feature_names": FEATURES if improves else BASE_FEATURES,
        "best_trained_parameters": best["parameters"], "scikit_learn_version": sklearn.__version__,
        "best_trained_rank_score": "raw decision_function; pointwise weighted binary logloss model",
        "selected_model_sha256": best["model_sha256"] if improves else PINS["baseline_model_sha256"],
        "selected_model_kind": "hist_gradient_boosting_pointwise" if improves else "frozen_r4_ridge_pairwise_logistic",
        "selected_rank_score": "raw histogram-tree decision_function" if improves else "frozen R4 standardized six-feature linear score",
        "rank_score_is_probability": False, "policy": {"calibrated": False, "threshold": None}}
    write_json(output/"model-summary.json", model_summary)
    report = {**common, "status": "completed_research_only", "feature_names": FEATURES,
        "counts": COUNTS, "candidate_rows": ROW_COUNTS, "consumed_partitions": ["train", "dev"],
        "training": {"fits": 4, "trained_rows": len(indices), "trainable_queries": 3280,
            "trainable_families": fitted_families, "skipped_missing_positive_train_queries": 33,
            "weight_mean": float(weights.mean()), "positive_weight_total": positive_weight,
            "negative_weight_total": negative_weight,
            "weighting": "equal usable family, then query, then positive/negative half mass; mean row weight one",
            "preprocessing": "native train-only histogram binning; no scaling", "development_early_stopping": False},
        "runtime": runtime, "frozen_baseline": baseline_metrics, "optimizer_candidates": candidates,
        "selection": {"method": selected, "baseline_retained": not improves, "best_trained_method": best["method"],
            "best_trained_dev": best["dev"], "selected_dev": retrieval_metrics(query_tables[selected]["dev"]),
            "selected_model_sha256": model_summary["selected_model_sha256"],
            "selected_model_kind": model_summary["selected_model_kind"],
            "rule": "dev Recall@1, MRR, fewer leaves, larger L2; exact tie retains frozen R4"},
        "private_artifact_sha256": {"best_trained_model": best["model_sha256"],
            "predictions": sha(private/"predictions.csv"), "query_metrics": sha(private/"query_metrics.csv")},
        "model_summary_sha256": sha(output/"model-summary.json"),
        "execution": {"elapsed_seconds": time.monotonic()-started, "serialization_prediction_parity": True,
            "frozen_score_reconstruction_max_abs_error": baseline_score_error,
            "prediction_rows": sum(ROW_COUNTS.values()), "query_metrics_rows": 5*sum(COUNTS.values())},
        "limitations": ["Pointwise histogram-tree classification scores are used only for within-query ranking; this is not LambdaMART.",
            "Development was reused for model selection; these are not fresh qualification metrics.",
            "Missing positives remain in every evaluation denominator; no candidates are injected.",
            "Frozen reverse-rank and density features use unlabeled same-split query batches.",
            "The added RADIO and OCR pair features come from the verified pinned extraction; foundation models are not fine-tuned.",
            "OCR text presence and lexical overlaps do not measure transcription accuracy.",
            "The four HGB configurations were copied unchanged from R7 before R8 development scores were viewed."]}
    write_json(output/"report.json", report)
    print(json.dumps({"stage": "complete", "selected_method": selected, "baseline_retained": not improves,
                      "report_sha256": sha(output/"report.json"), **FLAGS}, sort_keys=True), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("control", "prepared", "baseline-model", "protocol", "output"):
        parser.add_argument("--"+key, required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--verification-sha256", required=True)
    args = parser.parse_args()
    started = time.monotonic()
    state = {"output_created": False}

    def timeout(signum, frame):
        raise TimeoutError("cpu_wall_budget_exhausted")

    signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, RUNTIME["max_wall_seconds"])
    try:
        run(args, started, state)
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        signal.setitimer(signal.ITIMER_REAL, 0)
        code = str(error) if re.fullmatch(r"[a-z_]+", str(error)) else type(error).__name__
        failure = {"schema_version": 1, "work_id": WORK_ID, "experiment": EXPERIMENT,
                   "status": "FAILED", "error_code": code, "elapsed_seconds": time.monotonic()-started, **FLAGS}
        if state["output_created"] and args.output.is_dir() and not args.output.is_symlink() and not (args.output/"failure.json").exists():
            write_json(args.output/"failure.json", failure)
        print(json.dumps(failure, sort_keys=True), file=sys.stderr, flush=True)
        raise SystemExit(1)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == "__main__":
    main()
