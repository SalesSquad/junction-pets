"""The single place where version-2 code touches scribe/v2/data_tools.py and the data files.

data_tools.py is written by another step. Everything the training and evaluation code needs from it
goes through this module, so a change of name there is a one-line change here.

What is looked up in data_tools (first name that exists wins):

  splits      load_split(name) | load_rows(name) | read_split(name)
              name is one of SPLITS below; returns a list of row dicts.
  expression  expression_messages(row) | messages_expression(row)
              -> chat messages (system + user) that ask for the expression format
              expression_target(row) | to_expression(row) | target_expression(row)
              -> the exact text the model must emit (a dict is dumped as compact JSON)
              resolve_expression(obj, note_date) | resolve(obj, note_date) | to_absolute(obj, note_date)
              -> the absolute form {"entry_route": ..., "events": [{"type", "date", "precision"}]}
              EXPRESSION_SCHEMA | expression_schema()
              -> optional JSON schema for constrained decoding

When data_tools has no split loader, files are tried in this order and the source is recorded:
  1. one file per split and writer: <folder>/<name>.{parquet,jsonl}, e.g. train_haiku.parquet;
  2. one file per split holding both writers: <folder>/{train,val,test}.{parquet,jsonl}, filtered on
     the row's writer;
  3. the version-1 files for the Nemotron splits and data/scribe/haiku-test.jsonl for test_haiku.
<folder> is data/scribe/v2/dataset-v2, data/scribe/v2 or data/scribe/dataset-v2.

Rows are normalised to carry: id, note_text, note_date, target_json (absolute, canonical),
distractors, writer ("nemotron" | "haiku" | other) and kind ("standard" when the row has none).
"""

from __future__ import annotations

import importlib
import json
import pathlib

import _paths  # noqa: F401  (sets sys.path)
from core import DATA, V2_DATA
from prompts import canonicalise

SPLITS = ("train_nemotron", "train_haiku", "val_nemotron", "val_haiku", "test_nemotron", "test_haiku")
TEST_SPLITS = ("test_nemotron", "test_haiku")
V1_FILES = {
    "train_nemotron": DATA / "dataset-v1/train.parquet",
    "val_nemotron": DATA / "dataset-v1/val.parquet",
    "test_nemotron": DATA / "dataset-v1/test.parquet",
    "test_haiku": DATA / "haiku-test.jsonl",
}
_NAMES = {
    "load": ("load_split", "load_rows", "read_split"),
    "messages": ("expression_messages", "messages_expression"),
    "target": ("expression_target", "to_expression", "target_expression"),
    "resolve": ("resolve_expression", "resolve", "to_absolute"),
    "schema": ("EXPRESSION_SCHEMA", "expression_schema"),
}


class SplitUnavailable(FileNotFoundError):
    pass


class DataToolsMissing(ImportError):
    pass


def data_tools():
    """The data_tools module, or None when it does not exist (yet)."""
    try:
        return importlib.import_module("data_tools")
    except ModuleNotFoundError as e:
        if e.name == "data_tools":
            return None
        raise


def lookup(role, required=True):
    """The data_tools attribute that plays `role` (see the module docstring)."""
    module = data_tools()
    if module is not None:
        for name in _NAMES[role]:
            if hasattr(module, name):
                return getattr(module, name)
    if required:
        where = "scribe/v2/data_tools.py is missing" if module is None else "scribe/v2/data_tools.py has none of"
        raise DataToolsMissing(f"{where} {', '.join(_NAMES[role])} (needed for: {role})")
    return None


def canonical_json(obj):
    return json.dumps(canonicalise(obj), ensure_ascii=False, separators=(",", ":"))


def writer_label(row):
    text = str(row.get("writer") or row.get("teacher_model") or "").lower()
    for label in ("haiku", "nemotron"):
        if label in text:
            return label
    return text or "unknown"


def normalise(row):
    row = dict(row)
    if not row.get("target_json"):
        truth = row.get("ground_truth") or {"entry_route": row["entry_route"], "events": row["events"]}
        row["target_json"] = canonical_json(truth)
    row["writer"] = writer_label(row)
    row["kind"] = row.get("kind") or "standard"
    row["distractors"] = list(row.get("distractors") or [])
    row["id"] = str(row.get("id") or row["target_json"])
    return row


def _read(path):
    path = pathlib.Path(path)
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq

        return pq.read_table(path).to_pylist()
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


FOLDERS = (V2_DATA / "dataset-v2", V2_DATA, DATA / "dataset-v2")


def _candidates(name):
    """(path, writer to filter on or None), in order of preference."""
    prefix, writer = name.split("_")
    for folder in FOLDERS:
        for suffix in (".parquet", ".jsonl"):
            yield folder / f"{name}{suffix}", None
    for folder in FOLDERS:
        for suffix in (".parquet", ".jsonl"):
            yield folder / f"{prefix}{suffix}", writer
    if name in V1_FILES:
        yield V1_FILES[name], None


def load_split(name):
    """Rows of one split and where they came from: (rows, source)."""
    if name not in SPLITS:
        raise ValueError(f"unknown split {name!r}; expected one of {SPLITS}")
    loader = lookup("load", required=False)
    tried = []
    if loader is not None:
        try:
            rows = loader(name)
            if rows:
                return [normalise(r) for r in rows], f"data_tools.{loader.__name__}({name!r})"
            tried.append(f"data_tools.{loader.__name__} returned no rows")
        except (FileNotFoundError, KeyError, ValueError) as e:
            tried.append(f"data_tools.{loader.__name__}: {type(e).__name__}: {e}")
    for path, writer in _candidates(name):
        shown = str(path.relative_to(_paths.ROOT)) + (f" (writer {writer})" if writer else "")
        if path.exists():
            rows = [normalise(r) for r in _read(path)]
            if writer:
                rows = [r for r in rows if r["writer"] == writer]
            if rows:
                return rows, shown
        tried.append(shown)
    raise SplitUnavailable(f"split {name!r} is not available; tried: {'; '.join(tried)}")


def available(name):
    try:
        load_split(name)
        return True
    except SplitUnavailable:
        return False


def training_rows(train_data):
    """Rows and sources for a training-data setting: 'nemotron' or 'nemotron+haiku'."""
    rows, sources = [], {}
    for writer in train_data.split("+"):
        part, source = load_split(f"train_{writer}")
        rows += part
        sources[f"train_{writer}"] = {"rows": len(part), "source": source}
    return rows, sources


def heldout_rows(prefix):
    """All available splits of one kind ('val' or 'test'): ({split: rows}, {split: source})."""
    out, sources = {}, {}
    for writer in ("nemotron", "haiku"):
        name = f"{prefix}_{writer}"
        try:
            rows, source = load_split(name)
        except SplitUnavailable as e:
            sources[name] = {"rows": 0, "source": None, "unavailable": str(e)}
            continue
        out[name] = rows
        sources[name] = {"rows": len(rows), "source": source}
    return out, sources


def assert_disjoint(train_rows, heldout, label="held-out"):
    """Identical ground truth (the row id) must never sit on both sides."""
    train_ids = {r["id"] for r in train_rows}
    overlap = sorted(train_ids & {r["id"] for r in heldout})
    if overlap:
        raise ValueError(f"{len(overlap)} ids are in both the training rows and the {label} rows, e.g. {overlap[:3]}")
