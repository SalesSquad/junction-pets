# Experiment & Learning Registry — shared Meta / Verda / Apple

An **evidence-only**, versioned, Node 22+ service. It neither starts GPU VMs,
trains models, updates a privileged Chibi host nor approves a release. It is
not the existing `services/dispatch-ledger` or `ops/registry.mjs`.

The repository retains only *redacted run metadata* and source/artifact hashes;
licensed video, personal data, private experiment input, model weights and
provider credentials stay in their authorized private stores.

## Quick start

```sh
node services/experiment-registry/cli.mjs summary
node services/experiment-registry/cli.mjs record-policy --input /path/to/frozen-policy.json
node services/experiment-registry/cli.mjs record-run --input /path/to/redacted-run.json
node services/experiment-registry/cli.mjs record-run --input /path/to/candidate-run.json --baseline baseline-id --policy /path/to/frozen-policy.json
node services/experiment-registry/cli.mjs record-failure --input /path/to/redacted-failure.json
node services/experiment-registry/cli.mjs review-case --input /path/to/review.json
node services/experiment-registry/cli.mjs plan-next --input /path/to/next-experiment.json
node services/experiment-registry/cli.mjs compare --baseline baseline-id --candidate candidate-id --policy /path/to/frozen-policy.json
node --test services/experiment-registry/registry.test.mjs
```

**Register the policy before the first baseline run:** `record-policy` saves
the *full* immutable policy at `policies/policy.<sha256>.json`, with every
metric role, bound, accepted evidence level, sample-set digest and protocol.
A model-evaluation cannot be recorded unless that exact policy is already in
the registry. A comparison also requires the registered bytes so an independent
reviewer can reproduce it later; a bare hash is insufficient. The declared
`frozenAt` is user-supplied metadata, **not independently authenticated time**:
publish its policy file to a reviewed repository commit before training, and
verify the commit history independently for claims of predeclaration.

**Model admission is fail-closed:** importing a `model-evaluation` without
`--baseline` and `--policy` retains the evidence as an unpromoted baseline
(`admission.status:not-compared`) but exits **2**. Never treat successful
persistence as permission to advance. A candidate import with both options
immediately writes a comparison; exit 0 means *eligible for independent review
only*. Non-model run imports exit 0 on successful recording. For a first
baseline, an exit of 2 is expected until a separate newer candidate exists.

All commands work with `--root /some/approved/private/path`; default is
`ops/experiments`. Run IDs are stable and immutable. Re-ingesting the same
canonical JSON is idempotent; conflicting content under an existing ID fails.
Atomic hard-link publication prevents concurrent writers overwriting results.
Git itself remains the cross-device source of truth: use owned branches, PRs,
and normal review to sync new sanitized records. This CLI does **not** provide
distributed locking, continuously poll providers or claim automatic cloud sync.

### Run contract

`record-run` requires `schemaVersion:1`, safe `runId/projectId/taskId`, `kind`,
`capturedAt`, `status`, `{source:{repository,commit}}` with full commit SHA,
`evidence:{level,ref,receiptSha256}`, `dataset` (or null), `evaluation` (or
null), `artifact` (or null), `metrics` (each with unit, direction, samples),
`limitations` and `policySha256` (or null). `kind: model-evaluation` requires
all model-specific evidence, including a registered frozen policy digest and a real
checkpoint SHA. The supported evidence labels are explicitly **not provider
attestations**. Historical imports with unknown dataset/protocol hashes must
use `historical-result`, remain non-comparable and say what is missing.
After an approved learning plan, a real training/model-evaluation run may include
`planId`: its referenced plan, task ID and capture timestamp are verified, making
`failure → case → review → plan → run` traversable. This does not dispatch work.

### Failure → new proposed case → next training experiment

1. `record-failure` accepts `failureId`, `runId`, `caseSha256`, `failureCode`,
   `severity`, and `observedAt`; it creates a deterministic proposed case.
2. That case has `trainAdmission:false`, `evaluationAdmission:false`, and
   `quarantined-pending-review` status. Raw image, transcript, user ID and
   labels are **never accepted** in the record schema.
3. `review-case` appends a separate, unverified reviewer statement (`reviewId`,
   `proposalId`, `decision`, `reviewer`, `reviewedAt`, `evidenceSha256`).
4. `plan-next` requires that statement to approve development, preserves the
   same task ID, requires an objective metric actually observed in the original
   run, and fixes `datasetRole:new-training-or-development-only`.
   It creates only `planned-not-dispatched`, never a training run.

If a failed case is used as training input, its evaluation must be performed on
**a distinct frozen independent set**. No auto-labeling, holdout admission,
provider call or private-data transfer occurs here. A self-reported reviewer
name does not establish authenticated approval.

### Compare candidates safely

Provide a *predeclared* policy with `policyId/taskId/evaluationKind`,
`sampleSetSha256`, `protocolSha256`, `frozenAt`, `minSamples`,
`allowedEvidenceLevels` and a list of metrics:

```json
{
  "id": "false-candidate-rate", "unit": "rate", "direction": "lower",
  "role": "safety", "minimumImprovement": 0, "maxRegression": 0,
  "maxValue": 0.03
}
```

At least one metric needs `role:primary`, at least one other or shared metric
must have `role:safety` with zero permitted regression, and the exact policy
must already be registered. Both runs must pin the canonical
policy SHA-256, be successful model evaluations for the same task, same exact
evaluation dataset and sample-set hash, independent holdout/shifted split,
protocol, evidence class, sample count and metric definitions. A candidate must
be captured **strictly after** its baseline, refer to a different checkpoint,
and all metric values must be finite/nonnegative (counts also safe integers).
Missing or
non-comparable results return `incomparable`. Any primary or safety regression
outside the declared bounds or a failed absolute safety limit returns
`rejected`. Only primary improvement with no disallowed metric regression is
`candidate-eligible-for-review`; it never authorizes release or host effects.
The CLI exits 2 on rejection/incomparability/**missing comparison**, so it can
be used as a fail-closed gate.
`record-run --baseline ... --policy ...` records the new candidate **and
automatically compares it at ingestion**: rejected results remain auditable,
while CI/job orchestration receives a nonzero exit code. The caller must provide
the frozen baseline and policy; the registry never guesses a comparable prior
run or initiates a model deployment.

Important: hashes and supplied run metadata are **not cryptographic provider
or reviewer signatures**. Independent provider, human and device attestation
must be checked elsewhere before any production decision. Never compare a
validation score with a shifted/holdout score as if they share the same cases.

## Initial historical index

`ops/experiments/runs/` includes explicitly non-promotable evidence pointers
for the verified Meta kernel, numeric-only synthetic PR #70, Apple source
typechecks PR #73, and separate Verda Savi/Wan examples. They are an inventory,
not proof of live glasses, an iPhone release or a trained Meta vision model.
Future runs should be recorded from **actual immutable receipts**, with unknown
fields left unknown rather than inventing a digest. For full scientific
comparison, first freeze genuine independent samples and a policy before new
runs, then emit comparable `model-evaluation` envelopes for both baselines.
