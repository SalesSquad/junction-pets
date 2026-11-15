#!/usr/bin/env python3
"""Run NVIDIA OCR v2 / Nano VL on the frozen R5 development cases.

Example (run from a clean committed checkout; output must be outside it):
  python -B run_nim.py --cases /data/cases.json --output /data/nim-canary \
      --source-commit COMMIT
The default is one case, both distinct NIM providers, at most two calls.
Use --models ocr|nano|both, --start-index 0..7, --case-count 1..8,
--workers 1..4, and --max-output-tokens 256..2048 (Nano only).
Only provider.load_nim_key reads NVIDIA_API_KEY; no Keychain fallback exists.
Missing/invalid credentials produce BLOCKED_AUTH, zero calls, and exit 2.
No retry occurs. The first failed job stops undispatched jobs; up to --workers
calls can already be in flight. The deadline bounds dispatch, not in-flight I/O.
Official request contracts are recorded in nim_models.SOURCE_DOCS.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import argparse
import io
import json
from pathlib import Path
import re
import subprocess
import threading
import time

from PIL import Image

from nim_models import (NANO_ENDPOINT, NANO_MODEL, OCR_ENDPOINT, OCR_MODEL,
                        SOURCE_DOCS, build_nano_payload, build_ocr_payload, parse_ocr_response)
from protocol import WORK_ID, image_bytes, make_messages, parse_response
from provider import NIM_NANO, NIM_OCR, canonical, completion_text, load_nim_key, post, sha256

ROOT = Path(__file__).resolve().parent
SOURCE_FILES = ("run_nim.py", "provider.py", "protocol.py", "nim_models.py")
ROUTES = {"ocr": NIM_OCR, "nano": NIM_NANO}


def write_json(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def source_binding(commit):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    if git("rev-parse", "HEAD") != commit or git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("clean_pinned_execution_source_required")
    return Path(git("rev-parse", "--show-toplevel")).resolve(), {
        name: sha256((ROOT / name).read_bytes()) for name in SOURCE_FILES}


def payload_for(case, model, max_tokens):
    # The existing protocol admits the exact pixels, aliases and source views.
    messages = make_messages(case, "ocr" if model == "ocr" else "visual")
    if model == "ocr":
        raw, mime = image_bytes(case["query"], case["image_root"])
        return build_ocr_payload(raw, mime)
    # Nano documents RGB without alpha. Reject rather than transform/hash new pixels.
    for item in [case["query"], *case["candidates"]]:
        raw, _ = image_bytes(item, case["image_root"])
        with Image.open(io.BytesIO(raw)) as decoded:
            if decoded.mode != "RGB" or "transparency" in decoded.info:
                raise ValueError("nano_admitted_rgb_image_required")
    return build_nano_payload(messages, max_tokens)


def run(args):
    if (args.models not in ("ocr", "nano", "both") or not 1 <= args.workers <= 4 or
            not 0 <= args.start_index < 8 or not 1 <= args.case_count <= 8 - args.start_index or
            not 256 <= args.max_output_tokens <= 2048 or not 120 <= args.deadline_seconds <= 1800):
        raise ValueError("bounded_nim_budget_required")
    if (NIM_OCR.model, NIM_OCR.url, NIM_NANO.model, NIM_NANO.url) != (
            OCR_MODEL, OCR_ENDPOINT, NANO_MODEL, NANO_ENDPOINT):
        raise ValueError("provider_adapter_route_mismatch")
    repo, sources = source_binding(args.source_commit)
    if args.output.resolve().is_relative_to(repo):
        raise ValueError("output_must_be_outside_execution_checkout")
    case_bytes = args.cases.read_bytes()
    input_hash = sha256(case_bytes)
    document = json.loads(case_bytes)
    cases = document.get("cases")
    if (document.get("work_id") != WORK_ID or not isinstance(cases, list) or len(cases) != 8 or
            any(not isinstance(c, dict) or c.get("split") != "dev" or
                not isinstance(c.get("case_id"), str) or not re.fullmatch(r"q[0-9]{4}", c["case_id"])
                for c in cases) or len({c["case_id"] for c in cases}) != 8):
        raise ValueError("eight_frozen_development_cases_required")
    selected = cases[args.start_index:args.start_index + args.case_count]
    models = list(ROUTES) if args.models == "both" else [args.models]
    jobs = [(case, model) for case in selected for model in models]
    args.output.mkdir(parents=True, exist_ok=False)
    started, stop = time.monotonic(), threading.Event()
    plan = {"schema_version": 1, "work_id": WORK_ID, "source_commit": args.source_commit,
            "source_sha256": sources, "cases_sha256": input_hash, "source_docs": SOURCE_DOCS,
            "providers": [{"provider": ROUTES[m].name, "model": ROUTES[m].model,
                           "url": ROUTES[m].url} for m in models],
            "start_index": args.start_index, "case_count": args.case_count,
            "maximum_inference_calls": len(jobs), "max_concurrent_calls": args.workers,
            "max_output_tokens_nano": args.max_output_tokens, "max_attempts_per_job": 1,
            "retry_performed": False, "deadline_seconds": args.deadline_seconds,
            "call_timeout_seconds": 120, "new_gpu_instances": 0, "verified_cost_usd": None,
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "qualification": False, "action_authorized": False}
    write_json(args.output / "plan.json", plan)

    def finish(status, records, **extra):
        result = {**plan, "status": status, "records": records,
                  "inference_calls_attempted": sum(r.get("provider_call_attempted", False) for r in records),
                  "http200_calls": sum(r.get("http_status") == 200 for r in records),
                  "valid_observations": sum(r["status"] == "observed_schema_valid" for r in records),
                  "ended_utc": datetime.now(timezone.utc).isoformat(),
                  "elapsed_seconds": time.monotonic() - started, **extra}
        write_json(args.output / "summary.json", result)
        return result

    try:
        key = load_nim_key()
    except RuntimeError:
        return finish("BLOCKED_AUTH", [], reason="nvidia_nim_credential_missing_or_invalid")
    # Admit all selected payloads before any spend. Never persist base64 requests.
    try:
        prepared = [(case, model, payload_for(case, model, args.max_output_tokens)) for case, model in jobs]
        if any(len(canonical(payload)) > 16 * 1024 * 1024 for _, _, payload in prepared):
            raise ValueError("bounded_request_required")
    except Exception as error:
        return finish("BLOCKED_INPUT", [], error_type=type(error).__name__)
    for model in models:
        (args.output / ROUTES[model].name).mkdir()

    def job(item):
        case, model, payload = item
        route = ROUTES[model]
        stem = args.output / route.name / case["case_id"]
        record = {"case_id": case["case_id"], "split": "dev", "provider": route.name,
                  "requested_model": route.model, "source_commit": args.source_commit,
                  "cases_sha256": input_hash, "request_sha256": sha256(canonical(payload)),
                  "query_image_sha256": case["query"]["image_sha256"],
                  "candidate_image_sha256": [] if model == "ocr" else
                      [c["image_sha256"] for c in case["candidates"]],
                  "provider_call_attempted": False, "qualification": False, "action_authorized": False}
        if stop.is_set() or time.monotonic() - started >= args.deadline_seconds:
            record["status"] = "SKIPPED_STOP_OR_DEADLINE"
        else:
            try:
                write_json(stem.with_suffix(".request.json"), record)
                record["provider_call_attempted"] = True
                receipt, response, raw = post(route, payload, key, timeout=120)
                record.update(receipt)
                if raw:
                    with stem.with_suffix(".response.json").open("xb") as handle:
                        handle.write(raw)
                if receipt["status"] == "response_received" and receipt.get("http_status") == 200:
                    if receipt.get("returned_model") != route.model:
                        raise ValueError("returned_model_mismatch")
                    parsed = (parse_ocr_response(response) if model == "ocr" else
                              parse_response(completion_text(response), "visual", case))
                    observation = {**parsed, "schema_version": 1, "case_id": case["case_id"],
                                   "provider": route.name, "model": route.model,
                                   "source_commit": args.source_commit, "cases_sha256": input_hash,
                                   "request_sha256": record["request_sha256"],
                                   "response_sha256": receipt["response_sha256"],
                                   "observation_type": "ocr_text" if model == "ocr" else "visual_comparison"}
                    write_json(stem.with_suffix(".observation.json"), observation)
                    record["observation_sha256"] = sha256(stem.with_suffix(".observation.json").read_bytes())
                    record["status"] = "observed_schema_valid"
            except Exception as error:
                # No exception message, request, environment or key enters output.
                record["status"] = "preparation_or_schema_error"
                record["error_type"] = type(error).__name__
            if record["status"] != "observed_schema_valid":
                stop.set()
        write_json(stem.with_suffix(".receipt.json"), record)
        return record

    with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="meta-r5-nim") as pool:
        records = list(pool.map(job, prepared))
    try:
        unchanged = (sha256(args.cases.read_bytes()) == input_hash and
                     source_binding(args.source_commit) == (repo, sources))
    except (OSError, ValueError, subprocess.SubprocessError):
        unchanged = False
    status = ("SOURCE_CHANGED" if not unchanged else "COMPLETE" if
              all(r["status"] == "observed_schema_valid" for r in records) else "PARTIAL_OR_FAILED")
    return finish(status, records, source_and_cases_unchanged=unchanged)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--models", choices=("ocr", "nano", "both"), default="both")
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--case-count", type=int, default=1)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--deadline-seconds", type=int, default=900)
    result = run(parser.parse_args(argv))
    print(json.dumps({k: result[k] for k in ("status", "inference_calls_attempted", "http200_calls", "valid_observations")}))
    return 0 if result["status"] == "COMPLETE" else 2 if result["status"] == "BLOCKED_AUTH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
