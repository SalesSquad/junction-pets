"""Reference solution for the offline settlement-reconciliation Harbor task.

Only synthetic, caller-provided data is processed. No payment provider exists here.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def reconcile(document: dict) -> dict:
    if document.get("schemaVersion") != 1:
        raise ValueError("unsupported input schema")

    orders = {order["orderId"]: order for order in document["orders"]}
    events_by_order: dict[str, list[dict]] = defaultdict(list)
    event_id_owners: dict[str, list[str]] = defaultdict(list)
    attempt_id_owners: dict[str, list[str]] = defaultdict(list)
    receipt_owners: dict[str, list[str]] = defaultdict(list)
    orphans: list[str] = []

    for event in document["events"]:
        order_id = event["orderId"]
        event_id_owners[event["eventId"]].append(order_id)
        if event.get("type") == "attempt":
            attempt_id_owners[event.get("attemptId", "")].append(order_id)
        if event.get("type") == "result" and event.get("outcome") == "success" and isinstance(event.get("receiptId"), str):
            receipt_owners[event["receiptId"]].append(order_id)
        if order_id in orders:
            events_by_order[order_id].append(event)
        else:
            orphans.append(event["eventId"])

    corrupted: set[str] = set()
    for owners in (*event_id_owners.values(), *attempt_id_owners.values(), *receipt_owners.values()):
        if len(owners) > 1:
            corrupted.update(owner for owner in owners if owner in orders)

    # A result tied to an attempt started for a different order taints both.
    for event in document["events"]:
        if event.get("type") != "result":
            continue
        origin_orders = attempt_id_owners.get(event.get("attemptId", ""), [])
        if origin_orders and event["orderId"] not in origin_orders:
            corrupted.update(owner for owner in [event["orderId"], *origin_orders] if owner in orders)

    decisions = []
    for order_id in sorted(orders):
        order = orders[order_id]
        total = order["quantity"] * order["unitPriceCents"]
        authorized = order["authorized"] and total <= order["approvedCapCents"]
        events = events_by_order[order_id]
        attempts: dict[str, dict] = {}
        latest: str | None = None
        had_attempt = False
        invalid = order_id in corrupted
        successful_receipt: str | None = None

        for event in events:
            kind = event.get("type")
            if kind == "note":
                continue

            if kind == "attempt":
                had_attempt = True
                attempt_id = event.get("attemptId")
                amount = event.get("amountCents")
                if not isinstance(attempt_id, str) or not attempt_id:
                    invalid = True
                    continue
                if type(amount) is not int or amount != total or not authorized:
                    invalid = True
                if attempt_id in attempts or (latest is not None and attempts[latest]["outcome"] in (None, "timeout", "success")):
                    invalid = True
                attempts[attempt_id] = {"outcome": None, "receipt": None}
                latest = attempt_id

            elif kind == "result":
                attempt_id = event.get("attemptId")
                outcome = event.get("outcome")
                if attempt_id not in attempts or attempts[attempt_id]["outcome"] is not None:
                    invalid = True
                    continue
                if outcome not in {"success", "failure", "timeout"}:
                    invalid = True
                    continue
                if outcome == "success":
                    receipt = event.get("receiptId")
                    if not isinstance(receipt, str) or not receipt.strip():
                        invalid = True
                    else:
                        successful_receipt = receipt
                        attempts[attempt_id]["receipt"] = receipt
                elif "receiptId" in event:
                    invalid = True
                attempts[attempt_id]["outcome"] = outcome
            else:
                invalid = True

        receipt_id: str | None = None
        if invalid:
            state, action = "ESCALATE", "NO_ACTION"
        elif not authorized:
            state, action = "BLOCKED", "NO_ACTION"
        elif not had_attempt:
            state, action = "READY", "SUBMIT_CHARGE"
        elif successful_receipt is not None:
            state, action = "PAID", "NO_ACTION"
            receipt_id = successful_receipt
        elif latest is not None and attempts[latest]["outcome"] == "failure":
            state, action = "RETRYABLE", "RETRY_WITH_NEW_ATTEMPT"
        else:
            state, action = "UNKNOWN", "VERIFY_EXISTING"

        decisions.append({
            "orderId": order_id,
            "totalCents": total,
            "state": state,
            "nextAction": action,
            "receiptId": receipt_id,
            "evidenceEventIds": [event["eventId"] for event in events],
        })

    return {"schemaVersion": 1, "orders": decisions, "orphanEventIds": orphans}


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile offline synthetic payment events")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    options = parser.parse_args()
    document = json.loads(options.input.read_text(encoding="utf-8"))
    result = reconcile(document)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
