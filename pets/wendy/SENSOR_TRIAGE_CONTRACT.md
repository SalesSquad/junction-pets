# Fictional sensor-log review contract

`triageFictionalSensorLog(jsonText)` in [sensor-triage.mjs](sensor-triage.mjs) is a
pure, bounded review of an invented snapshot and declared review ownership. It
has no device, networking, SDK, model, deployment or actuation interface. It does
not authenticate observations, confirm a running fallback or certify safety.
It is not official Wendy functionality or a registered Chibi runtime tool.

## Input

The only input is primitive JSON text of at most 32,768 UTF-8 bytes. Ordinary
`JSON.parse` semantics apply: duplicate object keys use the last value; numeric
literals use JavaScript binary64 semantics. There is no lossless parser,
duplicate-key guarantee or executable-object input. Malformed JSON, unsupported
types, extra/missing fields and invalid values throw `TypeError`.

The root has exactly these fields:

| Field | Accepted value |
| --- | --- |
| `schemaVersion` | `1` |
| `fictional` | `true` |
| `requestedAction` | `review-only`; requested live actuation, connection or deployment is refused |
| `referenceTimeMs` | Integer 0–86,400,000 on an invented relative clock, never a wall-clock read |
| `maxAgeMs` | Integer 1–60,000, a supplied test threshold, not a real-device safety limit |
| `requiredSensors` | 1–16 unique fictional tokens |
| `observations` | 0–64 closed records described below |
| `fallbacks` | 0–16 closed records with unique required sensor IDs |

A fictional token begins `fictional-`, followed by hyphen-separated lowercase
ASCII letters/digits, at most 64 characters with no whitespace. No real device,
operator identifier, URL, hardware command or private telemetry belongs here.

Each observation has exactly `sensorId`, `atMs`, `status`. The ID must name a
required sensor; the time is `null` for unknown or an integer 0–86,400,000.
Status is `nominal`, `fault` or `unknown`, all unverified fixture declarations.
Multiple observations per sensor are allowed, including repeated observations;
counts are counts of supplied rows, not independent evidence or confidence.

Each fallback has exactly `sensorId`, `owner`, `stopCondition`, `fallback`.
The sensor must be required. Owner is a fictional token or `null`. Stop condition
is `on-unresolved-or-fault` or `null`; fallback is `hold-simulation-for-review`
or `null`. These are declarations to inspect, never physical stop commands or
proof that an operator or safety mechanism exists. Missing mappings are visible
review gaps, not permission to infer one.

## Review semantics

For each required sensor, review **all** supplied rows. Missing observations,
unknown times, future times, stale observations, unknown statuses and declared
faults remain visible. Freshness includes the exact `maxAgeMs` boundary and
excludes unknown/future times. A fresh `nominal` and a fresh `fault` produce
`conflicting-fresh-status`; the helper does not select the reassuring one.
A stale or unknown row is not erased by a newer nominal row. This deliberately
conservative snapshot check is not an estimate of the device's current state,
a causal diagnosis, stream processor, clock authenticator or automatic repair.

The output preserves required-sensor order, supplied-row counts and a copied
declared fallback (or `null`). Reason codes have this fixed order:

1. `observation-missing`
2. `time-unknown`
3. `future-observation`
4. `stale-observation`
5. `status-unknown`
6. `fault-reported`
7. `conflicting-fresh-status`
8. `fallback-missing`
9. `owner-unknown`
10. `stop-condition-unknown`
11. `fallback-unknown`

Any reason makes `reviewState:needs-review`; none means `consistent-fixture`.
The overall `snapshotState` uses the same rule across sensors. Neither state is
an execution decision. `kind:fictional-sensor-review` and all five boundary
flags remain explicit: observations are not authenticated, no device is
connected, actuation is neither authorized nor executed, and safety is not
certified. A complete fallback declaration does not remove evidence problems.

## Reproduction and continuation

[The invented snapshot](examples/fictional-sensor-log.json) contains a current
nominal sensor, a stale unknown observation and a missing sensor with unknown
owner/stop/fallback declarations. Run:

```sh
node --test tests/pet-wendy.test.mjs
```

Work: `junction.wendy.capability-proof`; logical owner `junction-dev-wendy`.
The six existing authored model-evaluation cases remain unchanged and
unexecuted. Proposed next slice, not started: compare two fictional snapshots
with explicit clock-uncertainty bounds while preserving unresolved evidence;
no live device control or safety certification.
