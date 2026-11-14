# Chibi Lens root-cause correction — real cross-scene / open-set evaluation

Work ID `CHIBI-LENS-ROOTCAUSE-FIX-20261114`, task branch `codex/chibi-lens-generalization-fix-20261114`. Stacked on independent R3 PR #178 (which stacks R8 #177, real public YCB-V #173 and synthetic Meta R #163). This document records **changed science**, not proof of live Meta wearable recognition, production readiness or a new paid service. All R training is source-bound to a task commit; existing eight R8 and three R3 experiments are preserved and not rerun.

## Reproduced reasons the prior 8+3 R experiments failed

1. **Effective sample size was much lower than 525 images.** Training used only four physical YCB-V source scenes. A source video contributes many correlated frames, so treating every object crop as an independent learning example inflates confidence. The 225-crop heldout was only three physical scenes.
2. **The heldout labels were nearly perfectly entangled with the scene.** In that three-class YCB-V study, separate test scenes 56,57,58 each held a different target class (1,12,3); a model could learn colors/camera surroundings rather than visual semantics. Scene-heldout did not mean class-balanced heldout. The previous 4-class source heldout was also only a single scene.
3. **Feature representations were too weak.** Old models used 48 simple color/spatial/gradient measurements on cropped pixels, with no frozen semantic image backbone. Background may remain inside visible bounding rectangles; the model could exploit contextual shortcuts.
4. **Empirical <=5% calibration wrong-accept was overinterpreted.** Under physical scene shift, the original all-feature R model still made **72/300** accepted-wrong predictions, color **26/300**. The second R8 study's eight variants had no safe holdout result. Its R3 classwise exact risk-bound lowered wrong accepts from 62 to 49 of 225, but correct accepted fell from 149 to 78; metadata Mahalanobis shield worsened wrong accepts from 62 to 72. A binomial bound estimated on one calibration scene cannot guarantee low error on another.
5. **Volume of CRACI jobs was a proxy for productivity, not quality.** The observed eight and three CPU cohort runs were source-verified and technically green; these are workflow successes, not demonstrated model improvement.

These findings are derived from exact immutable results: [R8 training #43635307560](https://github.com/SalesSquad/junction-pets/actions/runs/43635307560), [R8 remaining #43635610887](https://github.com/SalesSquad/junction-pets/actions/runs/43635610887), and R3 [#43636400308](https://github.com/SalesSquad/junction-pets/actions/runs/43636400308) / [#43636605103](https://github.com/SalesSquad/junction-pets/actions/runs/43636605103), preserved in PRs #177/#178.

## Actual correction: independently sourced HomebrewedDB real camera data

Fresh REAL public benchmark: **BOP HomebrewedDB (HB) RGB-D**, from Kaskman et al., ICCVW 2019; [BOP official dataset and CC0 licensing](https://bop.felk.cvut.cz/datasets/). Exact source archive `hb_val_primesense.zip` in BOP Hugging Face has official pointer SHA-256 `8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f`, 2,354,714,266 bytes. The full archive was **NOT** downloaded or independently hashed; a custom, bounded HTTPS **byte-range ZIP central-directory reader** verifies the official linked source pointer and per-accessed-member ZIP CRC32/byte length. The archive's original 13 physical scenes and GT were inspected. Source and license: CC0 1.0, **not private or personal**.

Pre-registered experimental split with *the same known object labels present in all physical scenes*:
- **train**: public physical scenes 5+9, known classes 12+15 only;
- **calibration**: scene 10, known 12+15 + hard unknown distractors 3,22,23;
- **heldout**: distinct scene 11, same known classes 12+15 + unknown distractors, never used for fitting/thresholding/model selection.

The extraction downloaded **only required byte ranges**, opened 192 public real RGB frames, used BOP `bbox_visib` and `mask_visib` strictly to create 655 local public object crops with **object-background pixels neutralized to gray**. These ROI/ground-truth masks are not model input features. Actual verified counts: 186 known train, 234 cal (91 known, 143 unknown), 235 test (93 known, 142 unknown). Each source scene contributes 48 selected camera frames; at least 40 known examples from each train scene and both known classes in all scenes. Original camera frames and temporary masked image crops remain in task-owned local Mac scratch, never in GitHub/CRACI.

Apple Vision `VNGenerateImageFeaturePrintRequest(revision:2)` ran locally on the authorized Mac Mini, with **655/655** 768-dimensional Float32 image embeddings, no OCR, personal screenshots or network model inference. `scripts/craci/LensHBFeaturePrint.swift` is a local source tool; Vision network and pretrained weights were not modified. `scripts/craci/lens_hb_finalize.py` L2-normalized the embeddings and stored *only numerical* 768d Vision features, 48 prior RGB/luminance/edge features, source scene metadata and immutable data checksums in **Parquet and CSV**, with privacy/source admission JSON. No raw image or personal identifiers in the repository, no private ScreenshotContext/Taimi Lens access.

## Four useful experiments instead of repeated green cohorts

The manual CRACI workload `lens-hb-vision` has four CPU-4 candidate model arms:
1. `color`: old train-normalized color histogram logistic baseline, 3 decay variants.
2. `vision_prototype`: train-only normalized Vision class prototypes, 3 pre-registered similarity/margin variants.
3. `vision_pca`: train-only PCA of Vision embeddings (8/16/32 components) with regularized logistic regression.
4. `vision_guard`: train-only Vision PCA + image-embedding prototype similarity OOD gate, before calibration confidence.

**One original color baseline is refitted identically in each source-bound arm**, to compare on exact splits. Each candidate has three parameter settings chosen **only** on physical calibration scene 10, requiring no more than `floor(.05 * 234)=11` accepted wrong proposals across both known misclassifications AND unknown objects. No final heldout labels enter model fits, thresholding or candidate selection. The immutable physical test scene 11 is evaluated only after fitting/selection. Unlike the prior scripts, unknown object false acceptance and known-object coverage are both first-class outputs, alongside abstentions, per-object ground truth and a *frame-clustered* exploratory bootstrap interval (not an IID guarantee or provider attestation).

A model can earn an **exploratory** diagnostic flag only if in the never-before-used scene 11 it admits at most `floor(.05*235)=11` wrong object proposals, has <=5% unknown-item false accepts, captures >=20% of known objects correctly, and is not worse than the color baseline. **No hosted result automatically promotes or deploys a model.** One physical heldout scene and correlated video frames cannot establish wide-world performance, biometric identity or host tool authorization; further new field scenes and a real object detector are needed.

The standard source-bound CRACI result uses 4×4 vCPU (20-minute hard caps), with one `pilot` arm first and three new `remaining` arms only after the pilot has actually qualified. No repeated green matrix or accidental client invoices. On existing promotional credit (repository cap €1,000), 4×4×20 plus 2-vCPU planner 5 min is at most ~330 vCPU-min before provider variance, **actual provider billing UNKNOWN**. The approved global credit window remains open only through **2026-11-15T17:00:00Z** (19:00 Helsinki), with an independent owner shutdown and no changes to expired three-hour Immune/Chaos campaigns.

## Red-line rules

- Never export raw personally captured video, private iCloud screenshots, family photos, OCR text, API tokens, wearable image sequences or event ceremony recordings to CRACI.
- Never use source label, exact scene, camera intrinsics, ground-truth visibility, mask, bbox or sample ID as a predictor. These can be used for offline annotation/audit only.
- Never claim official BOP leaderboard comparability: this pipeline repurposes a BOP validation source for *its own* train/cal/test experiment.
- Never retune/test again on scene 11 after observing outcomes. Preserve negative receipts. Success is model quality, not number of CRACI jobs.
- No live Meta glasses model is built or installed; Chibi production identity, OAuth/Cedar consent and parent permissions remain independent.
