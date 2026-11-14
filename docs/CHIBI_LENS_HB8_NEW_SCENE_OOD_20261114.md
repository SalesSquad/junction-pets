# Chibi Lens: independent public HB scene 8 OOD and Pareto-safe selection

**Work ID:** CHIBI-LENS-HB8-OOD-20261114. This is an isolated stacked experiment on exact parent [PR #190](https://github.com/SalesSquad/junction-pets/pull/190) source commit `3f8d57cbd47e07be97137e03121205248e88d56f`. The existing source owner retains `lens_hb_r_train.R`; this branch only adds new scene8-specific tooling and one fixed manual CRACI job. Portfolio PR Recovery remains sole default-branch integrator. No merge or deployment.

## Why this experiment is new

Original four CRACI HB Vision arms on [43640473902](https://github.com/SalesSquad/junction-pets/actions/runs/43640473902) and [43640703367](https://github.com/SalesSquad/junction-pets/actions/runs/43640703367) all ran but chose the abstain-all baseline. Exact source review found that `lens_hb_r_train.R` ranks candidates by highest calibration correct-known count **before** checking the no-worse-than-baseline wrong acceptance constraint, discarding feasible 56-correct/0-wrong calibration alternatives. That defect is assigned to the original owner in PR #190 comment 6884236529; it has not been silently edited or its validators relaxed here.

Read-only census of the CC0 public HomebrewedDB `hb_val_primesense.zip` from official HF range index shows that original known object classes 12 and 15 coexist only in physical scenes 5,9,10,11; all four were previously used. There is no genuinely fresh both-class test scene in this archive. **Fresh scene 8** instead has original object classes 11,15,22,24,31,32. It provides an independent, narrower **known15 detection vs five unknown-class rejection** experiment; original known12 is entirely absent.

Our new public-only source data: **282 object crops from 48 real source frames**, including known15=42 and unknown objects 11,22,24,31,32 each 48 examples. Exact public archive official HF pointer SHA256 `8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f`, 2,354,714,266 bytes. Individual downloaded ZIP members passed CRC; full 2.35GB archive was **not** rehashed. Image masks remove all nonobject RGB background. The Mac Mini generated 282 local Apple Vision revision2 Float32 768-dimensional FeaturePrint embeddings, plus 48 public RGB histogram features. **Only 282 public numeric-feature CSV rows and a provenance JSON are committed.** Original PNG frames and intermediate crops remain in task-owned local scratch, never uploaded. No owner, child, family, screenshot/OCR or event media used.

## Frozen evaluation contract

- Train new fixed public class prototypes strictly from original 186 examples, **train physical scenes 5+9**; calibrate with **234 examples from scene 10**. Original previously exposed physical heldout **scene 11 is ignored** and cannot qualify this run.
- Prototype `temperature=25` and train-only 12th-percentile similarity gate are predeclared from the earlier calibration receipt. The calibration Pareto selection takes any candidate satisfying *no increase in accepted wrongs compared with the frozen calibrated baseline* before ranking correct knowns. **It does not increase the existing 5% empirical calibration cap** or tune using scene8 labels.
- Admit **one** new physical scene8 evaluation with 48 frame groups, known15 coverage and *unknown* false acceptance. Compute paired group-level bootstrap 95% CI; report no gain if the lower bound is not positive, any unknown false acceptance exceeds 5%, any accepted wrong count exceeds baseline, or calibration violates its previous constraints. A result may be a scientific RED even if the job succeeds.
- Scene8 has **no known class12**, and only one new physical scene. No balanced two-class recognition, official BOP benchmark, device identity, real Meta glasses behavior, user consent, agent tool authorization or hardware safety is claimed. Model deployment remains forbidden regardless of score. Never reuse this exposed scene8 to tune and call it blind later.

## Resource and ownership

The existing one authorized workflow `417767938` gains one **manual** `lens-hb-scene8-ood` cell, exactly pinned to its source/harness full SHA, CPU4 at most 20 minutes, network default-deny `github,ubuntu`, 7-day receipts with negative outcomes preserved. No new runner, vendor, GitHub daemon, credential, cash payment, webhook or production request. Conservative list-price reservation is **EUR0.153** (one 4-vCPU x 20min job plus 2-vCPU x 5min source-planning), actual provider bill and signed attestation unknown. Existing `CRACI_CREDIT_WINDOW_OPEN` flag and cutoff **15 Nov 2026 17:00 UTC** unchanged.

On an exact verified source HEAD, run once:

`gh workflow run craci-pilot.yml -R SalesSquad/junction-pets --ref codex/chibi-lens-hb8-ood-20261114 -f workload=lens-hb-scene8-ood -f source_sha=FULL_TASK_HEAD`

Record actual job run, exact source and harness identity, model RDS/JSON artifacts, adverse results and next source-owner action in this PR. Tests are scoped to new files: source admission positive/negative, source-byte digests, no raw media upload, planner one-cell pin/refusal, R parse/fit on verified executor, and actual hosted receipt.
