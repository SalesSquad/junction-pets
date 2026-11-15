# V13 original MuJoCo research harness


The main branch contains the qualifier, burst retainer, tests, public survey
fixture, V7 trace validator and a manual-only, source-pinned workflow route.
The route remains disabled until the existing credit window and the separate
source-review variable are both open; neither variable proves the actual
account balance or physical safety. The work record below describes the
original research branch, not a current dispatch or qualification. No model
promotion is authorized.
WorkID: `J26-CRACI-V13-SUSTAINED-RIGHT-HARNESS-20261115`.
Harness parent: `72653f5f6ac1ec46fa63128da11957ebe0c5cff9`.
Local task branch: `codex/craci-v13-novel-train-20261115`.
No dispatch, expenditure, PR, push, model promotion, product-source edits,
workflow/planner edits, or new-world outcome simulations were performed.

## Current compatibility STOP

Product source arrived during implementation, clean at
`faec266d6d3a44af3a564f46e0778209c1dc3af1`, descended from supplied parent
`c77158f9ae80acc2b1eafaf9284c4397426799b2`.
Its `v13-plan.json` SHA-256 is
`93013025c9e19d94911f249f4dbf0cc034c767da23dca0273d8808323c0b173c`.
The named factory/protocol signatures and cohort object ABI match.
The protocol accepts only nine compact trial fields; the harness explicitly
projects raw rows into that ABI without changing or discarding original rows.

**Frozen goal-threshold contract reconciled:** the V13 product plan, source
protocol and ORIGINAL V7 MuJoCo physics all accept **>=250 real contact dwell
ticks**, positive contacts and strict final error <0.02 m. The harness checks
the plan value is exactly 250 and rejects 249 and 251. The previous harness
requirement of >250 was a new incorrect constraint, not the original V7 goal;
its correction preserves the actual frozen physics criterion. This source-only
reconciliation does NOT qualify any V13 physical result. No product source was
copied or modified by this harness branch.

## Owned new files

- `scripts/craci/rokoko-mujoco-v13-original-qualification.py`
- `scripts/craci/rokoko-mujoco-v13-original-retain-evidence.py`
- `scripts/craci/test_rokoko_mujoco_v13_harness.py`
- This README.

The V13 retention validator does not invoke the V12 144-row packer.
It imports only the new harness for V13 seed/order/trace validation.
The replay reuses the unchanged V7 transition/sparse-row validator, never its
old dataset-level counts. Historical V10 and original V8 source are loaded from
the separately pinned product checkout.

## Execution interface

Manual-only Python CLI: `--stage full|original|qualify`, default `full`.
No dispatch function or retry loop exists. There is no raw shell command
parameter and subprocesses use fixed argument arrays with no shell.
`full` records originals, then starts a separate Python interpreter for
`qualify`, which reloads source/factories and checks files independently.
`original` alone is explicitly unqualified; it is not a completed event.

Required caller variables (configuration only; no secret-store access):

| Variable | Contract |
| --- | --- |
| `CRACI_SOURCE_ROOT`, `CRACI_SOURCE_SHA` | Separate product checkout, clean exact full HEAD; V10 and known product-parent ancestry required |
| `CRACI_HARNESS_ROOT`, `CRACI_HARNESS_SHA` | Clean full harness HEAD containing the actually invoked script; branch names need not match product |
| `CRACI_RECEIPT_DIR` | Existing private receipt root; collector subdirectory must be new |
| `RUNNER_TEMP` | Existing private temporary root with `mujoco-venv/bin/python` |
| `CRACI_WORKLOAD` | Exactly `rokoko-mujoco-v13-pilot` |
| `CRACI_CREDIT_WINDOW_OPEN` | Exactly `true` |
| `CRACI_CREDIT_REMAINING_SECONDS` | At least 7200 for originals/full, 3600 for qualification |
| `CRACI_MANUAL_SOURCE_REVIEWED` | Exactly `true`, supplied by coordinator only after review |
| `CRACI_V13_PLAN_PATH` | Exact plan path within the V13 product directory |
| `CRACI_V13_PLAN_SHA256` | Explicit SHA, equal to reviewed harness plan pin; never inferred from bytes |
| `CRACI_V13_PREFLIGHT_PATH` | Exact supplied preflight file, SHA below |

The actual running interpreter and named venv must use NumPy 2.3.4 and MuJoCo
3.3.7; merely checking another interpreter is insufficient. Admission requires
at least 120 minutes before `2026-11-15T17:00:00Z` for originals/full, and
60 minutes for qualification. The workflow enforces a 60-minute job timeout.
No credentials or personal
records are read. Source receipts do not attest a provider bill. The coordinator
owns aggregate credit accounting and duplicate source/cohort/seed admission
across hosts; this standalone harness does not create a distributed ledger.
The main workflow and planner pin this study's exact product source and leave
the manual source-review flag unset by default. No run follows automatically.

Frozen inputs:

- V12 model SHA-256:
  `82cfa42ba2240aff6d00ec3e2b15c06d78386d3c0682986a23e478977f2dbf9e`.
- Original V12 plan SHA-256:
  `8074f8f8978e2e55bdf201eeb9713888e44befe1d93856da44c1830bb86cfc48`.
- Original V12 policy SHA-256:
  `bd748f604dafbc6e0d3d59e0a5b7e08dab5e9e8ed010a13053f1417a32fd6fc6`.
- Public preflight SHA-256:
  `099d8cc69d0d11bca1e21d0fe2b4c7c397b3f094a352d80ea3fcc52a2fddad29`.

The harness verifies all 512 public resets for seeds 519024..519535,
178 near/334 clear, distinct world hashes, original finite 18D/7-mask ABI,
and the known preflight's selected world hashes. It independently derives the
first 40 near and first 8 clear worlds, merged in ascending seed order.
It refuses the executed/reserved V12 ranges and invalid 520000 range.
The exact world-major arms are `frozen_v5`,
`v12_phase_dwell_supported_actions`, `train_only_right4_burst2`,
`train_only_right4_burst4`; at most 192 originals, V5 first on every world.
Factories use `right_burst_factory(frozen_v5_factory, model_path,
burst_length=2|4)` and original V12 supported-action factory. No unsupported
learned action4 weights, DEV/CAL/TEST/OOD, deployment, or promotion is allowed.

## Evidence and STOP semantics

Each returned original row and complete raw trace is recorded before STOP or
validation decisions. Any unsafe row/positive transition cost or any nonbaseline
loss of a true safe V5 contact goal stops immediately, even when another arm
wins. Goal credit requires terminal dwell >=250, positive actual contacts,
final error <0.02, success, no unsafe and no abstention. Completed traces from
the final 192nd episode survive STOP and readout failures.

Full qualification checks source identity, all raw file SHA-256s, exact cohort,
ordered pairs, sparse/full consistency, full trace digests and protocol readback.
The separate interpreter replays all 512 starts and every option of all 192
original episodes, checking original seven masks, factory actions, states,
rewards, costs, done flags, contacts, current/max dwell, terminal errors and
physical step counts. Matching digests or producer success flags alone cannot
qualify the execution. Replay failures archive originals as
`UNQUALIFIED_FAILURE`; early STOP archives are `INCOMPLETE_STOP`, even with
192 completed rows. Only a complete replay can yield `COMPLETE_TRAIN_ONLY`;
science STOP/zero-novel outcomes remain explicit and never authorize promotion.

Archives use lossless 6 MiB raw chunks in ZIP parts, each <20 MiB and the whole
collector <63 MiB including proofs/manifest, at most 64 parts. Reassembly checks
exact compressed JSONL/gz bytes and raw JSON bytes against SHA-256s. Regular
files require one link; symlink roots/ancestors, file aliases, ZIP symlink
entries, traversal names and collector/private overlap are rejected. Private
originals are retained; the collector receives only bounded archives/proofs.
Resource-bound or OS-level I/O failures can still prevent publication; originals
are never deleted and such a run must not be called retained/qualified.

## Verification performed

Synthetic-only command, in the explicitly supplied isolated venv:

```sh
/private/tmp/rokoko-v12-safety-venv-20261115/bin/python -B -m unittest discover -s scripts/craci -p 'test_rokoko_mujoco_v13_*.py' -q
```

Result: **32 tests passed**, NumPy 2.3.4 / MuJoCo 3.3.7 installed.
The tests use fake environments; there is no new-world outcome simulation.
Coverage includes known preflight bytes, wrong seeds/cohort order, masks,
strict contact predicate/boolean spoof, each nonbaseline loss, first unsafe,
192nd STOP retention, 192nd readout failure retention, complete synthetic replay,
physics/policy drift despite bound digests, raw/ZIP tamper, rehashed ZIP symlink,
source symlink/hardlink, collector alias, old cohort refusal, no promotion,
qualification-failure archival, caller cutoff, compact ABI and strict plan STOP.
The known-preflight test requires the supplied local survey file at its original
`/private/tmp/rokoko-v13-new-world-survey-20261115.json` path; it does not rebuild
or resurvey worlds.

The verify-change skill's optional `codex-verify-plan` helper was absent at its
installed path. The targeted synthetic suite and final diff review were used.
No real MuJoCo trajectory replay, paid execution, independent external review,
provider qualification, or device qualification was performed. Next action:
integrator resolves threshold/pins with the product owner, independently reviews
both exact source heads, then separately owns any workflow wiring/admission.

SHA-256 of implementation files at this source-only handoff:

- Qualification: `d552d0b89bc2377b2b86917da649c787b76b9d699915c3bdac5ae9ddcc38438c`.
- Retention: `daf8803297c1a8fabff15fc46ae68da3536c3cf93f0b8cfa7a234b263a9e0b4d`.
- Tests: `73b87b02dfa3f6c43ff879eaa82bae20187cc43b16c73c7a8fbbfad80ca2f243`.

## Local Git preservation boundary

The requested worktree's Git index is stored outside the writable sandbox at
`/private/tmp/craci-meta2x-20261114/.git/worktrees/craci-v13-runner-20261115`.
`git add` failed with `Operation not permitted` creating `index.lock`.
No protected metadata was modified, and no push/rescue-to-GitHub is authorized.
The four new files remain in the requested worktree; its original HEAD remains
the supplied parent, so it must not be described as clean or committed there.
A separate task-owned Git metadata directory under writable `/private/tmp`
preserves precisely these four files on the named task branch, with the exact
supplied parent. A prerequisite-bound commit bundle is saved at
`/private/tmp/craci-v13-harness-20261115.bundle`; the integrator can import that
local bundle into an authorized checkout. This is preservation, not a claim that
the original worktree's protected branch/index was updated.
