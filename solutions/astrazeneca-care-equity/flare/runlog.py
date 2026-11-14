"""Append one JSON line per executed step to runs/laneC-step9.jsonl."""
import json, sys
from datetime import datetime, timezone
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "runs" / "laneC-step9.jsonl"


def log(step, command, inputs=None, outputs=None, metrics=None, status="ok", cost_usd=0.0):
    row = dict(ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), step=step, command=command,
               inputs=inputs or [], outputs=outputs or [], metrics=metrics or {}, cost_usd=cost_usd, status=status)
    with LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    # python flare/runlog.py STEP COMMAND STATUS '{"metrics":...}' [outputs,comma,separated]
    log(sys.argv[1], sys.argv[2], status=sys.argv[3], metrics=json.loads(sys.argv[4]) if len(sys.argv) > 4 else {},
        outputs=sys.argv[5].split(",") if len(sys.argv) > 5 and sys.argv[5] else [])
