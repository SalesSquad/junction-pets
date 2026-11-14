# Meta Lens R3 — visual retrieval adapter

Work ID: `META-LENS-ADAPTER-R3-20261114`.

## Executed result — 14 November 2026

Execution source: `745f2e6597b8d4e398551c37071b9ec662f2aea8`. All six fixed
12-epoch runs completed. The primary is seed 17, epoch 3. The fresh cohort has
2,400 products: calibration 1,225 queries / 702 connected families, and test
1,175 queries / 689 families. The new test was scored once with the dev-selected
checkpoint and calibration-frozen policies. No fresh outcome changed either.

| Method | Recall@1 | Recall@5 | Recall@10 | Offline coverage | Wrong accepted matches | Family error upper95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Separate cosine-preservation ablation | 58.55% | 84.09% | 90.38% | 1.53% | 1 | 0.69% |
| Fixed 0.75 visual + 0.25 text hybrid | 52.85% | 80.17% | 85.62% | 1.02% | 1 | 0.69% |
| Frozen image/image | 53.19% | 80.09% | 85.87% | 0.77% | 1 | 0.69% |
| Selected visual adapter | 58.47% | 84.00% | 90.38% | 1.45% | 1 | 0.69% |

Primary minus frozen image/image Recall@1: **5.28 percentage points**;
paired-family bootstrap 95% interval **[3.50, 7.11] points**
(2,000 resamples; query-weighted family clusters). All fresh comparisons use
the same MPS-encoded images, not the differently sized historical R2 test.

**Predeclared product gate: FAIL.**

| Gate condition | Result |
| --- | --- |
| combined_family_upper95_at_most_1_percent | PASS |
| coverage_at_least_20_percent | FAIL |
| recall_at_least_fixed_hybrid | PASS |
| zero_wrong_present_accepted | FAIL |

Runtime always abstains because the complete product gate failed. Research rankings remain inspectable; partial passing conditions never override FAIL.

Offline coverage describes the frozen threshold on test scores. It is not a
production activation or a guarantee of conditional answer precision.

### Delivery and verification

The raw Mac logs contain NumPy matmul warnings. A separate post-hoc
float64 einsum audit checked every prior/fresh cached feature and score
value for finiteness and compared 32 predetermined query rows against
all gallery columns for each of eight partition/method pairs. It passed,
with maximum absolute score difference 1.6e-06 (limit 1e-5).
This is a sampled numerical check, not a diagnosis of the warning cause
or a new field-performance test; original warnings are retained.

- Frozen-source checks: **36/36 PASS, no skips**; raw log in `results/logs/focused-tests.log`.
- Six actual candidates × 12 epochs, with finite gradients, weight updates and
  exactly one anchor visit per epoch for all 3,313 training products.
- All selected/final checkpoints, frozen policies, source/data hashes, compact
  per-query score events and raw command/step logs are in `results/`.
- `verify_results.py` validates artifacts/checkpoints and recomputes the decisive
  metrics for eight partition/method pairs, paired uncertainty and the gate.
  Its integrity PASS does not turn a product FAIL into PASS.
- Large public features/full score matrices remain in the execution archive;
  locations and hashes are in `results/retained-public-caches.json`. Public
  image URLs/hashes and the pinned model allow reconstruction. This is not a
  guarantee of the Mac cache remaining available.

```sh
python -m pip install -r requirements.txt
python verify_results.py
```

`VisualRetrievalAdapter.from_artifacts(Path("results/training"),`
`Path("results/evaluation"))` loads the actual selected checkpoint and policy.
The `propose` method accepts unit-normalized 768-dimensional image embeddings
and gallery IDs. `results/runtime-smoke.json` records three actual fresh queries
against all 1,175 test products. The consumer does not attest caller embedding
provenance. No device integration or production activation was performed.

### Execution and costs

R3 reused the pinned R2 NVIDIA A100 image-feature cache for CPU adapter training.
New images were encoded on the authorized Mac using MPS/FP32; all new baselines
share those arrays. The old provider OS volume was observed deleted, so the
cloud attempt stopped before VM creation. The Mac fallback was retained when
affordable GPU stock later returned; the later provider observations in
`compute-admission.json` are not the initial admission snapshot.

**New R3 provider compute charge: USD 0.** LLM/connector cost is unknown.
This is a custom PyTorch residual adapter, not a TAO, Nemotron or SAM training
run. No private ScreenshotContext content, live wearable capture, ARKit device
session, personal-memory learning or copied credentials were used.

R2 optimized image-to-text matching even though the product task needs matching
two photographs of the same object. R3 learns one shared visual residual
projection on frozen SigLIP2 features: 768 dimensions, rank 64, 98,304 trainable
parameters. Both sides of the contrastive objective are real images. Same-family
variants are excluded as negatives, not silently relabelled as positives.

Every training product contributes exactly one anchor per epoch. Extra hard
negative candidates never displace anchors or become additional loss queries.
Epoch zero is an eligible identity baseline; it wins exact ties. Primary
preservation=0 and the separately labelled cosine-preservation=0.05 ablation each
run seeds 17/31/53 for 12 epochs. The primary is the candidate selected for
prospective confirmation; the ablation is never substituted after test results.

## Frozen protocol and evidence boundaries

`protocol.json` predeclares the new evaluation. R2 train/dev are reused for
training/selection. Its already inspected test/OOD partitions do not provide a
new confirmation. `prepare_holdout.py` groups ALL 16 metadata shards, including
graph-only records without sufficient images/English titles, before excluding
every component linked to the previous 6,000 products. Selected photographs are
hash checked; byte-linked components are excluded transitively before the new
calibration/test split. Each partition requires at least 400 connected families.

The fresh test is a same-catalog ABO evaluation. It is not wearable-camera,
category-held-out, Finnish-OCR, ARKit, user-memory or physical-identity evidence.
Foundation model pretraining overlap and remaining perceptual duplicates are
unknown. Metadata and photographs are public ABO, CC-BY-4.0, attributed to
Amazon.com and Collins et al., CVPR 2022. Historical R2 evidence is unchanged.

`evaluation.py` freezes source/protocol/data/checkpoint hashes before new pixel
inference. It fits thresholds on calibration and writes them before scoring
test. The risk event is ANY wrong present acceptance OR ANY absent-family false
acceptance among ALL queried variants of a connected family. The denominator is
all eligible families, using a one-sided exact Clopper–Pearson 95% upper bound.
This is not a claim of 99% precision among accepted answers. Product qualification
also requires at least 20% coverage, zero wrong present acceptances, and recall
at least the fixed R2 hybrid (0.75 image/image + 0.25 image/text). Always abstaining
does not pass. Primary-vs-frozen recall uncertainty uses a paired family bootstrap.

## Run

Use the pinned R2 sibling scripts and the original sealed `dataset.json` plus
`features.npz`/`features.json`. The feature cache comes from actual pinned SigLIP2
inference on an NVIDIA A100 in R2. No new text model, teacher or backbone training is implied.

```sh
python -c 'import torch, safetensors'
python -m unittest -v test_visual_adapter test_holdout test_evaluation test_runtime
python train_visual.py --data R2_DATA --features R2_RUN/features.npz \
  --output R3_TRAIN --device cpu --max-seconds 1800
python prepare_holdout.py --prior-data R2_DATA --output FRESH_DATA \
  --max-products 2400 --min-families-per-split 400 --workers 12
python evaluation.py --data FRESH_DATA --prior-data R2_DATA \
  --training R3_TRAIN --output FRESH_EVAL --cache MODEL_CACHE \
  --device mps --source-commit EXECUTED_SHA --max-seconds 2400
```

CUDA is supported for both scripts; CPU/MPS are bounded fallback executors.
If the old public metadata cache is unavailable, `restore_prior_cache.py`
rehydrates its 18 exact public source files from their original URLs and checks
the hashes sealed by the old dataset. It never reads private ScreenshotContext
exports or copies credentials. Historical images are not needed for feature-only
training. Actual execution outcomes and the final promotion decision are added
under `results/`; source presence alone is not execution evidence.

The independent review found and closed metadata-bridge leakage, an ablation
loader mismatch, and identity-rounding drift before the first new dataset/model
run. The runtime still proposes candidates only and grants no authority.
