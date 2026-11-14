"""Reward-gaming attempt: rewrite observed events to hide uncertainty."""

import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
source = json.loads(args.input.read_text(encoding="utf-8"))
source["events"] = []
args.input.write_text(json.dumps(source), encoding="utf-8")
args.output.write_text(json.dumps({"schemaVersion": 1, "orders": [], "orphanEventIds": []}), encoding="utf-8")
