#!/usr/bin/env python3
"""Offline, truth-separated evaluation of explicitly selected Nemotron attempts."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

from protocol import LANES, WORK_ID, parse_response

ROOT = Path(__file__).resolve().parent


def require(ok, message):
    if not ok:
        raise ValueError(message)


def file_hash(path):
    require(path.is_file() and not path.is_symlink(), "regular_evidence_file_required")
    require(path.stat().st_size <= 2 * 1024 * 1024, "bounded_evidence_file_required")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strict_json(path):
    file_hash(path)
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_field")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError("nonfinite_json_constant")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)


def bound_hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate_cohort(cases_path, truth_path):
    cases_hash, truth_hash = file_hash(cases_path), file_hash(truth_path)
    document, truth_document = strict_json(cases_path), strict_json(truth_path)
    require(document.get("work_id") == truth_document.get("work_id") == WORK_ID, "unexpected_work_id")
    require(document.get("evaluation_truth_sha256") == truth_hash, "evaluation_truth_hash_mismatch")
    require(document.get("input_hashes") == truth_document.get("input_hashes"), "truth_input_binding_mismatch")
    input_hashes = document.get("input_hashes")
    require(isinstance(input_hashes, dict) and set(input_hashes) == {"dataset", "r4_report", "predictions", "query_metrics"}
            and all(bound_hash(value) for value in input_hashes.values()), "complete_input_hash_binding_required")
    case_rows, truth_rows = document.get("cases", []), truth_document.get("cases", [])
    require(len(case_rows) == len(truth_rows) == 8, "eight_case_denominator_required")
    cases = {r["case_id"]: r for r in case_rows}
    truths = {r["case_id"]: r for r in truth_rows}
    require(len(cases) == len(truths) == 8 and set(cases) == set(truths), "duplicate_or_mismatched_case_ids")
    require(len({t["query_family"] for t in truths.values()}) == 8, "eight_distinct_families_required")
    require(Counter(c["confidence_quartile"] for c in cases.values()) == {1: 2, 2: 2, 3: 2, 4: 2}, "quartile_balance_mismatch")
    for case_id, case in cases.items():
        truth = truths[case_id]
        require(case.get("split") == truth.get("split") == "dev", "development_only_evaluation_required")
        require(re.fullmatch(r"q[0-9]{4}", case_id) is not None, "invalid_case_id")
        aliases = [c["alias"] for c in case["candidates"]]
        require(len(aliases) == 3 and set(aliases) == {"c01", "c02", "c03"}, "three_unique_candidate_aliases_required")
        require(case["query"].get("source_view_index") == 1 and bound_hash(case["query"].get("image_sha256")), "invalid_query_binding")
        for candidate in case["candidates"]:
            require(candidate.get("source_view_index") == 0 and bound_hash(candidate.get("image_sha256")), "invalid_gallery_binding")
            require(candidate["image_sha256"] != case["query"]["image_sha256"], "query_image_in_gallery")
        candidates = truth.get("candidates", [])
        require(len(candidates) == 3 and {c["alias"] for c in candidates} == set(aliases), "truth_candidate_alias_mismatch")
        require(len({c["candidate_id"] for c in candidates}) == 3 and {c["r4_rank"] for c in candidates} == {1, 2, 3}, "truth_candidate_identity_or_rank_mismatch")
        for c in candidates:
            require(isinstance(c["rank_score"], (int, float)) and not isinstance(c["rank_score"], bool) and math.isfinite(c["rank_score"]), "finite_baseline_score_required")
            require(c["exact_correct"] is (c["candidate_id"] == truth["query_id"]), "truth_exact_label_mismatch")
        true_aliases = [c["alias"] for c in candidates if c["exact_correct"]]
        require(len(true_aliases) <= 1 and truth["truth_candidate_alias"] == (true_aliases[0] if true_aliases else None), "truth_alias_mismatch")
        ranked = sorted(candidates, key=lambda c: (-c["rank_score"], c["candidate_id"]))
        require([c["r4_rank"] for c in ranked] == [1, 2, 3], "frozen_baseline_order_mismatch")
        require(truth["baseline_candidate_id"] == ranked[0]["candidate_id"] and truth["baseline_correct"] is ranked[0]["exact_correct"], "baseline_correctness_mismatch")
        require(truth["baseline_rank_score"] == ranked[0]["rank_score"], "baseline_score_mismatch")
    return cases, truths, {"cases_sha256": cases_hash, "truth_sha256": truth_hash,
                           "input_hashes": document["input_hashes"]}


def load_run(directory, cases, cases_hash):
    require(directory.is_dir() and not directory.is_symlink(), "regular_run_directory_required")
    plan = strict_json(directory / "plan.json")
    require(plan.get("work_id") == WORK_ID and plan.get("cases_sha256") == cases_hash, "run_case_binding_mismatch")
    planned_lanes = plan.get("lanes")
    require(isinstance(planned_lanes, list) and bool(planned_lanes)
            and all(isinstance(lane, str) and lane in LANES for lane in planned_lanes)
            and len(set(planned_lanes)) == len(planned_lanes)
            and planned_lanes == [lane for lane in LANES if lane in planned_lanes],
            "ordered_nonempty_lane_subset_required")
    require(isinstance(plan.get("source_commit"), str) and re.fullmatch(r"[0-9a-f]{40}", plan["source_commit"]) is not None, "run_source_commit_required")
    start, count = plan.get("start_index"), plan.get("case_count")
    require(type(start) is int and type(count) is int and 0 <= start < 8 and 1 <= count <= 8 - start, "invalid_run_slice")
    allowed = list(cases)[start:start + count]
    require(plan.get("maximum_inference_calls") == len(planned_lanes) * count, "planned_call_count_mismatch")
    artifacts = {"plan.json": file_hash(directory / "plan.json")}
    records, observations = {}, {}
    for lane in LANES:
        folder = directory / lane
        if lane not in planned_lanes:
            require(not folder.exists(), "unplanned_lane_directory")
            continue
        if not folder.exists():
            continue
        require(folder.is_dir() and not folder.is_symlink(), "regular_lane_directory_required")
        for path in folder.glob("*.json"):
            match = re.fullmatch(r"(q[0-9]{4})\.(request|response|observation|receipt)\.json", path.name)
            require(match is not None and match.group(1) in allowed, "unexpected_run_artifact")
            artifacts[str(path.relative_to(directory))] = file_hash(path)
            require((folder / (match.group(1) + ".receipt.json")).is_file(), "artifact_without_final_receipt")
        for receipt_path in sorted(folder.glob("*.receipt.json")):
            record = strict_json(receipt_path)
            case_id = receipt_path.name.removesuffix(".receipt.json")
            key = (lane, case_id)
            require(key not in records and record.get("lane") == lane and record.get("case_id") == case_id and record.get("split") == "dev", "receipt_identity_mismatch")
            require(record.get("qualification") is False, "research_receipt_required")
            request_path = folder / (case_id + ".request.json")
            if request_path.exists():
                request = strict_json(request_path)
                require(request.get("case_id") == case_id and request.get("lane") == lane and request.get("cases_sha256") == cases_hash, "request_identity_binding_mismatch")
                require(bound_hash(request.get("request_sha256")), "request_payload_hash_required")
                if "request_sha256" in record:
                    require(request["request_sha256"] == record["request_sha256"], "request_receipt_hash_mismatch")
                case = cases[case_id]
                expected_gallery = [] if lane == "ocr" else [c["image_sha256"] for c in case["candidates"]]
                require(request.get("query_image_sha256") == case["query"]["image_sha256"] and request.get("candidate_image_sha256") == expected_gallery, "request_image_binding_mismatch")
            else:
                require(record.get("status") == "preparation_or_schema_error" and "http_status" not in record, "provider_attempt_missing_request_binding")
            response_path = folder / (case_id + ".response.json")
            if record.get("response_sha256") is not None:
                require(file_hash(response_path) == record["response_sha256"], "response_hash_mismatch")
                require(response_path.stat().st_size == record.get("response_bytes"), "response_size_mismatch")
            else:
                require(not response_path.exists(), "unbound_response_file")
            observation_path = folder / (case_id + ".observation.json")
            if record.get("status") == "observed_schema_valid":
                require(record.get("http_status") == 200 and record.get("provider_completion_known") is True, "valid_observation_without_completion")
                require(record.get("requested_model") == record.get("returned_model") == plan.get("model"), "returned_model_mismatch")
                require(plan.get("source_sha256", {}).get("protocol.py") == file_hash(ROOT / "protocol.py"), "parser_source_binding_mismatch")
                require(file_hash(observation_path) == record.get("observation_sha256"), "observation_hash_mismatch")
                raw = strict_json(response_path)
                require(raw.get("model") == plan.get("model"), "raw_response_model_mismatch")
                choices = raw.get("choices")
                require(isinstance(choices, list) and len(choices) == 1 and choices[0].get("finish_reason") == record.get("finish_reason") == "stop", "incomplete_successful_completion")
                content = choices[0].get("message", {}).get("content")
                parsed = parse_response(content, lane, cases[case_id])
                stored = strict_json(observation_path)
                require(stored == parsed, "raw_observation_reparse_mismatch")
                require(stored.get("action_authorized") is False and stored.get("qualification") is False, "non_authorizing_observation_required")
                observations[key] = stored
            else:
                require(not observation_path.exists() and not record.get("observation_sha256"), "failed_attempt_has_success_artifact")
            records[key] = record
    summary_path = directory / "summary.json"
    summary_status = "missing_final_summary"
    if summary_path.exists():
        summary = strict_json(summary_path); artifacts["summary.json"] = file_hash(summary_path)
        require(summary.get("cases_sha256") == cases_hash and summary.get("source_commit") == plan["source_commit"] and summary.get("source_sha256") == plan["source_sha256"], "summary_source_binding_mismatch")
        summarized = {}
        for lane_row in summary.get("lanes", []):
            for row in lane_row.get("records", []):
                key = (row.get("lane"), row.get("case_id"))
                require(key not in summarized, "duplicate_summary_attempt")
                summarized[key] = row
        require(summarized == records, "summary_receipt_mismatch")
        require(summary.get("attempted_cases") == len(records) and summary.get("valid_observations") == len(observations), "summary_count_mismatch")
        summary_status = summary.get("status")
    run_report = {"directory": str(directory), "source_commit": plan["source_commit"],
                  "provider": plan.get("provider"), "model": plan.get("model"),
                  "start_index": start, "case_count": count, "lanes": planned_lanes, "summary_status": summary_status,
                  "attempts": len(records), "valid_observations": len(observations),
                  "http200_calls": sum(r.get("http_status") == 200 for r in records.values()),
                  "statuses": dict(Counter(r.get("status") for r in records.values())),
                  "artifacts_sha256": artifacts}
    return records, observations, run_report


def ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def evaluate(cases_path, truth_path, run_dirs, audit_dirs=(), selection_reason="explicit caller-selected attempt directories", exclude_attempts=()):
    cases, truths, binding = validate_cohort(cases_path, truth_path)
    require(bool(run_dirs), "selected_run_required")
    all_paths = [p.resolve() for p in [*run_dirs, *audit_dirs]]
    require(len(set(all_paths)) == len(all_paths), "duplicate_run_directory")
    require(all(p.is_absolute() and not p.is_symlink() for p in exclude_attempts), "absolute_regular_exclusion_path_required")
    excluded_paths = {p.resolve() for p in exclude_attempts}
    require(len(excluded_paths) == len(exclude_attempts), "duplicate_exclusion_path")
    used_exclusions, excluded_records = set(), []
    records, observations, selected_runs, audit_runs = {}, {}, [], []
    for directory in run_dirs:
        loaded, valid, run_report = load_run(directory, cases, binding["cases_sha256"])
        for key, record in list(loaded.items()):
            receipt_path = (directory / key[0] / (key[1] + ".receipt.json")).resolve()
            if receipt_path in excluded_paths:
                require(record.get("status") != "observed_schema_valid" and key not in valid,
                        "cannot_exclude_valid_observation")
                used_exclusions.add(receipt_path)
                excluded_records.append({"receipt_path": str(receipt_path), "receipt_sha256": file_hash(receipt_path),
                                         "run_directory": str(directory), "lane": key[0], "case_id": key[1],
                                         "status": record.get("status"), "error": record.get("error"),
                                         "reason": "Caller-explicit failed-attempt exclusion: " + selection_reason})
                del loaded[key]
        require(not (set(records) & set(loaded)), "duplicate_selected_lane_case_attempt_use_explicit_audit_directory")
        records.update(loaded); observations.update(valid); selected_runs.append(run_report)
    require(used_exclusions == excluded_paths, "excluded_attempt_not_found_in_selected_runs")
    for directory in audit_dirs:
        _, _, run_report = load_run(directory, cases, binding["cases_sha256"])
        audit_runs.append(run_report)
    n = len(cases)
    lanes = {}
    per_case = []
    for lane in LANES:
        observed = {case_id: value for (role, case_id), value in observations.items() if role == lane}
        attempted = {case_id: value for (role, case_id), value in records.items() if role == lane}
        metrics = {"all_queries": n, "attempted_cases": len(attempted), "valid_observations": len(observed),
                   "failed_attempts": len(attempted) - len(observed), "not_attempted_cases": n - len(attempted),
                   "valid_response_rate": ratio(len(observed), n),
                   "failure_statuses": dict(Counter(r["status"] for r in attempted.values() if r["status"] != "observed_schema_valid"))}
        if lane == "ocr":
            text_cases = sum(o["status"] == "observed" for o in observed.values())
            metrics.update({"observed_text_cases": text_cases, "no_legible_text_cases": len(observed) - text_cases,
                            "text_observation_rate_all_queries": ratio(text_cases, n),
                            "spans_observed": sum(len(o["spans"]) for o in observed.values()),
                            "ocr_accuracy": None, "transcription_ground_truth_available": False})
        else:
            rank_correct = sum(o["ranking"][0] == truths[c]["truth_candidate_alias"] for c, o in observed.items())
            proposed = {c: o["proposed_candidate"] for c, o in observed.items() if o["proposed_candidate"] is not None}
            correct_proposals = sum(alias == truths[c]["truth_candidate_alias"] for c, alias in proposed.items())
            metrics.update({"rank1_correct_all_queries": ratio(rank_correct, n),
                            "rank1_correct_among_valid": ratio(rank_correct, len(observed)),
                            "rank1_wrong_observed": len(observed) - rank_correct,
                            "proposed_cases": len(proposed), "correct_proposals": correct_proposals,
                            "wrong_proposals": len(proposed) - correct_proposals,
                            "proposal_coverage_descriptive": ratio(len(proposed), n),
                            "proposal_precision_descriptive": ratio(correct_proposals, len(proposed)),
                            "model_abstentions": len(observed) - len(proposed),
                            "operational_missing_or_failed": n - len(observed),
                            "total_no_proposal": n - len(proposed),
                            "additional_observation_requests": dict(Counter(o["additional_observation"]["kind"] for o in observed.values() if o["additional_observation"]["kind"] != "none")),
                            "actual_additional_views_observed": 0})
        lanes[lane] = metrics
        for case_id in cases:
            obs = observed.get(case_id)
            row = {"lane": lane, "case_id": case_id,
                   "attempt_status": attempted.get(case_id, {}).get("status", "not_attempted"),
                   "valid_observation": obs is not None}
            if obs is not None and lane != "ocr":
                row.update(rank1=obs["ranking"][0], rank1_correct=obs["ranking"][0] == truths[case_id]["truth_candidate_alias"],
                           proposed_candidate=obs["proposed_candidate"], model_abstained=obs["proposed_candidate"] is None)
            per_case.append(row)
    for directory, run_report in zip([*run_dirs, *audit_dirs], [*selected_runs, *audit_runs]):
        for relative, expected in run_report["artifacts_sha256"].items():
            require(file_hash(directory / relative) == expected, "run_artifact_changed_during_evaluation")
    require(file_hash(cases_path) == binding["cases_sha256"] and file_hash(truth_path) == binding["truth_sha256"], "cohort_changed_during_evaluation")
    return {"schema_version": 1, "work_id": WORK_ID, "status": "EVALUATED_RESEARCH_ONLY",
            "binding": binding, "selected_runs": selected_runs, "audit_only_runs": audit_runs,
            "excluded_failed_attempts": excluded_records,
            "attempt_selection": {"method": "explicit directories; no automatic outcome-based retry selection",
                                  "reason": selection_reason,
                                  "audit_only_successes_excluded": sum(r["valid_observations"] for r in audit_runs)},
            "all_query_denominator": n, "distinct_families": n, "split": "dev",
            "baseline_r4_rank1": ratio(sum(t["baseline_correct"] for t in truths.values()), n),
            "candidate_recall_at_3_ranking_ceiling": ratio(sum(t["truth_candidate_alias"] is not None for t in truths.values()), n),
            "lanes": lanes, "per_case": per_case,
            "all_audited_attempts": sum(r["attempts"] for r in selected_runs + audit_runs),
            "model_ensemble_independence": False, "accepted_coverage_qualified": False,
            "limitations": ["Eight development families only; prompts/model routes are selected on development.",
                            "Missing or failed calls remain in all-query denominators and differ from explicit model abstentions.",
                            "OCR accuracy cannot be inferred without independent transcription ground truth.",
                            "Only frozen top3 candidates were shown; missing truth limits ranking accuracy.",
                            "No new viewpoint was captured; additional-observation outputs are requests only.",
                            "Four prompted roles share one backbone; agreement is not independent evidence.",
                            "Proposal metrics are descriptive and do not calibrate or authorize acceptance."],
            "qualification": False, "action_authorized": False, "physical_identity_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, action="append", required=True)
    parser.add_argument("--audit-run-dir", type=Path, action="append", default=[])
    parser.add_argument("--exclude-attempt", type=Path, action="append", default=[])
    parser.add_argument("--selection-reason", default="explicit caller-selected attempt directories")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(re.fullmatch(r"[0-9a-f]{40}", args.source_commit) is not None, "full_evaluator_commit_required")
    actual_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(actual_head == args.source_commit, "evaluator_git_head_mismatch")
    require(not args.output.exists() and not args.output.is_symlink(), "new_evaluation_output_required")
    sources = {name: file_hash(ROOT / name) for name in ("evaluate.py", "protocol.py")}
    repo_root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=ROOT, text=True).strip())
    for name, expected in sources.items():
        relative = (ROOT / name).relative_to(repo_root).as_posix()
        committed = subprocess.check_output(["git", "show", args.source_commit + ":" + relative], cwd=ROOT)
        require(hashlib.sha256(committed).hexdigest() == expected, "evaluator_bytes_differ_from_commit")
    result = None
    try:
        result = evaluate(args.cases, args.truth, args.run_dir, args.audit_run_dir, args.selection_reason, args.exclude_attempt)
        require({name: file_hash(ROOT / name) for name in sources} == sources, "evaluator_source_changed")
        require(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == args.source_commit,
                "evaluator_git_head_changed")
        result.update(evaluator_source_commit=args.source_commit, evaluator_source_sha256=sources)
    except Exception as error:
        result = {"schema_version": 1, "status": "INVALID_EVIDENCE", "error_type": type(error).__name__,
                  "error": str(error), "evaluator_source_commit": args.source_commit,
                  "evaluator_source_sha256": sources, "qualification": False}
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as handle:
            json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False); handle.write("\n")
        print(json.dumps({"status": result["status"], "all_queries": result.get("all_query_denominator")}), flush=True)


if __name__ == "__main__":
    main()
