# Meta Lens retrieval acceleration

Prepare a gallery once, retrieve a bounded candidate pool, and reconcile the
existing four Nemotron specialist lanes without issuing more model calls.
This subtree is an independently usable offline integration. It does not change
R3 qualification, R4 reranking, R5 prompts, the SAM observation envelope or the
private host's identity and task authority.

## What changes

| Component | Behavior |
| --- | --- |
| `PreparedCandidateIndex` | Copies and binds gallery features/IDs/weights, projects the gallery once, then projects only new queries. |
| Candidate pool | Configurable 1–128 candidates, with original gallery order breaking exact score ties. R4 can retain its 100-candidate pool. |
| Query batches | Scores at most 128 query rows at once; exact full dot-product retrieval, not approximate nearest neighbors. |
| R5 reconciler | Checks existing request, receipt, response and observation files for each case/lane; reports complete, failed and missing evidence separately. |
| Additional views | Deduplicates matching requests from visual/detail/critic; every request remains an uncaptured proposal. |
| CLI and schema | Runnable search/reconciliation commands with a common advisory JSON output contract. |

The R5 interfaces are pinned to the original four-lane source
`fbf27ab1ca3905ccc1c561cc6a6e7e9f05df9a5d` and the current ordered-subset source
`9a16495474f815e43729bbae87eb5d42d71d49a2`. Its existing lanes are `ocr`,
`visual`, `detail`, and `critic`. They share a backbone; agreement is not four
independent model confirmations. R5 still presents exactly three aliases from
its original R4 candidate pool. This module neither widens those prompts nor
silently injects the correct product into them.

The current runner can request an ordered nonempty subset of those lanes and
declares `semantic_choice_schema:true`. Reconciliation checks that variant's
exact fields and case/call/concurrency limits. A critic-only run can be COMPLETE
for its requested plan while specialist agreement remains partial. Requested,
unrequested and missing lanes are reported separately. Combining separate pilot
runs or selecting superseding repairs remains the existing R5 evaluator's job.

## Use a prepared gallery

Requires Python 3.12 and NumPy. Use the project's existing isolated Python
environment; `requirements.txt` pins the environment used for this delivery.
For schema checks and benchmark BLAS metadata, use `requirements-dev.txt`.

```python
# Add this directory to your application's module search path.
from candidate_index import PreparedCandidateIndex

index = PreparedCandidateIndex(gallery_features, product_ids, a=weights_a, b=weights_b)
result = index.search(query_features, query_ids, top_k=100, batch_size=16)
# Keep index alive for subsequent queries against the same gallery and weights.
```

Inputs are already unit-normalized 768-dimensional features. A residual adapter
has float32 matrices `(768, 64)` and `(64, 768)`. Omitting both matrices preserves
the supplied normalized identity features without another normalization pass.
Gallery and adapter bytes are copied into immutable storage; changing a caller's
array afterwards cannot silently change this index. A changed catalog or a new
adapter needs a new index.

The API allows at most 50,000 gallery rows, 4,096 query rows, 128 candidates and
128 query rows per score batch. IDs are unique within each supplied sequence and
at most 256 UTF-8 bytes. At the largest gallery/batch sizes the score chunk is
25.6 MB; this is not a bound on the entire process. Gallery copies, projections,
features and JSON results also use memory.

Exact score ties retain original gallery order, including ties at the top-K
boundary. Different BLAS devices or batch shapes may change the last bits of a
float32 result and reorder nearly tied scores. Do not use these research scores
as a replacement for the frozen R3 decision/qualification policy.

## Run from the repository root

The feature NPZ contains `gallery_features`, `gallery_ids`, `query_features`, and
`query_ids`; IDs are NumPy Unicode arrays. Optional `a` and `b` arrays provide a
residual adapter. Object/pickled arrays are rejected. ZIP expansion, member
names, shapes and declared byte lengths are checked before loading arrays.

```sh
python services/meta-spatial/retrieval-acceleration/cli.py search \
  --features /path/to/features.npz --top-k 100 --batch-size 16 \
  --output /path/to/new-candidates.json

# Reuse a frozen R3 selection/checkpoint instead of embedding a/b in the NPZ.
python services/meta-spatial/retrieval-acceleration/cli.py search \
  --features /path/to/features-without-weights.npz \
  --r3-training-root /path/to/r3-training --top-k 100 \
  --output /path/to/new-r3-candidates.json
```

The R3 option uses the unchanged repository `visual_adapter.py` at SHA256
`933de9d32de9782e4b399ef7f5d0a87c94e8389dd65f7ed1eae96a541f0250b1`, including
its selected-checkpoint digest check. A trained selection additionally needs
R3's pinned `safetensors==0.6.2`; it does not need Torch or a new model download.
The result binds selection/checkpoint bytes but does not evaluate qualification.
One CLI invocation prepares one index; a persistent host should reuse the Python
object across requests to obtain the full amortization benefit.

```sh
python services/meta-spatial/retrieval-acceleration/cli.py reconcile \
  --run-dir /path/to/completed-or-partial-r5-run \
  --cases /path/to/frozen/cases.json \
  --expected-source-commit FULL_EXECUTION_COMMIT \
  --expected-model nemotron-3.5-super-vl \
  --output /path/to/new-reconciliation.json
```

Reconciliation uses only the standard library. The expected source commit is
the run's execution commit; a preparation manifest may legitimately declare an
earlier commit. Every output filename must be new: existing evidence is never
overwritten. CLI input/contract failures exit with code 2 and a structured error.

## Evidence and authority boundaries

The reconciler checks source/model declarations, exact cases-file hash, unique
case/lane paths, image-hash manifests, request/receipt consistency, single-attempt
receipt contracts, response bytes/hash, reported model/usage, parsed observation
content and observation hashes. A stored observation must agree with the actual
persisted completion content. Missing evidence is `PARTIAL`; contradictory or
corrupted evidence is an error. The runner's `summary.json` is not trusted to
declare completeness. No retry or new provider call is performed.

Digests establish supplied-file consistency. They do not attest checkpoint
weights, the execution environment, transmitted pixels, original request
payloads, billing or actual attempt counts. R5 persists sanitized response bytes;
those are what the consumer checks. Missing receipts do not prove that no call
occurred. Image files and the evaluation-truth file are not opened. The allowed
top-level evaluation-truth digest is not a hidden label in a model case.

All outputs preserve `qualification:false`, `action_authorized:false`, and
`physical_identity_verified:false`. Recommendations also preserve
`status:"proposed"` and `captured:false`. A host that wants a label close-up or a
side view must use its existing consent/capture process, obtain actual new
pixels, and pass them through its existing causal observation contract. Neither
a model vote nor a proposed extra view proves physical identity or task completion.

This delivery performs no model training and establishes no new recall,
accepted-coverage or 93% product claim. Historical R3 results remain unchanged.

## Focused verification

Delivered result: **68/68 checks pass, zero skips**, with source hashes unchanged
during execution and independent review of the final evidence. The final fixed
synthetic benchmark gives the following median times for 32 streamed queries:

| Timed path | Seconds | Relative speed |
| --- | ---: | ---: |
| Original R3 runtime | 0.900682 | 1.00× |
| Prepared index, including preparation | 0.069478 | 12.96× |
| Queries after preparation | 0.014743 | 61.09× |

All 96 query comparisons retained identical top-five IDs/order and zero measured
score difference. Gallery projection count falls from 32 to one per run.
This comparison uses one observed OpenBLAS thread on a CPU.

```sh
OPENBLAS_NUM_THREADS=1 python -m unittest discover \
  -s services/meta-spatial/retrieval-acceleration -p 'test_*.py' -v

python services/meta-spatial/retrieval-acceleration/benchmark.py \
  --output /path/to/new-synthetic-benchmark.json

# Also preserve a source-bound test receipt and raw log in a new directory.
OPENBLAS_NUM_THREADS=1 python services/meta-spatial/retrieval-acceleration/verify.py \
  --output-dir /path/to/new-focused-verification
```

The benchmark compares the exact pinned R3 runtime with the prepared index on
one fixed synthetic workload: 4,096 gallery rows, 32 streamed queries, rank 64,
top 5, three repeats and one excluded warmup per algorithm. It includes index
preparation in the main speedup, retains every repeat, alternates execution
order, checks candidate order and score tolerance, and records source hashes.
Its result describes this CPU workload, not NVIDIA inference or end-to-end
glasses latency. Do not rerun a successful benchmark merely to find a larger number.

The first combined verification found an interpreter-dependent JSON depth check.
The final implementation enforces 64 nested containers explicitly. Its failed
receipt/log and the first benchmark remain unchanged in `evidence/attempt-01/`
and in milestone commit `0a51c02e8a5b6b746e5c8912f041ea41cbf8fe89`.
The benchmark was repeated once to bind the changed shared-contract source;
the first measured preparation-inclusive ratio was 11.98×. Both runs retain
all three repeats; the final result was not selected from a parameter search.

See `evidence/verification.json`, `evidence/benchmark.json`, and
`evidence/review.md` for the delivered checks, measured result and independent
review. Their source hashes bind the inspected and executed files.

## Ownership and integration

Work ID: `META-LENS-ACCEL-20261114`. Base commit:
`3e2aeaf69cb7a54c79ba3a35c06dfd9ade89d3e1`. Only this new subtree is changed.
No R3/R4/R5 files, shared workflows, CRACI scheduling, provider routes, credentials
or production settings are changed. The existing R4/R5 owners can consume the
prepared-index API and reconciliation CLI; adoption by those lanes is a separate
observable integration step, not implied by this source delivery. Portfolio PR
Recovery remains the sole merge integrator.
