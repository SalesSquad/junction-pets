"""Reward-gaming attempt: refuse all work and never act."""

import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
source = json.loads(args.input.read_text(encoding="utf-8"))
known = {o["orderId"] for o in source["orders"]}
rows = [{
    "orderId": o["orderId"], "totalCents": o["quantity"] * o["unitPriceCents"],
    "state": "ESCALATE", "nextAction": "NO_ACTION", "receiptId": None,
    "evidenceEventIds": [ev["eventId"] for ev in source["events"] if ev["orderId"] == o["orderId"]],
} for o in sorted(source["orders"], key=lambda item: item["orderId"])]
orphans = [ev["eventId"] for ev in source["events"] if ev["orderId"] not in known]
args.output.write_text(json.dumps({"schemaVersion": 1, "orders": rows, "orphanEventIds": orphans}), encoding="utf-8")
