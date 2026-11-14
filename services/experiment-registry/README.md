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

## Event-ready private inbox (EXPERIMENT-AUTO-20261114)

`inbox.mjs` is a source-agnostic **one-shot importer**, not an automatic scheduler.
Meta, Verda and Apple producers can publish the same envelope format after any
job exit (including failed jobs). Nothing here installs a daemon, LaunchAgent,
provider connection, GPU workload or new resource. Wire the one-shot invocation
into an **existing authorized owner workflow** after its producer finishes; that
workflow must handle the exit code and deliver sanitized registry changes through
its existing writer/integrator. This code is **not auto-scheduled** and never
pushes Git. Existing producers may continue using `cli.mjs record-run` directly.

Use a private inbox owned by the executing UID with directory mode `0700`.
Keep it and receipts **outside the checkout**. Pass explicitly approved canonical,
symlink-free paths, including ancestors (`/private/tmp`, not macOS `/tmp`).
`--receipts-root` is mandatory authority to read that private tree, never inferred
from the envelope, environment or evidence URL. `--root` is also explicit: for
normal use select this repository's `ops/experiments`. It must already exist.

An envelope has exactly these fields (the run is the complete registry contract;
replace the illustrative digests, source and timestamp with actual values):

```json
{
  "schemaVersion": 1,
  "run": {
    "schemaVersion": 1,
    "runId": "apple.check-20261114-001",
    "projectId": "apple",
    "taskId": "apple.typecheck",
    "kind": "apple-check",
    "capturedAt": "2026-11-14T12:00:00Z",
    "status": "succeeded",
    "source": {
      "repository": "SalesSquad/junction-pets",
      "commit": "6e0bfe058f9e8ba1779b641ffdaeb39a9366a332"
    },
    "evidence": {
      "level": "local-receipt-unverified",
      "ref": "ops/experiments/README.md",
      "receiptSha256": "<actual SHA-256 of receipt bytes>"
    },
    "dataset": null,
    "evaluation": null,
    "artifact": null,
    "metrics": [],
    "limitations": ["Local receipt; no provider or device attestation"],
    "policySha256": null
  },
  "receipt": {
    "path": "apple.check-20261114-001.json",
    "sha256": "<same actual SHA-256>",
    "runId": "apple.check-20261114-001"
  }
}
```

The private receipt must be a UTF-8 JSON object with matching top-level `runId`,
for example `{"runId":"apple.check-20261114-001","exitCode":0}`.
It can contain a signed statement, but **no signature/provider verification is
performed**: the entire original receipt's byte hash must match both declarations.
A changed signed statement therefore fails; this is integrity, not authenticity.
Do not put private local paths, raw data or secrets into the run's free-text
fields or evidence reference: only the `run` object is persisted, unchanged.
Schema validation cannot detect secrets hidden in otherwise legal strings.

Producer hook pattern: construct a complete sanitized `run` from the actual job
result, hash the finalized receipt bytes, then publish `{schemaVersion:1, run,
receipt:{path,sha256,runId}}` privately. Use mode `0600`, a unique stable filename,
and atomic same-directory publication (e.g. create an exclusive non-`.json`
temporary file, close it, hard-link to a new `.json` name, then remove the temp).
Do not overwrite an existing envelope or alter a receipt after publication.
Never embed raw receipts/models/video/images into the envelope or copy them into
Git. No emitter helper is needed to keep existing producer formats usable.

```sh
node services/experiment-registry/inbox.mjs \
  --inbox /approved/canonical/private/inbox \
  --receipts-root /approved/canonical/private/receipts \
  --root /canonical/checkout/ops/experiments --limit 100 --dry-run
# Same invocation without --dry-run persists only sanitized run metadata.
node --test services/experiment-registry/inbox.test.mjs
```

Defaults: at most 100 `.json` envelopes per invocation (configurable 1–1000),
lexical filename order; refuse the whole batch when more envelopes than --limit are present (prevents silent starvation), at most 10,000 total directory entries (larger inboxes
fail closed), 256 KiB per envelope/registry prerequisite and 4 MiB per receipt.
Original envelopes are **always retained**, even on failure. Replays are
idempotent; existing conflicting run IDs fail. An owner workflow can archive
already handled envelopes outside the active inbox to advance subsequent bounded
batches; this importer never moves or deletes them. Files without `.json` are
ignored. Directory enumeration is bounded and refuses excess rather than
silently selecting an arbitrary subset.

Output contains aggregate `created/existing/failed/validated` counts and indexed
item results in scan order, without private filenames, paths, input strings or
exception details. Dry runs check schema, hashes, prerequisites and existing
conflicts without creating directories or records. Exit **1** means any failure
or missing authority; exit **2** means a valid model run is `not-compared` (even
if recorded or dry-run validated); exit **0** means non-model evidence ingestion
only. No comparison is inferred or run here. Use the existing explicit compare
CLI with baseline and preregistered policy separately. A missing/mismatched/future
policy prevents `recordRun()` entirely. No ingestion result grants model,
provider, release or effects approval.

Security limits: JSON uses native `JSON.parse`: duplicate keys have last-key-wins
semantics, including escaped key spellings; there is no duplicate-key detection.
Producers must emit ordinary `JSON.stringify` objects without duplicate keys.
Both envelope and receipt are byte-bounded before parsing; malformed UTF-8/JSON
fails. Files must be regular, never symlinks, with every ancestor checked by
`lstat`; opens use `O_NOFOLLOW`, and inode/device/mode/size/mtime/ctime are checked
before and after reading and again before persistence. These checks detect
observed changes, but portable Node path APIs do not supply an `openat` directory
capability: **they cannot defeat a hostile same-UID writer swapping and restoring
ancestor directories between checks**. Use an owner-controlled, quiescent private
receipt tree and a single registry writer; this is not a sandbox against a
malicious local owner. Hashes bind supplied bytes, not execution truth or trusted
wall-clock time. Private receipt content is parsed only for identity and never
written or printed by the importer.


### Automatic owner-side reconciliation (no additional GPU work)

A scheduled macOS one-shot importer reconciles trusted local experiment
envelopes without creating a second development agent or GPU process.
The local owner-only state lives under
~/Library/Application Support/JunctionExperimentRegistry, with three folders:
source (a clean dedicated GitHub main clone), inbox, and receipts.

Launch the one-shot runner using this documented command in your existing
authorized automation or a macOS LaunchAgent:

    python3 "$HOME/Library/Application Support/JunctionExperimentRegistry/source/services/experiment-registry/auto_sync.py"       --owner-root "$HOME/Library/Application Support/JunctionExperimentRegistry"       --verda-db "$HOME/Library/Application Support/JunctionVerda/jobs.sqlite3"

The runner locks one writer, verifies GitHub main, reads the existing Verda
coordinator SQLite database read-only, ingests SHA-verified receipts, commits
only new sanitized immutable metadata and opens a task-owned PR. The
existing portfolio PR integrator owns merge; no direct main push.
Private receipts and failed envelopes are retained, so missed/offline
runs can catch up after the owner Mac resumes. If a PR is still open,
the runner stops rather than creating a duplicate.

The first automatic producer is verda_collect.py: it emits one bounded
lease-state record for a new coordinator job or transition, with all records
classified non-promotable. Stopped VM state is NOT proof of executed GPU
training. Previous November 13 jobs are already in the history and are not
replayed as new. Manual verda vm actions outside that coordinator and SAVI,
Reality Twin, Meta, Apple/Xcode Cloud provider jobs require their producer
to emit a redacted run+receipt envelope using the inbox contract above,
or an explicitly integrated adapter; provider subscriptions are NOT implied.
No GPU starts, provider credentials, independent model acceptance, or
release are performed by this source-only tool.

Further useful checks: stale pending PRs, invalid envelopes, missing
provider receipts, measured costs versus quality improvement, and
failure -> quarantined-case -> next-training-plan feedback. Comparison
across differing loss definitions remains prohibited without rescoring
on the same frozen cohort.
