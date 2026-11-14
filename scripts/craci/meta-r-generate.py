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
    p.add_argument("--cohort", type=int, choices=range(24), required=True)
    p.add_argument("--profile", choices=("normal", "robust", "hardshift24"), default="normal")
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
    if args.profile == "normal":
        if args.cohort > 7:
            raise RuntimeError("Normal source cohort must be 0..7")
        seeds = {
            "train": 110_001 + args.cohort * 10_007,
            "cal": 220_003 + args.cohort * 10_009,
            "shifted": 330_007 + args.cohort * 10_037,
        }
        parts = (
            ("train", "train", TRAIN, "train"),
            ("cal", "validation", CAL, "cal"),
            ("shifted", "shifted_test", SHIFTED, "shifted"),
        )
    elif args.profile == "robust":
        if args.cohort > 11:
            raise RuntimeError("Robust cohort must be 0..11")
        # New scientific hypothesis: mixed source/shift training, a *shifted*
        # calibration set and independent source + shifted heldouts. None of
        # these seeds overlaps the original cohort's earlier datasets.
        seeds = {
            "train_normal": 510_001 + args.cohort * 10_007,
            "train_shifted": 610_003 + args.cohort * 10_009,
            "cal": 710_007 + args.cohort * 10_037,
            "shifted": 810_011 + args.cohort * 10_039,
            "normal_holdout": 910_013 + args.cohort * 10_043,
        }
        parts = (
            ("train", "train", 10_000, "train_normal"),
            ("train", "shifted_test", 10_000, "train_shifted"),
            ("cal", "shifted_test", 5_000, "cal"),
            ("shifted", "shifted_test", 5_000, "shifted"),
            ("normal_holdout", "train", 5_000, "normal_holdout"),
        )
    if args.profile == "hardshift24":
        # New disjoint source/cal/test seeds for 24 independent 35k cohorts.
        # These are different from the eight normal and twelve robust cohorts.
        seeds = {
            "train_normal": 2_110_001 + args.cohort * 101,
            "train_shifted": 2_310_003 + args.cohort * 101,
            "cal": 2_510_007 + args.cohort * 101,
            "shifted": 2_710_011 + args.cohort * 101,
            "normal_holdout": 2_910_013 + args.cohort * 101,
        }
        parts = (
            ("train", "train", 10_000, "train_normal"),
            ("train", "shifted_test", 10_000, "train_shifted"),
            ("cal", "shifted_test", 5_000, "cal"),
            ("shifted", "shifted_test", 5_000, "shifted"),
            ("normal_holdout", "train", 5_000, "normal_holdout"),
        )
    forbidden = {module.TRAIN_SEED, module.VALIDATION_SEED, module.TEST_SEED}
    if (len(set(seeds.values())) != len(seeds) or
            any(s in forbidden for s in seeds.values())):
        raise RuntimeError("Leaking baseline or held-out seed")
    fieldnames = ["split", "cohort", "row_id", "label", "hard_negative",
                  *FEATURES, "baseline_probability"]
    counts = {}
    positives = {}
    hard_negatives = {}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        for split, domain, count, seed_key in parts:
            examples = module.synthetic_examples(seeds[seed_key], count, domain=domain)
            if len(examples) != count:
                raise RuntimeError("Generator underfilled a declared domain")
            start_row = counts.get(split, 0)
            counts[split] = start_row + count
            positives.setdefault(split, 0)
            hard_negatives.setdefault(split, 0)
            for i, ex in enumerate(examples):
                if len(ex.features) != len(FEATURES):
                    raise RuntimeError("Unexpected model feature count")
                if ex.hard_negative and ex.same_object:
                    raise RuntimeError("Hard-negative source contradicts label")
                values = list(ex.features)
                if args.profile == "hardshift24" and split == "shifted":
                    # Predeclared synthetic stress: confusable negatives and
                    # degraded true positives. Label-aware perturbation only in
                    # the untouched test generator, NEVER in model predictors.
                    # Four variants prevent a single arbitrary perturbation
                    # from masquerading as broad domain robustness.
                    variant = args.cohort % 4
                    boost = 0.10 + 0.02 * variant
                    if not ex.same_object:
                        for axis in ((0, 2), (0, 1), (2, 3), (4, 0))[variant]:
                            values[axis] = min(1.0, values[axis] + boost)
                    else:
                        axis = (0, 1, 3, 4)[variant]
                        values[axis] = max(0.0, values[axis] * (0.80 + 0.02 * variant))
                row = dict(split=split, cohort=args.cohort, row_id=start_row + i,
                           label=int(ex.same_object), hard_negative=int(ex.hard_negative),
                           baseline_probability=format(
                               module._model_score(frozen, values), ".14g"))
                row.update({name: format(float(v), ".14g")
                            for name, v in zip(FEATURES, values)})
                writer.writerow(row)
                positives[split] += int(ex.same_object)
                hard_negatives[split] += int(ex.hard_negative)

    report = {
        "schema": "craci.meta-r-source-data.v1",
        "source_sha": META_SOURCE,
        "cohort": args.cohort,
        "source_kind": "synthetic-feature-scores-not-camera-images",
        "profile": args.profile,
        "robust_training": args.profile in ("robust", "hardshift24"),
        "stress_variant": args.cohort % 4 if args.profile == "hardshift24" else None,
        "stress_split_only": "shifted" if args.profile == "hardshift24" else None,
        "calibration_domain": ("shifted_test" if args.profile in ("robust", "hardshift24") else "validation"),
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
