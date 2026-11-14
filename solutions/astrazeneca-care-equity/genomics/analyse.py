"""Benchmark analysis of Evo 2 zero-shot scores on the BRCA1 saturation genome
editing table (Findlay et al. 2018). numpy only; every random step is seeded.

Uncertainty: variants at one position share a reference window and usually a class, so every
bootstrap resamples positions, not variants. Likelihood-ratio bounds per score bin: where a bin holds
at least 5 variants of each class, the more cautious of an exact (Clopper-Pearson) bound and the
position bootstrap; in sparser bins, the exact bound on effective counts (counts divided by the
worst-case design effect of position clustering). The headline evidence strength is the one for
missense variants alone; the all-consequence level is kept for reference.

Score used everywhere: s = -(delta log-likelihood), so a higher s means the model
finds the alternate sequence less likely than the reference.

The assay's functional classes (LOF / INT / FUNC in HAP1 cells) stand in for
pathogenicity. They are a laboratory proxy, not a clinical classification.
Research use only; not for clinical decisions.
"""
import argparse, csv, datetime, functools, json, math, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SEED = 20261114
N_BOOT = 2000
STATEMENT = "Research use only; not for clinical decisions."

# Verified constants. Tavtigian et al. 2018 (Genet Med 20:1054, doi 10.1038/gim.2017.210):
# prior 0.10, odds of pathogenicity for "very strong" 350, each lower strength the square root of the one above.
# Pejaver et al. 2022 (Am J Hum Genet 109:2163, doi 10.1016/j.ajhg.2022.10.013): prior 0.0441, c = 1124.
CALIBRATIONS = {
    "tavtigian2018": {"prior": 0.10, "very_strong_lr": 350.0,
                      "source": "https://pmc.ncbi.nlm.nih.gov/articles/PMC6336098/"},
    "pejaver2022": {"prior": 0.0441, "very_strong_lr": 1124.0,
                    "source": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9748256/"},
}
STRENGTH_EXPONENT = {"supporting": 1 / 8, "moderate": 1 / 4, "strong": 1 / 2, "very_strong": 1.0}
STRENGTH_ORDER = ["supporting", "moderate", "strong", "very_strong"]


# ---------------------------------------------------------------- basic statistics
def average_ranks(x):
    """Ranks starting at 1, ties get the average rank."""
    x = np.asarray(x, dtype=float)
    order = np.argsort(x, kind="mergesort")
    xs = x[order]
    start = np.concatenate(([True], xs[1:] != xs[:-1]))
    group = np.cumsum(start) - 1
    first = np.flatnonzero(start)
    last = np.concatenate((first[1:], [len(xs)])) - 1
    mean_rank = (first + last) / 2.0 + 1.0
    ranks = np.empty(len(x), dtype=float)
    ranks[order] = mean_rank[group]
    return ranks


def auroc(pos, neg):
    """Probability that a positive scores higher than a negative (ties count one half)."""
    pos, neg = np.asarray(pos, dtype=float), np.asarray(neg, dtype=float)
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    r = average_ranks(np.concatenate((pos, neg)))
    u = r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2.0
    return float(u / (len(pos) * len(neg)))


def average_precision(pos, neg):
    """Area under the precision-recall step curve: sum over thresholds of (recall step) x precision.
    Tied scores are treated as one threshold."""
    pos, neg = np.asarray(pos, dtype=float), np.asarray(neg, dtype=float)
    if len(pos) == 0:
        return float("nan")
    s = np.concatenate((pos, neg))
    y = np.concatenate((np.ones(len(pos)), np.zeros(len(neg))))
    order = np.argsort(-s, kind="mergesort")
    s, y = s[order], y[order]
    tp, n = np.cumsum(y), np.arange(1, len(y) + 1)
    last = np.concatenate((s[1:] != s[:-1], [True]))        # last index of each tie group
    tp, n = tp[last], n[last]
    recall = tp / len(pos)
    precision = tp / n
    return float(np.sum(np.diff(np.concatenate(([0.0], recall))) * precision))


def stratified_bootstrap(stat, pos, neg, n_boot=N_BOOT, seed=SEED):
    """Resample positives and negatives separately, with replacement (variants treated as independent).
    Kept for unit tests and for data without position labels; the analysis itself resamples positions."""
    pos, neg = np.asarray(pos, dtype=float), np.asarray(neg, dtype=float)
    rng = np.random.default_rng(seed)
    out = np.empty(n_boot)
    for b in range(n_boot):
        out[b] = stat(pos[rng.integers(0, len(pos), len(pos))], neg[rng.integers(0, len(neg), len(neg))])
    return out


def cluster_indices(groups, n_boot=N_BOOT, seed=SEED):
    """Position-cluster bootstrap: positions are drawn with replacement and every variant of a drawn
    position comes along. Variants at one position share a reference window and usually a class, so they
    are not independent draws. Yields one index array per resample."""
    groups = np.asarray(groups)
    _, inverse = np.unique(groups, return_inverse=True)
    order = np.argsort(inverse, kind="mergesort")
    members = np.split(order, np.cumsum(np.bincount(inverse))[:-1])
    rng = np.random.default_rng(seed)
    for _ in range(n_boot):
        yield np.concatenate([members[g] for g in rng.integers(0, len(members), len(members))])


def _pooled(pos, neg, groups_pos, groups_neg):
    s = np.concatenate((np.asarray(pos, dtype=float), np.asarray(neg, dtype=float)))
    y = np.concatenate((np.ones(len(pos), dtype=bool), np.zeros(len(neg), dtype=bool)))
    g = np.concatenate((np.asarray(groups_pos), np.asarray(groups_neg)))
    return s, y, g


def cluster_bootstrap(stat, pos, neg, groups_pos, groups_neg, n_boot=N_BOOT, seed=SEED):
    """Statistic under the position-cluster bootstrap. A resample without one of the classes gives nan."""
    s, y, g = _pooled(pos, neg, groups_pos, groups_neg)
    out = np.full(n_boot, np.nan)
    for b, idx in enumerate(cluster_indices(g, n_boot, seed)):
        yy = y[idx]
        if yy.any() and not yy.all():
            out[b] = stat(s[idx][yy], s[idx][~yy])
    return out


def with_interval(stat, pos, neg, n_boot=N_BOOT, seed=SEED, groups_pos=None, groups_neg=None):
    """Point estimate with a percentile 95% interval. With position labels the bootstrap resamples
    positions (all variants of a position together); without them it falls back to resampling variants."""
    if groups_pos is None:
        boots = stratified_bootstrap(stat, pos, neg, n_boot, seed)
        kind, n_clusters = "variants resampled within class (independence assumed), percentile interval", None
    else:
        boots = cluster_bootstrap(stat, pos, neg, groups_pos, groups_neg, n_boot, seed)
        kind = "positions resampled, all variants of a position together; percentile interval"
        n_clusters = int(len(np.unique(np.concatenate((np.asarray(groups_pos), np.asarray(groups_neg))))))
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return {"value": float(stat(pos, neg)), "ci95": [float(lo), float(hi)], "n_pos": int(len(pos)),
            "n_neg": int(len(neg)), "bootstrap": {"resamples": int(n_boot), "seed": int(seed), "type": kind,
                                                  "positions": n_clusters, "resamples_without_both_classes": int(np.isnan(boots).sum())}}


def paired_difference(stat, a_pos, a_neg, b_pos, b_neg, groups_pos, groups_neg, n_boot=N_BOOT, seed=SEED):
    """stat(score A) - stat(score B) on the same variants, with a position-cluster bootstrap interval
    (the same resample is applied to both scores)."""
    sa, y, g = _pooled(a_pos, a_neg, groups_pos, groups_neg)
    sb, _, _ = _pooled(b_pos, b_neg, groups_pos, groups_neg)
    out = np.full(n_boot, np.nan)
    for b, idx in enumerate(cluster_indices(g, n_boot, seed)):
        yy = y[idx]
        if yy.any() and not yy.all():
            out[b] = stat(sa[idx][yy], sa[idx][~yy]) - stat(sb[idx][yy], sb[idx][~yy])
    lo, hi = np.nanpercentile(out, [2.5, 97.5])
    return {"value": float(stat(a_pos, a_neg) - stat(b_pos, b_neg)), "ci95": [float(lo), float(hi)],
            "n_pos": int(len(a_pos)), "n_neg": int(len(a_neg)),
            "bootstrap": {"resamples": int(n_boot), "seed": int(seed), "type": "paired; positions resampled; percentile interval"}}


def spearman(a, b):
    ra, rb = average_ranks(a), average_ranks(b)
    return float(np.corrcoef(ra, rb)[0, 1])


# ---------------------------------------------------------------- ACMG/AMP Bayesian framework
def strength_lr(calibration, strength):
    """Likelihood ratio a single criterion of this strength carries (pathogenic direction)."""
    return CALIBRATIONS[calibration]["very_strong_lr"] ** STRENGTH_EXPONENT[strength]


def posterior(lr, prior):
    """Posterior probability from a likelihood ratio (odds of pathogenicity) and a prior probability.
    Tavtigian 2018 Table 1 footnote; Pejaver 2022 Eq. 7."""
    return lr * prior / ((lr - 1.0) * prior + 1.0)


def combined_lr(calibration, n_supporting=0, n_moderate=0, n_strong=0, n_very_strong=0,
                b_supporting=0, b_moderate=0, b_strong=0, b_very_strong=0):
    """Tavtigian 2018 Eq. 1 and 2: evidence lines combine as exponents on the very-strong odds."""
    e = (n_supporting - b_supporting) / 8 + (n_moderate - b_moderate) / 4 + (n_strong - b_strong) / 2 \
        + (n_very_strong - b_very_strong)
    return CALIBRATIONS[calibration]["very_strong_lr"] ** e


def strength_for_lr(lr_bound, calibration, direction):
    """Strongest evidence level whose target a one-sided bound meets.
    direction 'pathogenic': lower bound >= target. direction 'benign': upper bound <= 1/target."""
    reached = "none"
    for s in STRENGTH_ORDER:
        target = strength_lr(calibration, s)
        ok = lr_bound >= target if direction == "pathogenic" else lr_bound <= 1.0 / target
        if ok:
            reached = s
    return reached


# ---------------------------------------------------------------- likelihood ratios over score bins
def bin_counts(scores, edges):
    """Counts per bin; bin i holds edges[i] <= s < edges[i+1], the last bin also holds its upper edge."""
    idx = np.clip(np.searchsorted(edges, scores, side="right") - 1, 0, len(edges) - 2)
    return np.bincount(idx, minlength=len(edges) - 1)


def lr_from_counts(n_pos_bin, n_neg_bin, n_pos, n_neg):
    """Positive likelihood ratio of falling in a bin, with 0.5 added to each count so that
    empty cells give a finite value: ((a + 0.5) / (P + 1)) / ((b + 0.5) / (N + 1))."""
    return ((n_pos_bin + 0.5) / (n_pos + 1.0)) / ((n_neg_bin + 0.5) / (n_neg + 1.0))


def binom_cdf(k, n, p):
    """P(X <= k) for X ~ Binomial(n, p), summed in log space."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0
    lp, lq = math.log(p), math.log1p(-p)
    return min(1.0, sum(math.exp(math.lgamma(n + 1) - math.lgamma(j + 1) - math.lgamma(n - j + 1) + j * lp + (n - j) * lq)
                        for j in range(k + 1)))


def clopper_pearson(k, n, alpha):
    """Exact one-sided bounds for a binomial proportion: (lower, upper), each at level alpha."""
    def solve(f):                                   # f is decreasing in p; find f(p) = alpha
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(mid) > alpha:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
    lower = 0.0 if k == 0 else 1.0 - solve(lambda q: binom_cdf(n - k, n, q))     # P(X >= k | p) = alpha
    upper = 1.0 if k == n else solve(lambda p: binom_cdf(k, n, p))               # P(X <= k | p) = alpha
    return lower, upper


def exact_lr_bounds(a, n_pos, b, n_neg, alpha=0.05):
    """Conservative one-sided bounds for (a/n_pos) / (b/n_neg): Clopper-Pearson bounds on each share at
    alpha/2, combined. Valid for empty cells, which a bootstrap of the observed counts is not.
    Variants are treated as independent here; see exact_lr_bounds_clustered."""
    la, ua = clopper_pearson(int(a), int(n_pos), alpha / 2)
    lb, ub = clopper_pearson(int(b), int(n_neg), alpha / 2)
    return la / ub, (ua / lb if lb > 0 else float("inf"))


def _betacf(a, b, x, iters=1000, eps=1e-15):
    """Continued fraction for the incomplete beta function (modified Lentz method)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (tiny if abs(d) < tiny else d)
    h = d
    for m in range(1, iters + 1):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)), -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1.0 + aa * d
            d = 1.0 / (tiny if abs(d) < tiny else d)
            c = 1.0 + aa / c
            c = tiny if abs(c) < tiny else c
            h *= d * c
        if abs(d * c - 1.0) < eps:
            break
    return h


def betainc_reg(a, b, x):
    """Regularised incomplete beta function I_x(a, b) for real a, b > 0."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbt) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbt) * _betacf(b, a, 1.0 - x) / b


def clopper_pearson_real(k, n, alpha):
    """Clopper-Pearson one-sided bounds written with the beta distribution, so that k and n may be
    effective (non-integer) counts. For integer k and n it equals clopper_pearson."""
    def solve(g):                                   # g is increasing in p; find g(p) = target
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if g(mid) < 0:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
    lower = 0.0 if k <= 0 else solve(lambda p: betainc_reg(k, n - k + 1.0, p) - alpha)
    upper = 1.0 if k >= n else solve(lambda p: betainc_reg(k + 1.0, n - k, p) - (1.0 - alpha))
    return lower, upper


def design_effect(groups):
    """Worst-case design effect of a share counted over variants that cluster by position: sum(m^2) / sum(m),
    m = number of variants of the class at a position. It is the variance inflation if all variants of a
    position always fall in the same bin (within-position correlation 1); real data can only do better."""
    if groups is None or len(groups) == 0:
        return 1.0
    _, m = np.unique(np.asarray(groups), return_counts=True)
    return float((m.astype(float) ** 2).sum() / m.sum())


def exact_lr_bounds_clustered(a, n_pos, b, n_neg, deff_pos, deff_neg, alpha=0.05):
    """exact_lr_bounds on effective counts (each count divided by its class's worst-case design effect),
    so that the bound stays conservative when the variants of a position are not independent."""
    la, ua = clopper_pearson_real(a / deff_pos, n_pos / deff_pos, alpha / 2)
    lb, ub = clopper_pearson_real(b / deff_neg, n_neg / deff_neg, alpha / 2)
    return la / ub, (ua / lb if lb > 0 else float("inf"))


MIN_BOOT_COUNT = 5      # the bootstrap bound of a bin is used only if it holds this many variants of each class


def local_likelihood_ratios(pos, neg, n_bins=20, n_boot=N_BOOT, seed=SEED, groups_pos=None, groups_neg=None):
    """Likelihood ratio per quantile bin of the pooled score with one-sided 95% bounds.

    Bound used for a bin:
      bins with at least MIN_BOOT_COUNT variants of each class: the more cautious of
        exact      Clopper-Pearson on each class share, and
        bootstrap  position-cluster bootstrap with fixed bin edges (variants resampled if no position labels);
      sparser bins, where a bootstrap of the observed counts cannot be trusted:
        exact_clustered  Clopper-Pearson on effective counts (counts divided by the worst-case design effect of
                         position clustering), conservative whatever the within-position correlation.
    The clustered exact bound is reported for every bin. Bin edges are fixed from the full labelled set."""
    pos, neg = np.asarray(pos, dtype=float), np.asarray(neg, dtype=float)
    pooled = np.concatenate((pos, neg))
    edges = np.unique(np.quantile(pooled, np.linspace(0, 1, n_bins + 1)))
    a, b = bin_counts(pos, edges), bin_counts(neg, edges)
    point = lr_from_counts(a, b, len(pos), len(neg))
    boots = np.full((n_boot, len(edges) - 1), np.nan)
    if groups_pos is None:
        rng = np.random.default_rng(seed)
        for i in range(n_boot):
            pa = bin_counts(pos[rng.integers(0, len(pos), len(pos))], edges)
            nb = bin_counts(neg[rng.integers(0, len(neg), len(neg))], edges)
            boots[i] = lr_from_counts(pa, nb, len(pos), len(neg))
        kind = "variants resampled within class; fixed bin edges"
    else:
        s, y, g = _pooled(pos, neg, groups_pos, groups_neg)
        for i, idx in enumerate(cluster_indices(g, n_boot, seed)):
            yy = y[idx]
            if yy.any() and not yy.all():
                boots[i] = lr_from_counts(bin_counts(s[idx][yy], edges), bin_counts(s[idx][~yy], edges), yy.sum(), (~yy).sum())
        kind = "positions resampled, all variants of a position together; fixed bin edges"
    boot_lower = np.nanpercentile(boots, 5, axis=0)       # one-sided 95% lower bound
    boot_upper = np.nanpercentile(boots, 95, axis=0)      # one-sided 95% upper bound
    deff_pos, deff_neg = design_effect(groups_pos), design_effect(groups_neg)
    rows = []
    for i in range(len(edges) - 1):
        raw = None if b[i] == 0 else float((a[i] / len(pos)) / (b[i] / len(neg)))
        ex_lo, ex_up = exact_lr_bounds(a[i], len(pos), b[i], len(neg))
        cl_lo, cl_up = exact_lr_bounds_clustered(float(a[i]), float(len(pos)), float(b[i]), float(len(neg)), deff_pos, deff_neg)
        use_boot = a[i] >= MIN_BOOT_COUNT and b[i] >= MIN_BOOT_COUNT
        lower = min(ex_lo, float(boot_lower[i])) if use_boot else cl_lo
        upper = max(ex_up, float(boot_upper[i])) if use_boot else cl_up
        rows.append({"bin": i + 1, "score_min": float(edges[i]), "score_max": float(edges[i + 1]),
                     "n_lof": int(a[i]), "n_func": int(b[i]), "lr_plus_raw": raw, "lr_plus": float(point[i]),
                     "lr_lower_exact": float(ex_lo), "lr_upper_exact": float(ex_up),
                     "lr_lower_exact_clustered": float(cl_lo), "lr_upper_exact_clustered": float(cl_up),
                     "lr_lower_bootstrap": float(boot_lower[i]) if use_boot else None,
                     "lr_upper_bootstrap": float(boot_upper[i]) if use_boot else None,
                     "bound_used": "more cautious of exact and position bootstrap" if use_boot else "exact on effective counts (sparse bin)",
                     "lr_lower_95_one_sided": float(lower), "lr_upper_95_one_sided": float(upper)})
    return {"n_bins": len(rows), "n_bins_requested": int(n_bins), "edges": [float(e) for e in edges], "rows": rows,
            "bootstrap": {"resamples": int(n_boot), "seed": int(seed), "type": kind, "min_count_per_class": MIN_BOOT_COUNT},
            "design_effect": {"lof": deff_pos, "func": deff_neg,
                              "definition": "sum(m^2) / sum(m), m = variants of the class at a position: the variance inflation if all variants of a position fall in the same bin"},
            "bound_definition": "lr_lower_95_one_sided / lr_upper_95_one_sided: in a bin with at least 5 variants of each class, the more cautious of (a) the exact bound, one-sided Clopper-Pearson bounds on the loss-of-function share and the functional share of the bin, each at 2.5%, combined, and (b) the 5% / 95% percentile of the position-cluster bootstrap; in a sparser bin, the exact bound computed on effective counts, each count divided by its class's worst-case design effect (lr_lower_exact_clustered), which stays conservative however strongly the variants of a position are correlated. An upper bound of null means the bin holds no functional variant and no finite bound exists.",
            "lr_definition": "lr_plus = ((n_lof_bin + 0.5) / (N_lof + 1)) / ((n_func_bin + 0.5) / (N_func + 1)); lr_plus_raw is the uncorrected ratio (null when the bin has no functional variant)"}


def worst_case_rows(lr_table):
    """The rows with the clustered exact bound applied in every bin (also where the bootstrap was used):
    a sensitivity check, the most cautious reading of the table."""
    out = []
    for r in lr_table["rows"]:
        lo, up = r["lr_lower_exact_clustered"], r["lr_upper_exact_clustered"]
        if r["lr_lower_bootstrap"] is not None:
            lo, up = min(lo, r["lr_lower_bootstrap"]), max(up, r["lr_upper_bootstrap"])
        out.append({**r, "lr_lower_95_one_sided": lo, "lr_upper_95_one_sided": up})
    return {"rows": out}


def thresholds_from_bins(lr_table, calibration):
    """Score thresholds reaching each strength, in the spirit of Pejaver 2022 Eq. 8 and 9 on bins.
    Pathogenic: the lowest score t such that every bin at or above t has a lower bound >= the target.
    Benign: the highest score t such that every bin below t has an upper bound <= 1/target."""
    rows = lr_table["rows"]
    out = {"pathogenic": {}, "benign": {}}
    for s in STRENGTH_ORDER:
        target = strength_lr(calibration, s)
        thr = None
        for r in reversed(rows):
            if r["lr_lower_95_one_sided"] >= target:
                thr = r["score_min"]
            else:
                break
        out["pathogenic"][s] = {"target_lr": target, "score_threshold": "none" if thr is None else thr,
                                "rule": "score >= threshold"}
        thr = None
        for r in rows:
            if r["lr_upper_95_one_sided"] <= 1.0 / target:
                thr = r["score_max"]
            else:
                break
        out["benign"][s] = {"target_lr": 1.0 / target, "score_threshold": "none" if thr is None else thr,
                            "rule": "score < threshold"}      # bins are closed on the left, open on the right
    return out


def shares_reaching(thresholds, scores_all, scores_labelled):
    """Share of variants at or beyond each threshold (cumulative: 'at least this strength')."""
    out = {"pathogenic": {}, "benign": {}}
    for direction in ("pathogenic", "benign"):
        for s in STRENGTH_ORDER:
            t = thresholds[direction][s]["score_threshold"]
            if t == "none":
                out[direction][s] = {"share_of_all_scored": 0.0, "n_all_scored": 0,
                                     "share_of_lof_and_func": 0.0, "n_lof_and_func": 0}
                continue
            cmp = (lambda x: x >= t) if direction == "pathogenic" else (lambda x: x < t)
            na, nl = int(np.sum(cmp(scores_all))), int(np.sum(cmp(scores_labelled)))
            out[direction][s] = {"share_of_all_scored": na / len(scores_all), "n_all_scored": na,
                                 "share_of_lof_and_func": nl / len(scores_labelled), "n_lof_and_func": nl}
    return out


# ---------------------------------------------------------------- cross-fitted logistic calibration
def fit_logistic(x, y, ridge=1e-8, iters=100):
    """Logistic regression p = 1 / (1 + exp(-(a + b x))) by Newton steps. Returns (a, b)."""
    X = np.column_stack((np.ones(len(x)), x))
    w = np.zeros(2)
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(X @ w, -30, 30)))
        grad = X.T @ (p - y) + ridge * w
        hess = (X * (p * (1 - p))[:, None]).T @ X + ridge * np.eye(2)
        step = np.linalg.solve(hess, grad)
        w = w - step
        if np.max(np.abs(step)) < 1e-10:
            break
    return float(w[0]), float(w[1])


def stratified_folds(y, k=5, seed=SEED):
    rng = np.random.default_rng(seed)
    fold = np.empty(len(y), dtype=int)
    for cls in (0, 1):
        idx = np.flatnonzero(y == cls)
        rng.shuffle(idx)
        fold[idx] = np.arange(len(idx)) % k
    return fold


def grouped_folds(y, groups, k=5, seed=SEED):
    """Folds assigned by position: every variant of a position is in the same fold. Positions are
    stratified on their majority class (a tie counts as loss-of-function)."""
    y, groups = np.asarray(y), np.asarray(groups)
    uniq, inverse = np.unique(groups, return_inverse=True)
    share = np.bincount(inverse, weights=y.astype(float)) / np.bincount(inverse)
    majority = (share >= 0.5).astype(int)
    rng = np.random.default_rng(seed)
    fold_of_group = np.empty(len(uniq), dtype=int)
    for cls in (0, 1):
        idx = np.flatnonzero(majority == cls)
        rng.shuffle(idx)
        fold_of_group[idx] = np.arange(len(idx)) % k
    return fold_of_group[inverse]


def cross_fitted_calibration(scores, y, k=5, seed=SEED, n_table_bins=10, groups=None):
    """Each variant's probability comes from a logistic model fitted on the other folds. With position
    labels the folds keep all variants of a position together."""
    scores, y = np.asarray(scores, dtype=float), np.asarray(y, dtype=float)
    fold = stratified_folds(y, k, seed) if groups is None else grouped_folds(y, groups, k, seed)
    p = np.empty(len(y))
    coefs = []
    for f in range(k):
        tr, te = fold != f, fold == f
        mu, sd = scores[tr].mean(), scores[tr].std()
        a, b = fit_logistic((scores[tr] - mu) / sd, y[tr])
        p[te] = 1.0 / (1.0 + np.exp(-np.clip(a + b * (scores[te] - mu) / sd, -30, 30)))
        coefs.append({"fold": f + 1, "intercept": a, "slope_per_sd": b, "train_mean": float(mu), "train_sd": float(sd),
                      "n_train": int(tr.sum()), "n_test": int(te.sum())})
    brier = float(np.mean((p - y) ** 2))
    prevalence = float(y.mean())
    brier_ref = float(np.mean((prevalence - y) ** 2))
    order = np.argsort(p, kind="mergesort")
    table, ece = [], 0.0
    for i, chunk in enumerate(np.array_split(order, n_table_bins)):
        mp, ob = float(p[chunk].mean()), float(y[chunk].mean())
        ece += len(chunk) / len(y) * abs(mp - ob)
        table.append({"bin": i + 1, "n": int(len(chunk)), "predicted_min": float(p[chunk].min()),
                      "predicted_max": float(p[chunk].max()), "mean_predicted": mp, "observed_lof_fraction": ob,
                      "n_lof": int(y[chunk].sum())})
    return {"method": f"{k}-fold cross-fitted logistic regression on the standardised score "
                      + ("(folds stratified by class, variants independent)" if groups is None else "(folds assigned by position, stratified on the position's majority class)"),
            "folds": k, "seed": int(seed), "brier_score": brier, "brier_score_prevalence_only": brier_ref,
            "brier_skill_score": 1.0 - brier / brier_ref, "expected_calibration_error": float(ece),
            "prevalence_lof": prevalence, "n": int(len(y)), "fold_models": coefs, "reliability_table": table}, p


# ---------------------------------------------------------------- input / output
def read_csv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def load_joined(labels_csv, scores_csv, score_column):
    labels = {(r["pos"], r["ref"], r["alt"]): r for r in read_csv(labels_csv)}
    rows, missing_label = [], 0
    for r in read_csv(scores_csv):
        lab = labels.get((r["pos"], r["ref"], r["alt"]))
        if lab is None:
            missing_label += 1
            continue
        rows.append({**lab, **r, "s": -float(r[score_column])})
    return rows, len(labels), missing_label


def groups_of(rows):
    return np.array([r["pos"] for r in rows])


def assay_vs_clinvar(rows, n_boot=N_BOOT, seed=SEED):
    """How well the assay itself agrees with the ClinVar labels recorded in the supplement.
    Uses the benchmark table only (no model output): a check on the proxy, not on the model."""
    cls = np.array([r["func_class"] for r in rows])
    cv = np.array([r.get("clinvar_simple", "") for r in rows])
    cons = np.array([r["consequence"] for r in rows])
    fscore = np.array([float(r["function_score"]) for r in rows])
    g = groups_of(rows)
    path = np.isin(cv, ["Pathogenic", "Likely pathogenic"])
    ben = np.isin(cv, ["Benign", "Likely benign"])
    out = {"definition": "ClinVar labels as recorded in the 2018 supplement: Pathogenic or Likely pathogenic (positive) against Benign or Likely benign (negative)",
           "n_pathogenic_or_likely": int(path.sum()), "n_benign_or_likely": int(ben.sum()),
           "consequence_mix": {"pathogenic_or_likely": {c: int(np.sum(path & (cons == c))) for c in sorted(set(cons[path]))},
                               "benign_or_likely": {c: int(np.sum(ben & (cons == c))) for c in sorted(set(cons[ben]))}}}
    if path.sum() >= 5 and ben.sum() >= 5:
        out["auroc_assay_function_score"] = {
            "note": "the assay's own function score (negated) on these variants; no model involved",
            **{k: v for k, v in with_interval(auroc, -fscore[path], -fscore[ben], n_boot, seed + 6, g[path], g[ben]).items() if k in ("value", "ci95")}}
        out["assay_class_among_clinvar"] = {
            "pathogenic_or_likely": {c: int(np.sum(path & (cls == c))) for c in ("FUNC", "INT", "LOF")},
            "benign_or_likely": {c: int(np.sum(ben & (cls == c))) for c in ("FUNC", "INT", "LOF")}}
    return out


BASELINES = {   # predictors that come with the supplement; higher value = more damaging / more conserved
    "cadd": {"column": "cadd_score", "label": "CADD score as listed in the supplement (version not stated there)"},
    "phylop_mammalian": {"column": "phylop_mammalian", "label": "phyloP (mammalian) conservation as listed in the supplement"},
}
LR_BINS = 20                 # fixed: the script default since before any score existed
# Missense table: the same number of labelled variants per bin as the all-variant table, so the bin
# count is LR_BINS x (labelled missense / labelled variants). A rule fixed by the data's size, not its scores.
BIN_SENSITIVITY = {"all": (10, 20, 40), "missense": (5, 10, 20, 40)}


def consequence_only_scores(rows, k=5, seed=SEED):
    """A predictor with no model and no sequence: the loss-of-function rate of the variant's consequence
    class, estimated on the other folds (folds assigned by position). Returns one value per labelled row."""
    cls = np.array([r["func_class"] for r in rows])
    cons = np.array([r["consequence"] for r in rows])
    y = (cls == "LOF").astype(float)
    fold = grouped_folds(y, groups_of(rows), k, seed)
    p = np.empty(len(rows))
    for f in range(k):
        tr, te = fold != f, fold == f
        for c in set(cons[te]):
            m = tr & (cons == c)
            p[te & (cons == c)] = (y[m].sum() + 0.5) / (m.sum() + 1.0)
    return p


def consequence_only_baseline(rows, n_boot=N_BOOT, seed=SEED):
    lab = [r for r in rows if r["func_class"] in ("LOF", "FUNC")]
    p = consequence_only_scores(lab, 5, seed + 30)
    lof = np.array([r["func_class"] == "LOF" for r in lab])
    g = groups_of(lab)
    out = {"definition": "loss-of-function rate of the variant's consequence class, cross-fitted in 5 folds assigned by position; no model, no sequence",
           "n_lof": int(lof.sum()), "n_func": int((~lof).sum()),
           "auroc_lof_vs_func": {k: v for k, v in with_interval(auroc, p[lof], p[~lof], n_boot, seed + 31, g[lof], g[~lof]).items() if k in ("value", "ci95")}}
    return out, {(r["pos"], r["ref"], r["alt"]): float(v) for r, v in zip(lab, p)}


def evidence(s, lof, func, groups, n_bins, n_boot, seed, s_all):
    """Likelihood-ratio table and the evidence strength it reaches under both calibrations."""
    lr = local_likelihood_ratios(s[lof], s[func], n_bins, n_boot, seed, groups[lof], groups[func])
    worst = worst_case_rows(lr)
    top = lambda thr: {d: next((st for st in reversed(STRENGTH_ORDER) if thr[d][st]["score_threshold"] != "none"), "none")
                       for d in ("pathogenic", "benign")}
    acmg = {}
    for name, c in CALIBRATIONS.items():
        thr = thresholds_from_bins(lr, name)
        acmg[name] = {
            "prior": c["prior"], "source": c["source"],
            "strength_targets": {st: {"lr": strength_lr(name, st), "posterior_at_prior": posterior(strength_lr(name, st), c["prior"])}
                                 for st in STRENGTH_ORDER},
            "thresholds": thr,
            "share_reaching_at_least": shares_reaching(thr, s_all, s[lof | func]),
            "strongest_reached": top(thr),
            "strongest_reached_with_clustered_exact_bound_in_every_bin": top(thresholds_from_bins(worst, name)),
        }
    for r in lr["rows"]:
        for name in CALIBRATIONS:
            r[f"pathogenic_strength_{name}"] = strength_for_lr(r["lr_lower_95_one_sided"], name, "pathogenic")
            r[f"benign_strength_{name}"] = strength_for_lr(r["lr_upper_95_one_sided"], name, "benign")
    return lr, acmg


def bin_sensitivity(s, lof, func, groups, bins, n_boot, seed, s_all):
    out = []
    for nb in bins:
        lr, acmg = evidence(s, lof, func, groups, nb, n_boot, seed, s_all)
        out.append({"n_bins_requested": nb, "n_bins": lr["n_bins"],
                    "strongest_reached": {k: v["strongest_reached"] for k, v in acmg.items()},
                    "strongest_reached_with_clustered_exact_bound_in_every_bin": {
                        k: v["strongest_reached_with_clustered_exact_bound_in_every_bin"] for k, v in acmg.items()},
                    "top_bin": {k: lr["rows"][-1][k] for k in ("n_lof", "n_func", "lr_plus", "lr_lower_95_one_sided")},
                    "bottom_bin": {k: lr["rows"][0][k] for k in ("n_lof", "n_func", "lr_plus", "lr_upper_95_one_sided")}})
    return out


def analyse(rows, n_boot=N_BOOT, seed=SEED, n_lr_bins=LR_BINS):
    cls = np.array([r["func_class"] for r in rows])
    s = np.array([r["s"] for r in rows])
    cons = np.array([r["consequence"] for r in rows])
    fscore = np.array([float(r["function_score"]) for r in rows])
    g = groups_of(rows)
    lof, func, inter = cls == "LOF", cls == "FUNC", cls == "INT"
    ci = lambda stat, p, n, sd: with_interval(stat, s[p], s[n], n_boot, sd, g[p], g[n])
    out = {"score_definition": "s = -(mean log-likelihood of the alternate window - mean log-likelihood of the reference window); higher s = more disruptive",
           "interval_method": "95% percentile intervals from a position-cluster bootstrap: positions are resampled and all variants of a position stay together",
           "counts_scored_by_class": {c: int(np.sum(cls == c)) for c in ("FUNC", "INT", "LOF")},
           "positions_scored": int(len(set(g)))}

    out["auroc_lof_vs_func"] = {"definition": "LOF (positive) against FUNC (negative); INT excluded", **ci(auroc, lof, func, seed)}
    out["average_precision_lof_vs_func"] = {"definition": "LOF (positive) against FUNC; INT excluded",
                                            "prevalence_lof": float(lof.sum() / (lof.sum() + func.sum())),
                                            **ci(average_precision, lof, func, seed + 1)}
    out["auroc_lof_vs_func_and_int"] = {"definition": "LOF against FUNC and INT merged, as in the ArcInstitute/evo2 BRCA1 notebook (for comparison with published values)",
                                        **ci(auroc, lof, ~lof, seed + 2)}

    by_cons = {}
    for i, c in enumerate(sorted(set(cons))):
        m = cons == c
        entry = {"n_lof": int(np.sum(m & lof)), "n_func": int(np.sum(m & func)), "n_int_excluded": int(np.sum(m & inter))}
        if entry["n_lof"] >= 5 and entry["n_func"] >= 5:
            entry.update({k: v for k, v in ci(auroc, m & lof, m & func, seed + 100 if c == "Missense" else seed + 10 + i).items() if k in ("value", "ci95")})
        else:
            entry.update({"value": None, "ci95": None, "note": "fewer than 5 variants in one class; not computed"})
        by_cons[c] = entry
    out["auroc_by_consequence"] = by_cons

    lab = lof | func
    cal, _ = cross_fitted_calibration(s[lab], lof[lab].astype(float), 5, seed + 3, groups=g[lab])
    cal["brier_score_folds_by_variant"] = cross_fitted_calibration(s[lab], lof[lab].astype(float), 5, seed + 3)[0]["brier_score"]
    out["calibration"] = cal

    lr, acmg = evidence(s, lof, func, g, n_lr_bins, n_boot, seed + 4, s)
    out["likelihood_ratio_table"] = lr
    out["acmg_amp_evidence"] = acmg
    for name in CALIBRATIONS:           # which consequences sit above each pathogenic-direction threshold
        mix = {}
        for st in STRENGTH_ORDER:
            t = acmg[name]["thresholds"]["pathogenic"][st]["score_threshold"]
            if t == "none":
                mix[st] = None
                continue
            above = s >= t
            mix[st] = {"score_threshold": t, "n": int(above.sum()),
                       "by_class": {c: int(np.sum(above & (cls == c))) for c in ("LOF", "FUNC", "INT")},
                       "lof_by_consequence": {c: int(np.sum(above & lof & (cons == c))) for c in sorted(set(cons[above & lof]))},
                       "func_by_consequence": {c: int(np.sum(above & func & (cons == c))) for c in sorted(set(cons[above & func]))}}
        acmg[name]["consequence_mix_at_or_above_pathogenic_threshold"] = mix
    out["bin_count_sensitivity"] = {"note": "strength reached with other bin counts; the analysis uses 20, fixed as the script default before any score existed",
                                    "rows": bin_sensitivity(s, lof, func, g, BIN_SENSITIVITY["all"], n_boot, seed + 4, s)}

    # Missense variants alone: the class a computational criterion (PP3 / BP4) is meant for.
    mis = cons == "Missense"
    n_ml, n_mf = int(np.sum(mis & lof)), int(np.sum(mis & func))
    block = {"n_lof": n_ml, "n_func": n_mf, "n_int_excluded": int(np.sum(mis & inter)),
             "why": "nonsense and canonical splice variants are nearly all loss-of-function and are covered by other ACMG/AMP criteria; a computational score matters for missense variants"}
    if n_ml >= 20 and n_mf >= 20:
        per_bin = (lof.sum() + func.sum()) / n_lr_bins
        nb = max(2, round((n_ml + n_mf) / per_bin))
        mlr, macmg = evidence(s[mis], lof[mis], func[mis], g[mis], nb, n_boot, seed + 20, s[mis])
        block.update({"n_bins": nb, "bin_rule": f"about {per_bin:.0f} labelled variants per bin, the occupancy of the all-variant table",
                      "bin_rule_set": "on 2026-11-14 while fixing review findings, after the reviewer had reported missense results for 5, 10 and 20 bins "
                                      "on an earlier 423-variant sample; it is not a pre-registered choice, so the sensitivity rows (5 to 40 bins) belong with it",
                      "likelihood_ratio_table": mlr,
                      "acmg_amp_evidence": {k: {kk: v[kk] for kk in ("thresholds", "share_reaching_at_least", "strongest_reached",
                                                                      "strongest_reached_with_clustered_exact_bound_in_every_bin")} for k, v in macmg.items()},
                      "strongest_reached": {k: v["strongest_reached"] for k, v in macmg.items()},
                      "strongest_reached_with_clustered_exact_bound_in_every_bin": {
                          k: v["strongest_reached_with_clustered_exact_bound_in_every_bin"] for k, v in macmg.items()},
                      "bin_count_sensitivity": bin_sensitivity(s[mis], lof[mis], func[mis], g[mis], BIN_SENSITIVITY["missense"], n_boot, seed + 20, s[mis])})
    else:
        block.update({"strongest_reached": None, "note": "fewer than 20 missense variants in one class; evidence strength not established"})
    out["missense_evidence"] = block

    cv = np.array([r.get("clinvar_simple", "") for r in rows])
    path = np.isin(cv, ["Pathogenic", "Likely pathogenic"])
    ben = np.isin(cv, ["Benign", "Likely benign"])
    clin = assay_vs_clinvar(rows, n_boot, seed)
    if path.sum() >= 5 and ben.sum() >= 5:
        clin["auroc_evo2"] = {k: v for k, v in ci(auroc, path, ben, seed + 5).items() if k in ("value", "ci95")}
    out["clinvar_cross_check"] = clin

    sens = {"spearman_s_vs_assay_function_score": spearman(s, fscore)}
    if rows and rows[0].get("evo2_delta_score_f64") not in (None, ""):
        s64 = -np.array([float(r["evo2_delta_score_f64"]) for r in rows])
        sens["auroc_lof_vs_func_float64_delta"] = auroc(s64[lof], s64[func])
        sens["spearman_float32_vs_float64_delta"] = spearman(s, s64)
    if rows and all(r.get("evo2_site_llr") not in (None, "") for r in rows):
        site = -np.array([float(r["evo2_site_llr"]) for r in rows])
        sens["auroc_lof_vs_func_site_log_likelihood_ratio"] = auroc(site[lof], site[func])
    out["sensitivity"] = sens
    return out


def baseline_summary(m, label, n_rows):
    return {"label": label, "score_direction": "higher = more damaging", "n_with_value": n_rows,
            "auroc_lof_vs_func": m["auroc_lof_vs_func"],
            "average_precision_lof_vs_func": m["average_precision_lof_vs_func"],
            "auroc_by_consequence": m["auroc_by_consequence"],
            "brier_score": m["calibration"]["brier_score"],
            "clinvar_auroc": m["clinvar_cross_check"].get("auroc_evo2"),
            "acmg_amp_evidence": {k: {"strongest_reached": v["strongest_reached"], "thresholds": v["thresholds"],
                                      "share_reaching_at_least": v["share_reaching_at_least"]}
                                  for k, v in m["acmg_amp_evidence"].items()},
            "missense_strongest_reached": m["missense_evidence"].get("strongest_reached"),
            "likelihood_ratio_table": m["likelihood_ratio_table"]["rows"]}


def baselines_from_supplement(label_rows, n_boot=N_BOOT, seed=SEED, n_lr_bins=LR_BINS):
    """The same statistics for two established scores that are columns of the benchmark table.
    They need no model run and give the scale against which a foundation-model score can be read."""
    out = {}
    for name, spec in BASELINES.items():
        rows = [{**r, "s": float(r[spec["column"]])} for r in label_rows if r.get(spec["column"], "") != ""]
        if len(rows) < 50:
            out[name] = {"label": spec["label"], "n_with_value": len(rows), "note": "too few values; not analysed"}
            continue
        out[name] = baseline_summary(analyse(rows, n_boot, seed, n_lr_bins), spec["label"], len(rows))
    out["consequence_only"], _ = consequence_only_baseline(label_rows, n_boot, seed)
    return out


def same_sample_comparison(rows, n_boot=N_BOOT, seed=SEED, n_lr_bins=LR_BINS):
    """Evo 2 against the supplement's scores and the consequence-only predictor on exactly the scored
    variants, with paired differences (same position resamples for both scores)."""
    cls = np.array([r["func_class"] for r in rows])
    cons = np.array([r["consequence"] for r in rows])
    cv = np.array([r.get("clinvar_simple", "") for r in rows])
    g = groups_of(rows)
    lof, func, mis = cls == "LOF", cls == "FUNC", cons == "Missense"
    path, ben = np.isin(cv, ["Pathogenic", "Likely pathogenic"]), np.isin(cv, ["Benign", "Likely benign"])
    _, cons_p = consequence_only_baseline(rows, n_boot, seed)
    scores = {"evo2": np.array([r["s"] for r in rows]),
              "cadd": np.array([float(r["cadd_score"]) for r in rows]),
              "phylop_mammalian": np.array([float(r["phylop_mammalian"]) for r in rows]),
              "consequence_only": np.array([cons_p.get((r["pos"], r["ref"], r["alt"]), np.nan) for r in rows])}
    short = lambda v: {k: v[k] for k in ("value", "ci95")}
    out = {"n_variants": len(rows), "n_lof": int(lof.sum()), "n_func": int(func.sum()),
           "n_missense_lof": int((mis & lof).sum()), "n_missense_func": int((mis & func).sum()),
           "n_clinvar_pathogenic_or_likely": int(path.sum()), "n_clinvar_benign_or_likely": int(ben.sum()), "scores": {}, "evo2_minus": {}}
    for i, (name, x) in enumerate(scores.items()):
        # same seeds as analyse(): one statistic has one interval wherever it is printed
        e = {"auroc_lof_vs_func": short(with_interval(auroc, x[lof], x[func], n_boot, seed, g[lof], g[func])),
             "average_precision_lof_vs_func": short(with_interval(average_precision, x[lof], x[func], n_boot, seed + 1, g[lof], g[func]))}
        if name != "consequence_only":
            e["auroc_missense"] = short(with_interval(auroc, x[mis & lof], x[mis & func], n_boot, seed + 100, g[mis & lof], g[mis & func]))
            if path.sum() >= 5 and ben.sum() >= 5:
                e["auroc_clinvar"] = short(with_interval(auroc, x[path], x[ben], n_boot, seed + 5, g[path], g[ben]))
            if name != "evo2":
                m = analyse([{**r, "s": float(v)} for r, v in zip(rows, x)], n_boot, seed, n_lr_bins)
                e["strongest_reached"] = {k: v["strongest_reached"] for k, v in m["acmg_amp_evidence"].items()}
                e["missense_strongest_reached"] = m["missense_evidence"].get("strongest_reached")
        out["scores"][name] = e
        if name != "evo2":
            d = {"auroc_lof_vs_func": short(paired_difference(auroc, scores["evo2"][lof], scores["evo2"][func], x[lof], x[func], g[lof], g[func], n_boot, seed + 80 + i))}
            if name != "consequence_only":
                d["auroc_missense"] = short(paired_difference(auroc, scores["evo2"][mis & lof], scores["evo2"][mis & func], x[mis & lof], x[mis & func],
                                                              g[mis & lof], g[mis & func], n_boot, seed + 90 + i))
            out["evo2_minus"][name] = d
    return out


def windows_compared(rows, sample_csv, n_boot=N_BOOT, seed=SEED):
    """The same variants scored with two window sizes, reported side by side. Neither is 'the' result:
    the longer window was kept after an interim look at the data."""
    other = {(r["pos"], r["ref"], r["alt"]): r for r in read_csv(sample_csv)}
    both = [(r, other[(r["pos"], r["ref"], r["alt"])]) for r in rows if (r["pos"], r["ref"], r["alt"]) in other]
    if not both:
        return None
    cls = np.array([a["func_class"] for a, _ in both])
    cons = np.array([a["consequence"] for a, _ in both])
    g = np.array([a["pos"] for a, _ in both])
    w = {int(both[0][0]["window"]): np.array([a["s"] for a, _ in both]),
         int(both[0][1]["window"]): -np.array([float(b["evo2_delta_score"]) for _, b in both])}
    lof, func, mis = cls == "LOF", cls == "FUNC", cons == "Missense"
    short = lambda v: {k: v[k] for k in ("value", "ci95")}
    big, small = max(w), min(w)
    out = {"note": "both windows on exactly the same variants; the shorter-window scores come from a run that was stopped early",
           "n_variants": len(both), "n_lof": int(lof.sum()), "n_func": int(func.sum()), "n_positions": int(len(set(g))),
           "spearman_between_windows": spearman(w[big], w[small]), "by_window": {}}
    for i, k in enumerate(sorted(w)):
        e = {"auroc_lof_vs_func": short(with_interval(auroc, w[k][lof], w[k][func], n_boot, seed, g[lof], g[func]))}
        if (mis & lof).sum() >= 5 and (mis & func).sum() >= 5:
            e["auroc_missense"] = short(with_interval(auroc, w[k][mis & lof], w[k][mis & func], n_boot, seed + 100, g[mis & lof], g[mis & func]))
        out["by_window"][str(k)] = e
    out["difference_longer_minus_shorter"] = {
        "windows": [big, small],
        "auroc_lof_vs_func": short(paired_difference(auroc, w[big][lof], w[big][func], w[small][lof], w[small][func], g[lof], g[func], n_boot, seed + 9)),
        "auroc_missense": short(paired_difference(auroc, w[big][mis & lof], w[big][mis & func], w[small][mis & lof], w[small][mis & func],
                                                  g[mis & lof], g[mis & func], n_boot, seed + 9))}
    # The supplement's scores on the same variants, and each window minus them: a comparison with CADD that
    # does not depend on which window was kept after the interim look.
    base = {k: np.array([float(a[BASELINES[k]["column"]]) for a, _ in both]) for k in BASELINES}
    out["baselines_same_variants"] = {}
    out["window_minus_baseline"] = {}
    for j, (k, x) in enumerate(base.items()):
        out["baselines_same_variants"][k] = {
            "auroc_lof_vs_func": short(with_interval(auroc, x[lof], x[func], n_boot, seed, g[lof], g[func])),
            "auroc_missense": short(with_interval(auroc, x[mis & lof], x[mis & func], n_boot, seed + 100, g[mis & lof], g[mis & func]))}
        out["window_minus_baseline"][k] = {str(win): {
            "auroc_lof_vs_func": short(paired_difference(auroc, w[win][lof], w[win][func], x[lof], x[func], g[lof], g[func], n_boot, seed + 60 + j)),
            "auroc_missense": short(paired_difference(auroc, w[win][mis & lof], w[win][mis & func], x[mis & lof], x[mis & func],
                                                      g[mis & lof], g[mis & func], n_boot, seed + 70 + j))} for win in sorted(w)}
    return out


def interim_look(rows, sample_csv, order_csv, n_first):
    """Recomputes the interim comparison that settled the window: the first n_first variants in the order
    they were scored (order_csv, written from the run's checkpoint), both windows."""
    other = {(r["pos"], r["ref"], r["alt"]): r for r in read_csv(sample_csv)}
    mine = {(r["pos"], r["ref"], r["alt"]): r for r in rows}
    keys = [(r["pos"], r["ref"], r["alt"]) for r in sorted(read_csv(order_csv), key=lambda r: int(r["order"]))][:n_first]
    first = [k for k in keys if k in other and k in mine]
    cls = np.array([mine[k]["func_class"] for k in first])
    a = np.array([mine[k]["s"] for k in first])
    b = -np.array([float(other[k]["evo2_delta_score"]) for k in first])
    lof, func = cls == "LOF", cls == "FUNC"
    return {"n_variants": len(first), "n_positions": len({k[0] for k in first}), "n_lof": int(lof.sum()), "n_func": int(func.sum()),
            "auroc_by_window": {str(int(mine[first[0]]["window"])): auroc(a[lof], a[func]),
                                str(int(other[first[0]]["window"])): auroc(b[lof], b[func])},
            "note": "recomputed from the score files in scoring order; this comparison was looked at during the run and decided which window to continue with"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    d = os.path.join(ROOT, "data", "genomics")
    ap.add_argument("--labels", default=os.path.join(d, "raw", "brca1-findlay2018-snvs.csv"))
    ap.add_argument("--scores", default=os.path.join(d, "evo2-scores.csv"))
    ap.add_argument("--sources", default=os.path.join(d, "sources.json"))
    ap.add_argument("--run", default=os.path.join(d, "evo2-run.json"), help="run metrics written by score_evo2.py")
    ap.add_argument("--out", default=os.path.join(d, "brca1-evo2-v1.json"))
    ap.add_argument("--probe", default=os.path.join(d, "evo2-probe.json"), help="probe result written by score_evo2.py")
    ap.add_argument("--host-authorisation", default=os.path.join(d, "host-authorisation.json"),
                    help="provenance of the GPU host the scores were produced on (whose host it is, on what basis)")
    ap.add_argument("--window-sample", default=os.path.join(d, "evo2-scores-w2048-sample.csv"),
                    help="optional scores of a sample of variants with another window")
    ap.add_argument("--score-column", default="evo2_delta_score")
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--lr-bins", type=int, default=LR_BINS)
    ap.add_argument("--interim-variants", type=int, default=240, help="size of the interim look recorded in runs/genomics.jsonl")
    ap.add_argument("--scoring-order", default=os.path.join(d, "evo2-scoring-order.csv"), help="variant keys in the order they were scored")
    args = ap.parse_args()

    sources = json.load(open(args.sources))
    run = json.load(open(args.run)) if os.path.exists(args.run) else {}
    # Kept in its own file so that copying a new run file from the GPU box does not erase it.
    gpu_host = json.load(open(args.host_authorisation)) if os.path.exists(args.host_authorisation) else None
    if not run.get("status_reason") and run.get("stopped_early_by_time_budget"):
        run["status_reason"] = (f"The scoring run stopped by itself at its time budget ({run.get('score_seconds_this_run')} s of scoring, ended "
                                f"{run.get('ts_utc_end')}), after {run.get('n_scored'):,} of {run.get('n_rows'):,} variants.")
    if not os.path.exists(args.scores):
        doc = not_run_document(sources, run)
        label_rows = read_csv(args.labels)
        doc["benchmark_check_without_model"] = {"assay_vs_clinvar": assay_vs_clinvar(label_rows, args.n_boot, args.seed)}
        doc["baselines_from_supplement"] = baselines_from_supplement(label_rows, args.n_boot, args.seed, args.lr_bins)
        return doc, args
    rows, n_labels, missing = load_joined(args.labels, args.scores, args.score_column)
    metrics = analyse(rows, args.n_boot, args.seed, args.lr_bins)
    compared = interim = None
    if os.path.exists(args.window_sample):
        compared = windows_compared(rows, args.window_sample, args.n_boot, args.seed)
        if os.path.exists(args.scoring_order):
            interim = interim_look(rows, args.window_sample, args.scoring_order, args.interim_variants)
    probe = json.load(open(args.probe)) if os.path.exists(args.probe) else {}
    probe_rows = [{k: e.get(k) for k in ("window", "status", "seconds_per_forward", "peak_allocated_bytes", "peak_reserved_bytes",
                                         "nvidia_smi_process_mib", "error")} for e in probe.get("probe", [])]
    deviations = []
    if run.get("window") != 8192:
        deviations.append(f"Window of {run.get('window')} bp instead of the 8,192 bp of the published notebook. 8,192 bp exceeded the GPU memory cap set for "
                          f"this job; {run.get('window')} bp fits the memory cap but a full run did not fit the time budget, so the run is partial (see runtime.probe).")
    ck = run.get("checkpoint", {})
    table, ref = sources["sources"]["findlay2018_table"], sources["sources"]["reference_grch37_chr17"]
    same = same_sample_comparison(rows, args.n_boot, args.seed, args.lr_bins)
    short = lambda v: None if not v or v.get("value") is None else {"value": v["value"], "ci95": v["ci95"]}
    me = metrics["missense_evidence"]
    headline = {
        "evidence_strength_basis": "missense variants only. A computational ACMG/AMP criterion (PP3 / BP4) is meant for missense variants; "
                                   "nonsense and canonical splice variants are covered by other criteria, so the all-consequence level is reference only.",
        "labels": "assay function classes in HAP1 cells (Findlay et al. 2018), a laboratory proxy; not clinical classifications",
        "variants_scored": len(rows), "variants_in_table": sources["clean_table"]["kept_snvs"],
        "n_lof": metrics["counts_scored_by_class"]["LOF"], "n_func": metrics["counts_scored_by_class"]["FUNC"],
        "missense_n_lof": me["n_lof"], "missense_n_func": me["n_func"],
        "auroc_lof_vs_func": short(metrics["auroc_lof_vs_func"]),
        "auroc_missense": short(metrics["auroc_by_consequence"].get("Missense")),
        "missense_strongest_reached": me.get("strongest_reached"),
        "missense_strongest_reached_with_clustered_exact_bound_in_every_bin": me.get("strongest_reached_with_clustered_exact_bound_in_every_bin"),
        "missense_n_bins": me.get("n_bins"),
        "evo2_minus_cadd_same_variants": same["evo2_minus"]["cadd"],
        "all_consequences_strongest_reached_reference_only": {k: v["strongest_reached"] for k, v in metrics["acmg_amp_evidence"].items()},
        "window_caveat": f"the {run.get('window'):,} bp window was kept after an interim look at the data, so its AUROC is the larger of two estimates "
                         "(see method.window_choice and windows_compared)",
    }
    doc = {
        "schemaVersion": 2,
        "id": "brca1-evo2-v1",
        "statement": STATEMENT,
        "status": "complete" if len(rows) == sources["clean_table"]["kept_snvs"] else "partial",
        "status_reason": run.get("status_reason"),
        "gpu_host": gpu_host,
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headline": headline,
        "model": {
            "name": ck.get("model_name"), "repository": ck.get("hf_repo"), "revision": ck.get("hf_revision"),
            "weights_file": ck.get("weights_file"), "weights_bytes": ck.get("weights_bytes"),
            "weights_sha256": ck.get("weights_sha256_from_cache_blob_name"),
            "licence": "Apache-2.0 (code and weights, per the repository and model card)",
            "route": "open weights run directly with the evo2 Python package; the NVIDIA BioNeMo Evo 2 NIM was not used because no NVIDIA API key was available",
            "precision": "bfloat16 without Transformer Engine (the 7B family is the only one supported that way)",
            "packages": {k: run.get(k) for k in ("evo2", "vtx", "torch", "torch_cuda", "flash_attn", "transformer_engine")},
            "gpu": run.get("gpu"),
        },
        "data": {
            "benchmark": table["description"], "citation": table["citation"], "url": table["url"],
            "sha256": table["sha256"], "bytes": table["bytes"],
            "reference_sequence": {"description": ref["description"], "url": ref["url"], "sha256": ref["sha256"],
                                   "fasta_header": ref.get("fasta_header")},
            "coordinates": sources["clean_table"]["coordinates"],
            "variants_in_table": sources["clean_table"]["kept_snvs"],
            "variants_scored": len(rows), "variants_scored_without_label": missing,
            "counts_by_class": sources["clean_table"]["func_class_counts"],
            "counts_by_consequence": sources["clean_table"]["consequence_counts"],
            "counts_by_clinvar": sources["clean_table"]["clinvar_simple_counts"],
        },
        "method": {
            "window_bp": run.get("window"), "strand": run.get("strand"),
            "window_rule": "window/2 bases upstream of the variant, the variant, window/2 - 1 downstream, on the plus strand of GRCh37 (BRCA1 itself lies on the minus strand)",
            "delta": "mean log-likelihood(alternate window) - mean log-likelihood(reference window)",
            "score_column": args.score_column, "batch_size": run.get("batch_size"),
            "reverse_complement_averaging": run.get("average_reverse_complement"),
            "notebook_window_bp": 8192, "deviations_from_notebook": deviations,
            "window_choice": {"settled_during_the_run": True, "interim_look": interim,
                              "consequence": "the detailed tables use the longer window, which looked better at the interim look; its AUROC is the larger of two estimates and both windows are reported in windows_compared"},
        },
        "runtime": {k: run.get(k) for k in (
            "source_of_this_file", "seconds_per_forward_source", "peak_memory_source", "n_scored_on_gpu_box_when_last_seen",
            "host", "ts_utc_start", "ts_utc_end", "complete", "stopped_early_by_time_budget", "n_scored",
            "n_unique_ref_windows", "forward_passes_this_run", "score_seconds_this_run", "seconds_per_forward",
            "seconds_per_variant_this_run", "load_seconds", "peak_allocated_bytes", "peak_reserved_bytes",
            "nvidia_smi_process_mib_max_sampled", "cap_gib", "n_resumed_from_checkpoint") if k in run}
        | {"gpu_memory_limit_for_this_job": "18 GB (17,166 MiB as nvidia-smi reports it); PyTorch allocator capped at cap_gib",
           "probe": probe_rows},
        "windows_compared": compared,
        "metrics": {k: v for k, v in metrics.items() if k not in ("likelihood_ratio_table", "acmg_amp_evidence", "missense_evidence")},
        "missense_evidence": metrics["missense_evidence"],
        "likelihood_ratio_table": metrics["likelihood_ratio_table"],
        "acmg_amp_evidence": metrics["acmg_amp_evidence"],
        "same_sample_comparison": same,
        "baselines_from_supplement": baselines_from_supplement(read_csv(args.labels), args.n_boot, args.seed, args.lr_bins),
        "published_values_not_reproduced": sources.get("published_values"),
        "limits": [],
    }
    return doc, args


def not_run_document(sources, run):
    """Document written when no model scores exist: data provenance and the verified evidence
    thresholds only. It contains no model metric, because none was measured."""
    table, ref = sources["sources"]["findlay2018_table"], sources["sources"]["reference_grch37_chr17"]
    return {
        "schemaVersion": 1, "id": "brca1-evo2-v1", "statement": STATEMENT, "status": "not_run",
        "status_reason": run.get("status_reason", "No Evo 2 scores were produced; see runs/genomics.jsonl."),
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": {"name": run.get("intended_model"), "repository": run.get("intended_repository"), "revision": None,
                  "route": "open weights run directly with the evo2 Python package; the NVIDIA BioNeMo Evo 2 NIM was not used because no NVIDIA API key was available",
                  "install_progress": run.get("install_progress")},
        "data": {"benchmark": table["description"], "citation": table["citation"], "url": table["url"],
                 "sha256": table["sha256"], "bytes": table["bytes"],
                 "reference_sequence": {"description": ref["description"], "url": ref["url"], "sha256": ref["sha256"],
                                        "fasta_header": ref.get("fasta_header")},
                 "coordinates": sources["clean_table"]["coordinates"],
                 "variants_in_table": sources["clean_table"]["kept_snvs"], "variants_scored": 0,
                 "counts_by_class": sources["clean_table"]["func_class_counts"],
                 "counts_by_consequence": sources["clean_table"]["consequence_counts"],
                 "counts_by_clinvar": sources["clean_table"]["clinvar_simple_counts"]},
        "method": {"window_bp": None, "planned_window_bp": 8192, "strand": "+",
                   "delta": "mean log-likelihood(alternate window) - mean log-likelihood(reference window)"},
        "runtime": None, "metrics": None, "likelihood_ratio_table": None,
        "acmg_amp_evidence": {name: {"prior": c["prior"], "source": c["source"],
                                     "strength_targets": {st: {"lr": strength_lr(name, st),
                                                               "posterior_at_prior": posterior(strength_lr(name, st), c["prior"])}
                                                          for st in STRENGTH_ORDER},
                                     "thresholds": "none measured", "share_reaching_at_least": "none measured"}
                              for name, c in CALIBRATIONS.items()},
        "limits": [],
    }


def write(doc, path):
    def clean(o):
        if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
            return None
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        return o
    with open(path, "w") as fh:
        json.dump(clean(doc), fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    document, arguments = main()
    limits_path = os.path.join(HERE, "limits.json")
    if os.path.exists(limits_path):
        il = ((document.get("method") or {}).get("window_choice") or {}).get("interim_look")
        ms = (document.get("missense_evidence") or {}).get("strongest_reached")
        mw = (document.get("missense_evidence") or {}).get("strongest_reached_with_clustered_exact_bound_in_every_bin")
        fill = {"{interim}": "values not available" if not il else
                f"{il['auroc_by_window']['4096']:.3f} against {il['auroc_by_window']['2048']:.3f} on the first {il['n_variants']} variants scored",
                "{missense_level}": "The evidence level for missense variants was not established." if not ms else
                "On this sample the strongest level reached for missense variants is: " + "; ".join(
                    f"{k} LOF direction {v['pathogenic']}, functional direction {v['benign']}" for k, v in ms.items()) + ".",
                "{missense_worst}": "" if not mw else
                "With the most cautious bound in every bin: " + "; ".join(
                    f"{k} LOF direction {v['pathogenic']}, functional direction {v['benign']}" for k, v in mw.items()) + "."}
        document["limits"] = [functools.reduce(lambda t, kv: t.replace(*kv), fill.items(), t) for t in json.load(open(limits_path))]
    if document["status"] == "not_run":
        document["limits"].insert(1, "Evo 2 was not run. This file holds no Evo 2 metric. The baselines are two established scores "
                                     "taken from the supplement (CADD and phyloP); they are not a foundation model and say nothing about Evo 2.")
    elif document["status"] == "partial":
        document["limits"].insert(1, "Only part of the benchmark was scored (see data.variants_scored). The positions scored are a random "
                                     "sample, so the metrics are estimates on that sample with wider uncertainty than a full run. Score bins then hold few "
                                     "variants each, so the likelihood-ratio bounds are weak and the strength reached is limited by the sample size as much as by the model.")
    write(document, arguments.out)
    if document["status"] == "not_run":
        print(json.dumps({"out": os.path.relpath(arguments.out, ROOT), "status": "not_run", "variants_scored": 0}))
        sys.exit(0)
    m = document["metrics"]
    print(json.dumps({"out": os.path.relpath(arguments.out, ROOT), "status": document["status"],
                      "variants_scored": document["data"]["variants_scored"],
                      "auroc_lof_vs_func": m["auroc_lof_vs_func"]["value"], "ci95": m["auroc_lof_vs_func"]["ci95"],
                      "average_precision": m["average_precision_lof_vs_func"]["value"],
                      "brier": m["calibration"]["brier_score"],
                      "strongest_reached_all_consequences": {k: v["strongest_reached"] for k, v in document["acmg_amp_evidence"].items()},
                      "strongest_reached_missense": document["missense_evidence"].get("strongest_reached")}, indent=1))
