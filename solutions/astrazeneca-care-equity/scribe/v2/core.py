"""Paths, run log and small JSON helpers for version 2. Standard library only."""

import datetime
import json
import os
import pathlib
import platform
import socket

import _paths

ROOT = _paths.ROOT
DATA = ROOT / "data/scribe"
V2_DATA = DATA / "v2"
ARTIFACTS = _paths.V2 / "artifacts"
ABLATION_JSON = V2_DATA / "ablation-v1.json"
RESULTS_MD = _paths.V2 / "RESULTS.md"
# Run log written by the GPU-side code. The code-writing steps are logged separately in runs/v2-code.jsonl.
RUNLOG = pathlib.Path(os.environ.get("SCRIBE_V2_RUNLOG", ROOT / "runs/v2-ablation.jsonl"))


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(step, command="", inputs=None, outputs=None, metrics=None, cost_usd=0, status="ok", path=None):
    """Append one JSON line: ts, step, host, command, inputs, outputs, metrics, cost_usd, status."""
    p = pathlib.Path(path) if path else RUNLOG
    p.parent.mkdir(parents=True, exist_ok=True)
    line = dict(
        ts=utc_now(),
        step=step,
        host=socket.gethostname(),
        command=command,
        inputs=inputs,
        outputs=outputs,
        metrics=metrics,
        cost_usd=cost_usd,
        status=status,
    )
    with p.open("a") as f:
        f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
    return line


def save_json(path, obj):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str))
    tmp.replace(path)
    return path


def load_json(path):
    return json.loads(pathlib.Path(path).read_text())


def versions():
    """Library versions actually importable in this interpreter (None when a library is absent)."""
    out = {"python": platform.python_version()}
    for name in ("torch", "transformers", "peft", "accelerate", "pyarrow", "lmformatenforcer"):
        try:
            module = __import__(name)
            out[name] = getattr(module, "__version__", "unknown")
        except Exception:  # absent or broken install: recorded, never guessed
            out[name] = None
    return out
