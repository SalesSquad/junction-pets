# V12 manual pilot qualifier — authored source only

Work ID: `J26-CRACI-V12-PILOT-20261115`. Harness parent:
`3ddc0fcf8b13df0e2dc750c02d84fdb9f2fb76ad`; independent product source:
`64c9a32bf983c26099ece11f1c3a0f6da5bc4f1d` (PR226). Its original V11 ancestor
is `ab6df4054ef6ed350b479469590a48046a0c0a68`; immediate product parent is
`01439227998f27c87ee3fddb7f4c540c8893eb54`. Neither product nor historical
evidence is changed by this harness.

## STOP: dependency capability and independent review still required

No CRACI dispatch, push, PR, merge, model promotion or release was performed.
The authoring Mac's checked Python installations have neither MuJoCo nor
NumPy, so no local physics smoke or full qualification has run. Synthetic
contract passes do not establish physics or runner availability.

The strict `default: deny`, `[github, ubuntu]` network policy deliberately
excludes PyPI. The existing Ubuntu image has **not** been verified to include
`mujoco==3.3.7` and `numpy==2.3.4`. The manual job checks these existing packages
and fails closed; it does not download packages, create a provider, broaden
networking or silently change versions. **Do not dispatch** until the coordinator
establishes an existing authorized exact dependency capability under this
network policy. This is a concrete execution prerequisite, not evidence that
the image already has the packages. There is no dependency fallback interface
in this change.

## Manual admission (coordinator only, not executed here)

Use existing workflow **417767938** (`.github/workflows/craci-pilot.yml`), a
reviewed immutable harness ref containing this implementation, and inputs:

```json
{"workload":"rokoko-mujoco-v12-pilot","source_sha":"64c9a32bf983c26099ece11f1c3a0f6da5bc4f1d"}
```

Before dispatch, inspect actual hosted queued, running and completed runs and
their retained receipts for the tuple `(source=64c9a32bf983c26099ece11f1c3a0f6da5bc4f1d,
seeds=518000..518511, stage=pilot)`. **Do not duplicate this tuple**, including
a prior scientific RED or incomplete attempt. A local selector, branch name,
concurrency group or dry run is not a hosted-run check. The stable concurrency
group serializes active jobs only; it cannot enforce historical deduplication.
GitHub rerun attempts are rejected; the coordinator owns historical admission.
No followup is supported by this workload.

`CRACI_CREDIT_WINDOW_OPEN` must equal `true`; both planner and host enforce
at least 60 minutes before the immutable `2026-11-15T17:00:00Z` cutoff. The
source-bound Python entrypoint recomputes wall time itself. No expired
Immune/Chaos three-hour lane or admission bypass is used. One CPU8 matrix cell,
max parallel one, 30-minute job timeout; original execution plus replays have a
20-minute internal budget, leaving retention time. Actual provider cost stays
unknown in both qualifier and existing collector receipts.

## Physics and audit contract

The harness imports the original V11 uniquely named policy loader, V11's
immutable checkpoint stager, original V10 historical validator and original
V8 real-episode function/physics. It verifies the original V10 runner blob,
V11 ancestry and V5 `policy` / original `physics` module identities. The V12
model and full plan hashes are checked through product `policy.py` and
`protocol.py`, including supported actions `[1,2,3,5]` and unsupported RIGHT4.
The two V12 factories receive only public observations and original masks.
No model fitting or hypothetical unexecuted action labels occur.

All 512 public 18D/seven-mask starts are captured before outcome selection.
Product `derive_cohort(..., 'pilot')` selects first 40 near/8 clear, and the
three frozen arms execute all 144 original paired episodes. A second pass
rederives the cohort/readout from SHA-checked raw bytes, checks trace hashes,
then replays every initial world and every complete episode with fresh
controllers: all original observations, masks, actions, rewards, terminal
flags, dwell/contact counts and trial summaries must reproduce exactly.
This includes all near/clear physical positives and the TRAIN-only RIGHT4
probe. These are replay executions of the same trials, not additional cohorts.
The physical goal remains original contact, distance <20mm, >=250 actual
ticks and zero unsafe. A forward-reopen proxy cannot pass.

Missing/extra/duplicate worlds/trials, mutated support/plan or divergent
replays are execution failures. Any unsafe arm, lost V5 candidate goal or
zero novel nonexploratory safe goal gives **RED**, retains the full evidence,
and returns nonzero. Even a positive pilot means TRAIN-only review, never
promotion. Exploration is never promotable or used to train a RIGHT4 model.

## Retention and reproduction

Original raw streams live privately outside the collector. Before qualification,
`manifest.json` hashes all three original producer files. After reading/replay,
that immutable file becomes `original-manifest.json`; a separate outer
manifest binds every original, frozen plan/model and qualification receipt.
The unmodified V11 binary writer and reassembly verifier are reused with V12
schemas and original-file proof validation; no V11 800-trial proof is forged.
All large JSON/raw files use lossless ZIP binary parts, raw chunk size <=6MiB
minus 2KiB to keep ZIP overhead within 6MiB. Source/part/archive SHA-256s and
exact reassembly are checked before the existing 20MiB/file, 63MiB total
collector. Incomplete output is explicitly RED and packed without claiming
independent physics success. Originals are never reduced or rewritten.
Workflow finalization and 7-day upload run even on scientific RED; forced
provider termination remains an ordinary limit on any finalizer.

Focused author checks (no simulation):

```sh
node --test scripts/craci/plan.test.mjs
CRACI_SOURCE_ROOT=/path/to/clean/exact/V12-checkout python3 -B -m unittest discover \
  -v -s scripts/craci -p 'test_rokoko_mujoco_v12*.py'
```

The raw contract fixtures are explicitly synthetic. Local MuJoCo smoke is
blocked by missing packages; hosted physics, cost and runtime imports remain
unverified until an independently reviewed authorized run is admitted.
