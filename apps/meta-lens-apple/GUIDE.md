# Phone Lens Guide

`ChibiLensUI.PhoneLensGuideView()` is an iOS 17+ SwiftUI surface built on the
existing `PhoneSpatialCapture` owner. Embed it in an iOS application with a
nonempty `NSCameraUsageDescription`. It does not start on presentation, and it
does not change signing, entitlements, Meta pairing or the existing DATMockApp.

## User flow

1. Grant task camera consent and confirm clear surroundings; choose **Start camera**.
2. Enter an item name/place, ask for overview, label or another side, then move
   the phone and choose **Capture this view**.
3. A frame later than both the request and capture-button AR timestamps is
   frozen for review. A different JPEG alone does not verify the requested detail.
4. Check the physical item and the frozen image, then confirm the association.
5. Select a remembered item and choose **Pack these items**. Each packing action
   needs a new request/frame and user confirmation. Pause/resume keeps confirmed
   progress; a newly started packing task clears the old task's completion marks.
6. After capture, tap a surface in the live viewport to place one temporary
   marker. ARKit handles the viewport orientation through `raycastQuery`.

The marker uses an estimated horizontal/vertical surface within 0.1–5 metres.
It records its own measurement timestamp and transform; it is not a location
in the older review JPEG, proof of object identity, or a glasses coordinate.
Tracking loss, session interruption, camera stop, expiry, forget, and task
changes retire the request and marker. There is no LiDAR prerequisite and no
depth/mesh reconstruction. World maps are not persisted or shared.

## Data and integration

This native notebook lasts for the view's lifetime. It performs no network or
model call and stores no image on disk. The browser Guide has a separate,
explicitly enabled metadata notebook and selected ScreenshotContext handoff;
neither surface is silently synchronized or presented as the private Chibi host.

`GuideSession` is portable Swift state. `LensGuideModel` owns main-actor UI state,
permission lifetime, request expiry and revalidation. `PhoneSpatialCapture`
owns the single ARSession, delegate, JPEG encoding and renderer attachment.
The first accepted frame is stable until confirmation/cancellation. UI review
consent resets on request ID and accepted-frame digest, not only Boolean state.

Real private-host composition must submit the existing client-unverified draft
through authenticated Chibi admission and retain the returned observation
reference. A JPEG digest must never fill `LensScanRequest` host receipt fields.
No user-memory entry, SAM track, Nemotron suggestion or marker grants identity,
external actions or task completion without the relevant user/host authority.

## Focused verification

`scripts/verify-guide.swift`, compiled with `Sources/ChibiLensCore/GuideSession.swift`,
checks causal frame binding, consent, task invalidation, expiry, forgetting and
packing resume versus new-task behavior with synthetic metadata. Native module
emission must include Core → ARKit → UI with Swift 6 and the iOS 17 target.
The delivery receipt records actual runs separately. Compilation and these
checks do not establish an installed/signed app, live phone camera, raycast
accuracy, actual glasses display or host admission.
