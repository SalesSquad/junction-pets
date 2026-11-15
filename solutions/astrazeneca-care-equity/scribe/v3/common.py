"""Shared paths and helpers of scribe/v3 (gate of teaching round 2, dataset v3, audit inputs and scoring).

All text handled here is SYNTHETIC, written by language models from sampled answer keys. Not for clinical use.
"""

import datetime as dt
import hashlib
import json
import math
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = ROOT / "data/scribe/v3/teacher/candidates.jsonl"
JUDGES_DIR = ROOT / "data/scribe/v3/judges"
POLICY = JUDGES_DIR / "policy.json"
GATE = ROOT / "data/scribe/v3/gate"
DATASET_V2 = ROOT / "data/scribe/v2/dataset"
DATASET_V3 = ROOT / "data/scribe/v3/dataset"
AUDIT = ROOT / "data/scribe/v3/audit"
RUNLOG = ROOT / "runs/gate-v3.jsonl"

CURRICULA = ("hard_standard", "careful", "no_event", "long_multi_visit", "terse")


STYLE_LABELS = ("lähetekirje", "käyntimerkintä", "hoitajan puhelinmerkintä", "loppulausunnon ote")


def starts_with_style_label(note_text):
    """True when the note begins with one of the four style names (a formatting artefact; version 2 and the held-out
    files have none). Leading markdown marks and spaces are ignored."""
    head = note_text.lstrip("*#_ \n").lower()
    return any(head.startswith(x) for x in STYLE_LABELS)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def order_key(ident, salt):
    """Fixed pseudo-random order: SHA-256 of a salt and the id."""
    return hashlib.sha256(f"{salt}|{ident}".encode()).hexdigest()


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    tmp.replace(path)


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n")
    tmp.replace(path)


def log(step, **kw):
    """One JSON line per executed step in runs/gate-v3.jsonl."""
    RUNLOG.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(ts=now(), step=step, host=socket.gethostname(), command=kw.pop("command", " ".join(sys.argv)))
    for k in ("inputs", "outputs", "metrics", "cost_usd", "status"):
        rec[k] = kw.pop(k, None)
    rec.update(kw)
    with RUNLOG.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def frac(num, den):
    return dict(numerator=num, denominator=den, rate=(round(num / den, 4) if den else None))


def wilson(num, den, z=1.959963984540054):
    """Wilson score interval for a binomial proportion; (None, None) when the denominator is 0."""
    if not den:
        return None, None
    p = num / den
    d = 1 + z * z / den
    centre = (p + z * z / (2 * den)) / d
    half = z * math.sqrt(p * (1 - p) / den + z * z / (4 * den * den)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def share(num, den):
    lo, hi = wilson(num, den)
    return dict(
        numerator=num,
        denominator=den,
        share=(round(num / den, 4) if den else None),
        wilson95=[None if lo is None else round(lo, 4), None if hi is None else round(hi, 4)],
    )
