# MotionBridge Studio — teleoperation intelligence

**Status:** executable offline training-gym milestone. **Maturity 2/6; not a Rokoko SDK or robot integration.** Main challenge [M326](https://hackjunction.app/participate/45/challenges/326), source snapshot 2026-11-14, runtime agent junction.rokoko / partnerEvidenceKey rokoko; latestClarification was null, earlier 2026-11-13 sponsor guidance read.

## Real user job

A robotics engineer records a fragile-object movement, sees every safe proposal and tracking anomaly, deliberately re-arms only after two fresh frames plus acknowledgement, and exports an inspectable demonstration receipt. The operator can compare reference time, path length, target error and refusals before deciding whether a demonstration is eligible for offline training. This does **not** imply that a robot moved or that fragile grasp success was achieved. It separates a clean synthetic sample from an unsafe interrupted sample.

## Run (no dependencies, network or provider keys)

From this directory:

    node --test test/*.test.mjs
    node cli.mjs --episode fixtures/episodes.json
    node cli.mjs --csv fixtures/duplicate-columns.csv --map fixtures/mapping.json
    python3 -m http.server 8765

Open http://127.0.0.1:8765/web/ in a browser. All data is synthetic. Both source files and the user interface run offline after local access to the files. The local HTTP server serves static files only; no external calls, login or analytics. To inspect CSV data, use an **explicit positional mapping** so identical Rokoko-like duplicate headers do not silently override one another. The sample CSV in this repository is invented; it is not the downloaded Rokoko sponsor ZIP.

## Source, trust and actuation contract

- Only two source labels: SYNTHETIC_FIXTURE and UNVERIFIED_REPLAY. Imported user files are *never* relabeled as licensed device data or training-ready. Physical success is always unmeasured and actuation_authorized always false.
- Every frame uses a strictly increasing monotonic millisecond timestamp, calibrated tabletop-v1 meters, bounded workspace, tracking confidence and deadman flag. Refuse malformed data, non-finite numbers, unknown units, missing calibration and duplicate episode IDs.
- A long frame gap, loss of confidence, deadman release, workspace escape or excessive derived motion speed opens a **fail-closed safety hold**. Recovery requires two successive healthy frames and an explicit reset acknowledgement on the second or later frame. This is an illustrative offline guard, **not** a certified safety interlock, emergency stop or deterministic real-time controller.
- A non-actuating action proposal is emitted only while the offline guard is not held. An interrupted demonstration cannot be labeled a clean training candidate even after re-arm.
- Replay receipts retain per-frame decisions and cause codes, measured duration, reference comparison and source kind. CLI adds SHA-256 of canonical JSON input. The reference baseline and improvement percentages are **invented fixture values**, not experimental data.
- CSV preview is 5MB/2000 frames maximum, not an SDK ingestion pipeline for the sponsor's larger source archive. No hardware/device credentials or licensed sponsor data is redistributed here.

## Official integration gap & validation ladder

1. **Next acceptance dependency:** Obtain user-authorized Rokoko ID, official SDK licence and permitted example data, verify sample CSV column semantics, units and source permission with the actual sponsor, then implement the approved source adapter **without changing the explicit-position parser contract**.
2. Map and calibrate actual glove/suit poses into a simulator's coordinate system with recorded transforms, frame alignment and timing uncertainty; never stream this web demo into a physical device.
3. Compare end-to-end task success, intervention/hold rate, input-to-action latency and time for Rokoko versus leader-arm/gamepad on held-out tasks; verify motor/workspace guards on a real robot or simulator under human supervision. Device-specific safety and stop controls must be local and separate from this proposal code.
4. Grow into a multi-operator skill library with deduplicated provenance, session reviews, consented recording lifecycle, annotation/retraining, episode replay and commercial lab licensing. Real SDK, robot, ElevenLabs narration, deployment and business demand remain **unverified**.

## Acceptance evidence

Local Node targeted positive/negative checks and CLI smoke run on an authorized isolated Mac source checkout; report exact commit and results in PR / issue #80. Browser implementation targets 1440px and 390px responsive layouts, keyboard selection and aria-live verdict text; no browser qualification claim without executing a real browser harness. No live computer vision, privacy consent capture, direct robot control, model weights, runtime worker, sponsor account or physical integration was installed.

**Ownership:** only solutions/rokoko-teleoperation-gym/**; shared schemas, CRACI workflow and portfolio issue integration remain with their existing owners. Private Chibi tenant and consent systems are distinct.
