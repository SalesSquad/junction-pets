#!/usr/bin/env python3
"""Measure bounded note assertions against completed official reveal labels.

Reports precision and coverage separately. Unknowns never count as correct.
Only won orders have reveal labels; this is a selected policy cohort and does
not establish accuracy on all requests or a delivery success rate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from typed_notes import parse_notes, VERSION


FIELDS = {
    "readyAt": "readyAt", "releaseAt": "releasedAt", "pickupHours": "pickupHours",
    "deliveryHours": "deliveryHours", "noteDeadline": "noteDeadline",
    "manualRequired": "manualGearbox", "platesRequired": "needsPlates", "summerTyres": "summerTyres",
}


def compare_field(field: str, predicted: Any, truth: dict, request: dict, order: dict) -> str:
    actual = truth.get(FIELDS[field])
    if predicted is None:
        return "unknown"
    if field.endswith("Hours"):
        return "correct" if isinstance(actual, dict) and all(actual.get(k) == value for k, value in predicted.items()) else "false_assertion"
    if field == "readyAt":
        effective = max(request["legs"][0]["pickup"]["window"]["from"], predicted)
        return "correct" if effective == actual else "false_assertion"
    if field == "noteDeadline" and actual is None and predicted >= order.get("deadline", float("inf")):
        # Sponsor records a noteDeadline only when it actually tightens the
        # selected deadline. Preserve nonbinding evidence as a separate class.
        return "nonbinding"
    return "correct" if actual == predicted else "false_assertion"


def evaluate(paths: list[Path], sample_limit: int = 12) -> dict:
    totals = {name: Counter() for name in FIELDS}
    counts = Counter()
    sources, samples, per_world = [], [], []
    seen_worlds = set()
    for path in paths:
        encoded = path.read_bytes()
        bundle = json.loads(gzip.decompress(encoded) if path.suffix == ".gz" else encoded)
        if "reveal" not in bundle:
            continue
        if bundle["world_id"] in seen_worlds:
            raise ValueError("Duplicate world_id would double-count note evidence: " + bundle["world_id"])
        seen_worlds.add(bundle["world_id"])
        reveal = bundle["reveal"]
        requests = {row["request"]["id"]: row["request"] for row in reveal["requests"]}
        orders = {row["id"]: row for row in bundle["snapshot"]["orders"]}
        world_counts = Counter()
        for row in reveal["orders"]:
            request = requests.get(row["orderId"])
            if request is None:
                raise ValueError("Revealed order has no originating request")
            counts["revealed_orders"] += 1
            if not request.get("note"):
                counts["orders_without_note"] += 1
                continue
            counts["orders_with_note"] += 1
            parsed = parse_notes(request)
            counts[parsed.scope] += 1
            counts["orders_with_ambiguous_clauses"] += bool(parsed.ambiguous)
            counts["orders_with_unknown_clauses"] += bool(parsed.unknown)
            counts["unevaluated_pickupBefore_assertions"] += parsed.pickupBefore is not None
            if parsed.scope != "single_leg":
                continue
            if len(row["legs"]) != 1:
                raise ValueError("Request/reveal leg count mismatch")
            truth, order = row["legs"][0], orders.get(row["orderId"], {})
            for name in FIELDS:
                predicted = getattr(parsed, name)
                outcome = compare_field(name, predicted, truth, request, order)
                totals[name][outcome] += 1
                world_counts[outcome] += 1
                if outcome == "false_assertion" and len(samples) < sample_limit:
                    samples.append({"world_id": bundle["world_id"],
                                    "order_digest": hashlib.sha256(row["orderId"].encode()).hexdigest()[:12],
                                    "field": name, "predicted": predicted, "actual": truth.get(FIELDS[name]),
                                    "note": request["note"]["text"]})
        sources.append({"world_id": bundle["world_id"], "bundle_sha256": hashlib.sha256(encoded).hexdigest(),
                        "policy": bundle.get("policy"), "seed_group": bundle.get("seed_group")})
        per_world.append({"world_id": bundle["world_id"], **world_counts})
    summary = {}
    for name, counter in totals.items():
        tested = counter["correct"] + counter["false_assertion"]
        all_rows = sum(counter.values())
        # Descriptive Wilson interval over asserted fields. Rows within a
        # world are correlated, so this is not a cross-world confidence gate.
        interval = None
        if tested:
            proportion, z = counter["correct"] / tested, 1.959963984540054
            denominator = 1 + z * z / tested
            centre = (proportion + z * z / (2 * tested)) / denominator
            width = z * math.sqrt(proportion * (1 - proportion) / tested + z * z / (4 * tested * tested)) / denominator
            interval = [max(0.0, centre - width), min(1.0, centre + width)]
        summary[name] = {"correct": counter["correct"], "false_assertion": counter["false_assertion"],
                         "unknown": counter["unknown"], "nonbinding": counter["nonbinding"],
                         "assertion_precision": counter["correct"] / tested if tested else None,
                         "descriptive_wilson_95": interval,
                         "evaluated_rows": all_rows,
                         "emitted_assertions": tested + counter["nonbinding"],
                         "assertion_coverage": tested / all_rows if all_rows else None}
    return {"schemaVersion": 1, "parser_version": VERSION,
            "parser_sha256": hashlib.sha256(Path(__file__).with_name("typed_notes.py").read_bytes()).hexdigest(),
            "counts": dict(counts), "fields": summary, "worlds": per_world,
            "sources": sources, "false_assertion_samples": samples,
            "limitations": ["Won-order cohort only; not all requests", "Unscoped multi-leg notes excluded from field accuracy",
                            "Unknowns do not count as correct", "Hours compare only explicitly asserted components",
                            "pickupBefore has no direct reveal label and is not scored",
                            "Descriptive field intervals assume independent rows; worlds contain correlated rows",
                            "No delivery-rate or neural-training claim", "Development evidence if these notes informed grammar"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="A completed official bundle or directory of *.json.gz bundles")
    parser.add_argument("--output", required=True)
    parser.add_argument("--samples", type=int, default=12)
    args = parser.parse_args()
    source = Path(args.input)
    paths = sorted(source.rglob("*.json.gz")) if source.is_dir() else [source]
    if not paths:
        raise ValueError("No completed-world bundles found")
    result = evaluate(paths, max(0, args.samples))
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"counts": result["counts"], "fields": result["fields"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
