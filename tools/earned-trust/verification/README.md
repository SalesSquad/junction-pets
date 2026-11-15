# Frozen #2283 behavioral verification

This directory contains a real, reproducible comparison of the official Tieto
MessagePack sample base and its supplied #2283 AI patch. The same probe and the
same two input files ran on both revisions. No MessagePack implementation or
upstream test was edited for the comparison.

## Observed result

The completed run is in [`evidence/run-003/differential.json`](evidence/run-003/differential.json).

| Observation | Base `32258fdbee4bcd653c79f51b4376b5103c6f4d27` | Patch `9df83c38409c8bfad0517aebffe48211eda4a5b4` |
|---|---|---|
| Probe build | Succeeded, zero warnings/errors | Succeeded, zero warnings/errors |
| External library fixture compilation | Succeeded | Succeeded |
| Analyzer | `AD0001`, `IndexOutOfRangeException` | No diagnostics |
| Generator | `CS8785`, `IndexOutOfRangeException` | No diagnostics |
| Consumer resolver `App.AppResolver.g.cs` | **Absent** | **Present** |
| Generated application compiler errors | Zero | Zero |
| Same behavioral check | **Fail** | **Pass** |

The base failure is the actual issue: an ordinary compilation can have zero
errors while the generator fails and the application has no resolver. The probe
checks the resolver explicitly rather than treating a successful build as proof.

- Frozen bundle SHA256: `96961b0d0267a9988aef04e278bcf2eba715c18a5667224f752e199619304327`
- Frozen input SHA256: `723dc3d529194a22083046dc6ce7f267892e48ab08df09eca825a204a9a22bf6`
- Completed receipt SHA256: `cb9164598c280eafdbc677c8ad68030a1579b6a0d489add6faab5d06f1052e8e`

The receipt records the hash of every probe file, its project file, SDK overlay
and runner. It records each source commit, source tree, archive, original SDK
configuration, build/execution command, raw log and raw observation. Both
revisions have exactly the same frozen bundle hash. Raw observations retain
diagnostic messages, generated source text and hashes of loaded runtime
assemblies. All referenced log/observation hashes and current frozen source
bytes were checked after the run completed.

## What was executed

`fixtures/Library.cs` contains the external generic `record struct` from the
[original issue](https://github.com/MessagePack-CSharp/MessagePack-CSharp/issues/2283).
`fixtures/Application.cs` consumes `Item<int>` and requests a generated resolver.
The library is emitted to an in-memory assembly and supplied as a metadata
reference, so its symbols genuinely have no source syntax in the application
compilation.

`Program.cs` executes the actual `MsgPack00xMessagePackAnalyzer` and
`MessagePackGenerator` from each pinned source revision. It checks six things:
library compilation, no analyzer crash, no generator crash, no blocking
diagnostics, generated code compilation, and presence of the consumer resolver.
Every check must pass for a successful observation. The runner only classifies
a failure as a reproduced defect when the actual issue-specific crash or
missing resolver has been measured.

The build and behavioral phases are separate. Restore/build/environment errors,
timeouts, missing observations and unrelated unexpected outcomes are
**inconclusive**, not successful bug reproductions. There are no skipped
behavioral assertions. No human acceptance is manufactured: `humanDecision`
is `null`.

## Reproduce in Linux x64

Requirements: Python 3.12+, Git, and access to the public official repository,
Microsoft .NET downloads, and the upstream NuGet sources. The installer creates
an isolated toolchain; it does not change the system SDK.

```bash
python3 tools/earned-trust/verification/bootstrap.py \
  --directory /tmp/tieto-earned-trust-toolchain

git clone --bare \
  https://github.com/te-industry-tech-office/junction26-messagepack-csharp.git \
  /tmp/tieto-earned-trust-source.git

python3 tools/earned-trust/verification/run.py \
  --repo /tmp/tieto-earned-trust-source.git \
  --dotnet /tmp/tieto-earned-trust-toolchain/dotnet/dotnet \
  --toolchain /tmp/tieto-earned-trust-toolchain/toolchain.json \
  --output /tmp/tieto-earned-trust-run
```

Choose new output/toolchain directories for a new run. Existing runs are never
overwritten. A complete public repository history is required by the upstream
Nerdbank.GitVersioning build task. Local source copies are detached at the exact
base/head commits. The runner does not push, merge, or alter the caller's source
checkout. Exit code `0` means the recorded comparison demonstrated fail→pass;
exit code `2` means no such demonstration was established.

## Environment and limits

The actual recorded execution used **.NET SDK 9.0.100**, **.NET runtime 8.0.11**,
and **net8.0** on Linux x64. The downloaded SDK/runtime archives were verified
with SHA512 hashes from Microsoft's official release metadata. `bootstrap.py`
provides the equivalent pinned installation procedure and has been syntax
checked; the archives were installed with the same download/hash/extraction
steps during this session.

This is explicitly a compiler compatibility experiment. The original source's
`global.json` pins SDK 8.0.402; it was retained untouched in the source checkouts,
and the separate probe's SDK overlay selects 9.0.100. The original SDK 8 build
was not run here. This is not qualification of the report's Windows/.NET 10
environment, a NativeAOT application, a serialization round trip, the other
three challenge patches, or the complete upstream test suite.

SHA256 checks provide **local file-integrity evidence**. They do not authenticate
the runner or make the receipt tamper-proof against an actor who can replace the
receipt and its manifest. There is no runner signature, attestation service,
human approval, deployment, model-training claim, or competition submission.

## Retained setup failures

`evidence/prior-attempts/` retains the original minimal logs and partial receipts
from two setup attempts. They are not counted as behavioral tests:

1. `run-001`: parallel MSBuild restore stopped before execution. A separate
   single-node diagnosis also exposed GitVersioning's dependence on real Git
   metadata when building source archives.
2. `run-002`: a shallow public checkout lacked Git history needed by upstream
   versioning; preparation of the second revision also failed. The partial
   receipt remains inconclusive.

`run-003` used complete public source history and a single MSBuild node. It
executed the frozen behavioral probe once per revision and produced the genuine
fail→pass result above. Fixing these build prerequisites changed no upstream
implementation and relaxed no behavioral assertion.
