# Phone geometry and selected work memory

Work: `LENS-ARKIT-SCREEN-CONTEXT-20261114`. Source audit: 14 November 2026.
Admission base: `27fb74b999f41718237958e03404390350f75a65`.

The useful product is a task that continues across surfaces: select an assembly
instruction on the Mac, inspect the actual part with the phone, and resume the
same confirmed step through the glasses. Keep the selected instruction, the
current camera observation and the user's confirmed progress distinguishable.

## What already exists

| Component | Verified source or execution | Remaining boundary |
| --- | --- | --- |
| SAM3.1 | The [pinned worker](https://github.com/SalesSquad/agents/tree/95fdbd30714dc6323e1a5c5e1e23f9fefc34daf2/cloud-services/verda/experiments/meta-sam31) uses `build_sam3_multiplex_video_predictor`, `facebook/sam3.1`, checked checkpoint bytes and at most 32 frames. Its saved qualification passes 10 CPU contract checks with constructed masks. | `gpuExecution=NOT_RUN`, `modelQuality=NOT_QUALIFIED` in the saved 08:29 UTC record. Current GPU/checkpoint availability was not probed in this work. |
| Nemotron | The [local inference summary](https://github.com/SalesSquad/agents/blob/95fdbd30714dc6323e1a5c5e1e23f9fefc34daf2/cloud-services/verda/experiments/nemotron-local-20261114/inference-summary.json) records four actual bounded trials of `NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4`, including vision and typed tool-call formation. The pinned runtime was vLLM 0.32.0; tool effects were zero. | The summary says the server stopped. This is historical model execution, not an available production endpoint or a SAM-to-glasses acceptance run. |
| Lens observation and learning | Existing [observation integration](../../services/lens-learning/OBSERVATION.md) binds an admitted observation to task/capture/learning revisions and drops it after forget, revoke, expiry or task change. | Its 8 simulation checks and 5 browser checks used synthetic responses and zero provider calls. |
| ScreenshotContext | Private [main source](https://github.com/SalesSquad/screenshot-context/tree/0f8bf49b585ee770669b54f875cd206ea498e50b) already contains local OCR/FTS, immutable visual events, explicit project links, SourceReferenceV1, Vision feature prints and a personal-learning prototype. | Repository state, installed app state and activated model state are separate. No private source implementation or screenshot content is copied here. |
| ARKit | This increment adds the `ChibiLensARKit` package product beside the existing Core/UI products. Its phone observation carries an existing `LensFrameDraft`, encoded image and same-frame geometry. | A client observation is unregistered and client-unverified. Physical camera capture, glasses registration and host admission require their own execution evidence. |

The ScreenshotContext Mac read-only check found the installed app version 2.3,
build 5, and an answering local search service reporting 4,604 indexed records.
The three inspected LaunchAgent plists did not set the visual-events opt-in.
These observations do not prove the newer source or its learning model is active.
No OCR, image, window title, browser URL or personal label was opened or exported.

Its preserved [11 November learning pilot](https://github.com/SalesSquad/screenshot-context/blob/0f8bf49b585ee770669b54f875cd206ea498e50b/docs/verification/learning-mbp-pilot-0bee79dcd417.json)
collected four local observations and fitted four visual prototypes. It had
zero validation/test samples and zero confirmed labels; promotion was refused
with `missing_visual_holdout`, and the model remained inactive. That is useful
pipeline evidence, not evidence that the app already understands the user's work.

## Responsibility of each sensor and model

| Input | Useful contribution | Meaning retained in the episode |
| --- | --- | --- |
| Selected ScreenshotContext item | The instruction, earlier decision or work state the user chooses to recall | Historical screen evidence with original capture time and coverage |
| Phone ARKit frame | Camera geometry in the current phone tracking world | Phone-only pose, tracking state, intrinsics, image geometry and session generation |
| Meta DAT frame | Hands-free first-person observation | Independently identified glasses capture and its own timing/session |
| SAM3.1 result | Candidate segmentation and temporal track association | Model result bound to exact admitted image bytes; no physical identity authority |
| Nemotron result | A bounded interpretation or suggested next step from admitted evidence | Advisory output; current host policy still decides permitted effects |
| Confirmed user feedback | Correct project, right step, useful assistance style, correction or exclusion | Explicit, revocable learning input; no implicit fact from an unconfirmed prediction |

## ScreenshotContext interoperability

Reuse its existing local interface rather than building another screenshot
archive. `visual_memory.py context --project <project>` returns selected project
links, bounded excerpts and SourceReferenceV1; it does not transmit them. Keep
this command and the archive inside the authorized private application.
The existing loopback search service is not an internet-facing Lens API.

The [existing interface implementation](https://github.com/SalesSquad/screenshot-context/blob/0f8bf49b585ee770669b54f875cd206ea498e50b/source_reference.py)
separates identities that an adapter must not conflate:

| Existing field | Exact meaning | Required Lens treatment |
| --- | --- | --- |
| `shot_id` | SHA256 of the archive-relative path | Correlation only; never an image-content digest |
| `sourceID` | Stable UUID representation of that path identity | Preserve it without treating it as access authority |
| `sourceTextSHA256` | Hash of the exact full UTF-8 OCR text | A truncated excerpt alone cannot independently verify it |
| `evidenceSHA256` | In the context export, canonical event-metadata revision | Never substitute for `LensFrameDraft.frameSHA256` |
| `image_bytes_verified` | False for metadata-only context export | Keep false until the exact selected image bytes are read and hashed locally |
| `captured` and `coverage` | Original capture time and completeness/degradation of the search | Preserve history and partial coverage; do not restamp an old image as current |
| `status=candidate_unverified` | An explicit work link is still a correlation | Does not prove present task state, object identity or task completion |

The next concrete bridge is **one user-selected context card for one current
Resume episode**. Selection/review happens in ScreenshotContext. A private host
adapter checks owner, project, current consent, task revision and epoch before
reading the selected artifact and again before publishing it. An optional
reviewed/redacted excerpt or image is a separate approved payload, not automatic
export of the archive. Forget, revoke, episode change and source exclusion must
invalidate its use, including queued model requests. Lens does not delete the
original screenshot as a side effect of clearing an episode context card.

If actual image bytes are supplied, the generic source is `import` and remains
two-dimensional/unregistered. A metadata-only card must stay a source reference;
it must not fabricate an image draft. The current strict Nemotron
`runTaskObservation` accepts `meta.sam31.observation` only. A screen import cannot
claim a SAM model pin, mask, track or `MODEL` receipt merely to pass that validator.
Route through existing generic capture/admission interfaces or an explicitly
versioned host extension, with real SAM output only when inference was performed.

**This increment does not install or activate this private host bridge.** It
documents the exact reusable contract and adds the independent ARKit source
adapter. ScreenshotContext PR29 and its installed caretaker retain their scope.

## ARKit expansion sequence

1. **Same-frame geometry:** collect only explicitly requested phone observations,
   bind encoded image digest, original ARKit timestamp/clock domain, intrinsics,
   camera-to-session-world transform and tracking/mapping state. Retire pending
   work after stop, lost tracking, interruption or session restart. Loss of
   established normal tracking requires an explicit restart with a new world ID;
   `PhoneSpatialCapture.validateCurrent` rechecks an asynchronous consumer against
   the live capture owner. This is the code increment in this PR.
2. **Selected point / surface:** add a raycast result for the user's selected
   image location and retain target/alignment, result transform, tracking epoch
   and uncertainty. A plane is not a physical object identity. Do not re-use a
   result from a different frame or tracking world.
3. **Depth and masks:** on supported devices, join scene depth/confidence with
   the same admitted image and the actual SAM mask. Account for depth/image
   resolution, camera calibration, display crop/orientation and invalid pixels.
   Decline a metric point when the supporting measurements are missing.
4. **Persistent physical task:** add explicit map/anchor recovery and separately
   tested relocalization. Retain uncertainty and reject old world references
   after resets. A restored map is not evidence that an object stayed put.
5. **Glasses registration:** estimate the glasses-camera-to-phone-world relation
   from independent common observations/calibration and validated timing. The
   existing host registration validator remains authoritative. Carry measured
   quality and expiry; phone pose alone never qualifies the glasses location.

LiDAR depth and scene reconstruction are optional capability-gated enhancements;
basic phone world tracking is the first path. The user's exact iPhone model and
capability support have not been established by this work. No hardware purchase
is needed to review or compile this adapter.

Primary Apple references checked for this design:
[ARFrame](https://developer.apple.com/documentation/arkit/arframe),
[ARWorldTrackingConfiguration](https://developer.apple.com/documentation/arkit/arworldtrackingconfiguration),
[supportsFrameSemantics](https://developer.apple.com/documentation/arkit/arconfiguration/supportsframesemantics(_:)),
and [supportsSceneReconstruction](https://developer.apple.com/documentation/arkit/arworldtrackingconfiguration/supportsscenereconstruction(_:)).
Frame semantics support is queried on `ARWorldTrackingConfiguration`, as Apple's
documentation requires, rather than on the base `ARConfiguration` class.

## Efficient learning and inference

Keep capture, Vision OCR and geometry close to the device. Retrieve only the
selected task's context. Route a changed, useful crop or short bounded sequence
to SAM/Nemotron through the existing authorized executor when justified; do not
send every camera frame or the whole screenshot archive by default.

Separate three updates: retrieval may find new evidence immediately; a confirmed
correction may change the current task/help preference; a new model version needs
an independent held-out evaluation and explicit promotion. ScreenshotContext's
existing exclusion/undo and cohort-reservation semantics are reusable. A proposed
project classification must not silently become its own training label.

The NVIDIA Skills catalog was checked at
[`894f2d7dfee49085e84e21c1aad2513bc44a5b6d`](https://github.com/NVIDIA/skills/tree/894f2d7dfee49085e84e21c1aad2513bc44a5b6d).
Its VSS vision-stack builder and RT-VLM customization guides concern their own
deployment/service architecture. This bounded adapter reuses our existing
Nemotron/SAM interfaces; it does not install a second VSS stack, change model
endpoints or infer that a running container proves useful inference. The catalog
CLI listing timed out during clone; the pinned authenticated catalog read
succeeded. No NVIDIA skill install, GPU job or provider call was made.

## Acceptance still needed for the complete product

One meaningful physical pilot is: select a consent-safe instruction screenshot,
start a phone observation, identify a real part, interrupt/revoke capture, then
resume only from confirmed progress. Measure wrong-step assistance, ambiguity,
task completion time against phone-only guidance, stale-context rejection,
capture-to-useful-answer latency and bystander/permission handling. Report actual
model/hardware/host routes individually. A compile, synthetic pose or successful
Nemotron trial does not qualify this end-to-end pilot.
