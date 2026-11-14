# Meta Lens R3 — visual retrieval adapter

Work ID: `META-LENS-ADAPTER-R3-20261114`.

R2 optimized image-to-text matching even though the product task needs matching
two photographs of the same object. R3 learns one shared visual residual
projection on frozen SigLIP2 features: 768 dimensions, rank 64, 98,304 trainable
parameters. Both sides of the contrastive objective are real images. Same-family
variants are excluded as negatives, not silently relabelled as positives.

Every training product contributes exactly one anchor per epoch. Extra hard
negative candidates never displace anchors or become additional loss queries.
Epoch zero is an eligible identity baseline; it wins exact ties. Primary
preservation=0 and the separately labelled cosine-preservation=0.05 ablation each
run seeds 17/31/53 for 12 epochs. The primary is the prospectively confirmed
candidate; the ablation is never substituted after test results.

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
python -m unittest -v test_visual_adapter test_holdout test_evaluation
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
