# Lens Guide — teach once, resume later

A bounded, local workbench for ten user-confirmed object/place associations.
It connects a requested view to actual browser-captured bytes, a visible user
confirmation, and a task checkpoint. The existing SAM 3.1/Nemotron research and
observation services remain separate; no recognition model runs in this page.

## Run

From the repository root, using Node 22+:

```sh
node services/meta-spatial/guide-server.mjs
# http://127.0.0.1:8790/guide/
```

The existing `observation-server.mjs` also serves `/guide/`, and the Resume page
links here. The standalone server loads no provider configuration or API key.
Both use exact local static routes. The loopback server is a development
surface, not a phone-accessible/public deployment. Browser camera capture
requires an allowed camera on HTTPS or the same device's localhost.

## Complete local flow

1. Choose **Use my camera**. The visible action opens one bounded view request
   and the browser's camera permission flow. Microphone access is not requested.
2. Show the requested detail and choose **Take this photo**. The camera stops
   after a new JPEG is captured. The request expires after 30 seconds.
3. Enter your item name/place, check the physical item yourself and explicitly
   confirm. Repeat for up to ten items.
4. Choose **Pack these items**. Each step requires a new request/photo and your
   confirmation. Pause and resume preserve confirmed steps; starting a new
   packing task clears its completion marks.
5. Optionally enable **Keep my place for next time**. Only strict metadata is
   retained in this browser: user descriptions, selected notes and task history.
   Reload starts a new session, disables capture and pauses an unfinished task.
6. Correct a description, forget an item or forget the whole workbench. Failure
   to remove saved data is reported; the page must never call failed deletion
   successful. Another tab cannot silently republish an old saved notebook.

Selected images and the illustrated sample are preview-only. They cannot
satisfy a fresh request or enable a camera-backed confirmation. No template,
manual metadata edit, screenshot note, model proposal or image hash verifies
physical identity or an item's current location.

## ScreenshotContext reuse

Choose the existing macOS app's explicitly exported `context.json`, or paste a
selected metadata card. The adapter recognizes `ScreenshotContext.handoff.v1`,
as defined in `SalesSquad/screenshot-context` source
`0f8bf49b585ee770669b54f875cd206ea498e50b` (`ChatGPTHandoff.swift`). No private
implementation or personal screenshot corpus was copied into this project.

Only the chosen note (up to 240 characters) and the handoff export time survive
conversion. Filename, application, window, URL, OCR and image fields are
discarded; images and filesystem paths are never followed. A note containing
a link/path needs manual sanitization. Documents are bounded to 16 KiB and
duplicate keys are rejected. `generatedAt` is explicitly **handoff export time**,
not the original screenshot capture time.

The common card has `schema: lens.selected-context/v1`, explicit user selection,
and one of `captured`, `handoff-export` or `user-note` as each entry's time basis.
The visible template shows the complete accepted format.

## Optional assistant and compact surfaces

`?display=1` provides a compact, keyboard/D-pad navigable browser layout.
It does not claim Meta display-device qualification, raw camera access on the
display, eye tracking, 6DoF or registration into the phone's ARKit world.

Assistant sharing is off by default and is separate from local saving. When
the user enables it and `document.modelContext` is available, three tools can
read selected local metadata, propose another view or propose resuming. A tool
cannot start capture, confirm memory, complete a step or execute an external
effect. Visible approval and a subsequent camera action remain separate.
Turning sharing off invalidates registered callbacks and queued proposals.

The public WebMCP surface is a capability-dependent developer integration.
Its absence/failure leaves the visible controls usable. No runtime polyfill,
agent server or hidden network endpoint is installed.

## Trust and storage boundaries

`guide-contract.d.ts` describes the typed integration contract; `guide-core.mjs`
enforces it at runtime. Requests bind session ID, capture generation, task and
revision, memory epoch, request ID and frame watermark. The core copies bytes,
checks their SHA-256, then repeats the live binding/freshness checks after the
asynchronous digest and at confirmation. Distinct pixels do not establish that
the requested identifying detail is present. Capture provenance stays locally
supplied, not camera-attested or authenticated private-host evidence.

The local save is bounded to 32 KiB. It is browser-local metadata, not an
encrypted private Chibi vault. Photos, camera permission, pending requests and
accepted-frame bytes never enter it. A Web Lock, epoch tombstone and old-value
checks coordinate writes; unavailable safe storage means session-only use.

Phone AR is a separate native surface in
[`Phone Lens Guide`](../../meta-lens-apple/GUIDE.md). Its single ARKit session
produces same-frame image/geometry and viewport raycasts with measured, temporary
phone-surface markers. The native view's notebook is in memory and is not
silently synchronized to this browser. Private Chibi admission, durable private
memory and glasses/phone calibration require their real host/device adapters.
Never place a JPEG hash into a host observation-receipt field.

## Verification scope

Focused Node checks cover causal/consent/forget/restore races, actual image-byte
digests, note conversion, storage failure and assistant-sharing boundaries.
Local HTTP checks cover the route allowlist and origin rejection. These are
synthetic/local developer checks, not a physical identity or real-user study.

```sh
node --test apps/meta-resume-web/guide/guide-core.test.mjs \
  apps/meta-resume-web/guide/context-handoff.test.mjs \
  apps/meta-resume-web/guide/guide-ui-boundaries.test.mjs
```

The delivery receipt records the exact source identities, checks actually run,
original failures, and the browser/native execution limitations. No model
quality promotion, training, paid provider request, production deployment or
physical-device operation is part of this source change.
