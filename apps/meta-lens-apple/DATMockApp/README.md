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
  -resultBundlePath .native-proof/Integration.xcresult CODE_SIGNING_ALLOWED=NO
```

The real-SDK acceptance test requires frame delivery and OCR, then revocation,
no late frames, explicit restart, disconnect and cleared preview. It does not
silently swap in a fake SDK when a host or SDK cannot run it. The app-local
generation fence also has focused tests in `ChibiLensCoreTests`.

## Observed verification — 14 November 2026

The official-SDK iOS app and integration test **compile successfully** on Xcode
27.2 for arm64 Simulator at code commit `a1fefd76`. The two unchanged core
cancellation-fence tests pass. The simulator frame/OCR/revocation test did not
reach a test-case result: simulator startup consumed disk headroom and the
guarded run was interrupted. Its disposable simulator was subsequently shut
down and deleted successfully. **No end-to-end frame or hardware pass is claimed.**
See [the source-bound verification record](VERIFICATION.json) for exact hashes,
review bindings, original interruption limits and the single resume action.

## Lifecycle and trust

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
