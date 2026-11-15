# Object-aware inspection and labelled risk calibration

Work `J26-INTEL-OBJECT-VISION-M9`, partner `ignite-next-and-intel`, brief M330.
This extends the merged M7 real-image pipeline; it does not replace or relabel
M1–M6 synthetic decisions, the studio, or the separately owned M8 simulator.
**Offline diagnostics only: no physical actuation, automatic acceptance, live
camera, VLA, station permission or Intel NPU/iGPU qualification.**

## What changed

Whole-image background peaks are no longer used directly as object evidence.
An Otsu foreground detector localizes each object. A square crop preserves its
aspect ratio with 12% context. Scoring uses the convex hull, nearby foreground
inside the crop and a 4% margin. This retains tested notches and nearby detached
fragments; it cannot prove coverage of arbitrarily distant fragments or unseen
surfaces. Missing objects, more than eight components or boundary-truncated
objects refuse the capture instead of silently discarding difficult examples.

A pinned PatchCore feature extractor is fitted only on normal images. Thresholds
are selected on **separate labelled normal and defective calibration images**.
With the fixed 40-defect/64-normal calibration set, the working point requires at
least 38 defect detections and at most 6 false defect decisions. These are
engineering point targets, **not sponsor criteria or population certification**.
Threshold candidates are float64 midpoints between distinct scores. Comparisons
use strict `score > threshold`, including after JSON serialization.

The diagnostic three-way rule reports good, defect and hold separately. A hold
is neither a detected defect nor a successful normal classification. If the
binary operating point is infeasible, the run records that failure and leaves
the evaluation set untouched. Decode/model refusals retain image identities and
count against completeness; integrity and storage failures remain fatal.

## Frozen fresh-category inputs

The prior 200 candle test images are development-only and are excluded. The new
VisA `cashew` experiment uses 256 normal fit images; 64 other normals plus 40
defects for calibration; and 50 normals plus 60 defects for evaluation. Selection
was fixed before acquisition using the pinned official CSV and salted path
hashes. Physical-object and capture-session IDs are unknown: conclusions are
**image-level, category-specific**, not independent robot trials.

`object_dataset.json` includes immutable metadata and image hashes, not images.
All five metadata files and all 470 acquired image bytes are checked before a
run. The dataset license is CC BY 4.0. Attribution: Yang Zou, Jongheon Jeong,
Latha Pemula, Dongqing Zhang and Onkar Dabeer, *SPot-the-Difference*, ECCV 2022.
Source: https://registry.opendata.aws/visa/ ; official split revision
`2a692ab575001cbde74d402d897a7286086c6199`.

## Reproduce

Use the M7 pinned project-local dependencies in `requirements.txt`. This path
also needs the already-declared OpenCV dependency from Anomalib. Run from this
`vision/` directory. `DATA`, `CACHE` and `OUT` must be absolute local paths outside
the source repository; each preparation/run output directory must be new.

```sh
python prepare_objects.py data --output "$DATA" --connections 4
python prepare_objects.py backbone --profile wide_resnet50_2 \
  --cache "$CACHE" --output "$BACKBONE_RECEIPT"
python object_pipeline.py run --inputs "$DATA" --cache "$CACHE" \
  --profile wide_resnet50_2 --output "$OUT"
python object_pipeline.py verify --bundle "$OUT"
# Present only when calibration and export allow the first evaluation:
Rscript analyze_objects.R "$OUT/predictions.csv"
```

A previously downloaded exact-hash safetensors file can be supplied with
`--weights /absolute/path/model.safetensors`; arbitrary weights, pickle or an
unapproved model identifier are not accepted. The model-weight license and
training-data rights are separate from the VisA license; retained upstream
model cards state the model terms. No credentials are needed for preparation.
Network fetching is an explicit preparation command, never an inference fallback.

Two reproducible development profiles exist: the initial `resnet18`, and the
stronger `wide_resnet50_2` selected after the first candidate failed calibration.
The original protocol/data split remains immutable; actual profile and public
weight revision/hash are recorded in each run. This is calibration-only model
selection, not tuning against evaluation labels.

## Evaluation and export

Once calibration is feasible, export/readback must compile on OpenVINO CPU.
Otherwise the run stops without evaluation. Weights, configuration, ROI policy,
thresholds and export hashes are frozen before evaluation starts. A local
`EVALUATION_CONSUMED.json` is created exclusively; this is an operational guard,
not hostile-host rollback protection. A failed/interrupted evaluation must not
be retried as a new independent result. Every completed image is fsynced to an
unlabelled JSONL journal before the later truth join.

Export parity compares full maps, foreground scores and final decisions using
predeclared absolute/relative tolerances of 0.001. Successful export is not model
quality approval. Old M7 parity does not transfer to these new models. The
reported CPU executor may be Apple ARM: it is not Intel target evidence.

```sh
python object_pipeline.py inspect --bundle "$OUT" \
  --image /absolute/path/cleared-image.jpg --sha256 ACTUAL_IMAGE_SHA256 \
  --output /absolute/path/new-inspection
```

Inspection requires a completed parity-passed artifact bundle and verified model
identity. It emits real per-object scores/maps and a diagnostic decision, but
its effective decision remains **HOLD**, with `automatic_acceptance:false` and
`actuation:false`. The input domain, operator authority and physical interlocks
are not established by supplying an image. Hash ledgers detect corruption, not
malicious-author provenance. No network listener or daemon is started.

## Verification and current limitation

Focused structural checks exercise split/label tampering, pinned weights,
finite scores, threshold ties, unknown denominators, object bounds, notch/chip
coverage, inference refusal retention and failed-export diagnostic refusal.
These synthetic checks are not detector-quality results. Executed results and
exact source hashes are recorded separately; prior failed candidates are kept.

The next acceptance dependency remains a candidate meeting the frozen data
quality target and, separately, licensed station-specific captures plus an
authorized SO-101/Intel host for camera, grasp, real second-view reinspection,
physical stop/rearm and latency qualification. No merge, deployment or sponsor
submission is authorized by this document.
