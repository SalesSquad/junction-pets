"""Offline replay of committed R5 model artifacts; never execute inference.

Inputs are the unchanged text subset published in PR195 at the pinned commit,
plus the download index with Git blob identities. Each run is reconciled alone.
The existing R5 evaluator owns campaign selection and superseded failures.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re

import contract
import reconcile
from contract import ContractError, advisory_fields, strict_json_loads

PUBLISHED_COMMIT = "b3d6e31ceb797c49293613480af510f999eaeeb2"
CONSUMER_REFERENCE_COMMIT = "4210b617b087a63a52b0ea1d09ae33b2df9d6d46"
PUBLISHED_MANIFEST_SHA256 = "cd9abe18fdf73137c109e0db2592263354e512ce4712e018e40d05bc5362df11"
PINNED_CONSUMER_SHA256 = {
    "reconcile.py": "e864c0eac73f94755e844c1daf806c2d4aa61c39328017830992b5948f470025",
    "contract.py": "45c7a2b1295e5fd4818125481d68fbeffbbe95b7e1ba2c9a0e3adf04e74708d9",
}
PILOTS = tuple(f"pilot-{number:02d}" for number in range(1, 7))
TEXT_SELECTION = re.compile(
    r"(?:pilot-0[1-6]/.*\.json|prepared-01/.*\.json|nim-01/.*\.json|"
    r"evaluation\.json|verification\.json|evidence-manifest\.json|r-summary\.csv)"
)
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024


def require(condition, code, message):
    if not condition:
        raise ContractError(code, message)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def regular_bytes(path):
    path = Path(path).absolute()
    require(not any(item.is_symlink() for item in (path, *path.parents)), "unsafe_path", "Input symlink refused")
    require(path.is_file() and path.stat().st_size <= MAX_FILE_BYTES, "input_bound", "Expected bounded regular input file")
    with path.open("rb") as handle:
        raw = handle.read(MAX_FILE_BYTES + 1)
    require(len(raw) <= MAX_FILE_BYTES, "input_bound", "Input exceeds byte limit")
    return raw


def verified_inputs(input_root, download_index):
    root = Path(input_root).absolute()
    require(root.is_dir() and not root.is_symlink(), "unsafe_path", "Expected regular input directory")
    index_raw = regular_bytes(download_index)
    index = strict_json_loads(index_raw)
    require(index.get("source_commit") == PUBLISHED_COMMIT and index.get("repository") == "SalesSquad/junction-pets",
            "source_commit_mismatch", "Download index is not for the pinned published source")
    rows = index.get("files")
    require(isinstance(rows, list) and 1 <= len(rows) <= 220, "input_count", "Invalid bounded input inventory")
    raw_files = {}
    for row in rows:
        relative = row.get("path")
        require(isinstance(relative, str) and TEXT_SELECTION.fullmatch(relative) is not None,
                "unsafe_path", "Only the declared published text subset is accepted")
        parts = PurePosixPath(relative)
        require(not parts.is_absolute() and ".." not in parts.parts and str(parts) == relative,
                "unsafe_path", "Invalid artifact path")
        require(relative not in raw_files, "duplicate_artifact", "Duplicate download-index path")
        raw = regular_bytes(root / relative)
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        require(blob == row.get("git_blob_sha") and sha256(raw) == row.get("sha256") and len(raw) == row.get("bytes"),
                "download_hash_mismatch", "Downloaded bytes differ from Git/index binding: " + relative)
        raw_files[relative] = raw
    require(sum(map(len, raw_files.values())) <= MAX_TOTAL_BYTES, "input_bound", "Input set exceeds byte budget")
    require(sha256(raw_files.get("evidence-manifest.json", b"")) == PUBLISHED_MANIFEST_SHA256,
            "manifest_hash_mismatch", "Published evidence manifest differs from the pinned source")
    manifest = strict_json_loads(raw_files["evidence-manifest.json"])
    expected = {name for name in manifest["artifacts"] if TEXT_SELECTION.fullmatch(name)} | {"evidence-manifest.json"}
    require(set(raw_files) == expected, "input_inventory_mismatch", "Published selected artifact set is incomplete or unexpected")
    for relative, raw in raw_files.items():
        if relative == "evidence-manifest.json":
            continue
        declared = manifest["artifacts"][relative]
        require(sha256(raw) == declared["sha256"] and len(raw) == declared["bytes"],
                "manifest_hash_mismatch", "Bytes differ from the published manifest: " + relative)
    # No host paths inside a manifest are followed. Only these downloaded files
    # become parser inputs; original images and command logs are not accessed.
    objects = {name: strict_json_loads(raw) for name, raw in raw_files.items() if name.endswith(".json")}
    return raw_files, objects, {"source_commit": PUBLISHED_COMMIT, "download_index_sha256": sha256(index_raw),
                              "manifest_sha256": PUBLISHED_MANIFEST_SHA256, "git_blob_verified_files": len(raw_files),
                              "manifest_verified_files": len(raw_files) - 1, "bytes": sum(map(len, raw_files.values())),
                              "artifact_sha256": {name: sha256(raw) for name, raw in sorted(raw_files.items())}}


def reported_usage(receipts, expected_pairs):
    fields = {}
    for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        numbers = [(receipt.get("usage") or {})[name] for receipt in receipts
                   if isinstance(receipt.get("usage"), dict) and name in receipt["usage"]]
        require(all(type(value) is int and 0 <= value <= 1_000_000_000 for value in numbers),
                "usage_mismatch", "Invalid published token count")
        fields[name] = {"reported_sum": sum(numbers) if numbers else None, "reporting_receipts": len(numbers),
                        "pairs_without_reported_field": expected_pairs - len(numbers)}
    return {"fields": fields, "receipts_without_usage": sum(not isinstance(row.get("usage"), dict) for row in receipts),
            "planned_pairs_without_receipt": expected_pairs - len(receipts), "verified_cost_usd": None}


def receipt_inventory(name, plan, objects):
    receipts = [value for path, value in objects.items() if path.startswith(name + "/") and path.endswith(".receipt.json")]
    pairs = {(row["case_id"], row["lane"]) for row in receipts}
    require(len(pairs) == len(receipts), "duplicate_pair", "A run contains duplicate case/lane receipts")
    expected_pairs = len(plan["lanes"]) * plan["case_count"]
    require(len(receipts) <= expected_pairs, "unexpected_pair", "Run has more receipts than planned pairs")
    failures = [row for row in receipts if row["status"] != "observed_schema_valid"]
    return receipts, {
        "basis": "Published receipt declarations; consumer validation is reported separately.",
        "requested_pairs": expected_pairs, "receipt_files": len(receipts),
        "reported_valid_observations": len(receipts) - len(failures), "reported_failed_pairs": len(failures),
        "pairs_without_receipt": expected_pairs - len(receipts),
        "reported_statuses": dict(sorted(Counter(row["status"] for row in receipts).items())),
        "reported_failure_errors": dict(sorted(Counter(row.get("error", "unspecified") for row in failures).items())),
        "reported_usage": reported_usage(receipts, expected_pairs),
    }


def evaluation_diagnosis(objects, raw_files):
    """Check supplied evaluator/truth arithmetic; never select or join attempts."""
    evaluation = objects["evaluation.json"]
    cases = objects["prepared-01/cases.json"]
    truth = objects["prepared-01/evaluation_truth.json"]
    cases_sha = sha256(raw_files["prepared-01/cases.json"])
    truth_sha = sha256(raw_files["prepared-01/evaluation_truth.json"])
    require(cases["evaluation_truth_sha256"] == truth_sha and evaluation["binding"]["cases_sha256"] == cases_sha
            and evaluation["binding"]["truth_sha256"] == truth_sha, "truth_binding", "Published evaluation/truth bindings differ")
    require(evaluation["split"] == "dev" and evaluation["all_query_denominator"] == 8,
            "evaluation_denominator", "Expected exactly eight development cases")
    truths = {row["case_id"]: row for row in truth["cases"]}
    require(len(truths) == len(truth["cases"]) == 8, "evaluation_denominator", "Duplicate or missing truth cases")
    present = [key for key, row in truths.items() if row["truth_candidate_alias"] is not None]
    baseline = [key for key, row in truths.items() if row["baseline_correct"] is True]
    recoverable = [key for key, row in truths.items() if row["truth_candidate_alias"] is not None and row["baseline_correct"] is False]
    require(evaluation["baseline_r4_rank1"]["numerator"] == len(baseline) and
            evaluation["candidate_recall_at_3_ranking_ceiling"]["numerator"] == len(present),
            "evaluation_arithmetic", "Declared baseline/top-three ceiling disagrees with supplied truth")
    r_rows = {row["lane"]: row for row in csv.DictReader(io.StringIO(raw_files["r-summary.csv"].decode("utf-8")))}
    lanes = {}
    all_rows = evaluation["per_case"]
    for lane in ("visual", "detail", "critic"):
        rows = [row for row in all_rows if row["lane"] == lane]
        require(len(rows) == 8 and {row["case_id"] for row in rows} == set(truths),
                "evaluation_denominator", "Published lane diagnosis has duplicate or missing cases")
        correct = wrong_proposals = proposals = 0
        lost = []
        won = []
        for row in rows:
            actual = truths[row["case_id"]]
            is_correct = row["rank1"] == actual["truth_candidate_alias"]
            require(row["rank1_correct"] is is_correct, "evaluation_arithmetic", "Published per-case correctness disagrees with supplied truth")
            correct += is_correct
            proposals += row["proposed_candidate"] is not None
            wrong_proposals += row["proposed_candidate"] is not None and row["proposed_candidate"] != actual["truth_candidate_alias"]
            if actual["baseline_correct"] and not is_correct:
                lost.append(row["case_id"])
            if not actual["baseline_correct"] and is_correct:
                won.append(row["case_id"])
        declared = evaluation["lanes"][lane]
        require((correct, proposals, wrong_proposals) == (declared["rank1_correct_all_queries"]["numerator"],
                 declared["proposed_cases"], declared["wrong_proposals"]), "evaluation_arithmetic", "Published aggregate lane counts differ")
        r = r_rows[lane]
        require((int(r["rank1_correct_all_queries"]), int(r["wrong_proposals"]), int(r["paired_wins"]), int(r["paired_losses"]))
                == (correct, wrong_proposals, len(won), len(lost)), "r_arithmetic", "Published R counts differ from supplied evaluator/truth arithmetic")
        lanes[lane] = {"rank1_correct": correct, "denominator": 8, "proposed": proposals,
                       "wrong_proposals": wrong_proposals, "abstentions": 8 - proposals,
                       "baseline_wins": won, "baseline_losses": lost,
                       "accuracy_gain_qualified": False}
    visual = {row["case_id"]: row for row in all_rows if row["lane"] == "visual"}
    detail = {row["case_id"]: row for row in all_rows if row["lane"] == "detail"}
    return {"basis": "Arithmetic over the already published evaluation and its hash-bound truth; no new campaign selection.",
            "split": "dev", "cases": 8, "distinct_families_declared": evaluation["distinct_families"],
            "baseline_correct": len(baseline), "top3_candidate_oracle": len(present),
            "outside_pool_case_ids": sorted(set(truths) - set(present)),
            "recoverable_baseline_errors_inside_pool": len(recoverable), "recoverable_case_ids": recoverable,
            "lanes": lanes, "visual_detail_same_rank1_cases": sum(visual[key]["rank1"] == detail[key]["rank1"] for key in visual),
            "same_backbone_independent_models": False,
            "ocr": {key: evaluation["lanes"]["ocr"][key] for key in (
                "observed_text_cases", "no_legible_text_cases", "spans_observed", "ocr_accuracy", "transcription_ground_truth_available")},
            "published_additional_view_requests": evaluation["lanes"]["detail"]["additional_observation_requests"],
            "additional_views_actually_captured": 0, "published_r_arithmetic_matches": True,
            "accepted_coverage_qualified": evaluation["accepted_coverage_qualified"]}


def build_report(input_root, download_index):
    source_dir = Path(__file__).parent
    source_hashes = {name: sha256(regular_bytes(source_dir / name)) for name in PINNED_CONSUMER_SHA256}
    require(source_hashes == PINNED_CONSUMER_SHA256, "consumer_source_mismatch", "Consumer bytes differ from the replay baseline")
    raw_files, objects, inputs = verified_inputs(input_root, download_index)
    runs = []
    all_receipts = []
    for name in PILOTS:
        plan = objects[name + "/plan.json"]
        receipts, inventory = receipt_inventory(name, plan, objects)
        all_receipts.extend(receipts)
        row = {"run": name, "execution_source_commit": plan["source_commit"], "plan_sha256": sha256(raw_files[name + "/plan.json"]),
               "requested_lanes": plan["lanes"], "case_count": plan["case_count"], "start_index": plan["start_index"],
               "published_receipt_inventory": inventory}
        try:
            result = reconcile.reconcile_run(Path(input_root) / name, Path(input_root) / "prepared-01/cases.json",
                                              plan["source_commit"], plan["model"])
            agreement = Counter(case["agreement"]["status"] for case in result["cases"])
            requests = result["additional_observation_requests"]
            row.update({"consumer_status": result["status"], "consumer_report_sha256": sha256(canonical(result)),
                        "plan_variant": result["plan_variant"], "consumer_counts": result["counts"],
                        "consumer_reported_usage": result["reported_usage"],
                        "case_agreement_counts": {key: agreement[key] for key in ("agreement", "all_abstain", "disagreement", "partial")},
                        "additional_view_proposals": {"deduplicated_count": len(requests),
                            "kinds": dict(sorted(Counter(item["observation_kind"] for item in requests).items())),
                            "requesting_lanes": dict(sorted(Counter(lane for item in requests for lane in item["requesting_lanes"]).items())),
                            "captured": False, "action_authorized": False}})
        except ContractError as exc:
            row.update({"consumer_status": "VALIDATION_ERROR", "error": {"code": exc.code, "message": str(exc)},
                        "historical_plan_outside_supported_contract": name in ("pilot-01", "pilot-02"),
                        "missing_supported_plan_fields": sorted({"chat_template_kwargs", "response_format"} - plan.keys()),
                        "case_agreement_counts": None, "additional_view_proposals": None})
        runs.append(row)
    evaluation = evaluation_diagnosis(objects, raw_files)
    manifest = objects["evidence-manifest.json"]
    declared_usage = reported_usage(all_receipts, len(all_receipts))
    require(len(all_receipts) == manifest["inference_calls"] and
            {key: field["reported_sum"] for key, field in declared_usage["fields"].items()} == manifest["reported_usage"],
            "accounting_mismatch", "Historical published receipt accounting differs from the manifest")
    require(sum(row["status"] == "observed_schema_valid" for row in all_receipts) == manifest["valid_observations"],
            "accounting_mismatch", "Published observation total differs from individual receipt declarations")
    failures = [row for row in all_receipts if row["status"] != "observed_schema_valid"]
    nim = objects["nim-01/summary.json"]
    require(nim["status"] == "BLOCKED_AUTH" and nim["inference_calls_attempted"] == 0,
            "nim_status_mismatch", "Pinned NIM launch no longer matches its documented zero-call blocker")
    # Re-read after replay to bind the recorded results to unchanged local bytes.
    for path, raw in raw_files.items():
        require(regular_bytes(Path(input_root) / path) == raw, "input_changed", "Published input changed during replay")
    return {**advisory_fields("meta.r5-committed-model-artifact-replay"),
            "work_id": "META-LENS-ACCEL-FOLLOWUP-20261114", "execution_mode": "offline replay of committed model artifacts",
            "new_inference_calls": 0, "new_gpu_instances": 0,
            "consumer": {"reference_commit": CONSUMER_REFERENCE_COMMIT, "source_sha256": source_hashes,
                         "replay_utility_sha256": sha256(regular_bytes(Path(__file__)))},
            "inputs": inputs, "input_bytes_unchanged_after_replay": True, "runs": runs,
            "published_receipt_accounting": {"reported_attempts": len(all_receipts), "reported_valid_observations": len(all_receipts) - len(failures),
                "reported_failed_observations": len(failures), "reported_usage": declared_usage,
                "failed_attempt_reported_usage": reported_usage(failures, len(failures)),
                "reported_reasoning_tokens": manifest["reported_reasoning_tokens"], "verified_cost_usd": None,
                "provider_execution_independently_attested": False},
            "development_diagnosis": evaluation,
            "nim": {"source": "published nim-01/summary.json", "status": nim["status"], "reported_inference_calls": 0,
                    "reason": nim["reason"], "live_ocr_and_nano_verified": False},
            "next_priorities": [
                "Predeclare a broader candidate pool and diagnostics with recoverable baseline errors; preserve a separate future qualification holdout.",
                "Keep the stronger existing R4 ranking as the baseline; investigate q0006 and the critic's wrong q0001 proposal before proposing fusion.",
                "Use independent transcriptions to measure OCR error; three text detections and 23 spans do not establish transcription accuracy.",
                "Treat the seven additional-view requests as proposed evidence acquisition; obtain and register real extra views before a multiview claim.",
                "Retain cheap structured-output canaries and exact schema tests; ten failed calls and reasoning-only output are historical efficiency failures, not valid observations.",
                "Resolve the separate NIM credential blocker through the authorized owner before planning independent-backbone inference.",
            ],
            "limitations": [
                "This run performs file verification and offline replay only; it does not run or retrain a model.",
                "Git blob and SHA-256 bindings verify committed/supplied bytes, not signed provider execution, checkpoint identity or billing.",
                "Consumer source and original case paths are unchanged; original images and private host files are never opened.",
                "Historical pilot01/02 plan rejections are preserved; the reader contract and historical inputs were not loosened or rewritten.",
                "Each pilot remains separate. The published R5 evaluator alone owns campaign joining and failure supersession.",
                "These eight deliberately selected development families cannot establish population accuracy, accepted coverage or >93% qualification.",
                "Four role prompts share one backbone. Agreement and abstention grant no identity or action authority.",
            ]}


def summary_text(report):
    lines = ["Offline replay of committed R5 model artifacts", "", "New inference calls: 0", ""]
    for row in report["runs"]:
        inventory = row["published_receipt_inventory"]
        message = (f"{row['run']}: {row['consumer_status']}; requested={inventory['requested_pairs']}, "
                   f"receipt-reported valid={inventory['reported_valid_observations']}, "
                   f"failed={inventory['reported_failed_pairs']}, missing receipts={inventory['pairs_without_receipt']}")
        if "error" in row:
            message += "; " + row["error"]["code"] + ": " + row["error"]["message"]
        lines.append(message)
    diagnosis = report["development_diagnosis"]
    lines += ["", f"Development cases: {diagnosis['cases']}; baseline correct: {diagnosis['baseline_correct']}; "
              f"top-three oracle: {diagnosis['top3_candidate_oracle']}; recoverable within-pool baseline errors: "
              f"{diagnosis['recoverable_baseline_errors_inside_pool']}."]
    for lane, metrics in diagnosis["lanes"].items():
        lines.append(f"{lane}: rank one {metrics['rank1_correct']}/8; proposals={metrics['proposed']}; "
                     f"wrong proposals={metrics['wrong_proposals']}; baseline losses={','.join(metrics['baseline_losses'])}.")
    lines += ["", "OCR: 3/8 text detections, 23 spans; transcription accuracy unknown.",
              "NIM: published BLOCKED_AUTH, zero reported calls; separate credential absent.",
              "Seven additional-view requests remain proposals; no additional capture occurred.",
              "The role prompts share one backbone. No product qualification or identity/action authority.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--download-index", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args(argv)
    report = build_report(args.input_root, args.download_index)
    targets = [(Path(str(args.output_prefix) + ".json"), (json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()),
               (Path(str(args.output_prefix) + ".txt"), summary_text(report).encode())]
    for path, _ in targets:
        require(not path.exists() and not path.is_symlink(), "output_exists", "Preserve prior replay outputs; choose a new output prefix")
        require(not path.absolute().is_relative_to(args.input_root.absolute()), "input_output_overlap", "Replay outputs cannot be written inside the input tree")
    for path, raw in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(raw)
    print(json.dumps({"status": "OFFLINE_REPLAY_RECORDED", "runs": {row["run"]: row["consumer_status"] for row in report["runs"]},
                      "new_inference_calls": 0, "report_sha256": sha256(targets[0][1])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
