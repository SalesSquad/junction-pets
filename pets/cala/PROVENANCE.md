# Cala: fictional field-provenance proof

This is an offline, deterministic development example, not a Cala API or dataset
schema. It checks whether **supplied** values, artifact contents and timestamps
agree. A consistent citation does not establish truth, authenticity, ownership,
completeness or permission. No connector, model, account or Chibi host is used.

## Bounded contract

`checkFieldProvenance(input)` in `provenance.mjs` accepts a data-only, JSON-like
record. The supplied example in `examples/field-provenance.json` is fictional.
No current clock or network state affects the result.

| Record | Exact keys |
| --- | --- |
| Input | `schemaVersion: 1`, `mode: "fictional-offline"`, `asOf`, `maxAgeSeconds`, `artifacts`, `claims` |
| Artifact | `id`, `sha256`, `sourceTime`, `observedTime`, `fields` |
| Claim | `field`, `type`, `value`, optional `source` |
| Claim source | `artifactId`, `field`, `sha256`, `sourceTime`, `observedTime` |
| Digest payload | `sourceTime`, `fields` |

Every key except claim `source` is required; unknown metadata keys are rejected.
`fields` is a dictionary of explicitly named structured fields, not a schema
completion engine. Names are case-sensitive, start with an ASCII letter and
contain at most 128 letters, digits, dots, underscores or hyphens. Dots are literal
name characters, never a path traversal. This slice supports no field aliases:
the claim and source field names must be identical. Artifact IDs start with
`fictional:` and are unique. Claim field names are unique.

Claim `type` is exactly `string`, `number`, `boolean`, `object` or `array`.
Values may be finite JSON scalars, plain records or dense arrays. A missing value
is malformed input; explicit `null` means unknown and cannot be consistent;
zero, false and an empty string remain present values. Omitted/null citation,
missing artifact/field, or null time is inconclusive, never silently filled in.
Malformed input, contradictory values or metadata, stale data and future times
fail the requested consistency/freshness check; this is not a verdict that the
underlying real-world claim is false.

Times are canonical UTC `YYYY-MM-DDTHH:mm:ss.sssZ` strings, including exactly
three fractional digits. Invalid calendar dates, timezone abbreviations, numeric
timestamps and silently normalized dates are rejected. Source and observation
time are distinct: `sourceTime <= observedTime <= asOf`, and both must be within
`maxAgeSeconds` of `asOf`. The age boundary is inclusive. `maxAgeSeconds` is a
nonnegative safe integer whose conversion to milliseconds is safe; zero is a
valid exact-time requirement. Null source/observation time remains unknown.

## Digest and exact association

`digestFictionalPayload({sourceTime, fields})` computes `sha256:<lowercase hex>`
over UTF-8 canonical JSON of that **supplied** payload: record keys sorted by
JavaScript code-unit order, dense array order preserved, JSON primitive encoding,
no whitespace. JSON serialization represents negative zero as zero; field-value
comparison additionally distinguishes them. The helper validates the data-only
shape, not the timestamp's chronology; the checker validates dates and freshness.

The checker recomputes each artifact digest. Every citation must then match its
artifact ID, exact field name/value, recomputed/supplied digest, source time and
observation time. Object key order does not affect value equality, while array
order, scalar type and missing/null/present state do. Artifact ID and observation
time are not part of the digest payload; they are checked as separate exact
metadata bindings. Even unused supplied artifacts are checked and can prevent
an overall consistent result.

**The caller controls every artifact and all metadata.** A caller can rewrite
both values and hashes consistently. Recomputing a hash detects disagreement
within this input, not forgery, an authentic source, a trusted retrieval clock or
real Cala facts. A fresh observation cannot make an old source fresh. A trusted
host would need a separately authenticated artifact/retrieval and authorization
path; this helper neither implements nor simulates one.

## Result and input safety

The result has `status: "consistent" | "fail" | "inconclusive"`, per-artifact and
per-field results, and structured issue codes. A failure takes precedence over an
inconclusive result. It always reports `sourceAuthenticated: false`,
`truthVerified: false` and `connectorExecuted: false`. An invalid input produces
a failed result without echoing its values. A field result includes its literal
field name, type, present/null state and citation, not the supplied value.

The implementation inspects own property descriptors before reading data.
Unknown keys, accessors, symbols, non-enumerable object properties, array extra
properties, holes, unsupported prototypes, functions, undefined, bigint,
nonfinite numbers and cycles are rejected. It does not call input getters,
methods, coercion hooks or `toJSON`. Frozen records and null-prototype records are
supported. Proxy objects are **outside the data-only contract**: do not treat
arbitrary JavaScript as a sandboxed input format. The Node implementation rejects
detected Proxies before descriptor/prototype inspection, but this is not a
general JavaScript isolation boundary. Prefer parsed JSON from a bounded file.

Limits: 32 artifacts, 64 nonempty claims, 256 entries per nested record/array,
16 levels of nesting, 8,192 total visited values and 131,072 total string/key
characters. Inputs are not mutated. The helper makes no completeness claim for
business fields absent from the supplied claims.

## Run the source proof

```sh
node --test tests/pet-cala.test.mjs
node --input-type=module -e 'import {readFile} from "node:fs/promises"; import {checkFieldProvenance} from "./pets/cala/provenance.mjs"; console.log(JSON.stringify(checkFieldProvenance(JSON.parse(await readFile("./pets/cala/examples/field-provenance.json", "utf8"))), null, 2));'
```

These are deterministic source tests, separate from the six unchanged authored
behavior-evaluation cases. Generated skills-only plugin bundles contain companion
instructions; the unchanged plugin producer does not bundle this executable
helper or execute these tests. Plugin registration, model quality and real Chibi
recipient acceptance remain separate, unverified gates.
