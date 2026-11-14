# Meta Lens R6: NVIDIA image and OCR features

R6 adds two measured inputs to the existing learned retrieval pipeline:
`nvidia/nemotron-ocr-v2` for visible text and `nvidia/C-RADIOv4-SO400M`
for image embeddings. It then fits a new pairwise ranker with base R.
The GPU extracts features; the R optimizer learns the downstream ranking
coefficients. The NVIDIA foundation models remain frozen.

Execution results are not available at this protocol commit. This source
does not establish >93% accepted coverage, OCR transcription accuracy,
physical identity, or production readiness. Actual runs and failed attempts
will be recorded with their source/input/model hashes.

## Why this experiment

[R4](https://github.com/SalesSquad/junction-pets/pull/187) selected a real
trained ranker whose development result was 466/727 exact rank-one matches.
Its retained top100 pool contains the correct product for 719/727 queries.
There are therefore 253 baseline errors that a better ranker can potentially
recover within this fixed pool; eight queries cannot be recovered from it.

[R5](https://github.com/SalesSquad/junction-pets/pull/195) tested four
Nemotron roles on eight development cases. Its top3 restriction left no
recoverable baseline errors in that pilot. R6 preserves the original top100
candidate pool and adds new image-derived evidence. It never inserts the
known correct product into a missing candidate list.

## Frozen protocol

`protocol.json` records the experiment before model execution. Training has
3,313 queries from 2,058 families; development has 727 queries from 489
families. The 404,000 retained candidate rows keep their original features,
identity labels and numeric tokens. No calibration or test image is admitted
to this experiment.

Query pixels are original source view 1; gallery pixels are original view 0.
The public image manifest contains only image hashes, paths and source URLs.
It contains no product identities, correctness labels or catalog titles.
The original dataset separately supplies candidate catalog information for
the downstream OCR matching features. The query's catalog text is excluded.

New pair features are RADIO cosine similarity, OCR token overlap between
query and gallery, OCR query-to-candidate-catalog overlap, and lexical digit
agreement/disagreement. They are model observations. No OCR text becomes a
gold transcription or a ground-truth training label.

Four fixed ablations (original six features, plus RADIO, plus OCR, and both)
each fit ridge strengths 0.01, 0.1 and 1. Scaling and optimization use training
families only. Development exact recall@1 and then MRR choose the candidate,
with fewer features and stronger regularization breaking remaining ties.
The frozen R4 baseline remains selected unless the experiment improves it.
Every missing positive stays in the evaluation denominator.

## Components

- `prepare_inputs.py` verifies the original dataset and R4 artifacts, checks
  split separation, and exports the train/dev candidate rows and pixel manifest.
- `extract_nvidia.py` executes the two public, revision-pinned NVIDIA models
  on CUDA, preserves raw OCR, and emits hash-bound image observations.
- `build_features.py` joins complete image observations to the retained pairs
  and frozen R4 scores. Missing, duplicate or inconsistent evidence is rejected.
- `train_reranker.R` performs the twelve actual optimization fits and records
  every candidate, the selected model and the frozen R4 comparison.

The extraction command requires Linux amd64, a compatible CUDA-enabled
PyTorch runtime, and Python 3.12 for the official OCR package. The OCR CUDA
extension must be installed from the same pinned snapshot. Its installed
Python files are compared with that snapshot before import. A portable source
archive records its script hash and declared source commit; without Git in
the GPU bundle, the extractor does not claim independent Git verification.

## Model sources

- [Nemotron OCR v2 pinned model and inference source](https://huggingface.co/nvidia/nemotron-ocr-v2/tree/0e83e83f17943524b90afa6c0fd82ac2bc1a40ca)
- [C-RADIOv4-SO400M pinned model and inference source](https://huggingface.co/nvidia/C-RADIOv4-SO400M/tree/c0457f5dc26ca145f954cd4fc5bb6114e5705ad8)

The models are governed by their NVIDIA Open Model License terms; the OCR
inference package includes Apache-2.0 code. Weights are downloaded into the
authorized executor's model cache and are not redistributed in this source
directory. Public weights do not require NVIDIA-hosted NIM credentials.

## Qualification limits

Development selection is exploratory. An improvement here would justify a
fresh, independently collected calibration/test campaign with absent-catalog
cases and real capture conditions. It would not by itself qualify >93%
accepted coverage. Historical test results remain historical, and the source
does not authorize an action from visual similarity or inferred identity.
