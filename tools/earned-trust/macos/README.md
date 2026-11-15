# Earned Trust for macOS

An offline, English-first native review desk for the Tieto Junction challenge.
The app maps requirements to claims, frozen before/after checks and pinned
source versions. It groups generated snapshots, explains unsupported claims and
exports a named person's local review declaration. It does not call a model,
execute imported code, authenticate a runner/person, push code or merge changes.

## Run on a Mac

Requires macOS 14 or later and an installed Swift 5.9+ toolchain. No third-party
Swift packages, account, API key or Xcode project is needed.

```sh
./script/build_and_run.sh
```

The Codex Run action uses this same script. It builds with SwiftPM, stages a
local `dist/EarnedTrust.app` including the resource bundle, and opens the app as
a foreground macOS application. It does not install into `/Applications` or
sign with a developer identity. Local development packaging is not notarized
distribution. `--verify` additionally checks process existence; this is not a
visual UI check. `--build-only` stages without launch. `--debug`, `--logs` and
`--telemetry` provide bounded development entrypoints.

## Review workflow

1. Select a supplied change. The badge states **Ready for human**, **Needs
   evidence**, or **Inspection only**.
2. Read the requirement, claim reasons and before/after check outcomes. Logs are
   read from the packet directory and compared with declared SHA-256 digests.
3. Open **Change map** to distinguish authored sources/tests from generated
   snapshots. This grouping is an inspection aid, not a risk score.
4. Inspect source SHAs and toolchain in the provenance pane. Links are limited
   to HTTPS GitHub URLs, and only open when selected.
5. **Record Review** asks for a declared name, decision and rationale. It rechecks
   the packet and logs, then exports a JSON record bound to the packet hash.
   Acceptance is unavailable while behavioral claims lack evidence. Nothing is
   sent remotely; the declaration is not an authenticated code approval.

Import (`⌘O`) accepts the v1 JSON packet contract in `../contract/PACKET.md`.
Keep referenced evidence files alongside the packet. Packets are limited to
5 MiB, individual logs to 2 MiB and total referenced logs to 32 MiB. Absolute,
traversal and symlink evidence paths are rejected. Reload (`⌘R`) invalidates a
recorded local decision if packet bytes or evidence integrity change. Decisions
are window-session state until explicitly exported; no hidden account store is
created. Import and export do not execute anything.

## Focused verification

```sh
swift test --filter TrustCoreTests
swift run trust-inspect /absolute/path/to/packet.json
```

The core tests exercise changed evidence, stale source versions, contradictory
checks, pass→pass invariants versus fix claims, missing evidence, unknown fields
and unsafe file paths. The CLI uses exactly the loader and evaluator used by
the app. JSON output includes the packet hash, verdict, generated snapshot
count, verified log pair count and claim reasons.

**Integrity is not authenticity:** matching local log digests establishes byte
integrity. It does not establish that a log describes a real run, identify its
executor or prove its claims. Source SHAs and declared harness hashes are shown
transparently; the reviewer must validate the provenance of the source packet.
No numerical confidence score is manufactured.

## Structure

- `TrustCore`: strict packet types, bounded file loading, integrity evaluation,
  local decision/export contract.
- `EarnedTrust`: native window, sidebar/detail/inspector, evidence views,
  import/export and review state.
- `TrustInspect`: small CLI using the same core.
- `Resources/Packets`: root-produced, source-bound example packets and evidence;
  synthetic outcomes must be explicitly labeled and cannot prove a fix.

This app is a reference implementation created for the challenge. It is not a
Tieto-endorsed product or an autonomous merge service.
