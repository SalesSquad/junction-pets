"""Rebuild the fixtures used by serve/smoke_test.py and serve/tests.

Needs pyarrow, so run it with the scribe venv:
    scribe/.venv/bin/python serve/tests/make_fixtures.py

Reads (never writes) data/scribe/dataset-v1/*.parquet and data/scribe/cache/*.json.
Everything copied is SYNTHETIC text and labels.

Outputs
  serve/fixtures/heldout-v1.jsonl             seeded sample of test-split notes for the smoke test
  serve/tests/fixtures/targets-v1.jsonl.gz    every canonical target with its date expressions
  serve/tests/fixtures/manifest.json          source hashes and counts
"""

import gzip
import hashlib
import json
import pathlib
import random

import pyarrow.parquet as pq

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATASET = ROOT / "data/scribe/dataset-v1"
CACHE = ROOT / "data/scribe/cache"
HELDOUT = ROOT / "serve/fixtures/heldout-v1.jsonl"
TARGETS = ROOT / "serve/tests/fixtures/targets-v1.jsonl.gz"
MANIFEST = ROOT / "serve/tests/fixtures/manifest.json"
SEED = 20261114
HELDOUT_N = 50


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    facts = {}
    for path in sorted(CACHE.glob("*.json")):
        row = json.loads(path.read_text())
        if "note_text" in row:
            facts.setdefault((row["id"], row["note_text"]), row["facts"])
    rows = {}
    for split in ["train", "val", "test", "rejected"]:
        rows[split] = pq.read_table(DATASET / f"{split}.parquet").to_pylist()
    matched = 0
    targets = []
    for split, items in rows.items():
        for r in items:
            f = facts.get((r["id"], r["note_text"]))
            matched += f is not None
            targets.append(
                {
                    "id": r["id"],
                    "split": split,
                    "note_date": r["note_date"],
                    "target_json": r["target_json"],
                    "facts": None
                    if f is None
                    else [
                        {k: x[k] for k in ["type", "date", "precision", "expression", "form"]}
                        for x in f
                    ],
                }
            )
    TARGETS.parent.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(TARGETS, "wb", mtime=0) as handle:
        for t in targets:
            handle.write((json.dumps(t, ensure_ascii=False, sort_keys=True) + "\n").encode())
    test = sorted(rows["test"], key=lambda r: r["id"])
    chosen = sorted(random.Random(SEED).sample(range(len(test)), HELDOUT_N))
    HELDOUT.parent.mkdir(parents=True, exist_ok=True)
    with HELDOUT.open("w", encoding="utf-8") as handle:
        for i in chosen:
            r = test[i]
            f = facts.get((r["id"], r["note_text"]))
            handle.write(
                json.dumps(
                    {
                        "id": r["id"],
                        "split": "test",
                        "note_date": r["note_date"],
                        "note_text": r["note_text"],
                        "target_json": r["target_json"],
                        "date_forms": r["date_forms"],
                        "facts": [
                            {k: x[k] for k in ["type", "date", "precision", "expression", "form"]}
                            for x in f
                        ],
                        "distractors": r["distractors"],
                        "synthetic": True,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    manifest = {
        "synthetic": True,
        "seed": SEED,
        "sources": {
            f"data/scribe/dataset-v1/{s}.parquet": sha256(DATASET / f"{s}.parquet")
            for s in rows
        },
        "counts": {s: len(v) for s, v in rows.items()},
        "targets_total": len(targets),
        "targets_with_expressions": matched,
        "heldout_notes": HELDOUT_N,
        "heldout_from": "test split, sorted by id, random.Random(seed).sample",
        "outputs": {
            "serve/fixtures/heldout-v1.jsonl": sha256(HELDOUT),
            "serve/tests/fixtures/targets-v1.jsonl.gz": sha256(TARGETS),
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
