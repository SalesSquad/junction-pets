# Real-image offline inspection — J26-INTEL-M330-M7

`REAL_DATA_OFFLINE / NO ROBOT`. An importable, CPU-only Anomalib PaDiM runner,
artifact verifier, saved-model image inspector and base-R descriptive analysis.
This directory does not call or change the product's synthetic STOP machinery.
No quality metric from synthetic pixels is real inference evidence.

## Fixed experiment

Amazon VisA candle, CC-BY-4.0, source repository `amazon-research/spot-diff`
commit `2a692ab575001cbde74d402d897a7286086c6199`. Attribute Yang Zou,
Jongheon Jeong, Latha Pemula, Dongqing Zhang and Onkar Dabeer,
*SPot-the-Difference Self-Supervised Pre-training for Anomaly Detection and
Segmentation* (ECCV 2022). Dataset source:
https://amazon-visual-anomaly.s3.us-west-2.amazonaws.com/VisA_20220922.tar
Official `split_csv/1cls.csv` SHA256:
`a48557e6033318cb90556f706196bc9d247a776a23ea51aecee5a80dd0332995`.

From 900 official training normals, sort SHA256(`330|image`), take 128 fit
and next 64 normal calibration images. All 200 official test images are heldout
(100 normal/100 anomaly). Actual bytes and official CSV membership are verified. The entire benchmark
manifest must also match SHA256
`e45d2caa0107fdc2c4fa973fd378d41d87559d9c2b0cc0f6977db4736a71df26`
byte-for-byte, including labels and JSON formatting. Structural fixture helpers
cannot admit synthetic pixels as this benchmark.
The runner does not acquire or substitute datasets; optional `prepare.py` reproduces the pinned public selection. Object/session identities are
unknown: unique files do not establish physical independence or reinspection.
VisA is neither Intel sponsor evidence nor robot/station evidence.

Seed 330, two CPU threads, frozen pretrained ResNet18, 50 features, Gaussian
fitting (`forward` memory bank then `fit()`), no neural gradient training.
128x128 EXIF-transposed RGB, Pillow bilinear resize, ImageNet mean/std.
Normal-only quantiles use NumPy `higher`: binary defect strictly above q95;
good strictly below q90; defect strictly above q99; otherwise hold (including
ties). These are proposals, not probabilities, calibrated defect guarantees,
or instructions to hardware. No heldout-driven tuning or automatic retry.

The backbone is `timm/resnet18.a1_in1k`, immutable revision
`491b427b45c94c7fb0e78b5474cc919aff584bbf`, safetensors SHA256
`80c49dee3da4822c009c5a7fe591e9223c5a2cfcf95a4067ca4dfb5a7b89c612`.
The runner resolves only that cached revision, checks exact bytes and loads
safetensors into the same ResNet18 feature extractor, without pickle. It never
downloads, resolves mutable `main`, or accepts a caller model URL.
The upstream model card declares Apache-2.0; underlying data rights remain
separate. This project makes no additional license grant. A successful run records upstream
pretrained configuration, tensor hashes, fitted safetensors, producer versions,
source/config/preprocess/manifest digests and a frozen model/threshold record.

## Execute

Use the already provisioned lab environment; do not reinstall it. From repo root:

```sh
PY=/Users/mikaelervamaa/Developer/j26-intel-vision-lab-20261114/.venv/bin/python
LAB=/Users/mikaelervamaa/Developer/j26-intel-vision-lab-20261114
VISION=solutions/intel-physical-ai/vision
export PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR="$LAB/mpl-cache"
export HF_HUB_CACHE="$LAB/hf-cache" HF_HUB_OFFLINE=1
"$PY" "$VISION/pipeline.py" validate-manifest --manifest "$LAB/manifest.json" \
  --data-root "$LAB/data" --split-csv "$LAB/visa-1cls.csv"
# Initial run-m7 failed before fitting and MUST be retained. Fresh destination:
(set -C
"$PY" "$VISION/pipeline.py" run --manifest "$LAB/manifest.json" \
  --data-root "$LAB/data" --split-csv "$LAB/visa-1cls.csv" \
  --backbone-cache "$LAB/hf-cache" --output-dir "$LAB/run-m7-network-restored" > "$LAB/run-m7-network-restored.log" 2>&1
)
"$PY" "$VISION/pipeline.py" verify --output-dir "$LAB/run-m7-network-restored"
/opt/homebrew/bin/Rscript "$VISION/analyze.R" "$LAB/run-m7-network-restored/predictions.csv"
# Requires a sealed successful run with complete 200-image CPU parity:
"$PY" "$VISION/pipeline.py" inspect --artifact-dir "$LAB/run-m7-network-restored" \
  --image /absolute/path/image.png --sha256 ACTUAL_IMAGE_SHA256 \
  --output-dir "$LAB/inspection-new"
```

Output directories must be outside this checkout, absent, with an existing
parent. No overwrite flag exists. Safetensors loading uses no pickle and does
not download weights. `verify` checks unsigned local integrity, not authenticity;
only inspect artifacts from a trusted local producer. `inspect` loads only
verified local OpenVINO IR/bin with a complete recorded CPU parity pass, checks
frozen configuration/threshold identity, output shapes and finite values. Its
output is `USER_IMAGE_OFFLINE`, `source=USER_SUPPLIED_UNVERIFIED_DOMAIN`,
`actuation:false`; a user image has no inferred VisA license, station/camera or
SO101 provenance. Inspection receives no
caller scores/confidence. Dataset labels join reporting after predictions freeze.
`predictions.csv` contains calibration/heldout rows, image scores, map hashes,
labels, partition, per-forward processing latency and proposals. `report.json` reports heldout image AUROC,
confusion, ternary counts, coverage and timing; no pixel-segmentation claims.
Every calibration/heldout map is persisted in `maps/*.npy`, numeric float32,
`allow_pickle=False`, indexed by `map_path` and little-endian tensor hash in CSV.
Inspection also saves `map.npy`. Latencies include forward/output validation,
exclude preprocessing and describe this CPU/runtime only; no robot throughput.

OpenVINO wraps actual `(score, map)` outputs, fixed batch 1, full-precision IR
(`compress_to_fp16=False`), then reads the IR back on CPU with f32 precision.
All 200 heldout scores/maps/binary and ternary proposals must agree with PyTorch
at predeclared atol=rtol=1e-3. Failed comparisons remain `fail`; conversion or CPU
execution errors remain `blocked` without discarding PyTorch results. Mac CPU
is not Intel NPU/iGPU qualification; timing is not robot cycles/min.

## Portable preparation (optional; do not repeat the existing lab download)

On another authorized host, choose fresh directories outside the checkout:

```sh
# Public downloads, token=False, no private account credentials or mutable main.
# Unset offline mode only for these explicit preparation commands.
HF_HUB_OFFLINE=0 "$PY" "$VISION/prepare.py" backbone \
  --cache-dir /chosen/hf-cache --output-dir /chosen/backbone-source-new
"$PY" "$VISION/prepare.py" data --output-dir /chosen/visa-frozen-new
```

Data preparation downloads the source-commit-pinned CSV (1 MiB cap) and reads
at most the first 256 MiB of the public tar, requiring HTTP 206. Only the 392
selected regular-file members (8 MiB each) are written exclusively, without tar
extraction, links or traversal. Final exact manifest hash must match. Partial
failed preparations stay available for investigation. Dataset attribution is
written alongside it; no binaries/dataset are committed. Backbone source JSON
records revision, exact weights hash and pinned model-card/config hashes.

## Focused checks and current evidence

```sh
(cd "$VISION" && "$PY" -B -m unittest test_pipeline.FrozenBenchmark -v)
# Full model/native qualification is owned by coordinator, not this repair.
```

Synthetic test pixels/random weights only exercise plumbing. The OpenVINO CPU
qualification test intentionally fails if conversion/readback is unavailable;
that is an environment gate, never an inferred parity pass. See
[RESULTS.md](RESULTS.md) for actual observations and retained failures.

Next station dependency: independently reviewed numerical/provenance source,
then separately authorized real camera/lighting/fixture integration with recorded
object/session IDs, station-specific calibration and Intel target execution.
Sponsor rubric conflict remains unresolved. No station maturity or 6/7 claim.

## Current measured quality and product gate

The first actual public-image run completed, including 200/200 OpenVINO CPU
parity. It **failed the intended detection-quality objective**: AUROC 0.8164,
23/100 defects detected by the binary rule, and 62/100 defects proposed good
by the raw three-way rule. See `EXECUTED_M7.json` and `RESULTS.md`.

`inspect` is diagnostic only: it preserves `diagnostic_proposal` but returns
effective `proposal: hold`, `automatic_acceptance: false`, and
`NOT_QUALIFIED_FOR_AUTONOMOUS_USE`. No field can authorize actuation.
The host/device and model-policy qualification are distinct. A new, separate
defect-labelled validation cohort is required; do not optimize on the exposed
200-image test set or present numerical parity as model-quality approval.
