"""Append one JSON line per executed step to runs/ship-flare.jsonl (comparability-gate job)."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "runs" / "ship-flare.jsonl"


def log(step, command, inputs=None, outputs=None, metrics=None, status="ok", cost_usd=0.0, note=None):
    row = dict(ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), step=step, command=command,
               inputs=inputs or [], outputs=outputs or [], metrics=metrics or {}, cost_usd=cost_usd, status=status)
    if note:
        row["note"] = note
    with LOG.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    # python flare/gate_runlog.py STEP COMMAND STATUS '{"metrics":...}' [outputs,comma,separated] [note]
    log(sys.argv[1], sys.argv[2], status=sys.argv[3], metrics=json.loads(sys.argv[4]) if len(sys.argv) > 4 else {},
        outputs=sys.argv[5].split(",") if len(sys.argv) > 5 and sys.argv[5] else [], note=sys.argv[6] if len(sys.argv) > 6 else None)
