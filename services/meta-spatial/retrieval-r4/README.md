# Meta Lens R4: trained candidate reranking

Two actual R training runs are complete. The selected research model improves
exact-product rank-one accuracy from **58.47% to 60.34%** on the preserved R3
historical test. **The >93% accepted-coverage target is not achieved.** No
calibration threshold met the declared error-evidence rule, so both exported
policies abstain. Models, reports, source hashes and numerical evidence are
preserved under `results/`.

This is an implemented and executed offline training/scoring pipeline. It does
not qualify a streaming-camera application, physical-object identity, or an
action in the private Chibi boundary.

## Measured results

Each test result uses the same 1,175 historical queries from 689 families.
The original R3 test had already been inspected before R4 and is diagnostic.

| Historical test metric | Original R3 | R4 run 01: RRF | R4 run 02: adapted top100 |
| --- | ---: | ---: | ---: |
| Exact product at rank one | 687 / 1,175 (58.47%) | 713 / 1,175 (60.68%) | **709 / 1,175 (60.34%)** |
| Exact product within top five | 84.00% | 85.70% | **86.04%** |
| Exact product within top ten | 90.38% | 92.51% | **92.43%** |
| Exact product retained within top100 | 99.23% | 97.70% | **99.23%** |
| Mean reciprocal rank | — | 0.72024 | **0.71916** |
| Eligible R4 calibration threshold | not comparable | none | **none** |
| R4 accepted coverage | not comparable | 0% | **0%** |

Run 02 is selected by **development exact Recall@1**, then MRR under
`comparison_protocol.json`. Development accuracy for run 01 is
**461/727 (63.41%)**, and for run 02 is **466/727
(64.10%)**. Selection deliberately follows development results even though
run 01 has slightly higher historical-test rank-one accuracy. Both runs remain
visible; no historical test result is treated as a fresh validation.

The R3 acceptance proposal covered 17/1,175 queries with one wrong acceptance
and was not qualified. R4 uses a different, stricter conditional calibration
rule. Its zero coverage is not a like-for-like ranking regression or a claim
of perfect precision: accepted precision is undefined with zero acceptances.

## What was trained

The visual encoder remains frozen: `google/siglip2-base-patch16-224`, revision
`75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2`. The images were genuinely encoded
in the prior NVIDIA A100 experiment. R4 reuses those hash-verified embeddings
and the selected, pinned R3 adapter.

Actual base-R optimization fits six ranking coefficients, with family/query
balanced pairwise logistic loss and a fixed ridge grid of `0.01, 0.1, 1`.
Both runs select `0.01` using development results. Inputs are frozen-image
similarity, adapted-image similarity, query-image to candidate-catalog-text
similarity, reverse rank, density correction, and adapted-score separation.
The query's title, catalog hint, true family and identity never enter the
feature allowlist. Same-family exact-product mismatches remain negatives;
missing positives are counted rather than injected.

| Partition | Queries | Purpose |
| --- | ---: | --- |
| Train | 3,313 | fit scaler and coefficients |
| Development | 727 | select from declared model/pool candidates |
| Calibration | 1,225 | freeze research acceptance policy |
| Historical test | 1,175 | diagnostic reporting only |

Each run exports **644,000 candidate rows**. Family, product and both original
image hashes are checked for separation across all prior/fresh partitions.
Reverse rank and density are explicitly transductive: they use unlabeled
queries in the same split. This is not a validated one-frame device protocol.

## Implemented components

- `features.py`: bounded deterministic pools, six permitted features, and a
  registered-multiview pooling helper with query/gallery image separation.
- `prepare_candidates.py`: immutable original-data/model admission and exact
  candidate CSV/manifest export. Explicit `rrf` and `adapted_topk` policies.
- `train_reranker.R`: real fitting, development selection, conditional
  calibration, numeric JSON/RDS models and per-query evaluation.
- `runtime.py`: portable hash-bound numeric scorer, bounded candidates and
  finite confidence. It always returns research-only, non-authorizing output.
- `run_experiment.py`: clean committed execution, bounded stages, preserved
  logs and exhaustive R/Python parity.
- `check_cached_numerics.py`: independent scalar/einsum check of 128
  predeclared label-blind image score comparisons.

The multiview helper is implemented and tested, but it was **not used** to
pretend that the historical two-view dataset contains extra capture angles.
No OCR, barcode capture, new image encoder fit, new GPU allocation or provider
inference call occurred in R4.

## Verification and provenance

| Run | Executed source commit | Original elapsed time |
| --- | --- | ---: |
| 01 | `0faa839b99b8fbee06d88bab7fee5c9c7a0aa0ad` | 101.54 s |
| 02 | `944cdde3705e742e06f0ece5604c721950c19c1a` | 140.32 s |

The initial independent numeric checker for run 01 was committed as
`b1d7cf9c8d1e86292228500a66287db1577c5e32`. The checker for run 02 is in
its executed source. Every run compares all 644,000 R scores and all 6,440 top
results with Python; largest score error is below 5.4e-14 and confidence error
below 5.7e-14. The independent image-score sample has maximum absolute error
below 1.1e-6 against the fixed 1e-5 tolerance.

The original macOS NumPy matrix-multiply warnings are preserved. Their backend
cause remains undiagnosed. Finite-value admission, original R3 Recall@K
reproduction, independent sampled arithmetic and exhaustive R/Python scoring
checks bound the observed risk; they are not a full encoder certification.

Independent reviews and repaired findings are recorded in `REVIEW.md`. The
final verifier explicitly rejects duplicate query metrics and NaN/Inf
reference confidence; it rechecks both complete experiments without rewriting
their historical receipts. `results/final_verification.json` binds final
source, evidence hashes and actual check outputs. Local execution evidence
does not stand in for a hosted/signed gate or an independent fresh test.

Selected portable-model SHA256:
`4f6db7b937a244b2a6cdf5298d6087bcd84d01445219882c2b7d041986a3a0b6`.
It is `results/run-02/training/model.json`; `results/selection.json` records
the development selection and both original model/report hashes.

## Reproduction

Use an environment with the preserved R3 Python dependencies and base R. The
executed environment used Python 3.12.16, NumPy 2.2.6, PyTorch 2.8.0,
safetensors 0.6.2 and R 4.6.2. No R package installation is required. The
original datasets, encoder receipts and selected R3 checkpoint must match the
immutable SHA256 values in `prepare_candidates.py`.

```sh
python -m unittest discover -s services/meta-spatial/retrieval-r4 -p 'test_*.py' -v
Rscript services/meta-spatial/retrieval-r4/test_reranker.R

python services/meta-spatial/retrieval-r4/run_experiment.py \
  --source-commit FULL_CLEAN_SOURCE_COMMIT \
  --rscript /absolute/path/to/Rscript \
  --prior-data /absolute/path/to/prior-data \
  --prior-features /absolute/path/to/r2/features.npz \
  --fresh-data /absolute/path/to/fresh-data \
  --fresh-features /absolute/path/to/r3/features.npz \
  --training /absolute/path/to/r3/training \
  --candidate-policy adapted_topk \
  --output /absolute/path/to/new-run
```

The current code can rerun either policy; exact original-run reconstruction
uses each recorded execution commit. Outputs must be new paths. The large
candidate/prediction CSVs remain in the original execution store, with hashes
and locations in `results/retained_artifacts.json`; compact models, per-query
outcomes, manifests, reports, warnings and verification are included here.

## Work remaining for >93% accepted coverage

This run establishes a measured baseline and an executable training loop.
The next improvement must resolve fine product variants and unavailable
visual evidence: admitted additional gallery/capture views, regional image
features and real OCR/barcode observations where available. New crops must be
labelled as crops, not new viewpoints, and same-family hard negatives need
verified exact-product labels. A newly collected independent test with real
absent-catalog examples is needed to qualify coverage and conditional error.

`compute_plan.json` records the NVIDIA worker's inspected route and a bounded
future GPU proposal. That proposal has not been launched. A new persistent
volume plan and applicable spending authority are required before allocation.
