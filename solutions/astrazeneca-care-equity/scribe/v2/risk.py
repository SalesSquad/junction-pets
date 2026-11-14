"""Risk control for auto-accepting scribe outputs. Standard library only, CPU only.

Decision rule: auto-accept a note when its confidence (mean token log-probability of the generated
answer) is at least a threshold; everything else goes to a person.
Target: P(note is wrong | note is auto-accepted) <= alpha, with probability >= 1 - delta over the draw
of the calibration notes. "Wrong" is fixed before looking at any data: the canonical JSON differs from
the label, or the output could not be parsed (unparsable outputs are never auto-accepted).

Method: Learn-then-Test (Angelopoulos, Bates, Candes, Jordan, Lei, arXiv:2110.01052), the selective
classification case of its Section 3.2. For a threshold t let n_t be the number of calibration notes
with confidence >= t and k_t the number of those that are wrong. Under H_t: risk(t) > alpha the count
k_t given n_t is binomial with success probability above alpha, so

    p_t = P(Binomial(n_t, alpha) <= k_t)

is a valid p-value (the exact binomial tail). Any procedure that controls the family-wise error rate
at delta over the thresholds then returns only thresholds with risk <= alpha, with probability >= 1 - delta.
Two such procedures are implemented on a threshold grid that is fixed in this file, independent of data:

- "fixed_sequence" (the procedure of the research step): walk the grid from the strictest threshold
  down, start at the first threshold that accepts at least n_min = ceil(log(delta) / log(1 - alpha))
  notes (fewer can never be certified), keep going while p_t <= delta, stop at the first failure.
  The start depends on calibration confidences but not on labels. The guarantee is exact when the
  start is the first threshold on which a false certification is possible; a start that lands inside
  a run of thresholds whose risk exceeds alpha is the only place where it can be loose, and the
  simulation in this file measures that case (scenario "overconfident_top").
- "bonferroni": test every grid threshold at delta / |grid| and take the lowest accepted one. It needs
  no assumption beyond exchangeability and is less powerful; it is reported next to the first.

Plain conformal risk control is not used: it bounds the expected joint rate P(accepted and wrong),
not the error among accepted notes, and not with probability 1 - delta.

Limits: the guarantee needs calibration and deployment notes to be exchangeable. Here both are
synthetic notes with imperfect labels, so a threshold bounds label-relative error on such notes only.
It is not a clinical safety claim. Calibrating on the split that was also used to select the model
breaks exchangeability mildly (the model was chosen to look good on it); the test check exposes that.
"""

from __future__ import annotations

import bisect
import math
import random

ACCEPT_ALL = -1e9  # threshold that accepts every parsable output
DELTA = 0.05
ALPHAS = (0.01, 0.05)


def binom_cdf(k, n, p):
    """P(Binomial(n, p) <= k), exact, summed in log space."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if p <= 0:
        return 1.0
    if p >= 1:
        return 0.0
    lp, lq = math.log(p), math.log1p(-p)
    terms = [
        math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq
        for i in range(k + 1)
    ]
    top = max(terms)
    return min(1.0, math.exp(top) * sum(math.exp(t - top) for t in terms))


def min_accepted(alpha, delta):
    """Smallest number of accepted notes that can be certified at all (zero errors among them)."""
    return math.ceil(math.log(delta) / math.log1p(-alpha))


def clopper_pearson_upper(k, n, delta=DELTA):
    """One-sided upper confidence bound (level 1 - delta) for a binomial proportion with k of n."""
    if n == 0:
        return 1.0
    if k >= n:
        return 1.0
    lo, hi = k / n, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if binom_cdf(k, n, mid) > delta:
            lo = mid
        else:
            hi = mid
    return hi


def default_grid(step=0.1, top=6.0):
    """Thresholds on mean token log-probability, strictest first, fixed independently of any data.

    The grid is uniform in "nines" of the geometric-mean token probability g = exp(confidence):
    g = 1 - 10^(-u) for u = top, top - step, ..., step; the last entry accepts every parsable output.
    """
    count = int(round(top / step))
    grid = [math.log1p(-(10.0 ** (-(step * i)))) for i in range(count, 0, -1)]
    return grid + [ACCEPT_ALL]


def bonferroni_grid():
    """Coarser grid (half a nine per step) for the Bonferroni variant: fewer tests, less correction."""
    return default_grid(step=0.5, top=6.0)


class _Counts:
    """n_t and k_t for any threshold, from the calibration confidences and errors."""

    def __init__(self, scores, errors):
        if len(scores) != len(errors):
            raise ValueError("scores and errors differ in length")
        pairs = sorted(((s, bool(e)) for s, e in zip(scores, errors) if s is not None), key=lambda t: -t[0])
        self.total = len(scores)
        self.valid = len(pairs)
        self._neg = [-s for s, _ in pairs]
        self._prefix = [0]
        for _, e in pairs:
            self._prefix.append(self._prefix[-1] + e)

    def at(self, threshold):
        n = bisect.bisect_right(self._neg, -threshold)
        return n, self._prefix[n]


def ltt_threshold(scores, errors, alpha, delta=DELTA, grid=None, method="fixed_sequence"):
    """Choose the auto-accept threshold on a calibration set.

    scores: confidence per note (higher = more confident); None marks an unparsable output.
    errors: True where the note-level output is wrong.
    Returns a dict; "threshold" is None when nothing can be certified (send everything to review).
    """
    if not 0 < alpha < 1 or not 0 < delta < 1:
        raise ValueError("alpha and delta must be in (0, 1)")
    if method not in ("fixed_sequence", "bonferroni"):
        raise ValueError(f"unknown method {method!r}")
    if grid is None:
        grid = default_grid() if method == "fixed_sequence" else bonferroni_grid()
    grid = sorted(grid, reverse=True)
    counts = _Counts(scores, errors)
    level = delta if method == "fixed_sequence" else delta / len(grid)
    n_min = min_accepted(alpha, level)
    out = {
        "method": method,
        "alpha": alpha,
        "delta": delta,
        "test_level": level,
        "grid_size": len(grid),
        "n_calibration": counts.total,
        "n_parsable": counts.valid,
        "n_min_accepted": n_min,
        "threshold": None,
        "threshold_geomean_token_probability": None,
        "n_accepted": 0,
        "errors_accepted": 0,
        "coverage": 0.0,
        "empirical_risk": None,
        "p_value": None,
        "risk_upper_bound": None,
        "thresholds_tested": 0,
        "reason": "",
    }
    if counts.valid < n_min:
        out["reason"] = (
            f"calibration set too small: {counts.valid} parsable notes, at least {n_min} accepted notes "
            f"without error are needed to certify alpha={alpha} at level {level:.6g}"
        )
        return out

    chosen = None
    tested = 0
    if method == "fixed_sequence":
        started = False
        for t in grid:
            n, k = counts.at(t)
            if not started:
                if n < n_min:
                    continue  # cannot be certified with this few notes whatever their labels
                started = True
            tested += 1
            p = binom_cdf(k, n, alpha)
            if p <= level:
                chosen = (t, n, k, p)
            else:
                break
    else:
        for t in grid:
            n, k = counts.at(t)
            tested += 1
            if n < n_min:
                continue
            p = binom_cdf(k, n, alpha)
            if p <= level:
                chosen = (t, n, k, p)  # the grid is descending, so the last hit has the highest coverage
    out["thresholds_tested"] = tested
    if chosen is None:
        out["reason"] = "no threshold passed the test: the observed error among confident notes is too high"
        return out
    t, n, k, p = chosen
    out.update(
        threshold=t,
        threshold_geomean_token_probability=math.exp(t) if t > ACCEPT_ALL else 0.0,
        n_accepted=n,
        errors_accepted=k,
        coverage=n / counts.total if counts.total else 0.0,
        empirical_risk=k / n,
        p_value=p,
        risk_upper_bound=clopper_pearson_upper(k, n, level),
        reason="certified",
    )
    return out


def selective_stats(scores, errors, threshold, delta=DELTA):
    """Coverage and error among accepted notes at a given threshold (used for the check on test)."""
    total = len(scores)
    if threshold is None:
        return {
            "n": total,
            "accepted": 0,
            "errors_accepted": 0,
            "coverage": 0.0,
            "risk": None,
            "risk_upper_bound": None,
        }
    accepted = [bool(e) for s, e in zip(scores, errors) if s is not None and s >= threshold]
    n, k = len(accepted), sum(accepted)
    return {
        "n": total,
        "accepted": n,
        "errors_accepted": k,
        "coverage": n / total if total else 0.0,
        "risk": k / n if n else None,
        "risk_upper_bound": clopper_pearson_upper(k, n, delta) if n else None,
    }


def calibrate_and_check(cal_scores, cal_errors, checks=None, alphas=ALPHAS, delta=DELTA):
    """Thresholds from a calibration split, then realised coverage and error on other splits.

    checks: {name: (scores, errors)} for splits that played no part in choosing the threshold.
    """
    report = {
        "delta": delta,
        "confidence": "mean token log-probability of the generated answer",
        "error_definition": "canonical JSON differs from the label, or the output is unparsable",
        "calibration_n": len(cal_scores),
        "calibration_error_rate": (sum(bool(e) for e in cal_errors) / len(cal_errors)) if cal_errors else None,
        "results": [],
    }
    for alpha in alphas:
        for method in ("fixed_sequence", "bonferroni"):
            fit = ltt_threshold(cal_scores, cal_errors, alpha, delta, method=method)
            entry = {"alpha": alpha, "method": method, "calibration": fit, "checks": {}}
            for name, (scores, errors) in (checks or {}).items():
                stats = selective_stats(scores, errors, fit["threshold"], delta)
                stats["risk_at_most_alpha"] = None if stats["risk"] is None else stats["risk"] <= alpha
                entry["checks"][name] = stats
            report["results"].append(entry)
    return report


# ---- simulation: does the guarantee hold on synthetic exchangeable data? -------------------------
#
# A note's confidence is drawn as "nines" x ~ Uniform(0, 4), i.e. log-probability log(1 - 10^-x).
# Each scenario gives the probability that a note with x nines is wrong.

SCENARIOS = {
    # Confidence is informative: error falls from 50% at x=0 to 0.5% at x=4.
    "informative": lambda x: min(1.0, 0.5 * 10 ** (-x / 2)),
    # Confidence carries no information and the error rate (8%) is above both alphas:
    # every certification is a violation.
    "uninformative": lambda x: 0.08,
    # Overconfident errors: the top 0.6% of notes are always wrong, the middle is clean, the bottom is poor.
    "overconfident_top": lambda x: 1.0 if x > 3.976 else (0.0 if x > 1.0 else 0.4),
}
_X_MAX = 4.0


def _score(x):
    return math.log1p(-(10.0 ** (-max(x, 1e-12))))


def true_risk(error_probability, threshold, points=20000):
    """Population error among notes with confidence >= threshold (midpoint rule over x)."""
    if threshold <= ACCEPT_ALL:
        lo = 0.0
    else:
        g = math.exp(threshold)
        lo = -math.log10(1.0 - g) if g < 1 else math.inf
    if lo >= _X_MAX:
        return None  # no note can be accepted
    width = (_X_MAX - lo) / points
    return sum(error_probability(lo + (i + 0.5) * width) for i in range(points)) / points


def simulate(scenario, alpha, delta=DELTA, n=500, trials=1000, seed=0, methods=("fixed_sequence", "bonferroni")):
    """Fraction of calibration draws after which the chosen threshold has true risk above alpha."""
    q = SCENARIOS[scenario]
    rng = random.Random(seed)
    risk_cache = {}
    stats = {m: {"violations": 0, "no_threshold": 0, "coverage_sum": 0.0, "found": 0} for m in methods}
    for _ in range(trials):
        xs = [_X_MAX * rng.random() for _ in range(n)]
        scores = [_score(x) for x in xs]
        errors = [rng.random() < q(x) for x in xs]
        for m in methods:
            fit = ltt_threshold(scores, errors, alpha, delta, method=m)
            t = fit["threshold"]
            if t is None:
                stats[m]["no_threshold"] += 1
                continue
            if t not in risk_cache:
                risk_cache[t] = true_risk(q, t)
            r = risk_cache[t]
            stats[m]["found"] += 1
            stats[m]["coverage_sum"] += fit["coverage"]
            if r is not None and r > alpha + 1e-12:
                stats[m]["violations"] += 1
    out = []
    for m in methods:
        s = stats[m]
        out.append(
            {
                "scenario": scenario,
                "method": m,
                "alpha": alpha,
                "delta": delta,
                "n_calibration": n,
                "trials": trials,
                "seed": seed,
                "violations": s["violations"],
                "violation_rate": s["violations"] / trials,
                "no_threshold": s["no_threshold"],
                "mean_coverage_when_found": s["coverage_sum"] / s["found"] if s["found"] else None,
            }
        )
    return out


def monte_carlo_bound(delta, trials, z=3.0):
    """Largest violation rate still compatible with a true rate of delta (z standard errors)."""
    return delta + z * math.sqrt(delta * (1 - delta) / trials)


def main():
    import argparse
    import json

    p = argparse.ArgumentParser(description="Simulation check of the risk-control guarantee (synthetic data only).")
    p.add_argument("--trials", type=int, default=2000)
    p.add_argument("--n", type=int, default=500)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()
    rows = []
    for scenario in SCENARIOS:
        for alpha in ALPHAS:
            rows += simulate(scenario, alpha, n=args.n, trials=args.trials, seed=args.seed)
    print(json.dumps({"bound": monte_carlo_bound(DELTA, args.trials), "results": rows}, indent=1))


if __name__ == "__main__":
    main()
