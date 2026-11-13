# Fictional collection-plan review — v1

`reviewCollectionPlan(jsonText)` in `collection-plan.mjs` is a pure local
consistency checker, not a crawler, Oxylabs API, permission service or legal
compliance decision. Every URL must use an invented `.invalid` host. Nothing
is fetched, resolved, authenticated or executed. Permission, visibility, robots
policy and sample quality are **supplied declarations**, never verified facts.

## Exact input

Accept a primitive JSON string of at most **32,768 UTF-8 bytes**. Ordinary
`JSON.parse` semantics apply: duplicate object members use their final value.
This is not a canonical JSON/signature parser. Every object is closed; omitted
or extra fields, malformed values and collection duplicates throw `TypeError`.
There are no implicit defaults, coercions or accepted executable objects.

| Object / field | Required domain |
| --- | --- |
| Root | Exactly `schemaVersion`, `scenario`, `allowedHosts`, `limits`, `fields`, `targets` |
| Version / scenario | `1` / `"fictional"` |
| `allowedHosts` | 1–8 unique lowercase ASCII DNS-shaped hosts ending in `.invalid`; at most 253 characters, labels 1–63, no wildcard/leading or trailing hyphen |
| `limits` | Exactly `maxPages`, `maxRetries`, `timeoutSeconds`, `maxAgeHours` |
| `maxPages` | Integer 1–1000 or explicit `null` (unbounded/unknown) |
| `maxRetries` | Integer 0–3 or explicit `null` (unknown) |
| `timeoutSeconds` | Integer 1–3600 or explicit `null` (unknown) |
| `maxAgeHours` | Integer 0–8760 or explicit `null` (unknown) |
| `fields` | 1–16 objects, exactly `{name, personal}`; unique names matching `[a-z0-9][a-z0-9_-]{0,63}`; `personal` is `true`, `false` or `null` |
| `targets` | 1–32 objects with unique `id` and exact URL strings |
| Each target | Exactly `{id, url, visibility, permission, robots, sample}` |
| `id` | Same bounded pattern as field names |
| `url` | At most 512 characters, literal `https://` + fictional host + optional path beginning `/`; path characters only ASCII letters/digits, `_`, `-`, `/` |
| `visibility` | `public`, `private`, `authenticated`, `paywalled` or `null` |
| `permission`, `robots` | `allowed`, `denied` or `null` |
| `sample` | `null`, or exactly `{records, missingRequired, duplicates, ageHours}` |
| Sample counts | `records`: integer 0–1000; each defective-count integer 0–`records` inclusive |
| Sample `ageHours` | Integer 0–8760 or explicit `null` |

No negative zero, non-finite/fractional number, whitespace/control in identifiers
or URLs, URL credentials, query, fragment, port or real hostname is accepted.
The intentionally narrow URL syntax is **not** a general URL parser. The
limits are this repository's fictional policy, not Oxylabs quotas or prices.
Missing is malformed; explicit null is unknown; zero retries, sample age, age
limit and sample counts remain meaningful and distinct from null.

## Exact output and interpretation

Returns `{schemaVersion:1, kind:"fictional-collection-plan-review", status,
findings, targets, bounds, boundary}`. Each finding is exactly `{code, subject}`.
Each target result is `{id, status, findings}` in input order. Status precedence
is `exclude` over `needs-review` over `candidate`. Global findings affect every
target's status without duplicating the global finding into each target array.
The root status is the highest resulting severity. No status grants collection
permission: even `candidate` means only that the invented declarations have no
listed inconsistencies under this narrow contract.

Global findings occur in this order:

1. Null limits: `unknown-page-limit`, `unknown-retry-limit`, `unknown-timeout`,
   `unknown-age-limit`, with subject `limits.<field>`; all need review.
2. More listed targets than known `maxPages`: `page-limit-exceeded`, subject
   `targets`, excluded. This compares listed pages only; no discovery happens.
3. In field order: `personal-field-excluded` for true (exclude), or
   `unknown-field-sensitivity` for null (review); subject is the field name.

Per target, findings use its ID as subject and occur in this order:

1. `host-not-allowlisted` (exclude): exact host equality only, no suffix or
   inherited subdomain permission.
2. `unknown-visibility` (review), or `non-public-target` (exclude) for private,
   authenticated or paywalled targets, even with a declared allowed permission.
3. For permission then robots: `unknown-permission` / `unknown-robots` (review),
   or `permission-denied` / `robots-denied` (exclude).
4. `missing-quality-sample` (review) for null, otherwise `empty-quality-sample`
   for zero records, `missing-required-fields`, `duplicate-records` for positive
   counts, then `unknown-sample-age` or `stale-sample` when age is strictly above
   the known limit. All quality findings need review, not an automatic exclusion.

`bounds` contains exactly `maxPages`, `attemptsPerPage` (`maxRetries + 1`),
`maxAttempts` (page cap × attempts), and `aggregateAttemptSeconds` (maximum
attempts × timeout). Each dependent result is null if a required input is
unknown. These are conservative arithmetic over declared caps, **not** elapsed
time, billed usage, enforced throttling or a real execution promise. All page
slots may use all attempts; fewer supplied targets do not reduce the stated cap.

`boundary` is permanently `{fictional:true, fetched:false,
permissionVerified:false, collectionAuthorized:false, complianceVerified:false}`.
Robots declarations do not replace site terms, consent or applicable law; public
visibility and a candidate result are not proof of any of those. No bypass,
login, paid access, real personal-data collection or proxy action is implemented.

## Example and checks

[`examples/fictional-collection.json`](examples/fictional-collection.json) is
entirely invented and returns `candidate`, no findings, caps of 4 attempts and
120 aggregate attempt-seconds. It has not collected a page.

Run `node --test tests/pet-oxylabs.test.mjs` from the repository root. Ten source
tests cover limits, public/private/auth/paywall declarations, denial/unknown
policy, exact host matching, sensitivity, quality, zero/null/missing, malformed
inputs and deterministic JSON/example handling. They are separate from the six
unchanged authored model eval definitions, which were not executed here. This
Node helper is source-only and is not an automatically exposed plugin tool.
