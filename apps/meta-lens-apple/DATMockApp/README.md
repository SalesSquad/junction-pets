# Chibi Resume — Meta DAT video harness

Debug-only iOS app. It links the **official Meta DAT SDK 1.0.1**, pairs simulated
Ray-Ban Meta glasses with MockDeviceKit, receives actual SDK camera frames and
runs Apple's Vision text recognition locally. No physical glasses, production
API key, server or paid inference is required for this mock path.

The UI explicitly labels the test source. It has consent and content-clearance
controls, a generated HEVC clip, import of an owned HEVC MP4 (20 MB maximum),
preview, recognized text, revoke/clear and simulated disconnect. It never
selects real glasses or starts a phone camera. Do not use this harness for real
capture or publish it as the production app.

## Run

Requires Xcode 26.4+, Swift 6.3+, iOS 17.2+. On a Mac with sufficient native
capacity:

```sh
cd apps/meta-lens-apple/DATMockApp
python3 scripts/generate_project.py
open .generated/ChibiDATMock.xcodeproj
```

Choose the ChibiDATMock scheme and an owned iOS simulator. Confirm the two
toggles and tap **Play demo**. The expected OCR includes `CHARGER A` and `65 W`.
This reads actual pixels; it does not prove a charger's identity or wattage.
Import requires HEVC in an MP4 container, as supported by Meta's mock camera;
an incompatible codec may fail to deliver frames and produces a bounded timeout.

To avoid downloading the SDK's full binary history, an existing clean shallow
checkout can be supplied. The generator refuses any HEAD except the pinned
official release commit (it does not accept a substitute SDK):

```sh
git clone --depth 1 --branch 1.0.1 https://github.com/facebook/meta-wearables-dat-ios /YOUR/CACHE/meta-dat-1.0.1
python3 scripts/generate_project.py --sdk-path /YOUR/CACHE/meta-dat-1.0.1
```

For the integration test (replace destination with an **owned** simulator):

```sh
xcodebuild test -project .generated/ChibiDATMock.xcodeproj -scheme ChibiDATMock \
  -destination 'platform=iOS Simulator,id=OWNED_UDID' -jobs 1 \
  -parallel-testing-enabled NO -derivedDataPath .native-proof/DerivedData \
  -resultBundlePath .native-proof/Integration.xcresult CODE_SIGN_IDENTITY="-"
```

The generated project uses local ad-hoc signing only for Simulator. The SDK
resolves its own app's Keychain access group during bootstrap, so do not pass
`CODE_SIGNING_ALLOWED=NO` to simulator builds. No Apple developer account,
team, provisioning profile or distribution certificate is needed for this
path; device signing remains disabled in the generator.
[Upstream bootstrap diagnosis and fix](https://github.com/meta/meta-wearables-dat-ios/issues/197#issuecomment-4549647052).

The real-SDK acceptance test requires frame delivery and OCR, then revocation,
no late frames, explicit restart, disconnect and cleared preview. It does not
silently swap in a fake SDK when a host or SDK cannot run it. The app-local
generation fence also has focused tests in `ChibiLensCoreTests`.

## Observed verification — 14 November 2026

**The official SDK mock-video acceptance passes at `57959db`: one actual XCTest
case, zero failures, 6.731 seconds.** The app/test build passes on Xcode 27.2
with pinned Meta DAT 1.0.1 and an owned iOS 27.2 simulator.

The unchanged acceptance conditions require actual SDK video frames, local
Vision recognition of `CHARGER`, a timestamp and frame digest, then revoke and
clear, no late admitted frames, explicit restart, SDK camera permission loss,
another restart and simulated disconnect. All of these conditions completed.
The source is an owned generated video delivered through MockDeviceKit; real
glasses, a phone camera and production capture remain unqualified.

The passing adapter uses the official sample's `AutoDeviceSelector` path,
with a Sendable filter that captures only the immutable owned mock identifier.
Existing exact-ID stream/snapshot checks, epoch fencing, cancellation, the
20-second watchdog and all test conditions remain in place. It does not wait
for or invent a `.compatible` state.

Three earlier continuation cases failed before streaming at `session.start()`
with `No eligible device available` and zero frames. The diagnostic case showed
connected/registered state and exact selector/session IDs while compatibility,
don and hinge metadata were undefined/unknown. Those failed runs remain
preserved alongside this pass. The comparison does not establish a particular
internal SDK defect.

[The verification record](VERIFICATION.json) binds every run to its source,
commands, file/product hashes, raw XCTest log and independent review. All four
continuation cases used the same acceptance predicates and deadlines; only
bounded failure diagnostics changed. All four owned simulators were shut down
and removed. Original local diagnostic commit `1b6f442` remains preserved.

## Lifecycle and trust

- Startup subscribes to SDK discovery before reading its current snapshot,
  waits only for the owned mock identifier and exact active-device selection,
  then rechecks generation, cancellation and current device presence before
  creating the exact-device session.
- User revocation/backgrounding invalidates the app generation synchronously,
  clears preview/text, cancels pending analysis and stops the camera/session.
- Camera permission is checked after awaits, before analysis and before result
  publication; a 300 ms watch also notices SDK permission loss. External revoke
  detection is not claimed to be instantaneous. A closed/paused session requires
  explicit restart. Cleanup must finish before starting another mock session.
- One analysis runs at a time, at most two admitted frames per second; no
  unbounded model-task queue. Vision work checks cancellation before/after OCR.
- Imported media is copied into a task-owned temporary file and removed on
  stop. Frames/results remain in memory, with no network upload or recording.
- `LensFrameDraft.source` is `fixture`, provenance `client-unverified`.
  Timestamps are SDK sample presentation timestamps, not attested wall time.
  JPEG hashes are local diagnostics, never host observation references.
- No Chibi host admission, private memory, physical identity verification,
  action permission, DAT real-device or production release is claimed.

## Official sources and pins

Consulted 14 November 2026. SDK exact version `1.0.1`, upstream commit
`0bd369298eef6a980ad0bdb6c8a5502f2c02a08c`. Current docs/source main observed at
`bbae597cd1c748cd29b9375a1624a8d75b1c9e14`; exact tagged Swift interfaces checked
where the docs and older samples differ. The SDK has a package manifest on the
release tag, not current main.

- [Meta Developer Center](https://wearables.developer.meta.com/)
- [Setup](https://github.com/meta/meta-wearables-dat-ios/blob/main/plugins/mwdat-ios/skills/getting-started/SKILL.md)
- [MockDeviceKit](https://github.com/meta/meta-wearables-dat-ios/blob/main/plugins/mwdat-ios/skills/mockdevice-testing/SKILL.md)
- [Session lifecycle](https://github.com/meta/meta-wearables-dat-ios/blob/main/plugins/mwdat-ios/skills/session-lifecycle/SKILL.md)
- [Permissions](https://github.com/meta/meta-wearables-dat-ios/blob/main/plugins/mwdat-ios/skills/permissions-registration/SKILL.md)
- [Pinned SDK](https://github.com/meta/meta-wearables-dat-ios/tree/1.0.1)

The Developer Center's camera documentation requires sign-in in this research
session; the official public SDK instructions and exact interfaces were readable.
No new account, permission, credential or Meta app was created.

`Resources/charger-label.mp4` is an original generated test card, no people or
third-party footage. Producer: `scripts/generate_video.py` (ffmpeg/libx265,
DejaVu Sans; set `CHIBI_TEST_FONT` for another installed font). The project file
is generated by the stdlib-only script and not hand-edited. SDK binaries remain
upstream under their own license; they are not vendored here.
