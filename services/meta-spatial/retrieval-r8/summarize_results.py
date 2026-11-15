#!/usr/bin/env python3
"""Publish allowlisted R8 aggregates from the preserved, verified R6-source run.

No network, Git calls, package dependencies, raw rows, OCR text, or local paths
are exported. This is an artifact summarizer, not an acceptance qualification.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys

COMMIT = "8948b44454f1a5dd174395e6d69e1ae8b533688b"
WORK_ID = "META-LENS-R8-20261115"
INPUT_WORK_ID = "META-LENS-R6-VERDA-20261114"
IMAGE_INPUT_SHA = "47a015b6cf7f2ef10ff246fbf325e3f63459aa277d8ab3bd4bd6f61b4e0ce25f"
PREPARED_SHA = "817435715686cc2d98eea94ea5d4fa95450fb803be3328eb66feb53185b631d0"
SOURCE_HASHES = {
    "extract_nvidia.py": "a31e08d925b439b5d9e01d75dc9eb8a4397696425c2908853a96f6809421da11",
    "prepare_inputs.py": "9d3a7a931be628f93ccb3c1a900aadc04cdec3aab3954fde232f011d2b35f2a8",
    "build_features.py": "90b726bd2aae727168d1605681a5ea9b7ae7c7e4559cbb5658a8ca32e3dc0fa1",
    "train_reranker.R": "4dcd524d7ea1ab5df2574bffaa6871c26c31c67ed22c00e92619e987e7e29ad5",
}
BASELINE_SHA = "4f6db7b937a244b2a6cdf5298d6087bcd84d01445219882c2b7d041986a3a0b6"
BASE = ["f_visual", "f_adapted", "f_text", "f_reverse_rank", "f_density", "f_gap"]
OCR = ["f_ocr_visual_match", "f_ocr_catalog_match", "f_ocr_digit_match", "f_ocr_digit_conflict"]
RECIPES = {"refit6": BASE, "plus_radio": BASE + ["f_radio"],
           "plus_ocr": BASE + OCR, "plus_both": BASE + ["f_radio"] + OCR}
COUNTS = {"train": 3313, "dev": 727}
ROWS = {"train": 331300, "dev": 72700}
FLAGS = {"qualification": False, "action_authorized": False,
         "physical_identity_verified": False}
PINS = {"ocr": ("nvidia/nemotron-ocr-v2", "0e83e83f17943524b90afa6c0fd82ac2bc1a40ca"),
        "radio": ("nvidia/C-RADIOv4-SO400M", "c0457f5dc26ca145f954cd4fc5bb6114e5705ad8")}
METRICS = ["candidate_recall", "recall_at_1", "recall_at_5", "recall_at_10",
           "recall_at_50", "recall_at_100", "mrr", "family_recall_at_1"]


def require(ok, code):
    if not ok:
        raise ValueError(code)


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def bad_constant(value):
    raise ValueError("nonfinite_json_constant")


def decode(raw):
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(path):
    require(path.is_file() and not path.is_symlink(), "regular_input_file_required")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def digest(value):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "invalid_digest")
    return value


def integer(value, low=0, high=None):
    require(type(value) is int and value >= low and (high is None or value <= high), "invalid_integer")
    return value


def number(value, low=None, high=None):
    require(type(value) in (int, float) and math.isfinite(value), "invalid_number")
    require((low is None or value >= low) and (high is None or value <= high), "number_out_of_range")
    return value


def close(left, right):
    return math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-10)


def false_flags(value):
    require(all(value.get(key) is False for key in FLAGS), "qualification_flag_not_false")


def version(value):
    require(type(value) is str and len(value) <= 80 and
            re.fullmatch(r"[0-9][a-zA-Z0-9_.+!\-]*", value), "invalid_package_version")
    return value


def provenance(value):
    require(value["source_commit"] == value["feature_source_commit"] == COMMIT, "training_source_mismatch")
    require(value["baseline_model_sha256"] == BASELINE_SHA, "baseline_model_mismatch")
    require(value["consumed_partitions"] == ["train", "dev"], "unexpected_partitions")
    require(all(value.get(k) is True for k in
                ("family_disjoint", "product_disjoint", "image_hash_disjoint")), "split_admission_missing")
    return {"source_commit": COMMIT, "feature_source_commit": COMMIT,
            **{k: digest(value[k]) for k in ("training_script_sha256", "input_sha256",
                                            "manifest_sha256", "baseline_model_sha256")},
            "consumed_partitions": ["train", "dev"], "family_disjoint": True,
            "product_disjoint": True, "image_hash_disjoint": True}


def metrics(value, split):
    n = COUNTS[split]
    require(value["queries"] == n, "metric_denominator_mismatch")
    result = {"queries": n, "families": integer(value["families"], 1, n),
              "missing_positive_queries": integer(value["missing_positive_queries"], 0, n)}
    result.update({key: number(value[key], 0, 1) for key in METRICS})
    require(close(result["candidate_recall"], (n - result["missing_positive_queries"]) / n),
            "candidate_recall_denominator_mismatch")
    previous = 0
    for k in (1, 5, 10, 50, 100):
        recall = result["recall_at_" + str(k)]
        require(recall >= previous and close(n * recall, round(n * recall)), "invalid_recall_count")
        result["correct_at_" + str(k)] = round(n * recall)
        previous = recall
    require(close(result["recall_at_100"], result["candidate_recall"]) and
            result["recall_at_1"] <= result["mrr"] <= result["candidate_recall"], "metric_bounds_mismatch")
    return result


def scaler(value, features):
    require(value["feature_names"] == features, "scaler_feature_mismatch")
    center, scale = value["center"], value["scale"]
    require(type(center) is list and type(scale) is list and
            len(center) == len(scale) == len(features), "scaler_shape_mismatch")
    constants = value["constant_features"]
    if type(constants) is str:  # The base-R serializer unboxes a singleton string.
        constants = [constants]
    require(type(constants) is list and len(set(constants)) == len(constants) and
            set(constants) <= set(features), "invalid_constant_features")
    return {"feature_names": features, "center": [number(x) for x in center],
            "scale": [number(x, 0) for x in scale], "constant_features": constants}


def fit_summary(value):
    method, ridge = value["method"], value["lambda"]
    require(method in RECIPES and ridge in (0.01, 0.1, 1), "unexpected_fit_recipe")
    features = RECIPES[method]
    require(value["feature_names"] == features and value["intercept"] == 0, "fit_features_mismatch")
    coefficients = value["coefficients"]
    require(type(coefficients) is list and len(coefficients) == len(features), "coefficient_shape_mismatch")
    coefficients = [number(x) for x in coefficients]
    scale = scaler(value["scaler"], features)
    require(all(x > 0 for x in scale["scale"]), "zero_scaler_scale")
    opt = value["optimization"]
    require(opt["convergence"] == 0 and opt["parameter_update_observed"] is True, "fit_not_converged_or_updated")
    diagnostic = {"convergence": 0, "parameter_update_observed": True,
                  **{k: number(opt[k], 0) for k in ("initial_objective", "final_objective",
                     "initial_gradient_max_abs", "final_gradient_max_abs", "parameter_update_l2")},
                  "evaluations": {k: integer(opt["evaluations"][k], 1) for k in ("function", "gradient")}}
    require(diagnostic["final_objective"] < diagnostic["initial_objective"] and
            diagnostic["parameter_update_l2"] > 0 and
            close(diagnostic["parameter_update_l2"], math.sqrt(math.fsum(x*x for x in coefficients))),
            "weight_update_or_loss_mismatch")
    training = {k: integer(value["training"][k]) for k in
                ("rows", "queries", "families", "trainable_queries", "trainable_families",
                 "skipped_untrainable_queries", "pairs")}
    require(training["rows"] == ROWS["train"] and training["queries"] == COUNTS["train"] and
            training["trainable_queries"] + training["skipped_untrainable_queries"] == COUNTS["train"] and
            training["pairs"] == 99 * training["trainable_queries"], "training_pair_counts_mismatch")
    training["weighting"] = "equal family, then query, then negative within query"
    return {"method": method, "lambda": ridge, "feature_names": features, "coefficients": coefficients,
            "intercept": 0, "scaler": scale, "optimization": diagnostic,
            "training": training, "dev": metrics(value["dev"], "dev")}


def fit_order(value):
    return (-value["dev"]["recall_at_1"], -value["dev"]["mrr"],
            len(value["feature_names"]), -value["lambda"])


def csv_rows(path, columns):
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == columns, "csv_schema_mismatch")
        for row in reader:
            require(None not in row and all(v is not None for v in row.values()), "malformed_csv_row")
            yield row


def csv_number(value):
    return number(float(value))


def csv_bool(value):
    require(value in ("TRUE", "FALSE"), "invalid_csv_boolean")
    return value == "TRUE"


def query_tables(path, selected, winners):
    tables = {method: {split: {} for split in COUNTS} for method in ["frozen_r4", *RECIPES]}
    columns = ["split", "query_id", "query_family", "candidate_id", "exact_correct", "family_correct",
               "positive_rank", "candidates", "top_score", "gap", "confidence", "method", "lambda", "selected"]
    for row in csv_rows(path, columns):
        method, split, query = row["method"], row["split"], row["query_id"]
        require(method in tables and split in COUNTS and bool(query), "unexpected_query_record")
        table = tables[method][split]
        require(query not in table and row["query_family"] and row["candidate_id"], "duplicate_or_empty_query")
        require(int(row["candidates"]) == 100 and csv_bool(row["selected"]) == (method == selected),
                "query_selection_or_pool_mismatch")
        rank = None if row["positive_rank"] == "" else int(row["positive_rank"])
        require(rank is None or 1 <= rank <= 100, "invalid_positive_rank")
        exact = csv_bool(row["exact_correct"])
        require(exact == (rank == 1) == (query == row["candidate_id"]), "query_correctness_mismatch")
        require((method == "frozen_r4" and row["lambda"] == "") or
                (method != "frozen_r4" and csv_number(row["lambda"]) == winners[method]["lambda"]),
                "query_ridge_mismatch")
        top, gap, confidence = [csv_number(row[k]) for k in ("top_score", "gap", "confidence")]
        require(gap >= 0 and close(confidence, top + gap), "query_score_mismatch")
        table[query] = {"family": row["query_family"], "candidate": row["candidate_id"],
                        "correct": exact, "family_correct": csv_bool(row["family_correct"]),
                        "rank": rank, "top_score": top}
    for split, n in COUNTS.items():
        baseline = tables["frozen_r4"][split]
        require(len(baseline) == n, "query_count_mismatch")
        for method in RECIPES:
            table = tables[method][split]
            require(table.keys() == baseline.keys() and all(table[q]["family"] == baseline[q]["family"] and
                    (table[q]["rank"] is None) == (baseline[q]["rank"] is None) for q in table),
                    "method_query_cohort_mismatch")
    require(not (tables["frozen_r4"]["train"].keys() & tables["frozen_r4"]["dev"].keys()), "query_split_overlap")
    return tables


def table_metrics(table, split):
    n = len(table)
    ranks = [row["rank"] for row in table.values() if row["rank"] is not None]
    raw = {"queries": n, "families": len({row["family"] for row in table.values()}),
           "missing_positive_queries": n - len(ranks), "candidate_recall": len(ranks)/n,
           "mrr": math.fsum(1/r for r in ranks)/n,
           "family_recall_at_1": sum(row["family_correct"] for row in table.values())/n}
    raw.update({"recall_at_"+str(k): sum(r <= k for r in ranks)/n for k in (1, 5, 10, 50, 100)})
    return metrics(raw, split)


def same_metrics(left, right):
    require(left.keys() == right.keys() and all(close(left[k], right[k]) for k in left), "csv_report_metrics_mismatch")


def verify_predictions(path, tables, selected):
    groups = {}
    columns = ["split", "query_id", "candidate_id", "rank_score", "r4_score", "selected_method"]
    for row in csv_rows(path, columns):
        split, query, candidate = row["split"], row["query_id"], row["candidate_id"]
        require(split in COUNTS and query in tables["frozen_r4"][split] and candidate and
                row["selected_method"] == selected, "prediction_cohort_mismatch")
        group = groups.setdefault((split, query), {})
        require(candidate not in group and len(group) < 100, "duplicate_or_excess_prediction")
        group[candidate] = (csv_number(row["rank_score"]), csv_number(row["r4_score"]))
    require(len(groups) == sum(COUNTS.values()), "prediction_query_count_mismatch")
    for (split, query), group in groups.items():
        require(len(group) == 100, "prediction_pool_incomplete")
        for method, index in ((selected, 0), ("frozen_r4", 1)):
            order = sorted(group, key=lambda candidate: (-group[candidate][index], candidate))
            expected = tables[method][split][query]
            rank = order.index(query) + 1 if query in group else None
            require(order[0] == expected["candidate"] and rank == expected["rank"] and
                    close(group[order[0]][index], expected["top_score"]), "prediction_ranking_mismatch")
        if selected == "frozen_r4":
            require(all(scores[0] == scores[1] for scores in group.values()), "baseline_passthrough_mismatch")


def paired(table, reference):
    require(table.keys() == reference.keys(), "paired_cohort_mismatch")
    counts = {"corrected_errors": 0, "new_errors": 0, "unchanged_correct": 0, "unchanged_incorrect": 0}
    for query, row in table.items():
        old, new = reference[query]["correct"], row["correct"]
        key = ("unchanged_correct" if old else "corrected_errors") if new else (
            "new_errors" if old else "unchanged_incorrect")
        counts[key] += 1
    require(sum(counts.values()) == COUNTS["dev"], "paired_denominator_mismatch")
    change = sum(r["correct"] for r in table.values()) - sum(r["correct"] for r in reference.values())
    require(change == counts["corrected_errors"] - counts["new_errors"], "paired_net_change_mismatch")
    return {"queries": COUNTS["dev"], **counts, "unchanged_total": counts["unchanged_correct"] +
            counts["unchanged_incorrect"], "net_correct_change": change,
            "recall_at_1_change_percentage_points": 100*change/COUNTS["dev"]}


def weight_inventory(files, expected):
    require(type(files) is list and bool(files), "empty_weight_inventory")
    names, total = [], 0
    for item in files:
        require(set(item) == {"path", "sha256", "size_bytes"} and type(item["path"]) is str,
                "weight_inventory_schema_mismatch")
        names.append(item["path"])
        digest(item["sha256"])
        total += integer(item["size_bytes"], 1)
    require(names == sorted(set(names)) and hashlib.sha256(canonical(files)).hexdigest() == digest(expected),
            "weight_inventory_digest_mismatch")
    return {"file_count": len(files), "total_bytes": total, "aggregate_sha256": expected}


def quantile(values, probability):
    if not values:
        return None
    values = sorted(values)
    at = (len(values) - 1) * probability
    lo, hi = math.floor(at), math.ceil(at)
    return values[lo] + (at - lo) * (values[hi] - values[lo])


def observation_aggregates(path, dimension):
    seen, spans_per_image, confidences = set(), [], []
    text_images = nonempty_spans = 0
    with path.open("rb") as stream:
        for raw in stream:
            row = decode(raw)
            require(set(row) == {"image_id", "sha256", "ocr", "radio"}, "observation_schema_mismatch")
            identity = digest(row["sha256"])
            require(row["image_id"] == "img-" + identity and identity not in seen, "duplicate_or_invalid_image")
            seen.add(identity)
            ocr, radio = row["ocr"], row["radio"]
            require(ocr["status"] == "ok" and type(ocr["spans"]) is list and len(ocr["spans"]) <= 4096,
                    "incomplete_ocr_observation")
            present = False
            spans_per_image.append(len(ocr["spans"]))
            for span in ocr["spans"]:
                require(type(span["text"]) is str and len(span["text"]) <= 65536, "invalid_ocr_text")
                has_text = bool(span["text"].strip())
                present |= has_text
                nonempty_spans += int(has_text)
                confidences.append(number(span["confidence"], 0, 1))
                box = span["box_normalized"]
                require(type(box) is list and len(box) == 4, "invalid_ocr_box")
                box = [number(x, 0, 1) for x in box]
                require(box[0] < box[2] and box[1] < box[3], "invalid_ocr_geometry")
            text_images += int(present)
            vector = radio["embedding"]
            require(radio["dimension"] == dimension and type(vector) is list and len(vector) == dimension,
                    "embedding_shape_mismatch")
            norm = math.sqrt(math.fsum(number(x)**2 for x in vector))
            require(abs(norm - 1) <= 0.001, "embedding_not_normalized")
    require(len(seen) == 6993, "observation_count_mismatch")
    return {"images": len(seen), "images_with_text": text_images, "images_without_text": len(seen)-text_images,
            "text_presence_fraction": text_images/len(seen), "images_with_spans": sum(x > 0 for x in spans_per_image),
            "span_count": len(confidences), "nonempty_text_span_count": nonempty_spans,
            "spans_per_image": {"mean": len(confidences)/len(seen), "median": quantile(spans_per_image, .5),
                                "p95": quantile(spans_per_image, .95), "max": max(spans_per_image)},
            "span_confidence": {"count": len(confidences),
                "mean": math.fsum(confidences)/len(confidences) if confidences else None,
                "min": min(confidences) if confidences else None, "max": max(confidences) if confidences else None,
                "median": quantile(confidences, .5), "p95": quantile(confidences, .95)},
            "confidence_is_transcription_accuracy": False, "transcription_ground_truth_evaluated": False}


def extraction_summary(value, observations):
    false_flags(value)
    require(value["schema"] == "meta_r6_extraction_v1" and value["source_commit"] == COMMIT and
            value["status"] == "complete" and value["complete"] is True, "extraction_not_complete")
    counts = {k: integer(value["counts"][k]) for k in
              ("manifest_images", "expected_images", "observed_images", "failed_images")}
    require(counts == {"manifest_images": 6993, "expected_images": 6993, "observed_images": 6993,
                       "failed_images": 0}, "extraction_count_mismatch")
    models = {}
    for name, (model_id, revision) in PINS.items():
        model = value["models"][name]
        require(model["model_id"] == model_id and model["revision"] == revision, "model_pin_mismatch")
        models[name] = {"model_id": model_id, "revision": revision,
            "weights": weight_inventory(model["files"], model["weights_sha256"]),
            "source_and_weights": weight_inventory(model["source_and_weight_files"], model["source_and_weights_sha256"])}
    runtime = value["runtime"]
    gpu = runtime["gpu"]
    require(gpu == "NVIDIA L40S",
            "unexpected_public_gpu_model_name")
    python_version = re.match(r"^(\d+\.\d+\.\d+)", runtime["python"])
    require(python_version is not None and runtime["device_count"] == 1, "runtime_shape_mismatch")
    packages = {k: None if runtime["packages"][k] is None else version(runtime["packages"][k]) for k in
                ("torch", "torchvision", "transformers", "timm", "numpy", "pillow", "huggingface_hub", "einops", "nemotron-ocr")}
    require(runtime["radio_autocast_dtype"] in ("torch.bfloat16", "torch.float16"), "invalid_radio_dtype")
    times = {k: value[k] for k in ("started_at_utc", "finished_at_utc")}
    require(all(type(v) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", v) for v in times.values()),
            "invalid_extraction_timestamp")
    dimension = integer(value["radio_dimension"], 32, 65536)
    memory = {k: integer(value["gpu_memory"][k]) for k in ("peak_allocated_bytes", "peak_reserved_bytes")}
    return {"status": "complete", "source_commit": COMMIT, "extractor_source_sha256": digest(value["source_sha256"]),
            "input_manifest_sha256": digest(value["input_sha256"]), "dataset_sha256": digest(value["dataset_sha256"]),
            "observations_sha256": digest(value["observations_sha256"]), "models": models, "counts": counts,
            "runtime": {"python_version": python_version.group(1), "packages": packages, "gpu_name": gpu,
                "device_count": 1, "cuda_runtime": version(runtime["cuda_runtime"]),
                "cudnn": None if runtime["cudnn"] is None else integer(runtime["cudnn"]),
                "radio_autocast_dtype": runtime["radio_autocast_dtype"]},
            "timing": {**times, "extractor_elapsed_seconds": number(value["elapsed_seconds"], 0)},
            "gpu_memory": memory, "radio_embedding_dimension": dimension,
            "ocr_observation_aggregates": observation_aggregates(observations, dimension),
            "new_foundation_weights_trained": False}


def summarize(control, extraction):
    require(extraction.resolve() == (control/"gpu-output-01/extraction-01").resolve(),
            "r8_extraction_directory_mismatch")
    own_source = Path(__file__).resolve()
    own_source_sha = sha(own_source)
    paths = {"training_report": control/"training-01/report.json", "trained_model": control/"training-01/model.json",
             "query_metrics": control/"training-01/query_metrics.csv", "predictions": control/"training-01/predictions.csv",
             "training_verification": control/"training-verification.json",
             "extraction_summary": extraction/"summary.json", "observations": extraction/"observations.jsonl"}
    hashes = {key: sha(path) for key, path in paths.items()}
    report, model, verified, extracted = [decode(paths[key].read_bytes()) for key in
                                         ("training_report", "trained_model", "training_verification", "extraction_summary")]
    false_flags(verified)
    require(verified["schema"] == "meta_r8_training_verification_v1" and
            verified["source_commit"] == COMMIT and verified["source_clean_after_training"] is True and
            verified["report_sha256"] == hashes["training_report"] and verified["model_sha256"] == hashes["trained_model"],
            "training_verification_binding_mismatch")
    require(verified["source_files_sha256"] == SOURCE_HASHES and verified["verified_images"] == 6993 and
            verified["accepted_coverage_measured"] is False and verified["ocr_transcription_accuracy_measured"] is False,
            "r8_verification_source_or_scope_mismatch")
    input_bindings = verified["input_artifacts_sha256"]
    require(input_bindings["prepared_manifest"] == PREPARED_SHA and
            input_bindings["inputs.json"] == extracted["input_sha256"] == IMAGE_INPUT_SHA and
            input_bindings["r4_model.json"] == BASELINE_SHA, "r8_verified_input_origin_mismatch")
    require(verified["predictions_sha256"] == hashes["predictions"] and
            verified["query_metrics_sha256"] == hashes["query_metrics"], "r8_verified_csv_digest_mismatch")
    extraction_bindings = verified["extraction_artifacts_sha256"]
    require(extraction_bindings["summary"] == hashes["extraction_summary"] and
            extraction_bindings["observations_sha256"] == hashes["observations"], "r8_verified_extraction_digest_mismatch")
    for name in ("raw_ocr_sha256", "admissions_sha256"):
        require(digest(extraction_bindings[name]) == extracted[name], "r8_raw_evidence_binding_mismatch")
    for name in ("postprocessor_sha256", "transfer_sha256", "worker_sha256", "extraction_archive_sha256"):
        digest(verified[name])  # Validate the receipt; never copy its job/storage details.
    integer(verified["extraction_archive"]["members"], 1, 256)
    integer(verified["extraction_archive"]["unpacked_bytes"], 1, 1024**3)
    expected_verification = {"baseline_dev_correct_at_1": 466, "dev_queries": 727, "candidate_recall_correct": 719,
        "training_fits": 12, "converged_fits": 12, "prediction_rows": 404000, "query_metrics_rows": 20200}
    require(all(verified.get(k) == v for k, v in expected_verification.items()) and
            verified["all_fits_updated_weights"] is True and verified["all_fits_reduced_objective"] is True,
            "training_verification_counts_mismatch")
    artifact_map = {item["path"]: digest(item["sha256"]) for item in report["artifacts"]}
    require(len(report["artifacts"]) == 3 and artifact_map == {"model.json": hashes["trained_model"],
            "predictions.csv": hashes["predictions"], "query_metrics.csv": hashes["query_metrics"]}, "training_artifact_hash_mismatch")
    require(extracted["observations_sha256"] == hashes["observations"], "observation_hash_mismatch")
    for doc in (report, model):
        false_flags(doc)
        require(doc["schema_version"] == 1 and doc["work_id"] == INPUT_WORK_ID, "training_schema_mismatch")
    require(report["status"] == "trained_research_only" and report["counts"] == COUNTS and report["rows"] == ROWS and
            report["consumed_partitions"] == ["train", "dev"] and report["feature_names"] == RECIPES["plus_both"],
            "training_cohort_mismatch")
    prov = provenance(report["provenance"])
    require(provenance(model["provenance"]) == prov, "model_provenance_mismatch")
    require(prov["training_script_sha256"] == SOURCE_HASHES["train_reranker.R"] and
            extracted["source_sha256"] == SOURCE_HASHES["extract_nvidia.py"] and
            verified["feature_csv_sha256"] == prov["input_sha256"] and
            verified["feature_manifest_sha256"] == prov["manifest_sha256"], "r8_training_source_or_feature_binding_mismatch")
    candidates = [fit_summary(item) for item in report["optimizer_candidates"]]
    require(len(candidates) == 12 and {(x["method"], x["lambda"]) for x in candidates} ==
            {(method, ridge) for method in RECIPES for ridge in (.01, .1, 1)}, "fit_grid_mismatch")
    require(report["training"]["fits"] == 12 and report["training"]["regularization_grid"] == [.01, .1, 1], "fit_count_mismatch")
    winners = {}
    require(set(report["ablation_selected_models"]) == set(RECIPES), "missing_ablation")
    for method in RECIPES:
        original = report["ablation_selected_models"][method]
        winner = fit_summary(original)
        require(winner == min((x for x in candidates if x["method"] == method), key=fit_order), "ablation_selection_mismatch")
        winners[method] = {**winner, "train": metrics(original["train"], "train")}
    best = min(candidates, key=fit_order)
    selection = report["selection"]
    baseline = metrics(selection["baseline_dev"], "dev")
    require(baseline["correct_at_1"] == 466 and baseline["correct_at_100"] == 719 and
            baseline["missing_positive_queries"] == 8, "frozen_baseline_drift")
    improves = (best["dev"]["recall_at_1"], best["dev"]["mrr"]) > (baseline["recall_at_1"], baseline["mrr"])
    selected = best["method"] if improves else "frozen_r4"
    require(selection["method"] == model["selected_method"] == selected and selection["baseline_retained"] is (not improves)
            and selection["best_trained_method"] == best["method"], "global_selection_mismatch")
    require(verified["selected_method"] == selected and verified["baseline_retained"] is (not improves),
            "r8_verified_selection_mismatch")
    same_metrics(metrics(selection["best_trained_dev"], "dev"), best["dev"])
    same_metrics(metrics(verified["best_trained_dev"], "dev"), best["dev"])
    tables = query_tables(paths["query_metrics"], selected, winners)
    table_stats = {method: {split: table_metrics(table, split) for split, table in partitions.items()}
                   for method, partitions in tables.items()}
    same_metrics(baseline, table_stats["frozen_r4"]["dev"])
    for method in RECIPES:
        for split in COUNTS:
            same_metrics(winners[method][split], table_stats[method][split])
    verify_predictions(paths["predictions"], tables, selected)
    expected_features = best["feature_names"] if improves else ["r4_score"]
    expected_coefficients = best["coefficients"] if improves else [1]
    expected_scaler = best["scaler"] if improves else {"feature_names": ["r4_score"], "center": [0], "scale": [1], "constant_features": []}
    expected_kind = "ridge_pairwise_logistic" if improves else "frozen_r4_score_passthrough"
    require(model["kind"] == expected_kind and model["feature_names"] == expected_features and
            model["coefficients"] == expected_coefficients and scaler(model["scaler"], expected_features) == expected_scaler and
            model["intercept"] == 0 and model["regularization"] == (best["lambda"] if improves else None), "selected_model_weights_mismatch")
    require(model["baseline_model_sha256"] == BASELINE_SHA and model["rank_score_is_probability"] is False and
            model["policy"]["calibrated"] is False and model["policy"]["threshold"] is None, "acceptance_policy_present")
    execution = report["execution"]
    r_version = re.match(r"^R version (\d+\.\d+\.\d+)", execution["R_version"])
    require(r_version is not None and execution["ranking_weights_optimized"] is True and
            execution["new_foundation_weights_trained"] is False and execution["provider_inference_calls"] == 0,
            "training_execution_mismatch")
    common = {"schema_version": 1, "work_id": WORK_ID, "input_training_work_id": INPUT_WORK_ID,
              "summarizer_source_sha256": own_source_sha, **FLAGS, "input_file_sha256": hashes,
              "upstream_input_hashes_are_provenance_not_recomputed_here": True,
              "accepted_coverage_evaluated": False, "ocr_transcription_accuracy_evaluated": False}
    training = {**common, "status": "trained_research_only", "provenance": prov, "counts": COUNTS, "rows": ROWS,
        "consumed_partitions": ["train", "dev"], "training_fits": 12, "all_optimizer_candidates": candidates,
        "all_ablation_selected_models": winners, "frozen_baseline": table_stats["frozen_r4"],
        "selection": {"method": selected, "baseline_retained": not improves, "best_trained_method": best["method"],
            "best_trained_dev": best["dev"], "selected_metrics": table_stats[selected],
            "rule": "dev Recall@1, then MRR, then fewer features, then larger ridge; exact tie retains frozen R4"},
        "execution": {"R_version": r_version.group(1), "ranking_weights_optimized": True,
            "new_foundation_weights_trained": False, "trainer_provider_inference_calls": 0,
            "trainer_elapsed_seconds": number(execution["elapsed_seconds"], 0)},
        "verification": {**expected_verification, "all_fits_updated_weights": True, "all_fits_reduced_objective": True,
            "local_artifact_digests_checked": True, "csv_counts_rankings_and_selected_metrics_checked": True},
        "limitations": ["Development was reused for selection; these are not independent confirmation metrics.",
            "OCR confidence is a model observation, not measured transcription accuracy.",
            "Retrieval Recall@1 is not accepted coverage; no acceptance threshold was fitted.",
            "Frozen R4 reverse-rank and density features use unlabeled same-split query batches."]}
    trained = {**common, "kind": expected_kind, "selected_method": selected, "feature_names": expected_features,
        "coefficients": expected_coefficients, "scaler": expected_scaler, "intercept": 0,
        "regularization": best["lambda"] if improves else None, "rank_score_is_probability": False,
        "baseline_model_sha256": BASELINE_SHA, "provenance": prov,
        "policy": {"calibrated": False, "threshold": None, "reason": "train_dev_only_no_acceptance_calibration"}}
    training["paired_dev_improvements"] = {"split": "dev", "queries": 727,
        "comparisons": [{"method": method, "reference": reference,
                         **paired(tables[method]["dev"], tables[reference]["dev"])}
                        for method in RECIPES for reference in ("frozen_r4", "refit6")]}
    extraction_output = {**common, **extraction_summary(extracted, paths["observations"])}
    require(all(sha(path) == hashes[key] for key, path in paths.items()) and sha(own_source) == own_source_sha,
            "input_or_summarizer_changed_during_summary")
    return {"training-summary.json": training, "trained-model.json": trained,
            "extraction-summary.json": extraction_output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--extraction", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    require(all(p.is_absolute() for p in (args.control, args.extraction, args.output)), "absolute_paths_required")
    require(not args.output.exists() and not args.output.is_symlink(), "new_output_directory_required")
    require(all(not p.is_symlink() for p in args.output.parents), "output_parent_symlink_refused")
    require(not any((parent/".git").exists() for parent in (args.output, *args.output.parents)),
            "output_must_be_outside_git_checkout")
    outputs = summarize(args.control, args.extraction)
    serialized = {name: (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
                  for name, value in outputs.items()}
    args.output.mkdir(parents=True, exist_ok=False)
    for name, raw in serialized.items():
        with (args.output/name).open("xb") as stream:
            stream.write(raw)
    print(json.dumps({"status": "aggregate_summary_complete", "files_sha256":
        {name: hashlib.sha256(raw).hexdigest() for name, raw in serialized.items()}, **FLAGS}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as error:
        # Never print a data-bearing traceback, path, identifier, or OCR excerpt.
        code = str(error) if type(error) is ValueError and re.fullmatch(r"[a-z_]+", str(error)) else type(error).__name__
        print("SUMMARY_FAILED " + code, file=sys.stderr)
        raise SystemExit(1)
