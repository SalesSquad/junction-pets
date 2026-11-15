"""Shared paths, row loading and run log for scribe/mlx2 (NVIDIA_OPTIONS.md step 3).

SYNTHETIC notes only. Research artefact, not a medical device: every extracted event is a proposal that a
person confirms. Standard library plus pyarrow; MLX is imported only by train.py and infer.py.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent  # solutions/astrazeneca-care-equity
for sub in ("scribe", "scribe/v2", "scribe/v3"):
    p = str(ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)

DATASET = ROOT / "data/scribe/v2/dataset"
OUT = ROOT / "data/scribe/v4/mlx"
ART = ROOT / "scribe/v4/artifacts"
RUNLOG = ROOT / "runs/laneA-step3.jsonl"
MLX_PY = ROOT / "scribe/artifacts/mlx-venv/bin/python"

BASES = {
    "270m": {
        "mlx": str(ART / "hf-cache/hub/models--mlx-community--gemma-3-270m-it-bf16/snapshots/c806ef3a4ed971bd75aaee3346e0fef808512f03"),
        "repo": "mlx-community/gemma-3-270m-it-bf16",
        "peft_base": "unsloth/gemma-3-270m-it",
    },
    "1b": {
        "mlx": str(ROOT / "scribe/artifacts/hf-cache/hub/models--mlx-community--gemma-3-1b-it-bf16/snapshots/60444cd9d4be58ce6995614c6551b4d8db047483"),
        "repo": "mlx-community/gemma-3-1b-it-bf16",
        "peft_base": "unsloth/gemma-3-1b-it",
    },
}

# Splits this step may read. Test files and any stress set are never read here (step 8 scores them once).
ALLOWED_SPLITS = ("train", "val")


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_split(name):
    if name not in ALLOWED_SPLITS:
        raise ValueError(f"step 3 reads only {ALLOWED_SPLITS}; {name!r} is scored once by step 8")
    import pyarrow.parquet as pq

    return pq.read_table(DATASET / f"{name}.parquet").to_pylist()


def load_rows(path):
    """Rows of any parquet or JSONL file (used by step 8 to run a trained arm on its own sets)."""
    path = pathlib.Path(path)
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq

        return pq.read_table(path).to_pylist()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rel(path):
    try:
        return str(pathlib.Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def save_json(path, obj):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def log(step, command="", inputs=None, outputs=None, metrics=None, cost_usd=0, status="ok"):
    """Append one JSON line per executed step to runs/laneA-step3.jsonl."""
    RUNLOG.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": now(),
        "step": step,
        "command": command,
        "inputs": inputs or {},
        "outputs": outputs or {},
        "metrics": metrics or {},
        "cost_usd": cost_usd,
        "status": status,
    }
    with RUNLOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
