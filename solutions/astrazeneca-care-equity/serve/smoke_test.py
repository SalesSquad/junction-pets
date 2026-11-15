#!/usr/bin/env python3
"""Smoke test for a running pathway-scribe endpoint. Standard library only.

Sends held-out SYNTHETIC notes, compares each canonical extraction with the
label, and reports note-level exact match and latency percentiles.

Exit status
  0  every floor met
  1  ran, but a floor was missed (exact match, valid-output rate or latency)
  2  could not run: bad arguments, endpoint unreachable, adapter name not served,
     or every request failed

The default exact-match floor is 0.2. It is a breakage alarm, not a quality bar.
The only measurement that exists (data/scribe/eval-v1.json: Gemma 3 1B with the
version-1 adapter, MLX, no guided decoding, 200 test notes) has the plain base
model at 0.0% note-level exact match and the adapter at 41.0% (95% interval
34.4 to 47.9). A wrong chat template, a missing adapter or a request served by
the base model lands near the first number; 0.2 lies between the two and leaves
room for the sampling noise of 50 notes. Set --min-exact-match to the lower
confidence limit measured for the adapter you actually serve.

Exact match is measured against machine-written labels on synthetic notes. It
says how well serving reproduces the training task. It says nothing about real
clinical notes.
"""

import argparse
import datetime
import hashlib
import json
import math
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "scribe"))

import client as scribe_client  # noqa: E402
from metrics import summary, wilson  # noqa: E402  (scribe/metrics.py, standard library only)
from runlog import log  # noqa: E402

DEFAULT_NOTES = HERE / "fixtures" / "heldout-v1.jsonl"


def percentile(values, q):
    """Nearest-rank percentile: the smallest value with at least q% of the data at or below it."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]


def latency_summary(results):
    """Latency of successful requests. The first request is reported apart:
    with scale-to-zero it carries the cold start."""
    ok = [r for r in results if r["latency_s"] is not None]
    steady = [r["latency_s"] for r in ok[1:]] if len(ok) > 1 else [r["latency_s"] for r in ok]
    out = {
        "definition": "client-side wall time of the successful HTTP attempt, in seconds; includes network and platform queueing; nearest-rank percentiles; the first request is excluded when more than one succeeded",
        "n": len(steady),
        "first_request_s": ok[0]["latency_s"] if ok else None,
        "first_request_total_s_with_retries": results[0]["total_s"] if results else None,
    }
    for q in (50, 90, 95, 99):
        out[f"p{q}"] = percentile(steady, q)
    out["max"] = max(steady) if steady else None
    out["mean"] = sum(steady) / len(steady) if steady else None
    return out


def build_report(rows, results, client, args, wall, served):
    predictions = [r["canonical"] for r in results]
    scored = summary(rows, predictions)
    outcomes = scored["outcomes"]
    failed = [r for r in results if r["status"] not in ("ok", "invalid_output")]
    answered = len(results) - len(failed)
    valid = sum(r["status"] == "ok" for r in results)
    decisions = {}
    reasons = {}
    for r in results:
        decisions[r["decision"]] = decisions.get(r["decision"], 0) + 1
        for reason in r["reasons"]:
            reasons[reason] = reasons.get(reason, 0) + 1
    accepted = [i for i, r in enumerate(results) if r["decision"] == "AUTO_ACCEPT"]
    wrong_accepted = sum(not outcomes[i] for i in accepted)
    scores_right = [r["score"] for r, ok in zip(results, outcomes) if ok and r["score"] is not None]
    scores_wrong = [r["score"] for r, ok in zip(results, outcomes) if not ok and r["score"] is not None]
    latency = latency_summary(results)
    exact = scored["note_exact_match"]
    valid_rate = wilson(valid, len(results))
    failures = []
    if exact["value"] is None or exact["value"] < args.min_exact_match:
        failures.append(f"exact match {exact['value']} below floor {args.min_exact_match}")
    if valid_rate["value"] is None or valid_rate["value"] < args.min_valid:
        failures.append(f"valid-output rate {valid_rate['value']} below floor {args.min_valid}")
    if args.max_p95_seconds is not None and (latency["p95"] is None or latency["p95"] > args.max_p95_seconds):
        failures.append(f"p95 latency {latency['p95']} s above ceiling {args.max_p95_seconds} s")
    return {
        "schemaVersion": "pathway-scribe-smoke-v1",
        "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "synthetic": True,
        "endpoint": scribe_client.endpoint_label(client.base_url),
        "served_models": served,
        "settings": dict(client.calibration_key(), prompts=client.prompts_path, threshold=client.threshold,
                         concurrency=args.concurrency, max_tokens=client.max_tokens),
        "notes_file": str(pathlib.Path(args.notes).resolve()),
        "notes_sha256": hashlib.sha256(pathlib.Path(args.notes).read_bytes()).hexdigest(),
        "n": len(results),
        "requests": {
            "answered": answered,
            "valid_output": valid,
            "invalid_output": answered - valid,
            "failed": len(failed),
            "retried": sum((r["attempts"] or 1) > 1 for r in results),
            "failure_kinds": sorted({r["status"] for r in failed}),
        },
        "exact_match": exact,
        "valid_output_rate": valid_rate,
        "route_accuracy": scored["route_accuracy"],
        "event_precision": scored["precision"],
        "event_recall": scored["recall"],
        "event_f1": scored["f1"],
        "distractor_extraction": scored["distractor_extraction"],
        "latency_seconds": latency,
        "wall_seconds": wall,
        "notes_per_second": len(results) / wall if wall > 0 else None,
        "decisions": decisions,
        "review_reasons": dict(sorted(reasons.items())),
        "auto_accept": {
            "n": len(accepted),
            "wrong": wrong_accepted,
            "error_rate": wilson(wrong_accepted, len(accepted)),
            "note": "empirical on these notes; not a guarantee",
        },
        "confidence": {
            "kind": client.confidence_kind,
            "mean_when_exact": sum(scores_right) / len(scores_right) if scores_right else None,
            "mean_when_wrong": sum(scores_wrong) / len(scores_wrong) if scores_wrong else None,
            "n_scored": len(scores_right) + len(scores_wrong),
        },
        "floors": {
            "min_exact_match": args.min_exact_match,
            "min_valid": args.min_valid,
            "max_p95_seconds": args.max_p95_seconds,
        },
        "passed": not failures,
        "failures": failures,
        "limits": "Synthetic notes with machine-written labels. Research artefact; not evidence about real clinical notes.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    scribe_client.add_endpoint_arguments(parser)
    parser.add_argument("--notes", default=str(DEFAULT_NOTES),
                        help="JSONL with note_text, note_date and target_json per line")
    parser.add_argument("--limit", type=int, default=None, help="use only the first N notes")
    parser.add_argument("--min-exact-match", type=float, default=0.2,
                        help="floor on note-level exact match (default 0.2: a breakage alarm, not a quality bar)")
    parser.add_argument("--min-valid", type=float, default=0.9,
                        help="floor on the share of answers that are schema-valid canonical JSON")
    parser.add_argument("--max-p95-seconds", type=float, default=None,
                        help="optional ceiling on the 95th percentile latency")
    parser.add_argument("--skip-model-check", action="store_true",
                        help="do not require the model name in GET /v1/models")
    parser.add_argument("--out", help="write the report JSON here")
    parser.add_argument("--results-out", help="write one result per note (JSONL) here")
    parser.add_argument("--no-log", action="store_true", help="do not append to runs/v2-serve.jsonl")
    args = parser.parse_args(argv)

    def record(status, metrics, outputs=None):
        if not args.no_log:
            log("smoke_test", command="serve/smoke_test.py",
                inputs={"notes": args.notes, "limit": args.limit, "model": args.model, "format": args.fmt,
                        "guided": args.guided, "concurrency": args.concurrency},
                outputs=outputs, metrics=metrics, status=status)

    try:
        client = scribe_client.client_from_arguments(args)
        rows = scribe_client.read_jsonl(args.notes)
        if args.limit is not None:
            rows = rows[: args.limit]
        if not rows:
            raise scribe_client.ScribeError("no notes to send")
        for number, row in enumerate(rows, 1):
            if "target_json" not in row:
                raise scribe_client.ScribeError(f"{args.notes}: note {number} has no target_json")
        # Fail before any network call if the prompt and the output format disagree.
        client.build_request(rows[0])
        served = None
        if not args.skip_model_check:
            served = client.list_models()
            if args.model not in served:
                raise scribe_client.ScribeError(
                    f"model {args.model!r} is not served by the endpoint (served: {served})"
                )
    except (scribe_client.ScribeError, ValueError, OSError) as exc:
        print(f"smoke test could not run: {exc}", file=sys.stderr)
        record("error", {"could_not_run": str(exc)[:300]})
        return 2

    started = time.monotonic()
    results = [client.extract(rows[0])]
    results += scribe_client.run_batch(client, rows[1:], args.concurrency)
    wall = time.monotonic() - started
    report = build_report(rows, results, client, args, wall, served)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    outputs = []
    if args.out:
        pathlib.Path(args.out).write_text(text + "\n", encoding="utf-8")
        outputs.append(args.out)
    if args.results_out:
        with open(args.results_out, "w", encoding="utf-8") as handle:
            for row, result in zip(rows, results):
                handle.write(json.dumps(result, ensure_ascii=False, default=scribe_client.jsonable) + "\n")
        outputs.append(args.results_out)
    metrics = {
        "n": report["n"],
        "exact_match": report["exact_match"]["value"],
        "exact_match_ci95": report["exact_match"]["ci95"],
        "valid_output_rate": report["valid_output_rate"]["value"],
        "requests_failed": report["requests"]["failed"],
        "latency_p50_s": report["latency_seconds"]["p50"],
        "latency_p95_s": report["latency_seconds"]["p95"],
        "first_request_s": report["latency_seconds"]["first_request_s"],
        "wall_seconds": wall,
        "endpoint": report["endpoint"],
        "failures": report["failures"],
    }
    if report["requests"]["answered"] == 0:
        print("smoke test could not run: every request failed", file=sys.stderr)
        record("error", metrics, outputs or None)
        return 2
    record("ok" if report["passed"] else "error", metrics, outputs or None)
    if not report["passed"]:
        for failure in report["failures"]:
            print("FAILED: " + failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
