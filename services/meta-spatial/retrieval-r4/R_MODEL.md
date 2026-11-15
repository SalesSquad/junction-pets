# R4 pairwise R reranker

Work: `META-LENS-R4-COVERAGE93-20261114`. The model is a small learned ranker
over the six explicitly allowed candidate features in `contract.json`. It is
research code, with actual training and qualification recorded separately by
the coordinator. Source presence is not evidence of an executed fit.

## Execution

The numerical fit uses base R (`stats::optim`, BFGS). Python 3, already required
by the candidate pipeline, validates the JSON admission manifest and SHA-256
bindings. No R package download, provider API or GPU is needed for this stage.

```sh
Rscript test_reranker.R
Rscript train_reranker.R --input /absolute/path/candidates.csv \
  --manifest /absolute/path/data_manifest.json \
  --output /absolute/path/new-r-training-output \
  --source-commit EXECUTED_40_CHARACTER_COMMIT
```

The optional `--maxit` argument is a bounded optimizer iteration limit (default
250, maximum 1,000). It does not change the predeclared hyperparameter grid.
Existing output artifacts are never overwritten. A failure records
`failure.json`; original partial outputs remain inspectable.

The manifest must declare `admission.family_disjoint=true`,
`admission.image_hash_disjoint=true`, exact ordered `feature_names`, and the
`input_sha256` of `candidates.csv`. The parser rejects duplicate JSON keys.
The R reader separately checks cross-split family and product identifiers,
candidate/query duplicates, at most one positive per query, finite numeric
features and the top-100 bound. Reciprocal-rank fusion may legitimately exclude
the original R3 rank-one candidate when capping the union. Original baseline
ranks remain unchanged as audit data, including ranks above one.
Image-hash admission is a source-builder assertion bound to exact input bytes;
R does not re-open the original images. Input and manifest hashes are checked
again after fitting.

## What is learned

For each training query with one exact positive candidate and at least one
negative, the ranker learns to give the positive a higher score. Its objective
is the mean weighted `log(1 + exp(-(positive_score - negative_score)))` plus
`lambda * sum(beta^2) / 2`. Stable softplus and `plogis` avoid overflow. The
weights give equal total mass to each usable family, then each query in that
family, then each negative candidate for the query. Candidate count and repeated
same-family queries therefore cannot silently dominate the fit.

Feature centers and scales use training rows only, balanced by family, query
and candidate. Constant training features have scale one. Identifiers, split,
family names, target labels and audit ranks never enter the feature matrix.
Missing-positive training queries cannot contribute a positive/negative pair;
their omission from the fitting objective is counted. They remain in all
reported retrieval denominators. No oracle positive is inserted.

`retained_candidate_r3_order` reports R3 ordering **within the retained union**.
It is not the original full-gallery R3 baseline: removing a wrong original top
candidate can improve this restricted ordering. The report counts queries whose
original rank-one candidate was retained or omitted; every query remains in the
denominator. The data manifest owns the separate full-gallery baseline.

The fixed ridge candidates are `0.01`, `0.1` and `1`. Development exact Recall@1
selects a candidate; MRR breaks a tie; original grid order breaks an exact tie.
The selected model is not refit on development, calibration or historical test.
The intercept is zero because pairwise comparisons cannot identify an
intercept. The exported score is a ranking score, not a probability.

## Acceptance and uncertainty

The confidence statistic is `top_score + (top_score - second_score)`. A query
with one candidate uses margin zero. Candidate ties use a stable candidate-ID
order. Twenty-one fixed quantile positions on **development confidence only**
define a finite threshold grid before calibration is read; duplicate threshold
values are collapsed.

Calibration reports query `wrong/accepted` separately from the fraction of
accepted families with any wrong accepted query. A threshold is eligible only
when empirical query error is at most 1% and the one-sided exact
Clopper–Pearson upper bound on the **accepted-family any-error event** is at
most 1%. The latter uses `alpha=0.05 / number_of_thresholds` to account for
selection across the fixed grid. Maximum calibration coverage selects an
eligible threshold; lower bound, then lower threshold break ties. This depends
on independent exchangeable source families, which the experiment does not
establish for a real wearable deployment.

This family-conditional statement is **not** a certificate of query-weighted
99% precision. The descriptive query binomial bound is also exported, labelled
with its independent-query assumption, which correlated families may violate.
No eligible threshold yields `calibrated=false` and `threshold=null`; runtime
must abstain. Absence of evidence is never represented as zero error.

Historical R3 test data have already been inspected. R4 test results are
diagnostic, even if recall, coverage or empirical error improve. Every exported
model therefore keeps `qualification=false`, `action_authorized=false` and
`physical_identity_verified=false`. The report gate is always `FAIL` for new
product qualification. Missing a positive inside the candidate set does not
constitute a realistic absent-catalog evaluation.

## Artifacts and runtime agreement

- `model.rds`: R model object, numeric scaler/coefficients and frozen policy.
- `model.json`: portable version of the same object. Feature order is exact;
  score is `(features - center) / scale` dot `coefficients` plus zero intercept.
- `predictions.csv`: all original candidate pairs and their learned `rank_score`.
- `query_metrics.csv`: per-query ranking, missing-positive and confidence facts.
- `report.json`: fixed candidate fits, development selection, per-split results,
  policy diagnostics, source/input bindings, elapsed execution and artifact hashes.

The producer emits finite numeric JSON with 17 significant digits. The Python
consumer must independently enforce its exact schema/feature order, dimensions,
finite values, positive scales, provenance and permanently withheld qualification.

The focused test script checks the analytic gradient against finite differences,
real fitted parameter movement, data leakage boundaries, missing-positive
denominators, deterministic ties, calibration insufficiency, family clustering,
valid omission of an original top-one candidate, input/hash refusal and JSON
portability. The coordinator records actual results.
