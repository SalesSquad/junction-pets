# Chibi Lens — Apple source port (iOS + macOS)

**Product promise:** _Memory for the physical world. With evidence, not guesses._

Next product direction: [Chibi Resume — the world paused, your intention didn't](PRODUCT_VISION.md),
with a 60-second challenge demo, staged cross-surface scope and explicit
requirements for a trustworthy own video model.

An Apple-native replay surface for the Junction Meta challenge. This first
increment ports the `services/meta-spatial/` request shape to Swift, provides
a real shared SwiftUI interface, and preserves the difference between **last
observed**, **candidate match**, and **host-verified identity**.

The scenario is one useful everyday question: **“Did I pack the right USB-C
charger?”** A historical sighting says where the charger was last seen; a fresh
frame contains two visual lookalikes; the system **declines to verify** until an
authenticated host confirms a unique ID. Revoking capture leaves a text-based
fallback. This is an honest synthetic replay, not a recording from Meta glasses.

## Run from the package directory

```sh
swift test
swift run chibi-lens-replay
./scripts/verify_contract_parity.sh
./script/build_and_run.sh
```

The last command builds and launches a real macOS SwiftUI `.app` bundle through
the project's Codex Run action. The executable emits a deterministic JSON
receipt with `receiptKind:SYNTHETIC`, `identityVerified:false` and
`actionAuthorized:false`. No external service, ML model, camera, login or SDK
credentials are used. The `.build` and `dist` outputs are ignored.
The `--verify` launcher mode checks for a newly started process from this
specific bundle; it does not prove that the UI rendered, is accessible, or
passed a device qualification test.
The parity script validates all three **real Swift-encoded** request modes
through the existing JavaScript `validateRequest`, including five adversarial
mutations; it is an integration acceptance check, not a host authorization.

For the **iOS source port**, create an iOS App target in Xcode, add this folder as
a local Swift package dependency, link `ChibiLensUI`, and use
[`Examples/iOS/ChibiLensDemoApp.swift`](Examples/iOS/ChibiLensDemoApp.swift)
as its app entrypoint. It displays the same synthetic replay on iPhone. This
package is **not** yet a signed iOS app or a tested simulator build.

## Trust boundary (required for real DAT capture)

| Responsibility | Owner | This increment |
| --- | --- | --- |
| DAT pairing, permission, camera and audio | Native iOS adapter | Pending; do not claim connected hardware |
| Local preview and candidate proposal | `ChibiLensCore` and `ChibiLensUI` | Source-only fixture and guarded draft |
| Identity, source receipt, tenant, consent and durability | Private Chibi Rust/Cedar host | Never created on this client |
| Inspect/find/verify execution | Existing `services/meta-spatial/` | `LensScanRequest` mirrors JSON input shape |
| Unique-tag verification | Host's `verifyIdentity` | **Never** inferred from score |
| Metric position / AR registration | Independent calibration and host | Unregistered; no phone→glasses pose shortcut |

`LensFrameDraft` is always `client-unverified`, even when its `source` field says
`meta-camera`. The host must resolve an immutable observation reference and
revalidate device session, consent, source revision, capture provenance and
receipt integrity. `LensScanRequest.inspect` and `.verify` take a **host-issued
observation digest**; a JPEG hash or model score is not a replacement.

`CaptureGate` denies preview unless scoped consent, OS permission, bystander
clearance and a current positive session generation are all present. After
revocation or session rollover, the adapter must discard in-flight frames and
return a manual path. Real capture must never be activated by the replay UI.
This gate is a **caller-supplied preflight snapshot**, not a durable consent
manager or an in-flight cancellation mechanism. `LensScanRequest.validated()`
checks request shapes for parity with the JS schema, but only the host can
enforce authority, expiry, idempotency and revocation at execution time.

## Meta SDK integration checklist

Meta's official iOS getting-started guide describes `MWDATCore` and
`MWDATCamera` Swift package products, app callback scheme, `MWDAT` Info.plist
dictionary, transport permissions, Developer Mode and MockDeviceKit. Implement
these in the **production iOS app target**, not in a fake privileged host here:

1. Set up an app in Meta Wearables Developer Center and add the official DAT
   Swift package; configure callback URL, `MetaAppID`, `ClientToken`, and Team ID
   through the Xcode build system's protected settings.
2. Implement a DAT frame adapter that drops late frames on capture stop,
   revocation or session-generation change; never record a bystander without
   clear consent. Preserve frame timestamps and source-device identifiers.
3. Run MockDeviceKit pairing, stream and revoke cases on a supported iOS device.
   Mock device tests do **not** qualify physical glasses or Display hardware.
4. Submit frames to the authenticated Chibi observation-admission interface;
   call `meta.scan.inspect`/`meta.memory.find`/`meta.object.verify` with host-issued
   references and source revisions, not client-declared identity.
5. Add optional routed audio guidance and the separate Display web UI only once
   permissions, cancellation and speech fallbacks have been device-qualified.

Primary resources:

- https://github.com/meta/meta-wearables-dat-ios
- https://github.com/meta/meta-wearables-dat-ios/blob/main/plugins/mwdat-ios/skills/getting-started/SKILL.md
- https://wearables.developer.meta.com/docs/develop/dat/camera-stream-processing
- https://github.com/meta/meta-wearables-webapp
- https://github.com/SalesSquad/junction-pets/blob/main/docs/META_SPATIAL_ARCHITECTURE.md

No real DAT SDK is linked into this package, and no hardware or App Store
release is claimed. Follow the official sample's exact Info.plist and callback
rules at integration time; don't put real client tokens in source control.

## Own model — training plan and go/no-go

`services/meta-spatial/ml/` is independently developed in
[draft PR #70](https://github.com/SalesSquad/junction-pets/pull/70). Its CPU-only
first model trains on synthetic numeric examples; it does **not** learn vision
from actual camera pixels. On a shifted holdout the measured false-candidate
rate is **13.71%** — sufficient evidence to reject deployment for verification.

| Stage | Data / compute | Output / gate |
| --- | --- | --- |
| 0. Baseline | Synthetic consent-safe trajectories; CPU | Reproducible ranking, explicit abstention, shifted holdouts; delivered separately |
| 1. Real perception | Licensed or newly consented first-person imagery, faces redacted; authorized GPU | Lightweight visual encoder adapted to chargers/keys, with lookalike hard negatives |
| 2. Temporal memory | Multiple sightings, moves, absence events and time drift; authorized GPU | Time-aware candidate ranking with append-only evidence, not fabricated location |
| 3. On-device Apple | Quantized/exportable Core ML candidate model + Swift Vision/OCR | Benchmark iOS latency, memory, battery, privacy and offline fallback |
| 4. Trust gates | Host-issued unique identity evidence + tests | No model-only `identityVerified`; deny/revoke/bystander checks remain mandatory |

For stages 1–2, orchestrate **bounded, checkpointed experiments** via the
existing Verda CLI only after the available-credit policy, projected burn and
GPU job authorization are verified. Separate GPU budgets, task IDs, code SHAs,
dataset consent/licenses, seeds, hyperparameters and evaluation artifacts for
every run. Existing `8× RTX PRO 6000` allocation is **not presumed free**.

Measure false candidate confirmations on identical-looking objects, abstention
quality, real changed-location accuracy, temporal source fidelity,
capture-to-answer P95, completion time compared with phone-only flow, battery,
denial/revocation latency, and real- versus synthetic-device provenance.

## Qualification status

- Portable Swift source, SwiftUI UI, deterministic Mac replay and unit-test
  source are present in this increment.
- **Not yet qualified:** Swift compilation on Apple SDK, native/macOS run,
  iOS simulator, Meta DAT pairing, physical glasses, real GPU image training,
  host-signed identity, production memory or calibrated location.
- No existing Taimi/Lens proprietary code, private Chibi secrets or real media
  is copied here. This package is source-port-only until tested on the chosen
  Mac/iPhone host.
