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
