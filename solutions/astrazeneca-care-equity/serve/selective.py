#!/usr/bin/env python3
"""Choose the auto-accept threshold with a stated risk guarantee. Standard library only.

Rule being calibrated: auto-accept a note when its confidence score s >= lambda.
Risk: R(lambda) = P(extraction wrong | s >= lambda), the error rate among the
notes that skip human review. Target: R(lambda_hat) <= alpha with probability
at least 1 - delta over the draw of the calibration notes.

Method: Learn-then-Test (Angelopoulos, Bates, Candes, Jordan, Lei,
arXiv:2110.01052, section 3.2 on selective classification). For each threshold
on a grid fixed before looking at the labels, test H: R(lambda) > alpha with the
exact binomial tail p = P(Bin(n, alpha) <= k), where n notes pass the threshold
and k of them are wrong. Thresholds are tested from the strictest downwards and
testing stops at the first one that fails (fixed-sequence testing), which keeps
the family-wise error at delta without a Bonferroni penalty.

Stricter than a common shortcut: a threshold that no calibration note passes
has p = 1 and stops the sequence; it is not skipped. So the grid has to start
where enough notes pass: at least ceil(log(delta) / log(1 - alpha)) accepted
notes with zero errors are needed to certify anything (45 for alpha 0.05,
delta 0.1). Choose the grid start from the scores of OTHER notes (for example
the validation split), not from the calibration notes: picking the start after
looking at the calibration scores is outside what the theorem covers. Never
re-run with a different grid after seeing the result.

What the guarantee does not cover: calibration and deployment notes must be
exchangeable. Synthetic notes with machine-written labels are not exchangeable
with real Finnish clinical notes, and 'wrong' here means different from a label
that itself can be wrong. This bounds label-relative risk on similar synthetic
notes. It is not a clinical safety bound.

Usage: python serve/selective.py results.jsonl --alpha 0.05 --delta 0.1 --out threshold.json
where each line of results.jsonl has "score" (number in [0,1]) and "correct" (true/false).
"""

import argparse
import json
import math
import sys


def binom_cdf(k, n, p):
    """P(Bin(n, p) <= k), summed exactly in log space."""
    if n < 0 or not 0.0 <= p <= 1.0:
        raise ValueError("need n >= 0 and 0 <= p <= 1")
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if p == 0.0:
        return 1.0
    if p == 1.0:
        return 0.0
    log_p, log_q = math.log(p), math.log1p(-p)
    terms = [
        math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * log_p + (n - i) * log_q
        for i in range(k + 1)
    ]
    top = max(terms)
    return min(1.0, math.exp(top) * sum(math.exp(t - top) for t in terms))


def clopper_pearson_upper(k, n, delta):
    """One-sided upper confidence bound for a binomial proportion at level 1 - delta."""
    if n == 0 or k >= n:
        return 1.0
    lo, hi = k / n, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if binom_cdf(k, n, mid) > delta:
            lo = mid
        else:
            hi = mid
    return hi


def min_accepted_for_zero_errors(alpha, delta):
    """Fewest accepted notes, all correct, for which the test can pass."""
    return math.ceil(math.log(delta) / math.log1p(-alpha))


def default_grid(start=0.995, step=0.005, stop=0.005):
    """start, start - step, ..., down to stop: fixed, strictest first."""
    if not 0 < step < 1 or not 0 <= stop <= start <= 1:
        raise ValueError("need 0 < step < 1 and 0 <= stop <= start <= 1")
    count = int(round((start - stop) / step)) + 1
    return [round(start - i * step, 10) for i in range(count)]


def ltt_threshold(scores, errors, alpha, delta, grid=None, method="fixed_sequence"):
    """Return the certified threshold (or None) and the evidence behind it.

    scores: confidence per calibration note, higher means more confident.
    errors: 1 or True where that note's extraction was wrong.
    grid:   thresholds in strictly descending order, chosen without the labels.
    method: 'fixed_sequence' (default) or 'bonferroni'.
    """
    if len(scores) != len(errors):
        raise ValueError("scores and errors differ in length")
    if not 0 < alpha < 1 or not 0 < delta < 1:
        raise ValueError("alpha and delta must be strictly between 0 and 1")
    grid = default_grid() if grid is None else list(grid)
    if any(b >= a for a, b in zip(grid, grid[1:])):
        raise ValueError("grid must be strictly descending")
    if method not in ("fixed_sequence", "bonferroni"):
        raise ValueError("unknown method")
    level = delta if method == "fixed_sequence" else delta / len(grid)
    trace = []
    chosen = None
    for lam in grid:
        passed = [bool(e) for s, e in zip(scores, errors) if s >= lam]
        n, k = len(passed), sum(passed)
        p = binom_cdf(k, n, alpha) if n else 1.0
        ok = p <= level
        trace.append({"threshold": lam, "n_accepted": n, "errors_accepted": k, "p_value": p, "certified": ok})
        if ok:
            chosen = trace[-1]
        elif method == "fixed_sequence":
            break
    result = {
        "method": "LTT " + method.replace("_", "-") + ", exact binomial tail",
        "alpha": alpha,
        "delta": delta,
        "n_calibration": len(scores),
        "grid_points": len(grid),
        "grid_first": grid[0] if grid else None,
        "grid_last": grid[-1] if grid else None,
        "thresholds_tested": len(trace),
        "threshold": None,
        "min_accepted_for_zero_errors": min_accepted_for_zero_errors(alpha, delta),
    }
    if chosen is None:
        result["note"] = "no threshold certified: send every note to human review"
        return result
    result.update(
        {
            "threshold": chosen["threshold"],
            "n_accepted": chosen["n_accepted"],
            "errors_accepted": chosen["errors_accepted"],
            "p_value": chosen["p_value"],
            "auto_accept_fraction": chosen["n_accepted"] / len(scores),
            "empirical_risk_accepted": chosen["errors_accepted"] / chosen["n_accepted"],
            "clopper_pearson_upper": clopper_pearson_upper(
                chosen["errors_accepted"], chosen["n_accepted"], delta
            ),
        }
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("results", help="JSONL with score and correct per calibration note")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--delta", type=float, default=0.1)
    parser.add_argument("--method", choices=["fixed_sequence", "bonferroni"], default="fixed_sequence")
    parser.add_argument("--grid-start", type=float, default=0.995,
                        help="strictest threshold tested; choose it from notes outside the calibration set")
    parser.add_argument("--grid-step", type=float, default=0.005)
    parser.add_argument("--confidence-kind", required=True)
    parser.add_argument("--format", dest="fmt", required=True)
    parser.add_argument("--guided", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--calibration-set", required=True, help="what the notes are, for the record")
    parser.add_argument("--out", help="write the threshold file here")
    args = parser.parse_args(argv)
    scores, errors = [], []
    with open(args.results, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if row.get("score") is None or not isinstance(row.get("correct"), bool):
                    raise SystemExit("every line needs a numeric score and a boolean correct")
                scores.append(float(row["score"]))
                errors.append(not row["correct"])
    result = ltt_threshold(scores, errors, args.alpha, args.delta, default_grid(args.grid_start, args.grid_step), args.method)
    result.update(
        {
            "schemaVersion": "pathway-scribe-threshold-v1",
            "confidence_kind": args.confidence_kind,
            "format": args.fmt,
            "guided": args.guided,
            "model": args.model,
            "calibration_set": args.calibration_set,
            "limits": "Label-relative risk on notes exchangeable with the calibration set. Synthetic data. Not a clinical safety bound.",
        }
    )
    text = json.dumps(result, indent=2)
    print(text)
    if args.out and result["threshold"] is not None:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    elif args.out:
        print("no threshold certified; nothing written", file=sys.stderr)
    return 0 if result["threshold"] is not None else 3


if __name__ == "__main__":
    sys.exit(main())
