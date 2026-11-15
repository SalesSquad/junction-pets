import collections
import datetime
import math
import json


def wilson(k, n):
    if not n:
        return {"value": None, "n": 0, "ci95": [None, None]}
    z = 1.959963984540054
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return {"value": p, "n": n, "ci95": [max(0, c - h), min(1, c + h)]}


def mcnemar(b, c):
    n = b + c
    if not n:
        return 1.0
    # Exact two-sided binomial; log-space prevents overflow for large test sets.
    return min(
        1.0,
        2
        * sum(
            math.exp(
                math.lgamma(n + 1)
                - math.lgamma(k + 1)
                - math.lgamma(n - k + 1)
                - n * math.log(2)
            )
            for k in range(min(b, c) + 1)
        ),
    )


def summary(rows, preds):
    tp = fp = fn = tt = pt = gt = exact = route = bad = nd = 0
    errors = []
    outcomes = []
    for row, p in zip(rows, preds):
        g = json.loads(row["target_json"])
        p = p or {"events": [], "entry_route": None}
        a = collections.Counter((e["type"], e["date"]) for e in g["events"])
        b = collections.Counter((e["type"], e["date"]) for e in p["events"])
        tp += sum((a & b).values())
        fp += sum((b - a).values())
        fn += sum((a - b).values())
        ga = collections.Counter(e["type"] for e in g["events"])
        pa = collections.Counter(e["type"] for e in p["events"])
        tt += sum((ga & pa).values())
        gt += sum(ga.values())
        pt += sum(pa.values())
        ok = p == g
        outcomes.append(ok)
        exact += ok
        route += p["entry_route"] == g["entry_route"]
        # Pair same-type events by sorted date for signed date errors; unmatched events excluded.
        # Types are visited in sorted order so that the list order does not depend on string hashing.
        for typ in sorted(ga.keys() & pa.keys()):
            gs = sorted(e["date"] for e in g["events"] if e["type"] == typ)
            ps = sorted(e["date"] for e in p["events"] if e["type"] == typ)
            errors.extend(
                (datetime.date.fromisoformat(v) - datetime.date.fromisoformat(u)).days
                for u, v in zip(gs, ps)
            )
        for d in row.get("distractors", []):
            nd += 1
            bad += any(e["date"] == d["date"] for e in p["events"])
    precision = wilson(tp, tp + fp)
    recall = wilson(tp, tp + fn)
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
        "type_only_f1": 2 * tt / (pt + gt) if pt + gt else 0,
        "note_exact_match": wilson(exact, len(rows)),
        "route_accuracy": wilson(route, len(rows)),
        "distractor_extraction": wilson(bad, nd),
        "date_errors_days": errors,
        "date_error_histogram": dict(sorted(collections.Counter(errors).items())),
        "date_error_distribution": [
            {"days": d, "count": n, "share": wilson(n, len(errors))}
            for d, n in sorted(collections.Counter(errors).items())
        ],
        "outcomes": outcomes,
        "f1_interval_note": "F1 is not a binomial proportion; Wilson intervals apply to precision, recall and note/distractor rates.",
    }


IN_SAMPLE_LIMIT = (
    "In sample: each cut-off is chosen on the same notes it is scored on, so the coverage is optimistic. "
    "Not an error guarantee and not a share of notes that may skip human review; for that, fix the cut-off "
    "on separate notes and report the error on the rest with an exact upper bound."
)


def risk_coverage(scores, outcomes):
    """In-sample risk-coverage curve: notes ranked by score, and for each error limit the largest share
    of top-ranked notes whose error rate ON THESE SAME NOTES is at or below the limit. Selecting and
    scoring on one set makes the shares optimistic (see IN_SAMPLE_LIMIT)."""
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    curve = []
    err = 0
    best = {"0.01": 0.0, "0.05": 0.0}
    # Equal confidence scores are admitted together.
    for pos, i in enumerate(order, 1):
        err += not outcomes[i]
        if pos < len(order) and scores[order[pos]] == scores[i]:
            continue
        risk = err / pos
        cov = pos / len(order)
        curve.append(
            {
                "coverage": cov,
                "coverage_interval": wilson(pos, len(order))["ci95"],
                "risk": risk,
                "error_interval": wilson(err, pos)["ci95"],
                "threshold": scores[i],
            }
        )
        for t in best:
            if risk <= float(t):
                best[t] = cov
    return {
        "curve": curve,
        "largest_empirical_coverage": best,
        "limit": IN_SAMPLE_LIMIT,
    }
