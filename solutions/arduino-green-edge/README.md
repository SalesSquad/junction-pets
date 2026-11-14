# Green Edge OS

WORK ID **J26-PF-ARDUINO-M356-T45-M1-20261114**. Base source verified locally:
`51ac807d03fe5c37d1fdf8518ef32830ff50ac2b`. English-first, dependency-free room
comfort/energy decision lab. **SYNTHETIC / OFFLINE_DETERMINISTIC**, no connected
UNO Q, no model inference, no firmware, no environmental savings claim.

## Run locally

Node 22+ (no install, network or dependencies):

```sh
cd solutions/arduino-green-edge
npm test
node cli.mjs empty --opt-in
node cli.mjs dropout --opt-in
node cli.mjs offline
npm run serve
```

Open `http://127.0.0.1:8080` in your browser. The server binds loopback only.
Python 3 is needed only for the static browser server; CLI/tests use Node.
All browser assets are local and work without internet while the local server
runs. ES modules require HTTP; opening the HTML as a file is not supported.
No analytics, fetch, external fonts, storage, cloud, account or retained personal
occupancy data. Replay state and last eight decision fingerprints live only in
memory; reload/reset clears them. CLI emits synthetic diagnostic records only.

Try two steps, opt in, then change to an empty room and step twice. Disconnect a
sensor, inject malformed data, advance without a sample, or revoke opt-in. All
controls are native keyboard inputs with visible focus, labels and status text.
A network outage toggle describes the absence of network dependency; it does
not claim to disconnect a real network. There are no background actions.

## Decision contract and assumptions

`core.mjs` is shared unchanged by CLI and browser. Caller supplies evaluation
clock, measurement and prior state. Samples include epoch milliseconds `at`,
finite numeric `temperature` °C, `humidity` %, integer aggregate `occupancy`,
`lux`, and boolean `connected`. All four readings are mandatory. Missing,
malformed, disconnected, future, >30-second-old and non-monotonic samples HOLD
with **no action command**, clearing pending/assumed outputs. HOLD is not a
physical switch-off confirmation. A real adapter must have its own local
watchdog and safe hardware state. More than 15 seconds between accepted samples
restarts debounce. UI's 45-second no-sample control explicitly exercises it.

Two consecutive fresh samples with the same proposal are required. Fan enters
at ≥27°C OR ≥70% humidity, remains on above 25°C OR above 65%; light enters below
250 lx and remains on below 400 lx. Zero occupants proposes both off, still
subject to debounce. Manual off overrides demand on valid samples; opt-in is
required before even an off command is simulated. No opt-in yields a proposal
only. These are **illustrative room-policy choices**, not health, HVAC, building
code or sponsor thresholds. A fan is not claimed to reduce room temperature or
humidity. No learned model or causal comfort prediction is present.

Each evaluation contains its timestamp, canonical input diagnostic fingerprint
(FNV-1a 32-bit, collision-prone, not cryptographic), policy fingerprint and
mode. Replay uses a fixed starting clock and fixed scenario vectors. No random
numbers, external data or person identities. State is caller-owned; use a fresh
`initialState()` for each session and never hydrate untrusted state as authority.

## Two ledgers — never combine them

1. **Estimated room-load ledger**: chosen hypothetical baseline is a continuously
   operating 40 W fan plus 20 W light. Scenario uses the same assumed wattages
   only when simulated on. For each explicit accepted interval:
   `kWh = watts × (end_ms − start_ms) / 3,600,000 / 1000`.
   Avoided estimate = baseline − scenario, including negative results. Each
   interval is at most 60 seconds; browser/CLI book 10 seconds per opted-in
   action. Invalid/HOLD/proposal intervals do not count; overlapping or duplicate
   intervals throw. Estimates describe a counterfactual scenario, not measured
   energy, whole-session extrapolation, carbon or verified environmental benefit.
2. **Measured UNO Q ledger**: watts and measured kWh remain `null` (unknown).
   No board power, sensor consumption, meter reading or net benefit is invented.
   Adapter acceptance needs a calibrated meter and separate timestamped samples;
   a future net estimate must explicitly subtract measured device overhead and
   disclose uncertainty, coverage and baseline assumptions.

Scenario values (23–28°C, 42–75% RH, 0–4 occupants, 180–650 lx) and 40/20 W loads
are authored synthetic assumptions, not quoted device specifications. They
exercise the local energy-efficiency direction in [M356](https://hackjunction.app/participate/45/challenges/356),
with the actual source text preserved in the [catalog](../../docs/challenge-research/current-source-catalog.json).
See also [Arduino research](../../pets/arduino/CHALLENGE_RESEARCH.md) and its
proposed bounded work/dependency roadmap. No separate Arduino roadmap file was
found in the source tree. Sponsor guidance is the catalog's 13 Nov dated entry,
with `latestClarification: null`; official briefs outrank older workshop notes.

## Bridge-shaped seam and hardware acceptance roadmap

`readBridge({call})` invokes injected method `green_edge.sample`. A test/local
transport can return `synthetic(at)`; all validation remains in `evaluate`.
This seam does not import an Arduino SDK, connect, infer, drive a relay, or grant
transport authority. Transport errors must be caught by a future host and fed
as missing samples into HOLD; use a bounded timeout plus hardware watchdog.

Earlier sponsor guidance names `Arduino_RouterBridge.h`, `Bridge.begin`,
`Bridge.provide`, and Python `arduino.app_utils`, `Bridge.call`, `App.run`.
These are source references, **not verified compile-ready firmware**. Future
adapter work must:

- Physically verify borrowed UNO Q/Modulino availability, licenses, wiring and
  exact installed App Lab/Bridge versions before selecting calls and units.
- Implement timestamped aggregate readings via a local Bridge provider; verify
  supported temperature/humidity sensors and separately source/verify occupancy
  and lux inputs. Never assume the supplied kit provides all four modalities.
- Reject clock drift, stale/replayed/corrupt packets, disconnects and transport
  timeouts; prove safe local behavior during host/network loss and recovery.
- Add explicit local per-session consent, emergency off and independently safe
  hardware actuation before any real fan/light. This demo is never wired to it.
- Run a licensed, pinned on-device model only after hardware verification; record
  model/license/input digests, latency, uncertainty, held-out results and power.
  Deterministic policy is not proof of Edge AI.
- Meter baseline/scenario/device energy separately with matching durations,
  repeated trials and uncertainty; demonstrate physical behavior and accessibility
  on the actual device/browser. None is qualified by Node tests.

## Separate challenge eligibility

**M356**: local greener coworking rooms address the green/local-impact direction.
Main rubric: technical/Edge AI 30%, environmental/social 30%, creativity 20%,
working physical prototype 20%. Useful synthetic software is implemented;
actual UNO Q/Edge AI, physical prototype and environmental outcomes remain missing.

**T45**: hardware + Edge AI 50%, working prototype/demo 30%, creativity 20%.
No hardware or on-device model proof exists; this offline milestone does not
establish prize eligibility. Both briefs require Junction submission **and**
Arduino Project Hub publication with tag **Junction Finland 2026**. Neither
submitted nor published; no provider/submission calls were made.

Scoped tests cover safety, hysteresis/debounce, override/consent, disconnected
and malformed sensors, recentness/watchdog, deterministic replay/injected
transport and energy double-counting. Browser rendering, screen reader behavior,
physical hardware, licensed model execution and actual power remain unqualified.
Coordinator owns publication; this work makes one local source commit only.

## M2: local meter-evidence comparison (14 November 2026)

This is a second, **completely separate** local-only user journey below the M1
room lab. Click **Review synthetic example**, **Review negative outcome**, or
select a local JSON file. A complete three-channel comparison is shown with the
baseline, switched-load and UNO Q/device-overhead channels visible separately.
Nothing is uploaded or saved to browser storage. User-supplied values and
self-declared calibration are never a verified physical meter record, even if
the file passes structural checks. An arithmetic difference is **not** evidence
of causal environmental savings. There is no connected board or sensor.

Run from this directory (Node 22+, no dependencies):

    node measurement-cli.mjs positive
    node measurement-cli.mjs negative
    node measurement-cli.mjs tests/meter-positive.json
    node --test tests/measurement.test.mjs

Strict contract: `green-edge.meter-review.v1` JSON, evidence labelled
`SYNTHETIC` or `USER_SUPPLIED_UNVERIFIED`, exact `mWh` unit (integer
milli-watt-hours), and separate `baseline`, `scenario`, `device` arrays of
2–96 matched, contiguous `{startMs,endMs,mWh}` intervals. Three matching
pseudonymous meter calibration declarations must include `meterId`,
`checkedAtMs` and `validUntilMs`. Parsed files cap at 128 KiB. Every interval
for each channel has the same endpoints; gaps, overlaps, negative/unsafe values,
expired declared calibration, extra fields and missing device costs refuse the
comparison. Conversion: **1 mWh = 0.000001 kWh**. Signed result = baseline
minus scenario minus device; negative results remain negative. No imputation or
extrapolation, no fusion with M1's counterfactual watt assumptions, and no
claims of authenticated timestamp, calibrated actual hardware, carbon impact
or real energy savings. The file includes no person or occupancy fields.

The positive SYNTHETIC example is +210 mWh (0.000210 kWh) over three 10-second
intervals; negative example is -135 mWh (-0.000135 kWh). Both are exercises,
not physical measurements. These numbers cannot qualify M356/T45.

**Exactly next acceptance dependency:** an authorized UNO Q + Modulino bench,
separately calibrated physical meter/channel provenance, and a consented
repeatable offline load comparison with measured power and stable environmental
conditions. Check installed Arduino App Lab/Bridge versions and supervisor safety
before wiring any output; no network, hardware/SDK or published Project Hub
submission was performed by this code. The local review cannot authenticate
self-reported files or independently identify a causal green outcome.

## M3: 24-hour Green Edge Twin

WORK ID **J26-PF-ARDUINO-M3-COUNTERFACTUAL-TWIN-20261114**. New simulator source
is in `sim/`; M1's `evaluate`, state machine and policy and M2's meter review
remain unchanged. **SYNTHETIC / HYPOTHETICAL / NOT MEASURED.** This twin never
reads or fuses M2 files, meter declarations or energy values.

From this directory, with Node 22+ and no dependencies:

```sh
node sim/cli.mjs winter 4
node sim/cli.mjs fault 4 --trace
node sim/cli.mjs summer 30 --seed=2 --seeds=12
node --test sim/tests/engine.test.mjs
npm run serve
```

Open the local page and scroll to **05 / The 24-hour Green Edge Twin**. Run
one day, inspect an individual 10-second slot, then run the shifted cohort.
Try `fault` at 4 W: reduced load can conceal missed fan service. Try 30 W:
the device can cost more than the load difference. Results expire on control
changes until rerun. No fetch, account, analytics, persistent storage, external
model, board, sensor or relay is used. CLI JSON has no wall-clock run timestamp;
identical arguments replay identically. `--trace` is single-day only.

### Experiment and machine contract

One seeded exogenous day has 8,640 contiguous 10-second intervals. The epoch is
fixed; the interval is within M1's 15-second watchdog bound. The first sample,
transitions, sensor noise and fault recovery exercise the actual M1 debounce.
Environment generation is independent of both controllers and device watts;
neither controller changes indoor conditions. No thermal/cooling or humidity
removal benefit is inferred from a fan command.

A uses seasonal timers: 08:00–18:00; winter fan 13:00–16:00, otherwise fan all
scheduled hours. Winter/evening lights run all scheduled hours; summer/fault
lights run 08:00–09:00 and 16:00–18:00. This is a conventional, explicitly chosen
comparison, not the best available controller. It can itself miss required
service, especially after hours. B calls the unchanged M1 policy with only the
current noisy aggregate sensor sample, local state and clock. It receives no
hidden true occupancy or future observations. Hidden synthetic truth scores
occupied warm/humid fan demand (≥27 °C OR ≥70% RH) and occupied darkness light
demand (<250 lx). These thresholds are illustrative, not health standards.

**HOLD never becomes an OFF command.** `action` stays `null`. On every HOLD,
including debounce, a separately labelled hypothetical schedule fallback is
used solely to complete this model's energy/service accounting. It is not a
physical action or a change to M1 state. Coverage reports action slots, fallback
slots/seconds/episodes and reason counts; `faultSlots` counts dropout/stale
only. A full `--trace` contains hidden scoring truth, sensor sample, decision,
reason, pending debounce count, original action, accounted output/source,
required service and per-slot watt-seconds. The browser has an hourly table and
a full slot inspector for single runs. No identities or person records exist.

`green-edge.synthetic-twin.v1` returns `baselineWs`, `edgeLoadWs`, `deviceWs`,
signed `grossWs = baselineWs - edgeLoadWs` and
`netWs = grossWs - deviceWs`. Fan/light are chosen **40 W / 20 W assumptions**.
Load energy accumulates integer watt-seconds. Overhead supports 0–30 W with up
to three decimals, represented as integer milli-watts and multiplied by the
full 86,400 seconds once; no slot is rounded to mWh. Display kWh is rounded only
at presentation (`Ws / 3,600,000`). `breakEvenDeviceWatts = grossWs / 86400` can
be negative. Break-even is net zero, which does not qualify as a candidate.
No emissions/carbon calculation or causal savings claim is made.

Recommendation is typed as `NOT_RECOMMENDED` or `MODEL_ONLY_CANDIDATE`, always
with `eligibilityScope: SIMULATION_ONLY`, `measured: false` and
`physicalExecution: false`. Any net ≤0, **any required fan/light service missed
while A supplied it**, or >5% hypothetical fallback refuses the candidate.
The 5% ceiling is an authored modeling guard, not a sponsor/safety criterion.
Baseline/edge total unmet service and edge-only missed service stay separate;
an improvement at one time cannot erase a degradation elsewhere. A candidate
can still have unmet service shared with the baseline. It is not real-world
verification or challenge eligibility.

`green-edge.synthetic-stress.v1` accepts **4–32 total cases** (12 by default in
the UI). Starting with the selected case, it cycles winter, summer, evening and
fault, advancing seeds (unsigned 32-bit wrap). Arrival shifts cycle
−2/−0.5/+1/+2 hours, rotating each group of four so each season spans multiple
shifts; temperature sensor bias cycles −1/+0.5/−0.5/+1 °C in groups of four.
The timer remains fixed. These are reproducible sensitivity cases,
not a statistical population or confidence interval. Worst, median, mean,
negative/non-positive counts, degradation/fallback counts and every case are
reported. Any refusing member refuses the cohort. Finite numeric ranges, seed
integers, bounded cases and CLI flag validation prevent unbounded runs.

### Source fit and acceptance limits

This is an implemented local counterfactual experiment for **M356 / T45**
(`partnerEvidenceKey=arduino`, owned brief refs M356/T45; latest clarification
null, older 13 Nov workshop, as supplied by the coordinator). The local green
direction is explored without treating a timer comparison as an environmental
outcome. This does not satisfy the briefs' physical prototype or Edge AI proof.

The targeted tests cover replay, paired disturbances/M1 inputs, exact units and
overhead losses, null-action fallback, exercised debounce/watchdog recovery,
dropout/stale/false-empty visibility, service refusals, bounded stress cohorts,
aggregate-only data and deterministic CLI behavior. They do not establish
browser accessibility, installed SDK compatibility or physical performance.
Actual test results belong to the worker handoff, not this timeless contract.

The separate integrated acceptance step requires an authorized **UNO Q +
Modulino**, independently calibrated meter channels, pinned installed Arduino
App Lab/Bridge, a licensed pinned on-device model, and safe actuation with a
local watchdog. Independently measure device/load power, coverage and service
under matched repeatable conditions before evaluating benefit. No firmware,
inference, physical calibration, real energy outcome, Project Hub publication
or external submission is delivered by M3.
