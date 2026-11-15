# Meta Lens R8: finite NVIDIA feature extraction

R8 executes the existing R6 OCR/RADIO experiment on one Verda L40S batch
replica. It keeps the frozen models, input images, train/dev split and twelve
ranker candidates unchanged. The R7 nonlinear experiment did not outperform
R4. R8 adds measured image features and evaluates both the original linear
rankers and four preregistered nonlinear rankers on those features.

## Execution status

The first deployment creation returned HTTP 400 and created no GPU job. The
second deployment started, but its inference request returned HTTP 404 before
extraction; its controller recorded the failure and verified the deployment's
`paused` state. No R8 feature archive or model fit was produced by either attempt.

The corrected worker/controller and the fixed nonlinear comparison have passed
their targeted source checks and independent review. Dispatch of a new retry was
blocked by automatic approval review as new compute spending. The retry has not
been created or invoked. It is prepared for one L40S with a 55-minute provider
deadline and a USD3 allocation cap, subject to explicit retry authorization.
The existing R4 development reference remains 466/727 (64.10%); R8 has no new
measured retrieval result and has not qualified the target above 93% coverage.

## Source and execution contract

The extraction and numerical training source is commit
`8948b44454f1a5dd174395e6d69e1ae8b533688b`. Use a separate, clean checkout of
that commit; the published R6 branch now has a later documentation/results
HEAD. `run_batch.py` separately binds the committed orchestration source and
the exact worker/bootstrap bytes before dispatch.

- Public image manifest: SHA256
  `47a015b6cf7f2ef10ff246fbf325e3f63459aa277d8ab3bd4bd6f61b4e0ce25f`.
- R6 source archive: SHA256
  `5d68feb39f2b3b718af2c18dfaa9bd7947b44b7d7c6af15dfc6acf4964a4bd73`.
- OCR: `nvidia/nemotron-ocr-v2`, revision
  `0e83e83f17943524b90afa6c0fd82ac2bc1a40ca`.
- RADIO: `nvidia/C-RADIOv4-SO400M`, revision
  `c0457f5dc26ca145f954cd4fc5bb6114e5705ad8`.
- CUDA image: `docker.io/nvidia/cuda@sha256:0eee3094c71518ad31d011a594ae6ed6de72959ee07e318cb31cffe71690e90c`
  (CUDA 13.0.2 development image, Ubuntu 24.04, Linux amd64).

The batch definition has maximum one replica and a provider-enforced
3,300-second deadline. Request TTL is 3,000 seconds. The controller checks actual
L40S availability, existing credit, the hourly price (at most USD2.22), and the
created deployment's image, command and deadline before making one invocation.
The compute allocation estimate must remain below USD3. Account balance is not
an itemized task bill. No top-up, credential creation or other job changes occur.

The worker conservatively counts queueing, image pull and bootstrap time against
an absolute deadline established before deployment creation. It uses the earlier
of the replica deadline and request TTL, leaving 300 seconds for export plus a
15-second termination grace. A long cold start therefore reduces the available
extraction time instead of silently consuming the export reservation.

## Data and recovery

Only the hash-bound public image manifest and pinned source reach the GPU.
Labels, product identities and candidate tables stay on the authorized host.
The worker receives two expiring PUT capabilities for unique task objects in
the existing private bucket; account-level keys remain in their existing host
store. Capabilities are never written to logs, source or result files.

The worker exports the complete extraction archive and a small hash-bound
result object. This avoids relying on undocumented large HTTP-response limits.
The host verifies the downloaded archive, pauses only the task's batch
deployment, and retains both raw evidence and object-storage outputs.

Create and invocation intents are recorded before dispatch. An unknown result
is reconciled against the same deployment and result objects; the controller
does not submit another job. Read-only transport failures are retried within
bounds. Failed downloads remain available as separate partial files.

An earlier invocation returned HTTP 404 before feature extraction. Its request
path was not logged, so the precise forwarding mismatch is not proven. The
worker now admits only the exact task's four root/run path aliases through the
same pinned input checks and logs safe method/route diagnostics. The controller
also reads the documented inference status endpoint: a definitive `Error` for
the exact request ends the wait and triggers cleanup. Read failures do not cause
an inference retry. Previous failed attempts and their evidence remain intact.

`finish_training.py` requires all 6,993 successful image observations, their
raw OCR/admission hashes, the frozen input hashes and a clean R6 source checkout.
It builds 404,000 candidate rows and trains the fixed twelve R6 rankers with
separate finite subprocess deadlines. It checks actual weight updates, losses,
prediction counts and paired evaluation against R4's 466/727 development
rank-one result. Complete predictions and OCR observations remain private.

## Fixed nonlinear comparison

`nonlinear_protocol.json` freezes four histogram gradient boosting models before
R8 development results are observed. The model settings are identical to R7:
15 or 31 leaves, L2 regularization 1 or 10, 150 iterations, learning rate 0.05,
minimum 100 samples per leaf, and seed 20261115. The input now contains all
eleven measured features: the original six, RADIO similarity, and four OCR
matching/conflict features. The frozen R4 score is used only for comparison.

`train_nonlinear_features.py` requires a complete, hash-bound twelve-fit linear
verification, the frozen prepared inputs, the new feature manifest, and clean
committed training source. Fits use only training queries with a positive
candidate, with equal family/query and positive/negative class weights.
All 727 development queries remain in the denominator, including the eight
whose correct candidate is absent. No development early stopping or grid
changes are permitted. Four CPU threads and a 600-second deadline bound the
run. Existing packages are reused; this comparison makes no provider calls.

The run writes numeric aggregate metrics separately from private candidate
predictions and joblib models. The selected development candidate replaces the
frozen control only if rank-one recall improves, or recall ties and MRR improves.
That development choice does not establish accepted coverage or authorize a
production change. OCR and RADIO remain frozen feature extractors; these runs
train the retrieval rankers, not the underlying NVIDIA foundation models.

## Interpretation

Execution of these scripts does not itself establish a retrieval improvement.
Only completed, verified runs may be reported. Development rank-one recall is
not accepted coverage, calibrated confidence, a fresh test result or an OCR
accuracy measurement. No transcription ground truth or new real-glasses
qualification is introduced. The user target above 93% remains unqualified
until a separate acceptance evaluation supports it.

Sources: [Verda batch jobs](https://docs.verda.com/containers/batch-jobs/),
[async request semantics](https://docs.verda.com/containers/synchronous-and-asynchronous-inference/),
[public API schema](https://api.verda.com/v1/openapi.json).
