# CRACI Chibi Lens R Model Tournament — 8 machines, 240k synthetic observations

Work ID `CRACI-META-R-SCALE-20261114`. Stacked development slice after [PR #155](https://github.com/SalesSquad/junction-pets/pull/155). Exact baseline source: [Meta ML draft PR #70](https://github.com/SalesSquad/junction-pets/pull/70), pinned commit `634f1e0e6cb2de46bcf0a783532d46c23f513d11`. This branch **does not** modify Meta's owned source files, Chibi private runtime, credentials, production traffic, or the expired three-hour Immune/Chaos runs.

## Why add another model family

Rokoko's completed four-CPU cohort R tournament showed no advantage over the fixed PUSH_MEDIUM baseline. Rather than repeat negative results, use the already trained Chibi Lens **five-score synthetic candidate ranker** as a second independent hypothesis. The original is an authenticated repository checkpoint, not a live camera/VLM model. Five features: `visual`, `text`, `shape`, `quality`, `recency`. No actual photos, identifying personal data, private prompts or sensor recordings are downloaded.

Each new CRACI trial uses the pinned exact Python `synthetic_examples` generator and frozen `trained-candidate-v1.json` model as source. The baseline's hard-negative and label-shift behavior is preserved. Eight disjoint seeded cohorts produce 20,000 synthetic training, 5,000 synthetic calibration and 5,000 **fresh distribution-shifted** observations each: **240,000 observations total**. Generator SHA256, original checkpoint SHA256, output CSV SHA256, source commit and seed IDs are saved in each cohort receipt.

## Models and no-leakage rule

R trains four models per cohort: main-effect logistic GLM, interaction GLM, rpart depth-3 tree, and rpart depth-5 tree. Thus **32 newly fitted R model variants** across eight trials, plus frozen and recalibrated baselines. No identity labels, row IDs, future outcomes, split names or baseline probabilities are model input features. Training is only on the 20,000-example cohort training split. All thresholds are calibrated to **at most 5% negative candidate rate** on calibration data, using exact conservative order statistics. An R model can replace the **same-calibration frozen baseline** only if its validation recall improves while FPR does not increase. No new model is promoted merely for improving on a stale fixed threshold.

The 5,000-example shifted holdout is touched only after selecting a model, and its **FPR, positive recall, hard-negative FPR, Brier score, abstention and paired bootstrap confidence interval** are reported. Every alternative's shifted outcome is included for audit, but never used to reselect a winner. Any test degradation, especially false candidates, is retained as a negative finding. Model selection never issues identity or authorization grants: `identityVerified=false`, `actionAuthorized=false` in all outputs. These are **synthetic score models, not actual Meta glasses or vision model training**.

## Cloud execution and financial bounds

The existing manual `.github/workflows/craci-pilot.yml` adds `workload=meta-r-tournament` on this task-owned branch only. Eight different matrix cohorts use **eight CRACI runners**, 4 vCPU each, 20-minute hard timeout per machine, `max-parallel:8`. Network is default-deny with only `github` and `ubuntu` presets. R dependencies are drawn from the approved `ubuntu.sources` only, no external R package registry, Python standard library only, exact Git source and harness SHA checks. One replayable, source-bound `run-receipt.mjs` wraps the real training and separate artifact upload.

Only `.json` and `.zip` are placed under CRACI's audited artifact collector. `dataset.csv` and `trained-models.rds` are kept within isolated runner scratch until packed into `training-evidence.zip`, never triggering allowlist exceptions. No credentials, secrets or synthetic personal profiles are included. Eight × 4-vCPU × 20 minutes plus 5-minute 2-vCPU planner is **650 vCPU-min worst case**, before any provider variance. Pricing, promotional coverage and account-level concurrency are **unverified**; no cash/top-ups or new accounts authorized. Respect existing global CRACI credit deadline `2026-11-15T17:00:00Z` and separate owner of its shutdown task; this request does **not** reopen the three-hour campaigns that ended at `2026-11-14T18:00:00Z`.

## Completion criteria

Verify exact source/harness commit, 8/8 distinct job statuses, 8 unexpired artifacts, each `receipt.json` status `succeeded` with source/harness verified, all eight RDS archives and CSV digests, negative findings, and no overlapping seeds. If 8 jobs fail on an actionable source issue, repair on the same task branch and requalify failed paths without rewriting prior receipts; do not repeat completed/unchanged green cohorts. Any environment or billing limit must be reported as unverified rather than silently bypassed.

Integration owner: Portfolio PR Recovery; this task branch owns only additional additive CRACI workload and `scripts/craci/meta-r-*` scripts/docs/tests. Do not merge, deploy, or assert wearable model accuracy from synthetic metrics.
