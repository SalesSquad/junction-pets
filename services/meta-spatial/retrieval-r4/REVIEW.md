# R4 independent review record

Work: `META-LENS-R4-COVERAGE93-20261114`.
Base: `6f3601b33fb875e8ea372c48f4b7be4db737b87d`.
Owned scope: `services/meta-spatial/retrieval-r4/**`.
Historical R2/R3 bytes and results remain preserved.

## Worker responsibilities

- R Programming Expert lane: actual base-R pairwise logistic model, analytic
  gradient, weighting, fixed development selection, conditional calibration,
  portable model and numerical tests.
- Source/feature lane: immutable data/cache/model bindings, six allowed
  features, candidate export, separation checks and independent source review.
- NVIDIA Skills lane: existing encoder/compute/budget inspection, current
  provider availability and an independent orchestration review. No new GPU,
  model endpoint, key, persistent volume or installed training framework was
  created for R4.
- Coordinator: integration, portable Python runtime, source-bound execution,
  actual Mac training, model parity, evidence and PR follow-through.

## Findings repaired before the first fit

1. **Candidate retention assumption.** Initial R source
   `e75a91babefd6044c217b613657c2bd90d2fe1b45ed98b238482dbbfda417ae8`
   required the original adapted rank-one candidate to survive RRF pruning.
   A numerical counterexample showed a legitimate capped pool without it.
   The unsupported rejection was removed. Restricted-pool baseline metrics
   were renamed `retained_candidate_r3_order`; the full-gallery baseline is
   separately recorded by the exporter. A dedicated omission test preserves
   every query in the denominator.
2. **Confidence overflow.** Initial runtime
   `45aa5675ceae816f11b93008f4a4d75a379fd6988bad19a8edfb99a319d4a727`
   could combine finite scores of opposite sign into infinite confidence.
   Runtime now rejects nonfinite confidence. The regression test exercises
   finite scores of +/-1e308; action authorization was always false.

Reviewed repaired bytes:

| File | SHA256 |
| --- | --- |
| `train_reranker.R` | `3a8a6cc620b6c5af94e36d8afd34b0fffc250412e1525ad91eece6a82ea28df5` |
| `runtime.py` | `a027a6b40f2495e0fb0c3fae3d86bd8cac59e4e5bff1dae09d1ce2ad23483512` |
| `contract.json` | `a45f587632d1ab14aeaf7140051b4f0f440a4f7bdb75110dc2f6896581759154` |

The source reviewer found no remaining blocker for the admitted multi-candidate
research run. Objective/gradient, train-only scaling, fixed development
selection, feature order, numeric JSON and missing-positive denominators were
reviewed. Query error and family-any-error bounds are different quantities;
the family bound does not certify query-weighted 99% precision.

## Explicit compatibility edge

The descriptive R table assigns a singleton the top score with margin zero.
Python deliberately returns no confidence and no diagnostic acceptance when
there is no runner-up. Every query in both executed experiments has 100
candidates. The exhaustive parity assertion covers those actual candidate
pools and does not claim general singleton confidence equivalence.

## Original numerical warnings

The preserved NumPy 2.2.6 / macOS encoder-cache projection emitted matrix
multiplication RuntimeWarnings. These were not suppressed, the source was not
changed, and the backend cause was not diagnosed. All full score matrices and
exported features passed finite-value admission. All original R3 full-gallery
Recall@K values reproduced. An additional label-blind sample independently
recomputes 128 image/image, image/text and adapted comparisons with scalar
`math.fsum` and float64 `einsum(optimize=False)`; the fixed tolerance is 1e-5.
Actual errors, source hashes and samples are in each run's numeric evidence.
This is a bounded cross-check, not an exhaustive encoder certification.

## Candidate-policy comparison

Run 01's RRF pool retained positives for 711/727 development queries, while
the original adapted top100 retained 719/727. Run 02 evaluates that explicit
alternative without changing the feature allowlist, train/cal/test split,
R trainer, ridge grid or risk target. `comparison_protocol.json` records the
development Recall@1/MRR selection rule. Both historical test results remain
visible, and neither becomes a fresh qualification.

## Execution evidence interpretation

Independent orchestration review reproduced two malformed-output acceptance
cases in runner `237c0fe54e03170614be24cc232a66b72a578feeefffb724ac3b3bcc24413f55`:
duplicate query-metric keys were silently overwritten, and a NaN reference
confidence could evade the tolerance comparison. Both are now rejected.
Three focused malformed/valid-output checks passed independently. Reviewed
fixed runner hash:
`bffabea2914b9c008c466e75c3d7615c2cc2edc36344a23a7bc3d3a250f62002`;
test hash: `99473476a7b672ff6a061e3fc47d07e618f522924c307b68f4702d6793eb544e`.
The original experiment receipts are preserved; a separate final verification
rechecks both complete outputs with the repaired validator. No malformed actual
campaign artifact was observed. This correction does not change model weights.

Command-receipt helper status is an operational record, not a signed or hosted
qualification. Commands that commit before starting the experiment naturally
change HEAD relative to receipt submission. Each experiment independently
requires a clean committed source at start/end, binds its exact source bytes
and verifies immutable inputs. The model report binds the actual CSV, manifest
and R training source. The Python parity result checks every actual candidate
score and every top result. See `results/` for executed source IDs and hashes.
