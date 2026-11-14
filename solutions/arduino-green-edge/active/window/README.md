# Open-Window Heat Sentinel — synthetic offboard kernel

**SYNTHETIC / HYPOTHETICAL. No real camera, board inference or hardware calls.**
Dependency-free Node 22+ experiment: a thermal cooling anomaly may purchase an
assumed information budget for a synthetic window ROI check, then propose a
human Buzzer/LED advisory if airing has not been explicitly declared intentional.
It never operates mains, controls heating, or certifies a window's physical state
or the cause of cooling. All proposals have `executed:false`.

From `solutions/arduino-green-edge`:

```sh
node --test active/window/tests/core.test.mjs
node active/window/demo.mjs
```

The CLI emits deterministic JSON for **90 virtual seconds**, immediately, with
no real-time wait. It starts offline/UNKNOWN, gets two stable Thermo samples,
encounters authored cooling and one selective camera proposal, receives a fresh
synthetic OPEN ROI, proposes a human advisory, accepts explicit five-minute Knob
airing intent, encounters steam T/RH confounding, rejects full lens occlusion as
UNKNOWN, and ends with an honest energy receipt. Intent expiry is exercised in
tests; the five-minute intent is still active at the demo's 90-second endpoint.

## API and fail-closed behavior

```js
import { initialState, transition } from './core.mjs';
let state = initialState();
const result = transition(state, {
  type: 'thermo', sample: { at: 0, temperature: 22, humidity: 45 },
}, 0);
state = result.state; // Preserve this complete kernel-owned state between events.
console.log(result.receipt);
```

`transition(previous, event, now)` is pure and deterministic: it clones its input
state, reads no clock, performs no I/O, and returns `{state, receipt}`. Timestamps
are nonnegative safe-integer milliseconds in one caller-provided monotonic time
domain. `now` must strictly increase, including between different event types.
State is a trusted kernel-owned continuation, not an untrusted input protocol;
do not edit it or restart it to erase replay history. Persistence/authentication
and cross-restart replay protection are unimplemented.

Accepted event shapes are exact; unknown fields are rejected without echoing or
retaining them:

- `{type:'tick'}` advances freshness, intent expiry and assumed board accounting.
- `{type:'thermo', sample:{at, temperature, humidity}}` allows finite -40..85°C
  and 0..100% RH. These are authored input bounds, not verified sensor specs.
  Future, over-20-second-old, duplicate and out-of-order samples fail closed.
  Two observations with at least five seconds between them are required. Cooling
  at or below -0.5°C/min is a hypothesis. An absolute RH change above five
  percentage points marks a confound and suppresses the query. This simple
  screen cannot identify every steam/radiator/weather/placement confound.
- `{type:'camera', fixture:{state, at, quality, regionOfInterestOnly:true,
  storedFrames:false, frameFingerprint, queryId}}` accepts only authored synthetic
  `open|closed|occluded|error` states. It runs no image classifier. Evidence must
  be at most ten seconds old, newer than its pending query, quality >=0.8, with
  a unique SINGLE-USE issued query ID and a format-checked 16..64 character
  lowercase hex fingerprint. Fingerprints are NOT persisted. The actual
  camera producer remains unauthenticated; matching an ID does not prove
  real camera input or independent observations. Occlusion/error, bad quality, stale/future,
  malformed and replayed frames yield UNKNOWN, never CLOSED. A valid CLOSED
  fixture is labeled `SYNTHETIC_CLOSED_ROI`, not certified closure or safety.
- `{type:'intent', at, confirmed:true, durationMs}` requires explicit synthetic
  human confirmation, a fresh event (<=2 seconds), and integer duration 1..900000
  ms. Knob events less than 1500 ms after the accepted intent are debounced
  without extending its expiry. Expiry uses the event timestamp, not receipt
  time, and is checked on every clock advance. No infinite airing is accepted.
  Subsequent explicit confirmations can declare a new bounded interval.
  A confirmed intent immediately cancels any pending camera query and
discards stale camera evidence; it cannot authorize a late camera reply.

Invalid events clear thermal and pending-camera evidence, not the
independent monotonic time or accrued assumed energy. A jittery sensor sample
less than five seconds after the previous accepted slope sample is consumed for
ordering but does not overwrite the earlier measurement pair. A spent camera
episode can rearm ONLY after at least 30 seconds of STABLE_OR_WARMING readings;
humidity confounds and insufficient spans cannot purchase repeated frames.
An explicitly confirmed Knob event cancels the pending camera query immediately.

Each camera request carries a monotonically increasing, one-time queryId. A
camera fixture with a missing, reused, or unrelated ID is rejected. Incoming
frame fingerprints are schema-checked but never saved; this avoids a hidden
identity channel or a permanent 128-frame exhaustion counter. A real device
still requires authenticated camera producer binding and durable anti-replay
across restarts. Synthetic OPEN/CLOSED means only an unverified ROI result, never
a physical state guarantee. Advisors are proposed only once per accepted query.
Stable periods and queries have authored limits; actual camera behavior is
still unmeasured and no safety guarantee is established.

## Assumed information auction and energy accounting

The fixed, uncalibrated upper proxy is:

```text
rhoCp = 1.2 kJ/(m³ K), airflow = 0.03 m³/s, DeltaT = 20 K
illustrative power = 1.2 × 1000 × 0.03 × 20 = 720 W
user-declared 300 seconds → UNVERIFIED modeled heat exposure = 60 Wh
```

This is a **prospective scenario illustration**, not a physical upper bound across
all buildings, measured loss, avoided saving, emissions or net environmental
benefit. The intent receipt multiplies by the original user-declared duration;
it does not integrate measured airflow or temperature differential.
The receipt field is called prospectiveScenarioIllustration with
UNVERIFIED_ASSUMPTIONS_ONLY and physicalUpperBound:false even if someone
has explicitly acknowledged airing. It never represents a real saving. Thermo
provides T/RH only; no outdoor DeltaT or airflow is measured here.

The authored information value uses `720 W × 300 s / 3600 × 0.01`, discounted by
thermal severity and freshness. Severity discount is clamped to 0..1 from
`(-0.5 - coolingRateCPerMinute) / 0.5`; freshness discount is
`1 - latestSampleAge / 20000`. These are toy utility assumptions, **not fitted
probabilities or expected avoided losses**. A query is proposed only for a fresh
thermal anomaly, no active intentional airing, no previous query in that episode,
and strictly greater assumed information value than the **0.01 Wh** query cost.
This is an auditable gate, not a validated energy optimization policy or a
matched-budget periodic/random baseline experiment.

Board energy is separately assumed at **4 W**, including offline/stale intervals:
`4 × monotonicElapsedMs / 3600000` Wh, from the first accepted clock value.
Every camera proposal reserves **0.01 Wh**, even if no result arrives; fixtures
do not double-charge it. These are accounting assumptions, not execution or
meter receipts. The demo ends at **0.1 Wh board + 0.01 Wh camera = 0.11 Wh**
(subject to floating-point representation). No proxy benefit is subtracted from
these costs. Rollbacks accrue no negative energy; invalid events with a valid
advancing clock still accrue board energy.

Every structured event receipt carries `SYNTHETIC`, `HYPOTHETICAL`,
`measuredEnvironmentalBenefit:false`, `physicalActuation:false`,
`onDeviceInference:false`, and `networkRequired:false`. The kernel retains only
bounded scalar T/RH history, intent timing, energy counters and synthetic one-time
query IDs/ROI scalar evidence: no frames, identities or person data. It does
not collect images and therefore cannot verify an upstream crop/privacy claim.

## Source and qualification limits

This slice reads the existing `../CONCEPT.md`, `../evidence/VERDA_RECEIPT.md`
and M3 `../../sim/{engine,cli,view}.mjs`; it does not import or change them. The
M5 V100 experiment remains **NO_GO**: held-out summer ~50.5% FN and fault
~58.8% FN; its 320 paired comparisons did not establish occupancy optimization
benefit under the assumed ~96 Wh/day board cost. This new synthetic kernel does
not improve, requalify or replace that evidence.

The specified target kit is UNO Q 2GB Linux/STM32, USB camera, Modulino Thermo,
Knob, Buzzer and on-board 8×13 LED matrix. These are owner-supplied target
descriptions, not hardware verified by this implementation. The permitted source
files contain no official documentation URLs; no new documentation source was
invented. Actual Thermo revision (V0.5+ GXHT30C/I2C 0x45 or earlier HS3003/I2C 0x44), real UNO Q/Modulino/USB
camera I/O, on-device classifier, calibrated power/latency, physical safety and
external submission are **UNVERIFIED**. The watchdog field names only a future
MCU interface: no physical watchdog or safety mechanism is implemented.

No provider calls, credentials, permissions, cloud dependencies, deployment or
external submissions are part of this slice. Required future hardware and field
qualification remains separate from these synthetic tests.
