#!/usr/bin/env python3
"""Generate disjoint score-feature datasets from the pinned Chibi Lens model.
Synthetic observations only; neither camera identity nor user authorization.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

META_SOURCE = "634f1e0e6cb2de46bcf0a783532d46c23f513d11"
TRAIN = 20000
CAL = 5000
SHIFTED = 5000
FEATURES = ("visual", "text", "shape", "quality", "recency")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument("--cohort", type=int, choices=range(8), required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    model_dir = args.source_root / "services/meta-spatial/ml"
    path = model_dir / "candidate_model.py"
    checkpoint = model_dir / "trained-candidate-v1.json"
    if not path.is_file() or not checkpoint.is_file():
        raise RuntimeError("Pinned Meta candidate source or baseline checkpoint absent")
    spec = importlib.util.spec_from_file_location("craci_meta_candidate_pinned", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load exact pinned Meta module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if module.FEATURES != FEATURES:
        raise RuntimeError("Feature schema drift")
    frozen = json.loads(checkpoint.read_text(encoding="utf8"))
    module.validate_model(frozen)

    # Every cohort has distinct train/cal/shifted worlds. Original baseline's
    # TRAIN/VALIDATION/TEST seeds are never reused, and never used as labels.
    seeds = {
        "train": 110_001 + args.cohort * 10_007,
        "cal": 220_003 + args.cohort * 10_009,
        "shifted": 330_007 + args.cohort * 10_037,
    }
    forbidden = {module.TRAIN_SEED, module.VALIDATION_SEED, module.TEST_SEED}
    if len(set(seeds.values())) != 3 or any(s in forbidden for s in seeds.values()):
        raise RuntimeError("Leaking baseline or held-out seed")
    parts = (
        ("train", "train", TRAIN),
        ("cal", "validation", CAL),
        ("shifted", "shifted_test", SHIFTED),
    )
    fieldnames = ["split", "cohort", "row_id", "label", "hard_negative",
                  *FEATURES, "baseline_probability"]
    counts = {}
    positives = {}
    hard_negatives = {}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        for split, domain, count in parts:
            examples = module.synthetic_examples(seeds[split], count, domain=domain)
            if len(examples) != count:
                raise RuntimeError("Generator underfilled a declared domain")
            counts[split] = count
            positives[split] = 0
            hard_negatives[split] = 0
            for i, ex in enumerate(examples):
                if len(ex.features) != len(FEATURES):
                    raise RuntimeError("Unexpected model feature count")
                if ex.hard_negative and ex.same_object:
                    raise RuntimeError("Hard-negative source contradicts label")
                row = dict(split=split, cohort=args.cohort, row_id=i,
                           label=int(ex.same_object), hard_negative=int(ex.hard_negative),
                           baseline_probability=format(
                               module._model_score(frozen, ex.features), ".14g"))
                row.update({name: format(float(v), ".14g")
                            for name, v in zip(FEATURES, ex.features)})
                writer.writerow(row)
                positives[split] += int(ex.same_object)
                hard_negatives[split] += int(ex.hard_negative)

    report = {
        "schema": "craci.meta-r-source-data.v1",
        "source_sha": META_SOURCE,
        "cohort": args.cohort,
        "source_kind": "synthetic-feature-scores-not-camera-images",
        "seed_sets": seeds,
        "original_baseline_seeds_disjoint": True,
        "counts": counts,
        "positives": positives,
        "hard_negatives": hard_negatives,
        "baseline_threshold": frozen["candidate_threshold"],
        "feature_names": list(FEATURES),
        "identityVerified": False,
        "actionAuthorized": False,
        "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "generator_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "dataset_sha256": hashlib.sha256(args.out.read_bytes()).hexdigest(),
        "real_visual_benchmark": False,
    }
    (args.out.parent / "dataset-receipt.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(json.dumps({
        "cohort": args.cohort, "cases": sum(counts.values()),
        "train": counts["train"], "cal": counts["cal"],
        "shifted": counts["shifted"], "datasetSha256": report["dataset_sha256"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
