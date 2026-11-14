#!/usr/bin/env python3
"""Run four bounded Nemotron roles; allow an explicit subset for isolated repairs."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import threading
import time

from protocol import LANES, make_messages, parse_response, response_format
from provider import NEMOTRON, canonical, completion_text, load_nemotron_key, post, sha256

ROOT = Path(__file__).resolve().parent


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def source_binding(commit):
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != commit:
        raise ValueError("source_commit_mismatch")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True):
        raise ValueError("clean_execution_source_required")
    return {p.name: file_hash(p) for p in sorted(ROOT.iterdir()) if p.is_file()}


def constrained_format(lane):
    """Prevent a null proposal from claiming an identified candidate."""
    output = response_format(lane)
    if lane == "ocr":
        return output
    schema = output["json_schema"]["schema"]
    permutations = [list(p) for p in itertools.permutations(("c01", "c02", "c03"))]
    schema["properties"]["ranking"]["enum"] = permutations
    schema["anyOf"] = [{"properties": {
        "identifiability": {"enum": ["insufficient"]}, "proposed_candidate": {"type": "null"}}}]
    for alias in ("c01", "c02", "c03"):
        schema["anyOf"].append({"properties": {
            "identifiability": {"enum": ["distinguishable"]},
            "proposed_candidate": {"enum": [alias]},
            "ranking": {"enum": [p for p in permutations if p[0] == alias]}}})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--deadline-seconds", type=int, default=900)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--case-count", type=int, default=8)
    parser.add_argument("--lanes", nargs="+", choices=LANES, default=list(LANES))
    args = parser.parse_args()
    if not 256 <= args.max_output_tokens <= 2048 or not 120 <= args.deadline_seconds <= 1800:
        raise ValueError("bounded_call_budget_required")
    sources = source_binding(args.source_commit)
    input_hash = file_hash(args.cases)
    document = json.loads(args.cases.read_text())
    cases = document["cases"]
    if len(cases) != 8 or len({c["case_id"] for c in cases}) != 8 or any(c["split"] != "dev" for c in cases):
        raise ValueError("eight_frozen_development_cases_required")
    if not 0 <= args.start_index < 8 or not 1 <= args.case_count <= 8 - args.start_index:
        raise ValueError("bounded_case_slice_required")
    cases = cases[args.start_index:args.start_index + args.case_count]
    if len(set(args.lanes)) != len(args.lanes):
        raise ValueError("unique_requested_lanes_required")
    active_lanes = [lane for lane in LANES if lane in args.lanes]
    expected_calls = len(active_lanes) * len(cases)
    if tuple(LANES) != ("ocr", "visual", "detail", "critic"):
        raise ValueError("four_declared_lanes_required")
    args.output.mkdir(parents=True, exist_ok=False)
    key = load_nemotron_key()
    started = time.monotonic()
    stop = threading.Event()
    barrier = threading.Barrier(len(active_lanes))
    plan = {"schema_version": 1, "work_id": "META-LENS-R5-NEMOTRON4-20261114",
            "source_commit": args.source_commit, "source_sha256": sources,
            "cases_sha256": input_hash, "provider": NEMOTRON.name, "model": NEMOTRON.model,
            "lanes": active_lanes, "max_concurrent_calls": len(active_lanes), "maximum_inference_calls": expected_calls,
            "start_index": args.start_index, "case_count": args.case_count,
            "max_output_tokens_per_call": args.max_output_tokens, "max_attempts_per_job": 1,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": "json_schema",
            "semantic_choice_schema": True,
            "deadline_seconds": args.deadline_seconds, "started_utc": datetime.now(timezone.utc).isoformat(),
            "new_gpu_instances": 0, "same_backbone_specialists_are_independent_models": False,
            "verified_cost_usd": None, "qualification": False, "action_authorized": False}
    write_json(args.output / "plan.json", plan)

    def lane_job(lane):
        folder = args.output / lane
        folder.mkdir()
        records = []
        print(json.dumps({"lane": lane, "status": "STARTED"}), flush=True)
        barrier.wait(timeout=30)
        for case in cases:
            if stop.is_set() or time.monotonic() - started >= args.deadline_seconds:
                break
            case_id = case["case_id"]
            record = {"case_id": case_id, "lane": lane, "split": "dev", "qualification": False}
            try:
                messages = make_messages(case, lane)
                if lane != "ocr":
                    messages[1]["content"][0]["text"] += (
                        " In this schema distinguishable means one candidate is identified, "
                        "so proposed_candidate MUST equal ranking[0]. If no candidate matches "
                        "or identification is uncertain, use insufficient and null. "
                        "Rank each of c01, c02, c03 exactly once.")
                payload = {"model": NEMOTRON.model, "messages": messages,
                           "temperature": 0, "max_tokens": args.max_output_tokens, "stream": False,
                           "chat_template_kwargs": {"enable_thinking": False},
                           "response_format": constrained_format(lane)}
                write_json(folder / (case_id + ".request.json"),
                    {**record, "request_sha256": sha256(canonical(payload)), "cases_sha256": input_hash,
                     "query_image_sha256": case["query"]["image_sha256"],
                     "candidate_image_sha256": [] if lane == "ocr" else
                         [c["image_sha256"] for c in case["candidates"]],
                     "status": "prepared_not_yet_observed_complete"})
                receipt, response, raw = post(NEMOTRON, payload, key)
                record.update(receipt)
                if raw:
                    with (folder / (case_id + ".response.json")).open("xb") as handle:
                        handle.write(raw)
                if receipt["status"] == "response_received":
                    if receipt.get("returned_model") != NEMOTRON.model:
                        raise ValueError("returned_model_mismatch")
                    parsed = parse_response(completion_text(response), lane, case)
                    write_json(folder / (case_id + ".observation.json"), parsed)
                    record["observation_sha256"] = file_hash(folder / (case_id + ".observation.json"))
                    record["status"] = "observed_schema_valid"
                if receipt.get("http_status") in (401, 403, 429):
                    stop.set()
            except Exception as error:
                record["status"] = "preparation_or_schema_error"
                record["error_type"] = type(error).__name__
                # Error text is controlled validation information, never request/payload/key.
                record["error"] = str(error).replace(key, "[REDACTED]")[:350]
            write_json(folder / (case_id + ".receipt.json"), record)
            records.append(record)
            print(json.dumps({"lane": lane, "case_id": case_id, "status": record["status"],
                              "http_status": record.get("http_status")}), flush=True)
            if record.get("http_status") in (400, 404, 413, 415, 422):
                break  # Do not repeat a request contract that the provider rejected.
            if record["status"] == "preparation_or_schema_error":
                break  # Inspect a contract failure before spending on more cases.
        return {"lane": lane, "attempted_cases": len(records),
                "valid_observations": sum(r["status"] == "observed_schema_valid" for r in records),
                "records": records}

    with ThreadPoolExecutor(max_workers=len(active_lanes), thread_name_prefix="meta-r5-nemotron") as pool:
        futures = [pool.submit(lane_job, lane) for lane in active_lanes]
        lanes = [f.result() for f in futures]
    if file_hash(args.cases) != input_hash or source_binding(args.source_commit) != sources:
        raise ValueError("execution_source_or_cases_changed")
    all_records = [r for lane in lanes for r in lane["records"]]
    usage = [r.get("usage") for r in all_records if isinstance(r.get("usage"), dict)]
    result = {**plan, "ended_utc": datetime.now(timezone.utc).isoformat(),
              "elapsed_seconds": time.monotonic() - started, "lanes": lanes,
              "attempted_cases": len(all_records),
              "http200_calls": sum(r.get("http_status") == 200 for r in all_records),
              "valid_observations": sum(r["status"] == "observed_schema_valid" for r in all_records),
              "reported_usage": usage, "all_expected_cases_completed": len(all_records) == expected_calls,
              "status": "COMPLETE" if len(all_records) == expected_calls and all(r["status"] == "observed_schema_valid" for r in all_records) else "PARTIAL_OR_FAILED"}
    write_json(args.output / "summary.json", result)
    print(json.dumps({k:result[k] for k in ("status", "attempted_cases", "http200_calls", "valid_observations", "elapsed_seconds")}), flush=True)


if __name__ == "__main__":
    main()
