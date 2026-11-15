# Meta Lens R6: NVIDIA features and a measured CPU control

R6 implements frozen Nemotron OCR v2 and C-RADIOv4 feature extraction,
then a learned R ranker over the retained top100 candidate pool. The NVIDIA
models remain frozen; the downstream ranking coefficients are trainable.

## Measured status

**Three real CPU fits completed. No NVIDIA extraction completed.** The CPU
control trained on 331,300 candidate rows and evaluated 72,700 development
rows. All three optimizations converged, changed weights, and reduced loss.
The best development result stayed at **466/727 exact rank-one matches
(64.10%)**, so the frozen R4 model remains selected.

| CPU control | Dev exact rank1 | Result |
|---|---:|---|
| Frozen R4 | 466/727 (64.10%) | Retained |
| Six-feature refit, ridge 0.01 | 466/727 (64.10%) | No improvement |
| Six-feature refit, ridge 0.1 | 458/727 (63.00%) | Not selected |
| Six-feature refit, ridge 1 | 451/727 (62.04%) | Not selected |

These are development retrieval results, **not accepted coverage**. No
acceptance threshold was calibrated, no OCR accuracy was measured, and no
physical identity or action is authorized. The >93% accepted-coverage target
remains unqualified.

The CPU control used the six existing R4 features. It did not manufacture
OCR/RADIO columns or observations. Its three fits are separate from the
predeclared twelve-fit NVIDIA experiment, which remains unexecuted.

## Actual GPU attempt

One RTX PRO 6000 CC instance was provisioned. NVIDIA attestation and usable
CUDA were verified, and the pinned OCR snapshot was downloaded. The native
OCR extension build did not finish: our first supervisor treated one
transient OAuth TLS status-read failure as fatal and released the compute.
The failed attempts and their evidence were preserved.

The runtime work identified required Python 3.12 venv/development packages
and build-essential. Attestation validation must inspect both output streams,
and result collection must fetch the archive for the exact attempt. Recovery
helpers now reserve export/cleanup time and do not terminate useful work on
a single transient provider read. These helper corrections have not yet
produced a complete extraction run.

Subsequent RTX and A100 admission attempts created no instances; A100 returned
`gpu-type-not-available`. An advertised availability row is not proof of
admission. The task's compute release was verified. One detached 100 GiB OS
volume preserves the interrupted runtime and build evidence and continues
storage billing (catalog $20/month); irreversible deletion was not performed.
No new credit was purchased, and unrelated instances were left untouched.

## Artifacts and provenance

- `results/cpu-refit6-report.json`: all three actual fits, diagnostics,
  development metrics, paired changes, and the baseline-retention decision.
- `results/cpu-refit6-model.json`: the selected six-feature numeric model,
  coefficients, scaler and provenance; its policy remains uncalibrated.
- `results/cpu-refit6-verification.json`: hashes and verified actual row/fit counts.
- `results/prepared-inputs.json`: aggregate counts and hashes of prepared inputs.
- `results/execution-summary.json`: completed work, failed GPU stages,
  verified release, retained storage and explicit qualification limits.

The GPU archive and original preparation are pinned to source commit
`8948b44454f1a5dd174395e6d69e1ae8b533688b`. The independently reviewed CPU runner
is bound by SHA256 `3a9fd91e4532959d7b91ee16deb485afa233871c5ba0f10b978a9118c72c5c58`.
Its admission verifies the known preparation-manifest hash before parsing,
checks the original dataset/report pins and source bytes in Git, and repeats
admission after optimization. Raw candidate rows, truth/catalog records,
image observations, identity-bearing predictions and command logs stay on
the authorized execution host. They are not included in this PR.

Focused source verification passed six extractor Python checks, seven
input/feature Python checks, and nine R numerical conditions. The actual
CPU run additionally verified 404,000 prediction rows, 16,160 query-metric
rows, three converged optimizations and the frozen 466/727 control. These
checks do not establish live NVIDIA inference correctness.

## Why this experiment

[R4](https://github.com/SalesSquad/junction-pets/pull/187) has 466/727 exact
rank-one development matches, while its retained top100 contains the correct
product for 719/727 queries (98.90%). A better ranker could recover 253 current
errors within that pool; the remaining eight stay in every denominator.
Top100 recall does not measure reliable automatic acceptance.

[R5](https://github.com/SalesSquad/junction-pets/pull/195) used four Nemotron
roles on eight development cases. Its top3 restriction left no recoverable
baseline error in that pilot. R6 therefore preserves top100 and seeks new
image evidence. No known correct item is inserted into a missing candidate list.

## Frozen NVIDIA protocol

`protocol.json` records 3,313 train queries and 727 dev queries.
The 404,000 retained rows preserve original features
and numeric tokens. Their 8,080 image slots deduplicate to 6,993 public images.
No calibration, test or absent-catalog image is exported to the GPU experiment.

Query pixels use original view 1; gallery pixels use view 0. The public image
manifest contains only hashes, paths and source URLs, without product labels,
truth or catalog titles. Candidate catalog information is admitted separately
for downstream OCR matching; query catalog text is excluded.

New pair features are RADIO cosine similarity, OCR query/gallery token
overlap, query/candidate-catalog token overlap, and lexical digit agreement
and conflict. OCR is model output, never gold transcription or identity truth.

Four ablations (six original features, plus RADIO, plus OCR, and both) each
fit ridge strengths 0.01, 0.1 and 1. Scaling and optimization use train only.
Development exact recall@1, then MRR, chooses the candidate; fewer features
and stronger ridge break remaining ties. Frozen R4 stays selected without
strict improvement. Those twelve enriched fits still require a completed GPU run.

## Components and resumption

- `prepare_inputs.py` verifies the original dataset and R4 artifacts, checks
  split separation, and exports the fixed train/dev rows and image manifest.
- `extract_nvidia.py` executes revision-pinned NVIDIA models on CUDA and emits
  complete, hash-bound observations or a preserved explicit failure.
- `build_features.py` requires complete observations, fixed model revisions,
  consistent hashes, normalized embeddings and the retained candidate pool.
- `train_reranker.R` implements the twelve-fit NVIDIA-enriched protocol.
- `train_cpu_refit.R` runs only the separately labeled six-feature CPU control.

Reproduce the CPU control with the retained host data and a new output directory:

```sh
Rscript train_cpu_refit.R \
  --prepared /work/prepared \
  --prepared-manifest-sha 817435715686cc2d98eea94ea5d4fa95450fb803be3328eb66feb53185b631d0 \
  --r6-source /work/source/services/meta-spatial/retrieval-r6/train_reranker.R \
  --baseline-model /work/r4/training/model.json \
  --output /work/cpu-refit6-new \
  --source-commit 8948b44454f1a5dd174395e6d69e1ae8b533688b
```

For the GPU experiment, use the preserved source archive and manifest rather
than rewriting historical evidence. On Linux amd64/Python 3.12, install a
compatible CUDA toolchain and the official OCR extension from its pinned
snapshot. The prepared runtime pins Torch 2.9.1/cu130 and torchvision 0.24.1.
The extractor compares installed OCR Python bytes with the pinned snapshot
and records compiled-extension and weight hashes. The Python preparation,
extraction and feature-builder entrypoints support `--help`. After verified
extraction and feature construction, the R entrypoint is:

```sh
Rscript train_reranker.R \
  --input /work/features/candidates.csv \
  --manifest /work/features/data_manifest.json \
  --output /work/training-new \
  --source-commit CURRENT_CLEAN_HEAD
```

Before joining GPU observations, verify the approved archive, extractor bytes,
input manifest and output hashes against the host's preserved source binding.
The standalone feature builder checks internal consistency, not an external
approval of the extractor's source. An archive without `.git` does not claim
independent Git verification. Preserve all failed attempts and actual runtime
records; successful admission and a completed model run must be observed.

## Pinned model sources and qualification

- [Nemotron OCR v2](https://huggingface.co/nvidia/nemotron-ocr-v2/tree/0e83e83f17943524b90afa6c0fd82ac2bc1a40ca)
- [C-RADIOv4-SO400M](https://huggingface.co/nvidia/C-RADIOv4-SO400M/tree/c0457f5dc26ca145f954cd4fc5bb6114e5705ad8)

Model weights stay in the authorized cache and are not redistributed here.
Development selection is exploratory. A later gain requires independent
calibration/test data, absent-catalog cases and real capture conditions before
any >93% accepted-coverage claim. Historical test results remain historical.
