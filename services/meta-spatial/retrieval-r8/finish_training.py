#!/usr/bin/env python3
"""Verify a preserved R8 extraction, build real R6 features, fit and verify once.

Only private control files are written. Existing outputs are never replaced.
No GPU, network calls, package installs, Git mutations, or publication occur.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import sys
import tarfile
import time

COMMIT = "8948b44454f1a5dd174395e6d69e1ae8b533688b"
REL = "services/meta-spatial/retrieval-r6"
SOURCE_HASHES = {
    "extract_nvidia.py": "a31e08d925b439b5d9e01d75dc9eb8a4397696425c2908853a96f6809421da11",
    "prepare_inputs.py": "9d3a7a931be628f93ccb3c1a900aadc04cdec3aab3954fde232f011d2b35f2a8",
    "build_features.py": "90b726bd2aae727168d1605681a5ea9b7ae7c7e4559cbb5658a8ca32e3dc0fa1",
    "train_reranker.R": "4dcd524d7ea1ab5df2574bffaa6871c26c31c67ed22c00e92619e987e7e29ad5",
}
PREPARED_SHA = "817435715686cc2d98eea94ea5d4fa95450fb803be3328eb66feb53185b631d0"
IMAGE_INPUT_SHA = "47a015b6cf7f2ef10ff246fbf325e3f63459aa277d8ab3bd4bd6f61b4e0ce25f"
R4_REPORT_SHA = "8eda9a3d532b931bc93a765e555bc9008ce9d3c781d1c9efef583e6db515ca80"
BASELINE_SHA = "4f6db7b937a244b2a6cdf5298d6087bcd84d01445219882c2b7d041986a3a0b6"
COUNTS = {"train": 3313, "dev": 727}
ROWS = {"train": 331300, "dev": 72700}
BASE = ["f_visual", "f_adapted", "f_text", "f_reverse_rank", "f_density", "f_gap"]
OCR = ["f_ocr_visual_match", "f_ocr_catalog_match", "f_ocr_digit_match", "f_ocr_digit_conflict"]
RECIPES = {"refit6": BASE, "plus_radio": BASE+["f_radio"], "plus_ocr": BASE+OCR,
           "plus_both": BASE+["f_radio"]+OCR}
FLAGS = {"qualification": False, "action_authorized": False, "physical_identity_verified": False}
MAX_UNPACKED = 1024**3
ROOT_FILES = {"runtime-freeze.txt", "prefetch-admissions.jsonl", "gpu-run.log", "gpu-exit.json"}


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
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


def valid_sha(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def finite(value):
    require(type(value) in (int, float) and math.isfinite(value), "nonfinite_numeric_value")
    return value


def close(a, b):
    return math.isclose(a, b, abs_tol=1e-11, rel_tol=1e-11)


def false_flags(doc):
    require(all(doc.get(key) is False for key in FLAGS), "qualification_flag_not_false")


def new_path(path):
    require(not path.exists() and not path.is_symlink(), "output_already_exists")


def source_binding(worktree):
    def git(*arguments):
        return subprocess.check_output(["git", "-C", str(worktree), *arguments], stderr=subprocess.DEVNULL, timeout=30)
    require(Path(git("rev-parse", "--show-toplevel").decode().strip()).resolve() == worktree.resolve(), "source_worktree_root_required")
    require(git("rev-parse", "HEAD").decode().strip() == COMMIT, "source_head_mismatch")
    require(not git("status", "--porcelain", "--untracked-files=all"), "clean_source_required")
    for name, expected in SOURCE_HASHES.items():
        path = worktree/REL/name
        require(sha(path) == expected and hashlib.sha256(git("show", COMMIT+":"+REL+"/"+name)).hexdigest() == expected,
                "pinned_source_bytes_mismatch")
    return dict(SOURCE_HASHES)


def input_bindings(prepared, baseline):
    manifest_path = prepared/"prepare_manifest.json"
    require(sha(manifest_path) == PREPARED_SHA, "prepared_manifest_anchor_mismatch")
    manifest = read_json(manifest_path)
    require(manifest["kind"] == "meta.r6.prepared_inputs" and manifest["source_commit"] == COMMIT and
            manifest["counts"] == COUNTS, "prepared_manifest_mismatch")
    names = {"inputs.json", "records.json", "truth.json", "train_dev_candidates.csv"}
    require(set(manifest["files_sha256"]) == names, "prepared_file_set_mismatch")
    hashes = {"prepared_manifest": PREPARED_SHA}
    for name in sorted(names):
        expected = manifest["files_sha256"][name]
        require(valid_sha(expected) and sha(prepared/name) == expected, "prepared_file_digest_mismatch")
        hashes[name] = expected
    require(hashes["inputs.json"] == IMAGE_INPUT_SHA, "image_input_digest_mismatch")
    require(sha(baseline/"report.json") == R4_REPORT_SHA, "r4_report_digest_mismatch")
    report = read_json(baseline/"report.json")
    artifacts = {a["path"]: a["sha256"] for a in report["artifacts"]}
    require(len(artifacts) == len(report["artifacts"]), "duplicate_r4_artifact")
    for name in ("model.json", "predictions.csv"):
        require(valid_sha(artifacts[name]) and sha(baseline/name) == artifacts[name], "frozen_r4_artifact_mismatch")
        hashes["r4_"+name] = artifacts[name]
    require(hashes["r4_model.json"] == manifest["baseline_model_sha256"] == BASELINE_SHA and
            hashes["r4_predictions.csv"] == manifest["baseline_predictions_sha256"], "frozen_baseline_binding_mismatch")
    hashes["r4_report"] = R4_REPORT_SHA
    return manifest, hashes


def validate_member(member):
    name = member.name.rstrip("/") if member.isdir() else member.name
    path = PurePosixPath(name)
    require(name and "\\" not in name and "\x00" not in name and not path.is_absolute() and
            ".." not in path.parts and path.as_posix() == name, "unsafe_archive_path")
    require((member.isdir() or member.isreg()) and not member.issym() and not member.islnk() and
            getattr(member, "sparse", None) is None, "archive_special_file_refused")
    require(type(member.size) is int and 0 <= member.size <= MAX_UNPACKED, "archive_member_size_invalid")
    allowed = (path.parts[0] == "extraction-01" and (len(path.parts) > 1 or member.isdir())) or (
        len(path.parts) == 1 and name in ROOT_FILES and member.isreg())
    require(allowed and (not member.isdir() or member.size == 0), "archive_member_not_allowed")
    return path


def extract_verified(archive, destination):
    new_path(destination)
    with tarfile.open(archive, "r:gz") as stream:
        admitted, seen, total = [], set(), 0
        for member in stream:
            require(len(admitted) < 256, "archive_member_count_exceeded")
            path = validate_member(member)
            require(path not in seen, "duplicate_archive_path")
            seen.add(path)
            total += member.size
            require(total <= MAX_UNPACKED, "archive_unpacked_budget_exceeded")
            admitted.append((member, path))
        required = {PurePosixPath("extraction-01")/name for name in
                    ("summary.json", "observations.jsonl", "raw-ocr.jsonl", "image-admissions.jsonl")}
        require(required <= {path for member, path in admitted if member.isreg()}, "required_extraction_artifact_missing")
        files = {path for member, path in admitted if member.isreg()}
        require(all(not any(parent in files for parent in path.parents) for path in seen), "archive_parent_file_conflict")
        destination.mkdir()
        for member, path in admitted:
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = stream.extractfile(member)
            require(extracted is not None, "archive_file_unreadable")
            copied = 0
            with extracted, target.open("xb") as output:
                while True:
                    chunk = extracted.read(min(1048576, member.size-copied+1))
                    if not chunk:
                        break
                    copied += len(chunk)
                    require(copied <= member.size, "archive_file_size_exceeded")
                    output.write(chunk)
            require(copied == member.size, "archive_file_truncated")
    return {"members": len(admitted), "unpacked_bytes": total}


def extraction_binding(directory, prepared_manifest):
    summary = read_json(directory/"summary.json")
    require(summary["schema"] == "meta_r6_extraction_v1" and summary["status"] == "complete" and
            summary["complete"] is True, "complete_extraction_required")
    require(summary["source_commit"] == COMMIT and summary["source_sha256"] == SOURCE_HASHES["extract_nvidia.py"] and
            summary["input_sha256"] == IMAGE_INPUT_SHA and
            summary["dataset_sha256"] == prepared_manifest["input_hashes"]["dataset"], "extraction_source_or_input_mismatch")
    require(summary["counts"] == {"manifest_images": 6993, "expected_images": 6993,
                                  "observed_images": 6993, "failed_images": 0}, "extraction_count_mismatch")
    false_flags(summary)
    hashes = {"summary": sha(directory/"summary.json")}
    for key, name in (("observations_sha256", "observations.jsonl"), ("raw_ocr_sha256", "raw-ocr.jsonl"),
                      ("admissions_sha256", "image-admissions.jsonl")):
        require(valid_sha(summary[key]) and sha(directory/name) == summary[key], "extraction_artifact_digest_mismatch")
        with (directory/name).open("rb") as handle:
            count = 0
            for line in handle:
                require(bool(line.strip()), "blank_extraction_record")
                count += 1
            require(count == 6993, "extraction_record_count_mismatch")
        hashes[key] = summary[key]
    return hashes


def run_stage(command, log_path, worktree, env, phase):
    print(json.dumps({"stage": phase}), flush=True)
    with log_path.open("xb") as log:
        process = subprocess.Popen(command, cwd=worktree, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            returncode = process.wait(timeout=600)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise ValueError(phase+"_timeout")
    require(returncode == 0, phase+"_failed")


def metric_check(value, queries, missing):
    require(value["queries"] == queries and value["missing_positive_queries"] == missing and
            close(value["candidate_recall"], (queries-missing)/queries), "metric_denominator_mismatch")
    for key in ("candidate_recall", "recall_at_1", "recall_at_5", "recall_at_10", "recall_at_50", "recall_at_100", "mrr"):
        require(0 <= finite(value[key]) <= 1, "metric_out_of_range")


def fit_order(fit):
    return (-fit["dev"]["recall_at_1"], -fit["dev"]["mrr"], len(fit["feature_names"]), -fit["lambda"])


def csv_reader(path, columns):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == columns, "output_csv_schema_mismatch")
        for row in reader:
            require(None not in row and all(v is not None for v in row.values()), "malformed_output_csv")
            yield row


def verify_outputs(directory, feature_directory):
    report, model = read_json(directory/"report.json"), read_json(directory/"model.json")
    require(report["status"] == "trained_research_only" and report["counts"] == COUNTS and report["rows"] == ROWS and
            report["consumed_partitions"] == ["train", "dev"] and report["feature_names"] == RECIPES["plus_both"], "training_contract_mismatch")
    feature_hash, manifest_hash = sha(feature_directory/"candidates.csv"), sha(feature_directory/"data_manifest.json")
    for doc in (report, model):
        false_flags(doc)
        require(doc["provenance"]["source_commit"] == COMMIT and doc["provenance"]["training_script_sha256"] == SOURCE_HASHES["train_reranker.R"] and
                doc["provenance"]["input_sha256"] == feature_hash and doc["provenance"]["manifest_sha256"] == manifest_hash and
                doc["provenance"]["baseline_model_sha256"] == BASELINE_SHA, "training_provenance_mismatch")
    require(model["policy"]["calibrated"] is False and model["policy"]["threshold"] is None and
            model["rank_score_is_probability"] is False, "unexpected_acceptance_policy")
    fits = report["optimizer_candidates"]
    require(report["training"]["fits"] == len(fits) == 12 and
            {(f["method"], f["lambda"]) for f in fits} == {(m, r) for m in RECIPES for r in (.01, .1, 1)}, "fit_grid_mismatch")
    for fit in fits:
        features, opt, training = RECIPES[fit["method"]], fit["optimization"], fit["training"]
        require(fit["feature_names"] == features and len(fit["coefficients"]) == len(features) and
                fit["scaler"]["feature_names"] == features, "fit_feature_mismatch")
        for number in fit["coefficients"] + fit["scaler"]["center"] + fit["scaler"]["scale"]:
            finite(number)
        require(all(x > 0 for x in fit["scaler"]["scale"]) and opt["convergence"] == 0 and
                opt["parameter_update_observed"] is True and finite(opt["parameter_update_l2"]) > 0 and
                finite(opt["final_objective"]) < finite(opt["initial_objective"]), "fit_not_converged_or_updated")
        finite(opt["initial_gradient_max_abs"]); finite(opt["final_gradient_max_abs"])
        require(close(math.sqrt(math.fsum(x*x for x in fit["coefficients"])), opt["parameter_update_l2"]), "coefficient_update_norm_mismatch")
        require(training["rows"] == 331300 and training["queries"] == 3313 and training["trainable_queries"] == 3280 and
                training["skipped_untrainable_queries"] == 33 and training["pairs"] == 324720, "training_pair_counts_mismatch")
        metric_check(fit["dev"], 727, 8)
    baseline = report["selection"]["baseline_dev"]
    metric_check(baseline, 727, 8)
    require(close(baseline["recall_at_1"], 466/727) and close(baseline["candidate_recall"], 719/727), "baseline_metric_drift")
    winners = report["ablation_selected_models"]
    require(set(winners) == set(RECIPES), "missing_ablation")
    for method, winner in winners.items():
        expected = min((f for f in fits if f["method"] == method), key=fit_order)
        require(all(winner[k] == expected[k] for k in ("method", "lambda", "feature_names", "coefficients", "scaler", "dev")),
                "ablation_selection_mismatch")
        metric_check(winner["train"], 3313, 33)
    best = min(fits, key=fit_order)
    improved = (best["dev"]["recall_at_1"], best["dev"]["mrr"]) > (baseline["recall_at_1"], baseline["mrr"])
    selected = best["method"] if improved else "frozen_r4"
    require(report["selection"]["method"] == model["selected_method"] == selected and
            report["selection"]["baseline_retained"] is (not improved), "selected_model_mismatch")
    if improved:
        require(model["kind"] == "ridge_pairwise_logistic" and model["coefficients"] == best["coefficients"] and
                model["scaler"] == best["scaler"] and model["regularization"] == best["lambda"], "selected_model_weights_mismatch")
    else:
        require(model["kind"] == "frozen_r4_score_passthrough" and model["feature_names"] == ["r4_score"] and
                model["coefficients"] == [1], "frozen_passthrough_mismatch")
    candidates, tops, row_counts = {}, {}, Counter()
    columns = ["split", "query_id", "candidate_id", "rank_score", "r4_score", "selected_method"]
    for row in csv_reader(directory/"predictions.csv", columns):
        split, query, candidate = row["split"], row["query_id"], row["candidate_id"]
        require(split in COUNTS and query and candidate and row["selected_method"] == selected, "prediction_identity_or_split_mismatch")
        key = (split, query)
        seen = candidates.setdefault(key, set())
        require(candidate not in seen and len(seen) < 100, "prediction_duplicate_or_excess_candidate")
        seen.add(candidate); row_counts[split] += 1
        score, frozen = finite(float(row["rank_score"])), finite(float(row["r4_score"]))
        if selected == "frozen_r4":
            require(score == frozen, "baseline_scores_changed")
        previous = tops.get(key)
        current = ((-score, candidate), (-frozen, candidate))
        tops[key] = current if previous is None else tuple(min(a, b) for a, b in zip(previous, current))
    require(dict(row_counts) == ROWS and Counter(s for s, q in candidates) == Counter(COUNTS) and
            all(len(values) == 100 for values in candidates.values()), "prediction_denominator_mismatch")
    cells, query_seen, query_rows = defaultdict(list), set(), 0
    qcolumns = ["split", "query_id", "query_family", "candidate_id", "exact_correct", "family_correct", "positive_rank",
                "candidates", "top_score", "gap", "confidence", "method", "lambda", "selected"]
    for row in csv_reader(directory/"query_metrics.csv", qcolumns):
        split, query, method = row["split"], row["query_id"], row["method"]
        key = (split, query)
        require(key in candidates and method in {"frozen_r4", *RECIPES} and (method, *key) not in query_seen,
                "query_metric_cohort_mismatch")
        require(row["exact_correct"] in ("TRUE", "FALSE") and row["selected"] == ("TRUE" if method == selected else "FALSE") and
                int(row["candidates"]) == 100, "query_metric_flags_mismatch")
        rank = None if row["positive_rank"] == "" else int(row["positive_rank"])
        correct = row["exact_correct"] == "TRUE"
        require((rank is None or 1 <= rank <= 100) and correct == (rank == 1) == (query == row["candidate_id"]) and
                (rank is not None) == (query in candidates[key]), "query_positive_rank_mismatch")
        if method in (selected, "frozen_r4"):
            index = 1 if method == "frozen_r4" else 0
            require(row["candidate_id"] == tops[key][index][1], "prediction_top_candidate_mismatch")
        cells[(method, split)].append((rank, row["query_family"]))
        query_seen.add((method, *key)); query_rows += 1
    require(query_rows == 20200, "query_metric_row_count_mismatch")
    for method in ("frozen_r4", *RECIPES):
        for split, n in COUNTS.items():
            entries = cells[(method, split)]
            require(len(entries) == n, "query_metric_denominator_mismatch")
            expected = baseline if method == "frozen_r4" and split == "dev" else winners[method][split] if method != "frozen_r4" else None
            if expected is not None:
                ranks = [r for r, _ in entries if r is not None]
                require(len(ranks) == n-expected["missing_positive_queries"] and
                        close(math.fsum(1/r for r in ranks)/n, expected["mrr"]), "query_metric_mrr_mismatch")
                for k in (1, 5, 10, 50, 100):
                    require(close(sum(r <= k for r in ranks)/n, expected["recall_at_"+str(k)]), "query_metric_recall_mismatch")
    artifacts = {a["path"]: a["sha256"] for a in report["artifacts"]}
    actual_artifacts = {name: sha(directory/name) for name in ("model.json", "predictions.csv", "query_metrics.csv")}
    require(len(report["artifacts"]) == 3 and artifacts == actual_artifacts, "training_artifact_digest_mismatch")
    return {"baseline_dev_correct_at_1": 466, "dev_queries": 727, "candidate_recall_correct": 719,
        "training_fits": 12, "converged_fits": 12, "all_fits_updated_weights": True, "all_fits_reduced_objective": True,
        "prediction_rows": sum(row_counts.values()), "query_metrics_rows": query_rows,
        "selected_method": selected, "baseline_retained": not improved,
        "best_trained_dev": best["dev"], "feature_csv_sha256": feature_hash, "feature_manifest_sha256": manifest_hash,
        "report_sha256": sha(directory/"report.json"), "model_sha256": actual_artifacts["model.json"],
        "predictions_sha256": actual_artifacts["predictions.csv"], "query_metrics_sha256": actual_artifacts["query_metrics.csv"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("control", "source-worktree", "prepared", "baseline-dir", "python", "rscript"):
        parser.add_argument("--"+name, required=True, type=Path)
    args = parser.parse_args()
    postprocessor_path = Path(__file__).resolve()
    postprocessor_sha = sha(postprocessor_path)
    require(all(path.is_absolute() for path in (args.control, args.source_worktree, args.prepared,
            args.baseline_dir, args.python, args.rscript)), "absolute_paths_required")
    c, w = args.control, args.source_worktree
    require(c.is_dir() and not c.is_symlink() and not c.resolve().is_relative_to(w.resolve()), "private_control_outside_checkout_required")
    require(all(not p.is_symlink() for p in c.parents), "control_parent_symlink_refused")
    for name in ("gpu-output-01", "features-01", "training-01", "features-01.log", "training-01.log", "training-verification.json"):
        new_path(c/name)
    source = source_binding(w)
    prepared_manifest, input_hashes = input_bindings(args.prepared, args.baseline_dir)
    transfer_path, archive = c/"transfer.json", c/"extraction.tar.gz"
    transfer_sha, archive_sha = sha(transfer_path), sha(archive)
    transfer = read_json(transfer_path)
    require(transfer["schema"] == "meta_r8_transfer_v1" and transfer["source_commit"] == COMMIT and
            transfer["verified"] is True and valid_sha(transfer["sha256"]) and transfer["sha256"] == archive_sha and
            type(transfer["bytes"]) is int and 0 < transfer["bytes"] == archive.stat().st_size <= MAX_UNPACKED+1048576 and
            valid_sha(transfer["worker_sha256"]) and type(transfer["job_id"]) is str and bool(transfer["job_id"]),
            "transfer_binding_mismatch")
    started = time.monotonic()
    print(json.dumps({"stage": "verifying_extraction_archive", "source_commit": COMMIT}), flush=True)
    extraction_stats = extract_verified(archive, c/"gpu-output-01")
    extraction = c/"gpu-output-01/extraction-01"
    extraction_hashes = extraction_binding(extraction, prepared_manifest)
    env = dict(os.environ)
    env.update(PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="4", OPENBLAS_NUM_THREADS="4", VECLIB_MAXIMUM_THREADS="4")
    env["PATH"] = ":".join((str(args.python.parent), str(args.rscript.parent), "/opt/homebrew/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"))
    s = w/REL
    run_stage([str(args.python), str(s/"build_features.py"), "--prepared", str(args.prepared),
        "--observations", str(extraction/"observations.jsonl"), "--extraction-manifest", str(extraction/"summary.json"),
        "--r4-predictions", str(args.baseline_dir/"predictions.csv"), "--r4-report", str(args.baseline_dir/"report.json"),
        "--output", str(c/"features-01"), "--source-commit", COMMIT], c/"features-01.log", w, env, "building_features")
    run_stage([str(args.rscript), str(s/"train_reranker.R"), "--input", str(c/"features-01/candidates.csv"),
        "--manifest", str(c/"features-01/data_manifest.json"), "--output", str(c/"training-01"), "--source-commit", COMMIT],
        c/"training-01.log", w, env, "training_twelve_rankers")
    verification = verify_outputs(c/"training-01", c/"features-01")
    require(source_binding(w) == source and input_bindings(args.prepared, args.baseline_dir)[1] == input_hashes and
            sha(transfer_path) == transfer_sha and sha(archive) == archive_sha and
            extraction_binding(extraction, prepared_manifest) == extraction_hashes and
            sha(postprocessor_path) == postprocessor_sha, "source_or_input_changed_during_postprocessing")
    result = {"schema": "meta_r8_training_verification_v1", "source_commit": COMMIT,
        "source_files_sha256": source, "source_clean_after_training": True,
        "postprocessor_sha256": postprocessor_sha, "transfer_sha256": transfer_sha,
        "worker_sha256": transfer["worker_sha256"], "extraction_archive_sha256": archive_sha,
        "extraction_artifacts_sha256": extraction_hashes, "extraction_archive": extraction_stats,
        "input_artifacts_sha256": input_hashes, "verified_images": 6993, **verification,
        "elapsed_seconds": time.monotonic()-started, "accepted_coverage_measured": False,
        "ocr_transcription_accuracy_measured": False, **FLAGS}
    with (c/"training-verification.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"stage": "training_verified", "selected_method": result["selected_method"],
        "baseline_retained": result["baseline_retained"], "verification_sha256": sha(c/"training-verification.json"), **FLAGS}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        code = str(error) if re.fullmatch(r"[a-z_]+", str(error)) else type(error).__name__
        print(json.dumps({"stage": "FAILED", "error_code": code, **FLAGS}), file=sys.stderr, flush=True)
        raise SystemExit(1)
