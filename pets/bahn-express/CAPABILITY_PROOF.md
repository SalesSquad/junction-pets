# Fictional pickup → handover consistency card

This source-only capability proof is an invented, redacted scenario, **not a
Bahn Express API, transport policy, legal checklist, signature verifier, live
tracking result or Chibi integration**. It adds no current company claims. The
package's existing dated official-source references remain unchanged.

`assessCustodyTimeline(input)` in `custody-timeline.mjs` is a pure synchronous
function. It performs no I/O, network, vehicle, provider, identity, model or
account action. It takes no caller callbacks and uses no ambient clock. Its
output is a consistency assessment of the supplied fiction, never evidence that
anything occurred in the world.

## Input contract (schema version 1)

The [complete valid example](examples/custody-timeline.json) supplies:

| Field | Required value / constraint |
| --- | --- |
| `schemaVersion` | Number `1` |
| `scenario` | Exact string `fictional-redacted` |
| `asOf` | Actual calendar time in canonical `YYYY-MM-DDTHH:mm:ss.sssZ` UTC |
| `freshnessWindowMinutes` | Integer 1–1440, explicitly minutes; no conversion or default |
| `events` | Dense array of 0–100 events in strictly increasing observation-time order |

Every event requires `eventId`, `kind` and `observedAt`. Event IDs and evidence
references are 1–80 ASCII characters matching
`[A-Za-z0-9][A-Za-z0-9._:-]{0,79}`. These are opaque redacted labels: format
validation cannot verify identity, redact private data, dereference a document
or establish that evidence exists. Use invented labels, not actual personal or
vehicle identifiers. Dates have no silent timezone normalization; invalid dates,
equal/reversed event times and observations after `asOf` are not accepted as a
consistent timeline.

| `kind` | Permitted predecessor | Custody effect in the fictional card |
| --- | --- | --- |
| `pickup-planned` | No events | Pending intent only; no reported custodian |
| `picked-up` | No events or pickup plan | Requires proof; reports `origin` → `carrier` |
| `handover-planned` | Pickup record | Pending intent only; carrier remains the reported custodian |
| `handed-over` | Pickup record or handover plan | Requires new proof; reports `carrier` → `recipient` |

Planning events are optional and may not include `custodyProof`. A reported
transfer without `custodyProof` is an unresolved evidence gap, not an inferred
transfer. A present proof must be an ordinary object with **exactly**:

- `fromRole`, `toRole`: role strings `origin`, `carrier` or `recipient`, matching
  the transfer above; these are not authenticated people.
- `observedAt`: same canonical timestamp as its event.
- `conditionRecordId`, `releasingPartyRecordId`, `receivingPartyRecordId`: three
  distinct opaque references. Every transfer needs new references; reuse within
  or across proofs is flagged. References remain unverified even when distinct.

Duplicate event IDs, repeated/backwards stages, missing pickup history, reused
proof references, role/time mismatch, future or out-of-order events all leave
the resulting synthetic current state unresolved. Events are never sorted or
deduplicated to make a questionable history appear coherent. This replay check
is **within one supplied array only**; there is no persistence or cross-request
replay protection.

Freshness is measured against the latest custody record, or the latest plan
when no custody record exists. Older pickup history does not invalidate a fresh
handover record, while a fresh handover *plan* cannot refresh stale pickup
evidence. Age equal to the window is allowed; greater age is stale. A record at
`asOf` has legitimate age zero. Both `asOf` and the window are caller-selected
simulation assumptions, not trusted wall time or the operator's requirements.

## Strict ordinary JSON-like boundary

The helper first copies only own enumerable data descriptors. Objects must have
`Object.prototype` or a null prototype; arrays must be ordinary, dense arrays
with no added properties. It rejects getters/setters without invoking them,
functions, `undefined`, nonfinite numbers, BigInts, Symbols, symbol/hidden keys,
custom prototypes, boxed primitives, dates, named/sparse arrays, cycles, shared
object aliases and unknown schema fields. It never calls caller `toJSON`,
coercion methods or iterators. It does not stringify caller values in errors.
Frozen ordinary data is supported. Limits are 100 array items, 16 own object
keys, 2,048 characters per input string, depth 6 and 4,096 visited values.

**Proxies are outside the ordinary JSON-like contract.** JavaScript reflection
can trigger Proxy traps; this function does not claim to sandbox arbitrary
executable objects, tampered platform built-ins or hostile same-process code.
Prefer ordinary data produced by `JSON.parse` on an appropriately bounded
redacted document. Input labels/format do not themselves guarantee redaction.

Malformed shape/type/unknown fields throw `CustodyInputError` with a fixed code
and safe structural path. Well-shaped but unsupported event claims return
`assessment: "unresolved"`, structured issue codes and **no current custodian or
evidence event**. No partial success is promoted to a current custody assertion.

## Output and limits

The valid example yields `assessment: "consistent"`,
`syntheticState: "handover-recorded"`, `reportedCustodianRole: "recipient"` and
`evidenceAgeMinutes: 15`. These fields summarize the supplied fictional record,
not verified reality. Planning alone leaves `syntheticState: "not-started"` and
no reported custodian. A handover plan following pickup preserves
`syntheticState: "pickup-recorded"` with a separate `pendingIntent`.

Every output has `mode: "synthetic-unverified"`,
`evidenceStatus: "unverified-reference-strings"`,
`realWorldStatus: "not-verified"` and **`completionVerified: false`**. There is no
successful real-world completion path. Confirm actual custody with the human
operator through an independently authorized workflow and genuine evidence.

## Reproduce the deterministic proof

From the repository root with Node 22+:

```sh
node --test tests/pet-bahn-express.test.mjs
```

The focused suite contains valid full, partial, empty, fresh-boundary, frozen
and leap-day controls plus replay, chronology, proof, freshness, finite/unit,
unknown-key and executable-object adversarial checks. The package's six
`evals.json` cases are preserved byte-for-byte. They remain **authored model
evaluation definitions**, not executed model passes. This module/example is not
bundled into the generated skills-only plugin; the existing producer copies
only the companion instructions and their provenance. No plugin registration,
live host permission, publication or deployment is performed by this slice.
