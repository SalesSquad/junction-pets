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
(100 normal/100 anomaly). Actual bytes and official CSV membership are verified.
This code does not acquire or substitute datasets. Object/session identities are
unknown: unique files do not establish physical independence or reinspection.
VisA is neither Intel sponsor evidence nor robot/station evidence.

Seed 330, two CPU threads, frozen pretrained ResNet18, 50 features, Gaussian
fitting (`forward` memory bank then `fit()`), no neural gradient training.
128x128 EXIF-transposed RGB, Pillow bilinear resize, ImageNet mean/std.
Normal-only quantiles use NumPy `higher`: binary defect strictly above q95;
good strictly below q90; defect strictly above q99; otherwise hold (including
ties). These are proposals, not probabilities, calibrated defect guarantees,
or instructions to hardware. No heldout-driven tuning or automatic retry.

Timm's default backbone is `resnet18.a1_in1k`; only its official pretrained
loader is used, never caller-supplied URLs. Timm/Anomalib code is Apache-2.0;
ImageNet pretrained weights and underlying data have separate upstream terms,
not a license grant from this project. A successful run records upstream
pretrained configuration, tensor hashes, fitted safetensors, producer versions,
source/config/preprocess/manifest digests and a frozen model/threshold record.

## Execute

Use the already provisioned lab environment; do not reinstall it. From repo root:

```sh
PY=/Users/mikaelervamaa/Developer/j26-intel-vision-lab-20261114/.venv/bin/python
LAB=/Users/mikaelervamaa/Developer/j26-intel-vision-lab-20261114
VISION=solutions/intel-physical-ai/vision
export PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/private/tmp/m7-mpl
# Optional writable cache for the official timm download; no credentials needed.
export HF_HOME="$LAB/hf-cache"
"$PY" "$VISION/pipeline.py" validate-manifest --manifest "$LAB/manifest.json" \
  --data-root "$LAB/data" --split-csv "$LAB/visa-1cls.csv"
# Initial run-m7 failed before fitting and MUST be retained. Fresh destination:
"$PY" "$VISION/pipeline.py" run --manifest "$LAB/manifest.json" \
  --data-root "$LAB/data" --split-csv "$LAB/visa-1cls.csv" \
  --output-dir "$LAB/run-m7-network-restored" > "$LAB/run-m7-network-restored.log" 2>&1
"$PY" "$VISION/pipeline.py" verify --output-dir "$LAB/run-m7-network-restored"
/opt/homebrew/bin/Rscript "$VISION/analyze.R" "$LAB/run-m7-network-restored/predictions.csv"
# Inspect a new file using this locally produced, trusted artifact directory:
"$PY" "$VISION/pipeline.py" inspect --artifact-dir "$LAB/run-m7-network-restored" \
  --image /absolute/path/image.png --sha256 ACTUAL_IMAGE_SHA256 \
  --output-dir "$LAB/inspection-new"
```

Output directories must be outside this checkout, absent, with an existing
parent. No overwrite flag exists. Safetensors loading uses no pickle and does
not download weights. `verify` checks unsigned local integrity, not authenticity;
only inspect artifacts from a trusted local producer. Inspection receives no
caller scores/confidence. Dataset labels join reporting after predictions freeze.
`predictions.csv` contains calibration/heldout rows, image scores, map hashes,
labels, partition and proposals. `report.json` reports heldout image AUROC,
confusion, ternary counts, coverage and timing; no pixel-segmentation claims.
Map bytes have float32 little-endian hashes; inspection also saves a safe `.npy`.

OpenVINO wraps actual `(score, map)` outputs, fixed batch 1, full-precision IR
(`compress_to_fp16=False`), then reads the IR back on CPU with f32 precision.
All 200 heldout scores/maps/binary and ternary proposals must agree with PyTorch
at predeclared atol=rtol=1e-3. Failed comparisons remain `fail`; conversion or CPU
execution errors remain `blocked` without discarding PyTorch results. Mac CPU
is not Intel NPU/iGPU qualification; timing is not robot cycles/min.

## Focused checks and current evidence

```sh
"$PY" -m unittest discover -s "$VISION" -p 'test_*.py'
```

Synthetic test pixels/random weights only exercise plumbing. The OpenVINO CPU
qualification test intentionally fails if conversion/readback is unavailable;
that is an environment gate, never an inferred parity pass. See
[RESULTS.md](RESULTS.md) for actual observations and retained failures.

Next station dependency: independently reviewed numerical/provenance source,
then separately authorized real camera/lighting/fixture integration with recorded
object/session IDs, station-specific calibration and Intel target execution.
Sponsor rubric conflict remains unresolved. No station maturity or 6/7 claim.
