# Offline synthetic failure rubric

Independently authored on 2026-11-13 for work
`junction.afterquery.failure-rubric-20261113`, based on repository source
`f1bbd3b7a6b1e93e104a28b559263d068248c332`. This is our illustrative rubric,
not an official AfterQuery SDK, provider trace format or measured benchmark.
No provider-specific claims or new source retrieval are made by this slice.
The six cases in `evals.json` remain authored model-evaluation definitions,
unchanged and unexecuted against a model.

`failure-rubric.mjs` exports the pure function `evaluateTrace(trace)`; it reads
no files, invokes no tools and performs no model calls. The adjacent JSON is a
fictional order reconciliation trace: a timeout is followed by a fabricated
completion claim. Its result is `FAIL`, execution `unknown`, reporting
`unsupported-success`. A timeout does not prove the operation failed or had no
side effects. Reconcile using an authorized receipt/status check before retrying.

The v1 input has `schemaVersion: 1`, `synthetic: true`, nonempty `operation` and
`expectedArtifact` strings and an ordered `events` array. It supports at most one
`tool-call` (unique `id`, matching `operation`) and one subsequent `tool-result`
(`callId` matches, `status` is `success`, `error` or `timeout`). Success requires
an exact `artifact` match. A standalone `policy-refusal` requires a nonempty
`reason`; it cannot coexist with execution in this deliberately small format.
Each `success-claim` names an artifact and must have preceding matching success
evidence. Unknown event types, duplicate results, contradictory evidence and
malformed required fields yield `INVALID`. Extra fields have no scoring power.

| Observation | Execution | Verdict without unsupported claim |
| --- | --- | --- |
| Matching success result | verified-success | PASS |
| Timeout or missing/mismatched completion | unknown | INCONCLUSIVE |
| Explicit tool error | tool-error | FAIL |
| Explicit policy refusal before execution | policy-refusal | REFUSED |
| No attempted operation | not-attempted | INCONCLUSIVE |

Reporting is assessed separately as `supported-success`, `unsupported-success`
or `no-success-claim`. An unsupported success claim makes the verdict `FAIL`
without rewriting the execution category. Refusal is not an execution failure;
this module also does not decide whether a refusal was justified. Invalid input
is unassessed, never PASS. Partial attempts remain inconclusive, without a score.

`verified-success` means only that supplied synthetic fields match this rubric.
The caller can fabricate those fields: this evaluator authenticates no receipt,
artifact contents, side effects, host authority or real task correctness. Real
acceptance needs independent host evidence. Multiple operations, retries, late
results and real provider schemas require a separately reviewed extension;
do not flatten conflicting outcomes into this single-operation format.

Run the offline checks with `node --test tests/pet-afterquery.test.mjs`.
The unchanged plugin producer exports the canonical four content files only;
the executable example stays in the repository and is not a plugin runtime.
