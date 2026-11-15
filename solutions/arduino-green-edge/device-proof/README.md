# Offline Bridge energy intake

Task `J26-PF-ARDUINO-20261115-1328`, admitted base
`cea0089f06a179047244872bd98529eafa2167ee`, `junction.arduino`, M356/T45.
Application-level, Bridge-shaped **telemetry ingestion**, with no board calls,
actuation, SDK, network, model, dependencies or persistent writes. All accepted
observations are `USER_SUPPLIED_UNVERIFIED`, even the authored demos;
`actuationAuthorized:false`, `producerAuthenticated:false` and
`measuredEnvironmentalBenefit:false` remain fixed. No cryptographic authenticity
is invented. No physical savings or challenge qualification is claimed.

## Run (Node 22+)

From `solutions/arduino-green-edge`:

```sh
node device-proof/cli.mjs demo positive
node device-proof/cli.mjs demo negative
node device-proof/cli.mjs fixture positive
node device-proof/cli.mjs replay device-proof/tests/fixtures/positive.ndjson stream-0000000000000001 clock-0000000000000001
node --test device-proof/tests/intake.test.mjs
```

`fixture` emits NDJSON to stdout; `demo` emits a comparison marked
`DEMO_FIXTURE_NOT_HARDWARE`. Both reuse `syntheticMeterDocument()` in the existing
`measurement.mjs`. The positive demo is **+210 mWh**, the negative **−135 mWh**,
including device overhead. They exercise the measured-input contract using
synthetic numbers. They are not measurements. No values are clipped to zero.
Replay reads one local regular file, refuses symlinks/devices/pipes and emits
only a complete comparison. On error: exit 1 (usage: 2), static reason code,
no partial comparison, input content or file path echoed. No file is written.

## Exact v1 packet

Each packet contains exactly these fields. Arrays, unknown fields and duplicate
JSON keys (including escaped duplicates) are rejected at every depth. Numbers
use decimal integer notation (no fraction/exponent encoding); clocks/sequence/
energy must be nonnegative safe integers (sequence/end/expiry at least 1).
No coercion, fractional mWh, silent floating-point rounding or unit conversion.

```json
{
  "schema": "green-edge.bridge-energy.v1",
  "method": "green_edge.energy_interval",
  "streamId": "stream-0000000000000001",
  "sequence": 1,
  "clock": {"kind":"monotonic-ms","id":"clock-0000000000000001","atMs":10000},
  "unit": "mWh",
  "channels": {
    "baseline": {"meterId":"meter-0000000000000001","clockId":"clock-0000000000000001","startMs":0,"endMs":10000,"mWh":170,"calibration":{"checkedAtMs":0,"validUntilMs":30000}},
    "scenario": {"meterId":"meter-0000000000000002","clockId":"clock-0000000000000001","startMs":0,"endMs":10000,"mWh":90,"calibration":{"checkedAtMs":0,"validUntilMs":30000}},
    "device": {"meterId":"meter-0000000000000003","clockId":"clock-0000000000000001","startMs":0,"endMs":10000,"mWh":10,"calibration":{"checkedAtMs":0,"validUntilMs":30000}}
  }
}
```

`green_edge.energy_interval` is this adapter's proposed application method tag,
not a verified installed UNO Q RPC. It is never invoked. The existing
`readBridge()` sample seam, room-policy core, active/window kernel and simulator
remain separate. Only `reviewMeterDocument()` decides the energy comparison:
**baseline − scenario − device**, with `1 mWh = 0.000001 kWh`.

| Field | Admission rule |
| --- | --- |
| Stream / clock IDs | Caller pins `stream-` / `clock-` + exactly 16 lowercase hex digits before intake. |
| Sequence | Starts at 1, increases exactly by 1; no duplicates, resets or gaps. |
| Clock | One declared `monotonic-ms` domain; packet/host/per-channel IDs must match. Packet clock strictly increases; host receive clock never decreases. |
| Freshness | Interval end ≤ packet clock ≤ host receive clock, and receive − end ≤ 30,000 ms. |
| Channels | Exactly baseline/scenario/device; distinct `meter-` + 16 lowercase hex IDs; aligned start/end on all three. |
| Intervals | Positive duration ≤ 1 hour; contiguous with the last accepted interval; total coverage ≤ 1 day; no imputation. |
| Energy | 0..1,000,000,000 integer mWh per channel/interval. Bounds plus 96 packets keep all totals/net exactly representable. |
| Calibration | Each channel declares checked/expiry in the same clock domain; check ≤ start < end ≤ expiry. First accepted IDs/windows pin the entire stream; replacement/renewal requires a separately enrolled stream. |
| Resource limits | 8 KiB UTF-8 packet/replay line, 1 MiB file, 96 packets, JSON depth ≤ 6 and values ≤ 128 per parse. |

These are authored protocol limits, not meter accuracy, board specifications or
uncertainty estimates. The 16 hex digits constrain free text; a pseudonym may
still encode identifying information. Use freshly allocated opaque IDs, never
names, emails, serial numbers or derived personal identifiers. No occupancy,
images, credentials, prose, action, consent or authenticity fields are accepted.
Rejected payloads are not retained or reflected into errors.

## Module and replay contract

```js
import { createTelemetryIntake } from './device-proof/intake.mjs';
const intake = createTelemetryIntake({
  streamId: 'stream-0000000000000001', clockId: 'clock-0000000000000001'
});
// jsonText is a serialized packet, not an arbitrary JS object.
// receivedClock is supplied by the trusted local host, in the SAME time domain.
const receipt = intake.append(jsonText, {
  kind: 'monotonic-ms', id: 'clock-0000000000000001', atMs: 10000
});
// After >=2 complete intervals:
const comparison = intake.review();
const existingMeterDocument = intake.document();
const acceptedObservations = intake.snapshot();
```

The private, bounded log exposes no replace/delete/reset/import-state API.
Returned snapshots/documents cannot mutate it. An invalid append throws
`IntakeError` and leaves all accepted history unchanged; the valid next packet
can still be admitted. One interval is only `COLLECTING`; no incomplete review
document escapes. At two or more, the entire candidate is checked by the
existing meter reviewer **before** an append commits. Calibration declarations
and clock labels are not independently verified. This is a volatile append-only
log, not durable/tamper-evident storage: restarting or creating another intake
loses replay history. Preserve complete input externally if needed; there is no
cross-restart protection or trusted host identity here.

Replay NDJSON has one exact `{ "receivedClock": <clock>, "packet": <packet> }`
object per line, 2–96 lines; LF/CRLF and one final newline are supported.
`receivedClock` records historical caller-supplied receipt time. Offline replay
checks freshness against that recorded clock, **not today's wall clock**; it
does not attest when a packet was physically received. IDs are additionally
pinned by the operator's CLI arguments. Failures stop the whole replay.

## Physical UNO Q integration gate

The repo's 14 Nov source catalog routes Arduino to M356/T45, latest clarification
null, with dated 13 Nov `Arduino_RouterBridge.h`, `Bridge.begin/provide` and
Python `arduino.app_utils`, `Bridge.call`, `App.run` guidance. That source is
context, not proof of installed versions or a working producer. The next real
dependency is an authorized **UNO Q + Modulino bench and three separately
calibrated physical energy channels**, plus an operator who verifies the exact
App Lab/Bridge versions, meter provenance, units and uncertainty. A future local
producer must map clocks explicitly (including offset/drift/reset checks),
provide fresh contiguous intervals, and prove unplug/restart/offline recovery.
An ID match alone cannot establish synchronization or independent meters.

| Evidence | Meaning |
| --- | --- |
| Estimated | Existing core/sim/active assumptions; no observed meter power. Never fused into this intake. |
| Declared measured input | Structurally admitted user-supplied mWh/calibration; unverified physical origin, baseline validity and uncertainty. Demo inputs remain synthetic fixtures. |
| Actual qualified outcome | Requires the real bench, independent calibration/provenance, synchronized repeated trials, matched service/environment and observed device power; no such evidence is supplied here. |

Any later actuation requires separately authorized local consent, safety review,
watchdog and emergency stop on the real hardware. This adapter cannot grant it.
No firmware, Edge AI execution, GPIO, Project Hub publication or submission is
implemented. Hardware/provider cost is **unknown**; this offline code makes no
provider request or purchase.
