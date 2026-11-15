#!/usr/bin/env python3
"""Train a tiny, synthetic-only object candidate ranker for Chibi Lens.

This model is deliberately NOT an identity verifier. A candidate score is only
one input to a future trusted host. No camera data, real person, remote model,
or network access is involved in this baseline.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FEATURES = ("visual", "text", "shape", "quality", "recency")
TRAIN_SEED = 117
VALIDATION_SEED = 919
TEST_SEED = 1327
TRAIN_COUNT = 3000
VALIDATION_COUNT = 1000
TEST_COUNT = 1500
EPOCHS = 180
BATCH_SIZE = 64
TARGET_VALIDATION_FPR = 0.05


@dataclass(frozen=True)
class Example:
    features: tuple[float, ...]
    same_object: bool
    hard_negative: bool


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))


def synthetic_examples(seed: int, count: int, *, domain: str) -> list[Example]:
    """Generate distinct train/validation/shifted-test observations.

    Labels are sampled before features. Image quality/recency are nuisance
    variables; matching appearance is intentionally imperfect, particularly
    among hard negatives. No source identity or host authorization is modeled.
    """
    if domain not in {"train", "validation", "shifted_test"}:
        raise ValueError("unsupported synthetic domain")
    if not 1 <= count <= 100_000:
        raise ValueError("invalid sample count")
    rng = random.Random(seed)
    shifted = domain == "shifted_test"
    samples: list[Example] = []
    for _ in range(count):
        same = rng.random() < 0.5
        hard = not same and rng.random() < (0.75 if shifted else 0.55)
        quality = rng.uniform(0.25, 1.0)
        recency = rng.uniform(0.0, 1.0)  # Label-independent: no timestamp leakage.
        blur = (1 - quality) * (0.22 if shifted else 0.14)
        if same:
            visual = rng.gauss(0.85 - blur, 0.105 if shifted else 0.08)
            text = rng.gauss(0.79 - blur, 0.17 if shifted else 0.12)
            shape = rng.gauss(0.82 - blur / 2, 0.10)
            if rng.random() < (0.17 if shifted else 0.10):
                text = rng.gauss(0.30, 0.15)  # Partly hidden/OCR-corrupted ID.
        elif hard:
            visual = rng.gauss(0.81 - blur / 2, 0.09)
            text = rng.gauss(0.39 + (0.06 if shifted else 0), 0.17)
            shape = rng.gauss(0.77, 0.10)
            if rng.random() < (0.15 if shifted else 0.08):
                text = rng.gauss(0.79, 0.12)  # Misleading duplicate text.
        else:
            visual = rng.gauss(0.37, 0.14)
            text = rng.gauss(0.32, 0.15)
            shape = rng.gauss(0.47, 0.15)
        samples.append(
            Example(
                features=tuple(map(_bounded, (visual, text, shape, quality, recency))),
                same_object=same,
                hard_negative=hard,
            )
        )
    return samples


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1 / (1 + z)
    z = math.exp(value)
    return z / (1 + z)


def _standardize(values: tuple[float, ...], means: list[float], scales: list[float]) -> list[float]:
    return [(v - mean) / scale for v, mean, scale in zip(values, means, scales)]


def _model_score(model: dict[str, Any], values: tuple[float, ...]) -> float:
    z = _standardize(values, model["means"], model["scales"])
    return _sigmoid(model["bias"] + sum(w * x for w, x in zip(model["weights"], z)))


def validate_observation(observation: dict[str, Any]) -> tuple[float, ...]:
    if not isinstance(observation, dict) or set(observation) != set(FEATURES):
        raise ValueError("observation must have exactly the five named scores")
    values: list[float] = []
    for feature in FEATURES:
        value = observation[feature]
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"invalid score: {feature}")
        values.append(float(value))
    return tuple(values)


def candidate_proposal(model: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    """A trained proposal, NEVER a physical identity/consent/authorization proof."""
    validate_model(model)
    probability = _model_score(model, validate_observation(observation))
    return {
        "kind": "candidate" if probability >= model["candidate_threshold"] else "abstain",
        "candidateProbability": round(probability, 6),
        "identityVerified": False,
        "actionAuthorized": False,
        "qualification": "synthetic-score-model-only",
    }


def validate_model(model: dict[str, Any]) -> None:
    if not isinstance(model, dict) or model.get("schemaVersion") != 1:
        raise ValueError("unsupported model schema")
    if model.get("modelKind") != "synthetic-logistic-candidate-only":
        raise ValueError("unsupported model kind")
    if model.get("featureNames") != list(FEATURES):
        raise ValueError("feature order mismatch")
    for key in ("means", "scales", "weights"):
        values = model.get(key)
        if not isinstance(values, list) or len(values) != len(FEATURES):
            raise ValueError(f"invalid {key}")
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in values):
            raise ValueError(f"nonfinite {key}")
    if any(x <= 0 for x in model["scales"]):
        raise ValueError("invalid scales")
    for key in ("bias", "candidate_threshold"):
        value = model.get(key)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"invalid {key}")
    if not 0.5 <= model["candidate_threshold"] <= 1:
        raise ValueError("invalid threshold")


def train(seed: int = TRAIN_SEED) -> dict[str, Any]:
    # The two assessment streams have fixed seeds. Reject an overlapping
    # training stream rather than silently evaluating examples seen in SGD.
    if type(seed) is not int or seed < 0 or seed > 2**32 - 1:
        raise ValueError("training seed must be a 32-bit nonnegative integer")
    if seed in (VALIDATION_SEED, TEST_SEED):
        raise ValueError("training seed overlaps a reserved evaluation stream")
    examples = synthetic_examples(seed, TRAIN_COUNT, domain="train")
    means = [sum(ex.features[j] for ex in examples) / len(examples) for j in range(len(FEATURES))]
    scales = [
        max(1e-6, math.sqrt(sum((ex.features[j] - means[j]) ** 2 for ex in examples) / len(examples)))
        for j in range(len(FEATURES))
    ]
    features = [_standardize(ex.features, means, scales) for ex in examples]
    weights = [0.0] * len(FEATURES)
    bias = 0.0
    order = list(range(len(examples)))
    rng = random.Random(seed ^ 0x7F7F)
    for epoch in range(EPOCHS):
        rng.shuffle(order)
        step = 0.16 / (1 + epoch * 0.015)
        for offset in range(0, len(order), BATCH_SIZE):
            batch = order[offset : offset + BATCH_SIZE]
            grad_w = [0.0] * len(FEATURES)
            grad_b = 0.0
            for i in batch:
                p = _sigmoid(bias + sum(w * x for w, x in zip(weights, features[i])))
                err = p - int(examples[i].same_object)
                grad_b += err
                for j, value in enumerate(features[i]):
                    grad_w[j] += err * value
            bias -= step * grad_b / len(batch)
            for j in range(len(weights)):
                weights[j] -= step * (grad_w[j] / len(batch) + 0.012 * weights[j])

    model: dict[str, Any] = {
        "schemaVersion": 1,
        "modelKind": "synthetic-logistic-candidate-only",
        "featureNames": list(FEATURES),
        "means": [round(x, 12) for x in means],
        "scales": [round(x, 12) for x in scales],
        "weights": [round(x, 12) for x in weights],
        "bias": round(bias, 12),
        "candidate_threshold": 1.0,
        "training": {
            "domain": "purely-synthetic-score-features",
            "seed": seed,
            "examples": TRAIN_COUNT,
            "epochs": EPOCHS,
            "validationSeed": VALIDATION_SEED,
            "validationCount": VALIDATION_COUNT,
            "targetValidationFalseCandidateRate": TARGET_VALIDATION_FPR,
            "separateShiftedTestSeed": TEST_SEED,
            "separateShiftedTestCount": TEST_COUNT,
        },
    }
    validation = synthetic_examples(VALIDATION_SEED, VALIDATION_COUNT, domain="validation")
    negatives = [ex for ex in validation if not ex.same_object]
    # Never fit on the holdout set. Choose on disjoint validation negatives only.
    for threshold_index in range(50, 1001):
        threshold = threshold_index / 1000
        false_candidates = sum(_model_score(model, ex.features) >= threshold for ex in negatives)
        if false_candidates / len(negatives) <= TARGET_VALIDATION_FPR:
            model["candidate_threshold"] = threshold
            break
    else:
        raise RuntimeError("failed to calibrate threshold")
    validate_model(model)
    model["validation"] = metrics(model, validation)
    return model


def metrics(model: dict[str, Any], examples: list[Example]) -> dict[str, Any]:
    tp = fp = tn = fn = hard_fp = hard_count = 0
    brier = 0.0
    for ex in examples:
        p = _model_score(model, ex.features)
        proposal = p >= model["candidate_threshold"]
        brier += (p - int(ex.same_object)) ** 2
        if ex.same_object:
            if proposal:
                tp += 1
            else:
                fn += 1
        elif proposal:
            fp += 1
        else:
            tn += 1
        if ex.hard_negative:
            hard_count += 1
            hard_fp += int(proposal)
    negatives = fp + tn
    positives = tp + fn
    return {
        "domain": "synthetic-only",
        "total": len(examples),
        "candidateThreshold": model["candidate_threshold"],
        "trueCandidate": tp,
        "falseCandidate": fp,
        "correctAbstainOnNegative": tn,
        "missedPositive": fn,
        "candidatePrecision": round(tp / (tp + fp), 6) if tp + fp else None,
        "positiveRecall": round(tp / positives, 6) if positives else None,
        "falseCandidateRate": round(fp / negatives, 6) if negatives else None,
        "hardNegativeFalseCandidateRate": round(hard_fp / hard_count, 6) if hard_count else None,
        "abstainFraction": round((tn + fn) / len(examples), 6),
        "brierScore": round(brier / len(examples), 6),
    }


def _emit(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    t = subcommands.add_parser("train", help="train a deterministic model and emit JSON checkpoint")
    t.add_argument("--output", required=True)
    e = subcommands.add_parser("evaluate", help="evaluate the frozen checkpoint on shifted heldout data")
    e.add_argument("--model", required=True)
    args = parser.parse_args()
    if args.command == "train":
        model = train()
        Path(args.output).write_text(_emit(model), encoding="utf-8")
        print(_emit({"model": args.output, "validation": model["validation"]}), end="")
    else:
        model = json.loads(Path(args.model).read_text(encoding="utf-8"))
        validate_model(model)
        holdout = synthetic_examples(TEST_SEED, TEST_COUNT, domain="shifted_test")
        print(_emit({"shiftedHoldout": metrics(model, holdout)}), end="")


if __name__ == "__main__":
    main()
