"""Deliberately incomplete agent: only handles the first order."""

import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
source = json.loads(args.input.read_text(encoding="utf-8"))
first = source["orders"][0]
result = {"schemaVersion": 1, "orders": [{
    "orderId": first["orderId"], "totalCents": first["quantity"] * first["unitPriceCents"],
    "state": "READY", "nextAction": "SUBMIT_CHARGE", "receiptId": None,
    "evidenceEventIds": [],
}], "orphanEventIds": []}
args.output.write_text(json.dumps(result), encoding="utf-8")
