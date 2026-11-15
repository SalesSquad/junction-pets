# Meta Lens R8: finite NVIDIA feature extraction

R8 executes the existing R6 OCR/RADIO experiment on one Verda L40S batch
replica. It keeps the frozen models, input images, train/dev split and twelve
ranker candidates unchanged. The R7 nonlinear experiment did not outperform
R4; R8 therefore adds measured image features rather than repeating that grid.

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
3,600-second deadline. Queue TTL is 3,000 seconds. The controller checks actual
L40S availability, existing credit, the hourly price (at most USD2.22), and the
created deployment's image, command and deadline before making one invocation.
The compute allocation estimate must remain below USD3. Account balance is not
an itemized task bill. No top-up, credential creation or other job changes occur.

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

`finish_training.py` requires all 6,993 successful image observations, their
raw OCR/admission hashes, the frozen input hashes and a clean R6 source checkout.
It builds 404,000 candidate rows and trains the fixed twelve R6 rankers with
separate finite subprocess deadlines. It checks actual weight updates, losses,
prediction counts and paired evaluation against R4's 466/727 development
rank-one result. Complete predictions and OCR observations remain private.

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
