"""Calendar-target isolation and per-horizon export admission (stdlib only).

This protocol is fixed before new runs. It does not qualify historical scores.
"""
import math

PROTOCOL = "target-year-disjoint-v1"
TRAIN_ORIGINS_THROUGH = 2020
TRAIN_LABELS_THROUGH = 2021
VALIDATION_ORIGINS = (2021,)
TEST_ORIGINS = (2023,)
HORIZONS = (1, 2)


def calendar_years(years):
    values = list(years)
    if not values or any(not isinstance(y, int) or isinstance(y, bool) for y in values):
        raise ValueError("Calendar years must be nonempty integers")
    if values != sorted(set(values)):
        raise ValueError("Calendar years must be sorted and unique")
    return values


def target_years(origins, through=None):
    return sorted({t + h for t in origins for h in HORIZONS
                   if through is None or t + h <= through})


def split_manifest(years):
    years = calendar_years([int(y) for y in years])
    train = [y for y in years if y <= TRAIN_ORIGINS_THROUGH]
    result = {
        "protocol": PROTOCOL,
        "trainOrigins": train, "trainLabelsThrough": TRAIN_LABELS_THROUGH,
        "validationOrigins": list(VALIDATION_ORIGINS), "testOrigins": list(TEST_ORIGINS),
        "horizons": list(HORIZONS),
        "targetYears": {
            "train": target_years(train, TRAIN_LABELS_THROUGH),
            "validation": target_years(VALIDATION_ORIGINS),
            "test": target_years(TEST_ORIGINS),
        },
    }
    validate_manifest(result)
    return result


def validate_manifest(split):
    if not isinstance(split, dict) or split.get("protocol") != PROTOCOL:
        raise ValueError("A new disjoint-target evaluation is required; historical artifacts cannot be relabelled")
    for key in ("trainOrigins", "validationOrigins", "testOrigins", "horizons"):
        calendar_years(split.get(key, []))
    if split["horizons"] != list(HORIZONS):
        raise ValueError("Unsupported forecast horizons")
    if split.get("trainLabelsThrough") != TRAIN_LABELS_THROUGH or max(split["trainOrigins"]) > TRAIN_ORIGINS_THROUGH:
        raise ValueError("Training target boundary differs from the fixed protocol")
    expected = {
        "train": target_years(split["trainOrigins"], split["trainLabelsThrough"]),
        "validation": target_years(split["validationOrigins"]),
        "test": target_years(split["testOrigins"]),
    }
    if split.get("targetYears") != expected:
        raise ValueError("Declared target years do not match origins and horizons")
    groups = list(expected)
    for i, a in enumerate(groups):
        if not expected[a]:
            raise ValueError("Empty target-year split")
        for b in groups[i + 1:]:
            if set(expected[a]) & set(expected[b]):
                raise ValueError("Target-year leakage between " + a + " and " + b)
    if not max(expected["train"]) < min(expected["validation"]) or not max(expected["validation"]) < min(expected["test"]):
        raise ValueError("Target years must be chronologically ordered")
    if split["validationOrigins"] != list(VALIDATION_ORIGINS) or split["testOrigins"] != list(TEST_ORIGINS):
        raise ValueError("Evaluation origins differ from the fixed, prespecified protocol")
    return split


def valid_score(score):
    return (isinstance(score, dict) and isinstance(score.get("n"), int)
            and score["n"] > 0 and isinstance(score.get("mae"), (int, float))
            and math.isfinite(score["mae"]))


def horizon_evidence(chosen, validation, test, training_counts):
    """No winner or no observations stays unavailable, including simple baselines."""
    model = "transformer" if isinstance(chosen, str) and chosen.startswith("config-") else chosen
    result = {"chosen": model, "selectedCandidate": chosen, "horizons": {}}
    for h in ("h1", "h2"):
        val = validation.get(chosen, {}).get(h, {}) if chosen else {}
        heldout = test.get(chosen, {}).get(h, {}) if chosen else {}
        train_n = training_counts.get(h)
        reasons = []
        if model not in ("transformer", "persistence", "drift", "ridge"):
            reasons.append("UNKNOWN_METHOD")
        if not chosen:
            reasons.append("NO_VALIDATION_WINNER")
        if not valid_score(val):
            reasons.append("NO_VALIDATION_EVIDENCE")
        if not valid_score(heldout):
            reasons.append("NO_TEST_EVIDENCE")
        if model in ("transformer", "ridge") and (not isinstance(train_n, int) or train_n <= 0):
            reasons.append("NO_EFFECTIVE_TRAINING_EVIDENCE")
        result["horizons"][h] = {
            "status": "WITHHELD" if reasons else "ELIGIBLE", "reasons": reasons,
            "validationN": val.get("n", 0), "testN": heldout.get("n", 0), "trainingN": train_n,
        }
    return result


def valid_quantiles(values):
    return (len(values) == 5 and all(isinstance(x, (int, float)) and math.isfinite(x) for x in values)
            and all(a <= b for a, b in zip(values, values[1:])) and values[0] < values[-1])
