"""Append-only execution receipts; local compute has no metered API charge.

The receipt file is runs/eventlog.jsonl unless EVENTLOG_RUNLOG names another
file relative to the solution root (the review-fix runs use runs/eventlog-fix.jsonl).
"""
import json, os, socket
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def runlog_path():
    return ROOT / os.environ.get('EVENTLOG_RUNLOG', 'runs/eventlog.jsonl')

def log(step, command, inputs=None, outputs=None, metrics=None, status='ok'):
    with runlog_path().open('a') as f:
        f.write(json.dumps(dict(ts=datetime.now(timezone.utc).isoformat(), step=step,
          host=socket.gethostname(), command=command, inputs=inputs or [], outputs=outputs or [],
          metrics=metrics or {}, cost_usd=0.0, status=status), allow_nan=False)+'\n')
