#!/usr/bin/env python3
"""Reconcile official scores, classify observed failures, and join live features.

Reveals/ledger are OUTCOME labels only. Features must have been recorded before
the quote in official_study.py; this exporter never invents retrospective live
state from an end-of-world snapshot. Missing rows or score mismatches fail closed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any


def load_bundle(path: Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()))


def labels_and_causes(bundle: dict) -> tuple[dict[str, dict], dict]:
    orders = {order["id"]: order for order in bundle["snapshot"]["orders"]
              if order["status"] != "cancelled"}
    events = sorted(bundle["events"], key=lambda event: event["seq"])
    by_order: dict[str, list] = defaultdict(list)
    gig_orders = {gig["id"]: {stop["orderId"] for stop in gig["stops"]}
                  for gig in bundle["snapshot"]["gigs"]}
    for event in events:
        ids = set()
        if event.get("orderId"):
            ids.add(event["orderId"])
        if event["kind"] == "ledger" and event["line"].get("orderId"):
            ids.add(event["line"]["orderId"])
        # A failed visit belongs to its explicit order, even in a shared gig.
        # Only events without an order identity can describe the whole gig.
        if not ids and event.get("gigId"):
            ids.update(gig_orders.get(event["gigId"], set()))
        for order_id in ids:
            by_order[order_id].append(event)
    labels, counts = {}, {"late": Counter(), "on_time": Counter()}
    for order_id, order in orders.items():
        history = by_order[order_id]
        incomplete = any(at is None for at in order["deliveredAt"])
        refund = any(event["kind"] == "ledger" and event["line"]["kind"] == "late_refund"
                     for event in history)
        late = int(incomplete or refund)
        reasons = sorted({event["reason"] for event in history if event["kind"] == "visit_failed"})
        flags = {"undelivered": incomplete, "late_refund": refund,
                 "failed_visit": bool(reasons),
                 "deadline_close": any(event["kind"] == "deadline_close" for event in history),
                 "driver_drop": any(event["kind"] == "gig_dropped" for event in history),
                 "no_show": any(event["kind"] == "no_show" for event in history),
                 "driver_late": any(event["kind"] == "driver_late" for event in history),
                 "next_day": order["option"] == "next_day",
                 "trade_in": len(order["legs"]) > 1}
        counter = counts["late" if late else "on_time"]
        counter["orders"] += 1
        counter.update(name for name, value in flags.items() if value)
        counter.update("visit_failed_" + reason for reason in reasons)
        labels[order_id] = {"late": late, "option": order["option"], "flags": flags,
                            "failure_reasons": reasons}
    official = bundle["score"]
    on_time = sum(row["late"] == 0 for row in labels.values())
    exact_on_time = round(official["onTimeShare"] * official["wonOrders"])
    if len(labels) != official["wonOrders"] or on_time != exact_on_time:
        raise ValueError(f"Official-score label mismatch for {bundle['world_id']}: "
                         f"labels={len(labels)}/{on_time}, score={official['wonOrders']}/{exact_on_time}")
    if abs(official["onTimeShare"] * official["wonOrders"] - exact_on_time) > 1e-6:
        raise ValueError("Official on-time share does not imply an integer count")
    return labels, {key: dict(sorted(value.items())) for key, value in counts.items()}


def build(root: Path, destination: Path) -> dict:
    from reliability_experiment import FEATURE_NAMES

    destination.mkdir(parents=True, exist_ok=True)
    all_rows, world_rows, summaries, seen_worlds = [], [], [], set()
    total_causes = {"late": Counter(), "on_time": Counter()}
    for path in sorted(root.rglob("*.json.gz")):
        bundle = load_bundle(path)
        if "snapshot" not in bundle or "reveal" not in bundle:
            continue
        world_id = bundle["world_id"]
        if world_id in seen_worlds:
            raise ValueError("Duplicate world bundle: " + world_id)
        seen_worlds.add(world_id)
        labels, causes = labels_and_causes(bundle)
        for category, values in causes.items():
            total_causes[category].update(values)
        run_path = path.parent / "run.json"
        run = json.loads(run_path.read_text()) if run_path.exists() else {}
        if bundle["snapshot"]["worldId"] != world_id:
            raise ValueError("Snapshot world identity mismatch")
        if run and (run.get("world_id") != world_id
                    or run.get("state") != "completed"
                    or run.get("config", {}).get("seed_group") != bundle["seed_group"]
                    or run.get("config", {}).get("policy") != bundle["policy"]
                    or run.get("evidence", {}).get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest()):
            raise ValueError("Run receipt does not bind this world, policy, seed and bundle")
        partition = run.get("config", {}).get("partition", "historical")
        score = bundle["score"]
        on_time = sum(row["late"] == 0 for row in labels.values())
        world_row = {"world_id": world_id, "seed_group": bundle["seed_group"],
                     "policy": bundle["policy"], "partition": partition,
                     "won_orders": score["wonOrders"], "on_time_orders": on_time,
                     "margin_cents": score["marginCents"], "ranked": score["ranked"]}
        world_rows.append(world_row)
        features_path = path.parent / "decision_features.jsonl"
        training_count = 0
        if features_path.exists():
            latest: dict[tuple[str, str], dict] = {}
            for line in features_path.read_text().splitlines():
                record = json.loads(line)
                if record["world_id"] != world_id:
                    raise ValueError("Feature world does not match bundle")
                if record.get("quoted_price") is not None:
                    latest[(record["order_id"], record["option"])] = record
            # Reveal's last quote/outcome validates the feature join. It never supplies a feature.
            reveals = {row["request"]["id"]: row for row in bundle["reveal"]["requests"]}
            for order_id, label in labels.items():
                record = latest.get((order_id, label["option"]))
                request = reveals[order_id]
                if request.get("outcome") != "won" or request.get("option") != label["option"]:
                    raise ValueError("Official reveal does not match the won chosen option: " + order_id)
                if record is None or record["at"] >= request["request"]["respondBy"]:
                    raise ValueError("Missing valid decision-time feature row: " + order_id)
                if record["quoted_price"] != (request["quote"] or {}).get(label["option"]):
                    raise ValueError("Recorded quote does not match official last quote: " + order_id)
                values = record["features"]
                if set(values) != set(FEATURE_NAMES):
                    raise ValueError("Feature schema mismatch")
                all_rows.append({"world_id": world_id, "seed_group": bundle["seed_group"],
                                 "order_id": order_id, "policy": bundle["policy"],
                                 "partition": partition, "late": label["late"],
                                 "official_won_orders": score["wonOrders"],
                                 "official_on_time_orders": on_time,
                                 **{name: values[name] for name in FEATURE_NAMES}})
                training_count += 1
        summaries.append({**world_row, "causes": causes, "decision_rows": training_count,
                          "bundle_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                          "source": bundle.get("source", {})})
    if not summaries:
        raise ValueError("No official bundles found")
    with open(destination / "results.csv", "w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(world_rows[0]))
        writer.writeheader()
        writer.writerows(world_rows)
    # Always replace the task-owned CSV, including the empty case, so a previous
    # dataset cannot survive underneath a fresh summary claiming zero rows.
    fields = ["world_id", "seed_group", "order_id", "policy", "partition", "late",
              "official_won_orders", "official_on_time_orders", *FEATURE_NAMES]
    with open(destination / "orders.csv", "w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)
    result = {"schemaVersion": 1, "world_count": len(summaries),
              "decision_rows": len(all_rows), "labels_reconcile_with_official_score": True,
              "causes_are_overlapping_associations_not_causal_attribution": True,
              "causes": {key: dict(sorted(value.items())) for key, value in total_causes.items()},
              "worlds": summaries}
    (destination / "dataset_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = build(Path(args.input), Path(args.output))
    print(json.dumps({key: value for key, value in result.items() if key != "worlds"}, sort_keys=True))


if __name__ == "__main__":
    main()
