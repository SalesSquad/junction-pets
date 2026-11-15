# Follow-up: measured failure modes and next useful experiments

Work: `META-LENS-ACCEL-FOLLOWUP-20261114`. Starting source: PR198,
`4210b617b087a63a52b0ea1d09ae33b2df9d6d46`. These are new scale, numerical and
real-artifact replay experiments, not another run of the original 68 checks or
the original 4,096-row speed benchmark. No new model inference or GPU was used.

## What was improved now

The original index converted the entire gallery to float64 to check row norms.
For 50,000 rows, preparation raised process RSS to roughly 956 MB despite a
25.6 MB maximum score chunk. The repair performs the same norm checks in fixed
1,024-row chunks. Copied float32 values, projection, normalization of projected
features, ranking and index bindings remain unchanged. Late zero/invalid norms
retain priority over an earlier merely nonunit row.

| 50,000-row mode | Original preparation peak RSS | Repaired peak RSS | Reduction |
| --- | ---: | ---: | ---: |
| Identity | 955,473,920 B | 495,554,560 B | 48.14% |
| Rank-64 residual | 955,580,416 B | 700,801,024 B | 26.66% |

Whole fixed-workload peaks were 993,763,328 → 533,950,464 B for identity and
1,001,046,016 → 732,459,008 B for residual. These are process measurements,
including resident inputs and Python/NumPy, not isolated buffer sizes or a
universal memory ceiling. The fixed-only RSS was recorded before constructing
the old reference implementation for parity comparison.

**14/14 affected checks passed**: nine existing index checks plus five new chunk
boundary, byte-preservation and error-priority checks. Full candidate/score
digests matched the pinned old implementation for 128 queries × 128 candidates
× three batch sizes × two modes: **98,304 candidate positions**. The two modes
also retained every index binding.

The improvement is a memory result. The first residual preparation sample was
slower (1.167 → 1.551 seconds), while later fresh-rebuild medians were faster
(1.116 → 0.941 seconds). These samples do not establish a universal preparation
speedup. Warm single-query medians in this environment were approximately
13 ms after the repair. Encoding, network, model inference and device capture
are outside those timings.

Evidence: [baseline](evidence/followup-20261114/index-stress.json),
[repaired cases](evidence/followup-20261114/index-stress-after-fix.json),
[comparison](evidence/followup-20261114/index-stress-repair-findings.json).
Baseline probe bytes and all original receipts remain intact. The experiments
used about 42.07 measured CPU seconds in total, one BLAS thread, six fixed scale
cases plus one diagnostic case, then only the two affected 50,000-row cases.

## Real R5 artifacts now work with this consumer

The model owner published the previously unavailable evidence in PR195 at
`b3d6e31ceb797c49293613480af510f999eaeeb2`. The replay checked 178 committed text
files (416,259 bytes), their Git blob identities, and 177 published SHA-256/size
entries plus the pinned manifest. No images, credentials or original host
paths were followed. Original bytes remained unchanged.

| Pilot | Consumer result | Requested pairs | Valid observations | Failed | Missing receipts |
| --- | --- | ---: | ---: | ---: | ---: |
| 03 | COMPLETE | 4 | 4 | 0 | 0 |
| 04 | PARTIAL | 28 | 21 | 1 | 6 |
| 05 | PARTIAL | 7 | 0 | 1 | 6 |
| 06 | COMPLETE, critic only | 7 | 7 | 0 | 0 |

Earlier pilots 01/02 predate required reasoning/response-format plan fields and
remain explicit validation errors. Their failed receipts are preserved and
separately inventoried; the consumer was not relaxed to make them pass. A complete
critic-only run still has partial cross-specialist agreement. The existing R5
evaluator owns combining pilots and superseding technical failures.

Evidence: [replay report](evidence/followup-20261114/r5-replay-report.json),
[download bindings](evidence/followup-20261114/r5-replay-downloads.json),
[replay checks](evidence/followup-20261114/r5-replay-checks.txt).

## The main quality bottleneck is upstream of another judge

The published evaluation, its bound truth file and retained R arithmetic agree:
the true product was in the shown top three for **6/8** development cases, and
R4 already ranked all six first. This cohort contained **zero recoverable
baseline errors inside the shown pool**. Visual/detail each ranked 5/8 correctly;
critic ranked 4/8 and made one wrong proposal. Visual and detail chose the same
first candidate in all eight cases. The prompted roles share one backbone.

This is a diagnosis of eight selected development families, not a population
accuracy estimate. Increasing the number of judges over the same three images
cannot recover a product that is absent from those candidates. It can also lose
a previously correct answer, as happened here.

OCR reported text in 3/8 images and 23 spans, but no independent transcription
labels exist. The detail role requested five label close-ups, one side view and
one other view; **none was captured**. A request for more information is not new
information. The recorded NIM attempt was BLOCKED_AUTH with zero reported calls;
this replay neither retries it nor asserts the current state of host credentials.

Across all historical pilot receipts, 42 attempts reported 32 valid observations
and 70,733 total tokens. Failed generation/contract attempts accounted for 22,395
reported tokens (31.7%). This is historical receipt accounting, not a current
failure rate or verified billing. Reasoning/schema repairs are already present
in the current R5 runner; retain a small canary before another broad campaign.

## Remaining risks and the next useful work

| Priority | Observed limit or integration risk | Next concrete action |
| --- | --- | --- |
| 1 | Current development cohort cannot demonstrate a useful reranking gain | Freeze a diagnostic cohort with recoverable baseline errors and inspect recall@3/10/32/100 before another model campaign. |
| 2 | Same-image, same-backbone specialists can agree and still lose baseline accuracy | Keep R4 as the measured baseline; diagnose q0006 and critic q0001 before proposing any fusion or majority policy. |
| 3 | Requested close-ups are still absent | Obtain actual authorized new frames through the existing capture host, then compare their added information and error reduction. Label OCR independently. |
| 4 | Residual preparation still reached about 701 MB and the workload about 732 MB | Budget process RSS and concurrent rebuilds, not just score chunks. Test any mapped/projected-cache design separately before using it on constrained devices. |
| 5 | Rebuilding a gallery frequently removes reuse benefit | Key host caches by current catalog/adapter/embedding version and relevant tenant/consent revision; atomically select a fully built index. Reuse the existing host ownership model. |
| 6 | Near-tied float32 scores can reorder with batching | Keep a declared batch/precision policy for comparisons; show ambiguous candidates without converting rank one into physical identity. Any shortlist rescore/tolerance rule needs its own frozen evaluation. |
| 7 | Larger batches improve throughput but can add waiting time | Measure capture-to-guidance tail latency; use bounded waiting rather than waiting to fill a large live batch. |

The numerical diagnostic deliberately created near-identical candidates. Top one
changed in 32/32 queries between batch sizes 1 and 16; same-batch repeats were
exact. The largest selected-score error against a float64 diagnostic was about
6.03e-7, with a float64 top-two gap of about 1.80e-10. This exposes a documented
precision limit, not a measured real-product error rate. Ranking math was not
changed to hide it.

Cache-amortization figures are arithmetic estimates using measured warm/fresh
times and one initial preparation, with resident inputs. They compare reuse
against rebuilding this index for each query, not against the old R3 runtime.
They suggested reuse from roughly the second query in most scenarios, but cold
start noise and changing catalogs prevent a universal break-even threshold.
Two read-only threads matched sequential results in the tested scenario; this
does not validate arbitrary concurrent rebuilds or host-level cache switching.

For device composition, use the existing session/capture-generation/task-revision
checks described in [OBSERVATION.md](../OBSERVATION.md). A stale sighting, a SAM
track and a catalog match do not establish current physical-item identity.
ARKit phone pose also does not register glasses geometry by itself.

## Suggested next experiment, before more provider calls

The R4/R5 owner should freeze a **development-only diagnostic** plan, for example
24 distinct families split into three explicitly labelled cohorts: baseline
wrong but truth inside top three; truth at ranks 4–100; and truth absent from
top 100 or visually ambiguous. If those cohorts are unavailable, report that
shortfall instead of duplicating cases. Truth may select this offline diagnostic
cohort but must never enter provider prompts, live routing or physical-identity
decisions. Its selected-error rates cannot estimate general product accuracy.

First compare candidate retention and baseline losses by cohort. Then test one
bounded additional observation or independently labelled OCR where information
is actually missing. Count corrections, regressions, abstentions, real extra
frames, latency and reported tokens per corrected error. Keep a separate future
qualification holdout untouched and retain all failures. This document launches
no new provider jobs, changes no thresholds and makes no 93% qualification claim.

## Reproduction

Run the affected checks in the existing isolated environment:

```sh
cd services/meta-spatial/retrieval-acceleration
OPENBLAS_NUM_THREADS=1 python -B -m unittest -v test_candidate_index test_index_memory
python -B replay_r5.py --input-root /path/to/pinned-r5-text-artifacts \
  --download-index evidence/followup-20261114/r5-replay-downloads.json \
  --output-prefix /path/to/new-replay
```

The download index pins the exact published text subset; replay inputs are not
duplicated into this subtree. They remain available in the source-bound
[R5 results directory](https://github.com/SalesSquad/junction-pets/tree/b3d6e31ceb797c49293613480af510f999eaeeb2/services/meta-spatial/retrieval-r5/results).
`stress_probe.py --help` describes the new fixed probe and the separate repair
comparison mode. The original probe source is retained in the baseline text
snapshot, so its recorded source hash remains reproducible.
