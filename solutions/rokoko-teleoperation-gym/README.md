# MotionBridge Studio — teleoperation intelligence

**Status:** executable offline training-gym milestone. **Maturity 2/6; not a Rokoko SDK or robot integration.** Main challenge [M326](https://hackjunction.app/participate/45/challenges/326), source snapshot 2026-11-14, runtime agent junction.rokoko / partnerEvidenceKey rokoko; latestClarification was null, earlier 2026-11-13 sponsor guidance read.

## G1 Moves research belongs to Rokoko

The separate [G1 Moves handoff](learning/G1_MOVES.md) assigns this public
humanoid motion-data work and its offline forecast results to the Rokoko lane.
CRACI was the compute executor for that experiment and has its own independent
build-provenance challenge lane. No Rokoko hardware or live capture is implied.

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

## M2: explicit calibrated CSV retarget and replay

Run from this directory (no server or hardware):

    node cli.mjs --retarget-csv fixtures/synthetic-retarget.csv --retarget-map fixtures/retarget-map.json

The tiny CSV is **invented synthetic input**, with duplicate `pose` headers,
not SDK output. The example assumes millimeters and microseconds, rotates
`target.x = -source.y`, `target.y = source.x`, `target.z = source.z`, scales to
meters and adds `(0.1, 0, 0)` meters. It produces three proposals at 0, 50 and
100 ms. The resulting episode always has source label `UNVERIFIED_REPLAY`.

The mapping/config is deliberately explicit:

- `columns` uses zero-based positional indexes for **all eight** distinct
  signals: time, x, y, z, grip, quality, deadman and reset_ack. No header lookup,
  signal inference, grip conversion or tracking confidence interpretation is
  supplied. Grip and quality must already be normalized to [0,1]; the last two
  fields must be literal 0 or 1. Only an intentional operator acknowledgement
  belongs in reset_ack; never derive it from tracking confidence.
- `source.frame_id`, `position_units` (m/cm/mm), `time_units` (ms/us) and
  source bounds in **source units** are required assumptions. Time is an
  unsigned integer string: us must divide exactly by 1000. Converted times
  must strictly increase within 0..120000 ms; fractional conversion,
  collisions and overflow are refused, with no rounding or rebasing.
- `rotation` maps each target axis to a signed source axis, each used once.
  Only determinant +1 rotations are accepted; reflections, general matrices,
  scale/shear and repeated axes are refused. `translation_m` is in target
  meters. Each translation component and each source/target bound endpoint
  converted to meters must have magnitude <=10; these are fixed offline
  admission limits, not device safety certification.
- Target `calibration` must explicitly set `accepted: true`, a nonempty
  `assumption_id`, frame `tabletop-v1`, units m and ordered finite bounds.
  This records operator acceptance of assumptions, **not a verified physical
  calibration**. The goal must lie in those bounds. Every input pose and its
  transformed pose must fit their respective bounds, otherwise the entire
  import is refused before any replay/proposal output. Unknown config fields
  are refused to expose typos and ambiguous assumptions.

Inspect `provenance` for SHA256 of the exact UTF-8 CSV and config bytes,
positional header/index records, source/target frames and bounds, conversion,
rotation/determinant and translation. These hashes bind the report to inputs;
they establish neither ownership nor authenticity. Invalid UTF-8 is refused.
Inspect `receipt.trace` and `receipt.events` for safety decisions: gaps >120 ms,
speed >1.6 m/s, quality <0.8 or released deadman cause HELD with null proposal.
Following a hold, two consecutive healthy frames plus explicit reset_ack on
the second or a later healthy frame are required for rearm. An acknowledgement
cannot override a hazard. To inspect this, change the first deadman to 0 in a
local copy: all frames stay held; set the third frame's ack to 1 to see rearm.
The engine guards and existing UI are reused unchanged; the new importer is a
CLI capability, not a new UI import control.

**Expected claim:** "This declared transform replayed three invented samples
as offline non-actuating proposals; source and simulator calibration are
unverified." **Forbidden claims:** licensed Rokoko data, actual robot task
success, calibrated simulator integration, training authorization, measured
30Hz/live latency or device safety. Even the historical receipt field
`TARGET_REACHED_IN_SIMULATION` only describes the deterministic coordinate
comparison here; no genuine calibrated simulator executed it. No replay is a
training candidate or an actuation grant. Baselines remain operator-provided
reference assumptions.

**Exactly next integration dependency:** sponsor-approved SDK licence and
sample data with confirmed positional column semantics, units, timestamps and
usage permission, followed by an approved simulator adapter with independently
verified source-to-workspace calibration and safety/latency measurements.
The sponsor's 207 MB ZIP, SDK licence and hardware access were not available
in this checkout. M326 permits physical or simulated teleoperation; this
coordinate replay does not establish either integration.
