# Chibi Lens R8 — eight CRACI training / metadata loops

Work ID: `CHIBI-LENS-R8-METADATA-20261114`. Separate task-owned development branch stacked on PR #173, which is itself stacked on #163. No merge, production model replacement, privacy grant or new vendor spending.

## Why a new object set
The prior real-image CRACI run #43633058307 trained color/texture R models on 4 object classes (4,6,9,15). On its fixed single heldout scene 59, 0/4 profiles met the absolute 5% wrongly accepted objective (color 26/300; full 72/300). **Re-running on that exact final test would be test leakage.**

Instead this experiment changes the hypothesis and object classes to **1, 3, 12** using only the previously fetched public BOP YCB-V MIT test-bop19 ZIP, exact SHA `c0c11251849877e7b2f373f6c7acf54739dc69d0fb2649c20050ca977bf5513d`. All data and rights are pinned; source license official <https://bop.felk.cvut.cz/datasets/>. It is not official BOP scoring or a live wearable benchmark.

`scripts/craci/lens-r8-contrast.py` extracts 975 **new** public real-camera object crops from 600 frames in eight physical scenes. Train scenes 48,49,51,54 (525 crops), calibration scene 55 (225), final diagnostic scenes 56,57,58 (225). New labels 1,3,12 have 150/225/150 train, 75/75/75 calibration, 75/75/75 test. Objects in an individual final scene are confounded with that scene, so generalization cannot be certified from this one study. Source-scene context partially overlaps the previous study, but the object labels/crops and held-out categories do not.

Each observation contains 48 numeric actual image features from the existing public extractor, plus **runtime-observable** pixel brightness/contrast/saturation/edge strength. Its separate `scene-metadata.json` holds camera intrinsics, bbox size, occlusion and class/scene/illumination summaries. **GT scene, frame IDs, label, visibility and bbox/camera information cannot be predictors**: they are explicitly excluded by `scripts/craci/lens-r8-model.R`, and are used only for provenance and post-selection failure slices. No raw frame pixels, user photos, personal OCR, child images, owner ceremony videos or private ScreenshotContext data are exported. Numeric Parquet/CSV+JSON only. No vision foundation model weights are trained.

`scripts/craci/lens-r8-admission.py` demands exact real public MIT source digest and exact derived CSV/Parquet/scene-metadata digests, prohibits symlinks/extra files and checks the owner source registry's quarantine status for all private sources. The original owner sources remain unmodified. No generic bypass flag.

## Eight independent R arms

1. `color-logit` — 24-bin RGB logistic regression.
2. `color-balanced` — class-reweighted RGB logistic regression, per-predicted-class calibration.
3. `fusion-logit` — 48-bin color, spatial and edge logistic regression.
4. `fusion-balanced` — class-reweighted 48-bin fusion, per-class calibration.
5. `texture-tree` — interpretable rpart on luminance/edge structure.
6. `quality-logit` — 48 visual plus four **observable** pixel-quality predictors; brightness-bin risk calibration.
7. `centroid-shrink` — train-only learned prototypes with three explicit distance temperatures.
8. `consensus-ensemble` — RGB logistic plus centroid confidence fusion, with three pre-specified mixture weights.

Each CPU lane evaluates **three pre-registered hyperparameters on calibration only**; the preferred candidate is frozen before test, and a train-only centroid baseline gets the identical fixed calibration opportunity. No test-driven hyperparameter/arm selection. Per-arm reports include train/cal/final counts, accepted correct, accepted wrong, abstentions, baseline, and metadata slices for scene, class, observable brightness, and ground-truth-only visibility/bbox. Empirical `wrongAccepted <= floor(.05*n_cal)` is required on calibration; unseen class/quality groups fail-closed to abstain. A limited *exploratory* quality claim requires <=5% test errors overall and in **every** test scene, plus improvement over the baseline. No cross-arm winner is automatically deployed, especially because the 8 arms are multiple comparisons on partly familiar BOP videos.

## CRACI execution and iteration

Existing manual `.github/workflows/craci-pilot.yml` adds opt-in `workload=lens-r8-meta`, 8 independent CRACI runner jobs (4 vCPU each, max 8 concurrent, max 20 min). `lane_slice=pilot` checks the first arm only; `lane_slice=remaining` checks the other 7 after the pilot qualifies, avoiding repeating the green tuple. After successful eight-lane qualification, new iterations require **new independent hypothesis/scene source or a concrete failing path**, not resampling the same heldout until green. Keep failed receipts; don't loosen empirical risk gates.

The network is CRACI `default:deny` with `[github,ubuntu]`; R packages come only from Ubuntu apt. The familiar pinned `run-receipt.mjs` produces source-reported (not provider-signed) provenance; evidence uploads contain only allowlisted JSON and ZIP with RDS models. No raw pixels are uploaded. One eight-arm batch worst-case 8×4 CPU×20 min + 2 CPU×5 min planner = **650 vCPU-min**; actual provider billing and usable credit are unverified. Stay within the existing Junction CRACI promotional credit (repo cap €1,000) and deadline **2026-11-15 17:00 UTC**; do not reopen separate expired Immune/Chaos three-hour campaigns or change global credit flags. No new payment method/top-up/credentials.

## Integration boundary and decision
This is a Junction public-research numeric model experiment. Private Chibi controls consent, identity, memory and model/provider execution. There is no Chibi runtime adapter or real glasses capture here. All test artifacts and any negative observations must be carried forward. A convincing camera-native product model requires **new independently labelled licensed/consented scenes, a real detector and privacy-preserving on-device evaluation**, which no synthetic/scene-heldout R result can replace.
