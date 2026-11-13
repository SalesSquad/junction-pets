# Fictional storage-scope and revocation snapshot review

`reviewStorageMatrix(jsonText)` from `storage-matrix.mjs` compares bounded,
invented declarations offline. It names missing evidence, cross-tenant scope,
revocation and expiry conflicts before any real integration is proposed.
It is **not** an IronShard API, cloud policy evaluator or authorization engine.
No storage, account, credential, MCP, network or signature operation occurs.

## Exact input contract

Input is a primitive JSON string of at most 65,536 UTF-8 bytes. Ordinary
`JSON.parse` semantics apply, including the last value winning for duplicate
object member names. This does not authenticate or canonicalize signed input.
Every field below is required and exclusive; unsupported fields, types,
collection bounds and malformed JSON throw `TypeError` without partial output.
Objects and executable hooks are neither accepted nor coerced.

| Record | Required fields |
| --- | --- |
| Root | `schemaVersion:1`, `scenario:"fictional"`, `asOfMs`, `snapshot`, `tenants`, `actors`, `objects`, `grants`, `requests` |
| Snapshot | `observedAtMs`, `maxAgeMs` |
| Actor / object | `id`, `tenantId` |
| Grant | `id`, `tenantId`, `actorId`, `objectIds`, `operations`, `startsAtMs`, `expiresAtMs`, `revoked` |
| Request | `id`, `tenantId`, `actorId`, `objectId`, `grantId`, `operation` |

Identifiers are 1–48 lowercase ASCII letters/digits/hyphens, starting with a
letter. They are opaque fictional labels, **not** bucket paths, prefixes, URLs,
tenant credentials or object versions. No wildcards, path normalization or
implicit identity aliases exist. IDs are unique within each record collection.
`tenants` is a unique list of at most 16 identifiers; actors, objects, grants
and requests have maximum lengths 32, 64, 64 and 128. Empty collections are
known empty lists, not unknown inventories or inferred permission.

Record identity `id` and tenant list members cannot be null. Other identity
references and a request's `operation` may be null, meaning unknown.
Undeclared identity references are reviewable denials, not silently invented
entities. Grant `objectIds` is a unique, nonempty list of at most 16 IDs;
`operations` is a unique, nonempty subset of exactly `read`, `write`,
`delete`. An unsupported request operation is denied as an unknown effect;
unsupported grant operations are malformed input.

All time fields are nonnegative JavaScript safe integers in **invented
milliseconds**, or null for unknown. Zero is valid, missing fields are invalid.
These values do not come from a trusted clock. `revoked` is exactly true,
false or null; false is only a supplied declaration, not verified active status.

## Rules and results

A request can return `matches-declared-scope` only when its named tenant,
actor, object and grant exist; all tenant and actor bindings match; the exact
object and operation occur in that **one** grant; the grant's entire declared
object scope is known and same-tenant; revocation is explicitly false; and
its supplied time window contains `asOfMs`. The start is inclusive and expiry
exclusive. Invalid/unknown windows and unknown or revoked status deny.
Rights from multiple grants are never combined. This is an allowlist-consistency
rule, not a proof that the scope is minimal for the user's actual task.

The supplied revocation snapshot must have known observation time and maximum
age. Age is `asOfMs - observedAtMs`; a future snapshot or age greater than
`maxAgeMs` denies every request. Age exactly at the bound is accepted; zero
requires the observation and as-of times to match exactly. Unknown timing
denies. A newer supplied revoked declaration therefore removes a previous
match, but omitted, false, replayed or forged revocation cannot be detected.
The caller supplies all data; no authenticity, completeness or liveness follows.

Results include the calculated snapshot age/reasons, per-grant reasons, and a
sorted request matrix with `id`, `decision`, `reasons`. `denied` is an offline
planning outcome, not an enforcement event. Reasons are sorted/deduplicated;
each call returns fresh output. Per-grant reasons describe the grant alone;
snapshot timing is additionally applied to every request. A grant with no
individual reasons does not bypass a stale/unknown snapshot.

Every result has all four qualification flags false:
`authorizationGranted`, `storageAccessed`, `credentialsIssued`,
`provenanceVerified`. Even a perfect declaration match grants no permission.
Real execution must remain in an independently authenticated host with current
tenant consent, revocation, object-version/digest and policy checks.

## Reproduce the invented example

```sh
node --input-type=module -e 'import {readFileSync} from "node:fs"; import {reviewStorageMatrix} from "./pets/ironshard/storage-matrix.mjs"; console.log(JSON.stringify(reviewStorageMatrix(readFileSync("./pets/ironshard/example.json", "utf8")), null, 2));'
node --test tests/pet-ironshard.test.mjs
```

The example matches the supplied read scope and denies the attempted write.
No real object is touched. This helper, contract and synthetic tests are
repository source; they do not create a tool in the generated skills-only
plugin. The package's six authored model eval cases remain unchanged.
