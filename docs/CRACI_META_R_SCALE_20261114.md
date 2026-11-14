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

## Hosted wave 1: eight machines, results, and next scientific hypothesis

The first complete CRACI-hosted [run 43627971042](https://github.com/SalesSquad/junction-pets/actions/runs/43627971042) at harness `81f5208ee1ecd45b9bc72268fd18d57aca384034` succeeded **8/8 distinct CRACI CPU-4 jobs**. All eight receipts independently show `status=succeeded`, verified source and harness SHAs and `issues=[]`. Eight non-expired GitHub artifacts contain 32 R-model fit files in ZIPs, 240,000 synthetic observations, their matching SHA-256 digests and 24 unique experiment seeds. The original model version, source SHA `634f1e0e6cb2de46bcf0a783532d46c23f513d11`, was never edited.

Calibrated model selection: 2/8 cohorts kept the frozen-recalibrated baseline; 6/8 selected the interaction GLM on calibration data. **Every cohort reported `NO_RELIABLE_SHIFTED_GAIN`.** The interaction GLM sometimes improved shifted positive recall by ~2–4 percentage points but also increased false candidate rate versus the *same-calibration baseline*. Absolute shifted FPR was often ~10–15% despite the 5% threshold on the original-domain calibration split. No trained model was deployed or promoted. Negative findings and their bootstrap intervals remain in the exact GitHub artifacts; recalibration/selection has no impact on the host's identity/authorization checks.

### New distinct training hypothesis: shifted-domain calibration

Rather than re-run eight unchanged successful cohorts, admit a new explicit `meta-r-robust` workload: **12 CPU-4 CRACI jobs** (max eight concurrent), with **35,000 fresh observations per cohort**, or **420,000 total synthetic observations and 48 additional R fits**. The five new source-bound seeds per cohort (60 overall) are distinct from both original Meta model seeds and all 24 wave-1 cohort seeds.

Each robust cohort has: 10k normal + 10k *shifted* synthetic training observations; 5k independent shifted calibration observations; 5k independent shifted holdout; plus 5k normal holdout to check regressions. Holdout seeds are never used in fitting, feature engineering, thresholds or choice of model. The original trained baseline gets **the same shifted-calibration opportunity** as every candidate, to avoid artificially advantaging the new model. A candidate is favored only when its shifted calibration recall improves at no higher FPR. After the candidate is frozen, the report checks shifted holdout recall/FPR, paired bootstrap lower bound, **and** normal holdout FPR within one percentage point of the recalibrated baseline. `EXPLORATORY_SYNTHETIC_HELDOUT_GAIN` is permitted only when all checks pass; no runtime deployment is authorized even then.

The shift is a *known synthetic generator domain*. This is a **shift-conditioned synthetic comparison**, not a new real-world camera domain or proof of unseen-distribution robustness. If this hypothesis fails too, further synthetic resampling is low-value: prioritize licensed/consented real camera and OCR features rather than purchasing repeated runs on synthetic fixtures.

New workload shares the existing manual source-pinned CRACI job and unchanged fail-closed collector. All outputs remain source-reported, never provider-attested; provider billing amount remains unknown. The original eight-cohort run is preserved with its old exact SHA and is **not rerun** merely because the harness gains an additional robustness profile.
