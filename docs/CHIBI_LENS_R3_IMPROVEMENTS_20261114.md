# Chibi Lens: three distinct CRACI/R improvements

Work ID `CHIBI-LENS-R3-IMPROVEMENTS-20261114`. This is an additive, task-owned source branch stacked on R8 PR #177, itself stacked on the licensed real-image feature PR #173 and synthetic meta R PR #163. No merge/production deployment, credential/permission changes, private image capture, or new provider contracts.

## Baseline and source / strict interpretation

R8 original pilot [run 43635307560](https://github.com/SalesSquad/junction-pets/actions/runs/43635307560) finished 1/1, and remaining seven [run 43635610887](https://github.com/SalesSquad/junction-pets/actions/runs/43635610887) finished 7/7 with source-bound successful RDS receipts. All **eight R8 methods failed the safe promotion rule** on the same fixed physical-scene holdout. Examples: color-logit 66/225 wrong accepted; quality-logit 53/225; fusion-balanced 49/225; consensus-ensemble 47/225. Texture-tree's 0 wrong was achieved by 0 correct accepted, not usable progress.

These three newly implemented hypotheses use the same pinned, public **MIT BOP YCB-V** numeric feature/quality metadata fixture only: classes 1,3,12, **525 train / 225 calibration / 225 heldout** RGB object crops; eight distinct physical source scenes. Historical source image archive SHA-256 `c0c11251849877e7b2f373f6c7acf54739dc69d0fb2649c20050ca977bf5513d`. Committed numeric CSV digest `a6d1ca17664544645a3fc26a7d8d9caba6c1d85b58bea00afc0125e991b9a015`, metadata and Parquet additionally source-bound by `scripts/craci/lens-r8-admission.py`. No raw RGB frames, original JPEG/PNG, private ScreenshotContext OCR, ceremony recordings, family/child photos or personal hardware data are exported to CRACI. Metadata ground truth scene, labels, BOP camera, physical bbox and visibility are audit-only, not learned predictors.

**Critical limitation:** R8 has already used these physical heldout frames. New analyses on the same fixed holdout are **posthoc research diagnostics**, NOT a fresh independent qualification or a new opportunity to claim real-scene generalization. All scripts label themselves `POSTHOC_EXPLORATORY_ONLY_SAME_PRIOR_BOP_SCENES`. Even if a new model passes a numeric 5% posthoc condition, deployment remains blocked without new independently obtained physical scenes from an approved license/scope.

## Three new algorithmic approaches, not three repeats

1. **Class-conditional exact risk bound (`risk-upper`).** Fit one frozen train-only color multinomial model, then on calibration data, choose per-predicted-class acceptance thresholds using a one-sided **95% Clopper–Pearson upper confidence bound**. Require that bound to be <=5% for each class (zero accepted samples never imply safety). Under independent identically distributed conditions this is more conservative than the former raw empirical `floor(0.05*n)` rule; under genuine scene shift it is **not** a distribution-free or simultaneous multiple-testing guarantee. Report every class's admitted samples, wrong count, upper bound, and heldout acceptance. Its goal is to reduce confidently wrong suggestions by abstaining rather than falsely promising recall.
2. **Image-quality distribution-shift shield (`metadata-shield`).** Fit real labeled RGB+image-observable brightness/contrast/saturation/edge on train only. Fit a regularized 4D covariance on train **without labels**, then set a quadratic-distance cutoff using only the calibration set's unlabelled 90th percentile. Reject unusually shifted image quality even if the color classifier is highly confident; separately choose a calibration wrong-accept threshold. Report how many heldout samples were blocked, how many baseline mistakes would be blocked, remaining coverage, false accepts, and per-scene metadata diagnostics. No ground-truth scene/occlusion/camera values enter this decision.
3. **Out-of-scene hard-negative teacher (`hard-negative`).** Train **four separate out-of-scene models within TRAIN only** (each excludes exactly one train scene), score that excluded scene, and mark confident errors as hard examples (bounded max weight 4×) and ambiguous correct cases at 2×. Train three weighted multinomial model variants on the entire 525-sample training partition, choose only using calibration improvement over a common frozen color baseline *without increasing calibration wrong-accept count*. No test label or scene-ID enters hardness supervision. Report OOF train errors, training weights, calibration candidate comparison and heldout posthoc metrics. This can reveal whether baseline confusion is remediable by smarter sampling instead of more cycles of identical data.

The three methods share a deterministic baseline fitted on TRAIN, and append their own independent source-bound RDS and JSON evidence. The 225-row fixed heldout is read only after each method and calibration policy is frozen. The objective is to improve a **source-scoped decision process**, not claim a new 95%-accurate wearable classifier.

## CRACI execution and cost caps

The existing repo-authorized manual CRACI pilot workflow gains `workload=lens-r3-methods` with precisely three distinct CPU-4 cells (no dynamic self-repetition), `lane_slice=pilot` then `lane_slice=remaining`, source pin = harness commit, 20-minute hard timeout per cell, maximum three simultaneous jobs, `default:deny` network and only GitHub/Ubuntu package repositories. Source registration, SHA-256 and private-data exclusions are checked before training. R nnet/jsonlite dependencies use only pinned Ubuntu apt source, receipts from existing `run-receipt.mjs`, model and metadata in allowlisted JSON+ZIP artifacts. All source-reported evidence remains separate from provider-attested billing; **actual CRACI charges are unknown**. Worst-case reserved 3 × 4-vCPU × 20 min plus 2-vCPU × 5 min planner = 250 vCPU-min for one R3 wave, using only existing Junction-approved promotional credit, not cash/top-ups. Global window stops **2026-11-15 17:00 UTC** with its separate shutdown controller. This task does not revive expired three-hour Immune/Chaos campaigns.

Avoid repeating any of the 8 already-green R8 cohorts, and only requalify a failed R3 method after a material source fix. No test/validator downgrades, no public corpus augmentation without new provenance approval, and no automatic trained-model promotion. The next scientifically decisive milestone is new independently labelled, licensed real object scenes or on-device validation that has never been used for tuning.
## Completed CRACI hosted training and immutable evidence

Both **source-bound** CRACI workflows successfully completed at original experiment
harness SHA `08645c6d83e4fc47093a16220de36098f3f1e1b6`:

- [Pilot #43636400308](https://github.com/SalesSquad/junction-pets/actions/runs/43636400308): `risk-upper`, 1/1 CPU4 job and original R model archive.
- [Remaining #43636605103](https://github.com/SalesSquad/junction-pets/actions/runs/43636605103): `metadata-shield` and `hard-negative`, 2/2 CPU4 jobs and model archives.

The standalone `scripts/craci/lens-r3-audit.py` downloaded all three source-reported artifacts and independently checked the exact source/harness SHA, license/admission gate, no private media/OCR transfer, real nnet-trained RDS/model reports, common dataset and three unique method names. The archive's report bytes match the root report; calibration totals, accepted-correct/wrong counts and test metadata slices are consistent. Actual provider billing is **UNKNOWN** without authenticated provider invoices. These are GitHub-hosted source-reported receipts, not CRACI provider-signed attestations.

| New method | Calibration wrong /225 | Heldout accepted correct /225 | Heldout accepted wrong /225 | Abstained /225 | Baseline accepted correct/wrong | Model eligible for promotion? |
|---|---:|---:|---:|---:|---|---|
| Exact class-conditional upper risk bound | 0 | 78 | 49 (21.8%) | 98 | 149/62 | NO |
| Pixel-metadata Mahalanobis shift shield | 1 | 151 | 72 (32.0%) | 2 | 149/62 | NO |
| Train-scene OOF hard-negative weighting | 11 | 149 | 62 (27.6%) | 14 | 149/62 | NO |

The exact risk bound reduced false accepted claims by 13 but also reduced correct accepted suggestions by 71. Its per-class upper-bound calibration admitted 75 `1` samples and 61 `12` samples with 0 wrong, but **no** `3` samples; the independent physical scene test still shifted drastically, and an exact binomial bound on one calibration distribution does not imply distribution-shift safety.

The metadata shield rejected only **two** test examples as OOD and blocked **one** prior baseline mistake. Adding quality features actually increased wrong accepted suggestions by 10 while correct suggestions increased by 2. Thus this particular feature/threshold hypothesis **failed** and must not be advertised as drift immunity.

The OOF hard-negative teacher found 200 confident training-scene errors and 49 ambiguous training examples. Three weighted multinomial candidates were fitted, but calibration selected the unchanged baseline (variant index 0). No evidence that the reweighting helps, and no additional training on the fixed test should be initiated without new independent data.

**No method achieves the <=5% heldout wrong-accepted objective; no model has been deployed, promoted or integrated into Chibi.** The public BOP test-scenes are repeated from R8 and must remain explicitly labelled posthoc. Do not turn these results into official BOP leaderboard scores or claims about real Meta wearable recognition. The work's next legitimate evidence source is a new independently licensed and labelled set of physical capture scenes with hard unknown objects and controlled camera/lighting changes.

Permanent summary in this task branch: `docs/CHIBI_LENS_R3_RESULTS_20261114.json`, matched against original GitHub artifacts by the audit script, not by a later docs-only commit.
