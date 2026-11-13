# Fictional public-page extraction worksheet

`extractSnapshotFields(json)` in `extract-snapshot.mjs` extracts a small, auditable
worksheet from **supplied fictional plain text**. It does not fetch a page, parse
HTML, run Context.dev, monitor anything or verify a page claim. `example.json`
describes an invented Paper Tern product, not a company or real product.

The helper accepts a primitive JSON **string** of at most 32,768 UTF-16 code
units. Objects (including getters, Proxies and `toJSON` hooks) are rejected
without inspection or conversion. Standard `JSON.parse` semantics apply,
including last-member-wins for duplicate JSON object keys; this is not a custom
JSON parser or a security/authorization input format. Arrays of requested fields
must not repeat a field. The parsed envelope and source have exactly the keys in
the example; extra or missing keys are invalid. No coercion or default clock.

## Fixed policy and source evidence

`schemaVersion` is `1`; `mode` is `fictional-only`. `targetUrl` must be exactly
one of these literals, and `source.url` must equal it:

- `https://paper-tern.invalid/public/product`
- `https://paper-tern.invalid/public/release-notes`

No URL normalization occurs. Real domains, private paths, credentials, query
strings, fragments, alternate schemes, encodings and subdomains are rejected.
These are fictional identifier allowlists, not permission to retrieve a URL.
`source.visibility` must be `public`; any other declaration is rejected. Neither
the visibility tag nor `.invalid` proves that supplied text is safe or public.
Use invented text only: the helper is not a secret/PII detector or HTML sanitizer.

`source.text` is nonblank, well-formed Unicode of at most 8,192 UTF-16 code units
and at most 128 LF-separated lines (a trailing LF creates an empty final line).
LF and CRLF are supported; lone CR is rejected. The exact UTF-8 text is hashed
with SHA-256. Both `source.observedAt` and `asOf` must be valid canonical UTC
calendar timestamps with milliseconds: `YYYY-MM-DDTHH:mm:ss.sssZ`.
`maxAgeSeconds` is an integer from 0 through 86,400 inclusive. Future observations
and ages strictly greater than the limit are rejected; zero accepts equal times
only. Supplied timestamps are unauthenticated assertions, not retrieval evidence.

Missing/null/blank source evidence and stale evidence stop extraction completely.
The rejected result has `source:null`, `fields:[]`, and one static issue code,
without echoing supplied source text. Missing required keys are `invalid-input`.

## Deterministic field mapping

`fields` is a nonempty subset of these three exact lowercase IDs, without
duplicates. Results always use this order, independent of request order:

| Field | Exact case-sensitive line prefix | Value |
| --- | --- | --- |
| `title` | `Title: ` | Remaining line text |
| `version` | `Version: ` | Remaining line text, never a number conversion |
| `summary` | `Summary: ` | Remaining line text |

Only a prefix at column zero matches. There is no HTML, selector, fuzzy label,
semantic or multiline extraction. Embedded instructions are inert data. Values
are preserved without trimming; `0` and `false` remain known **strings**.
Each candidate has `{start,end,line,quote}`: zero-based, end-exclusive UTF-16
offsets into the exact supplied text and a one-based line number. CRLF bytes are
not normalized. For every candidate, `text.slice(start,end) === quote`.
The result's source URL, observation time, as-of time and snapshot digest bind
these offsets to one supplied snapshot.

One nonblank candidate gives `state:known`, exact `value`, and `reason:null`.
No matching line gives `value:null`, `state:unknown`, `reason:missing-field`,
and no evidence. One blank candidate gives `blank-field`; two or more give
`ambiguous-field` even when identical. All candidate spans remain available,
but the helper never picks a winner or invents a missing value. Any unknown makes
the worksheet `needs-review`; otherwise it is `extracted`. Neither is a fact
verification. Every outcome retains `fixtureOnly:true`, `sourceFetched:false`,
`factVerified:false`, `providerExecuted:false`, and `authorization:false`.

## Worked example and next company action

The supplied example is exactly at its 300-second age limit. It returns `title`
`Paper Tern` at `[7,17)`, version string `0` at `[27,28)`, and summary
`A fictional folding guide.` at `[38,64)`, on lines 1, 2 and 3. Adding a second
Version line produces an explicit ambiguous unknown. Moving `asOf` one
millisecond later rejects the entire extraction as `stale-source`.

From repository root:

```sh
node --input-type=module -e 'import {readFileSync} from "node:fs"; import {extractSnapshotFields} from "./pets/context-dev/extract-snapshot.mjs"; console.log(extractSnapshotFields(readFileSync("pets/context-dev/example.json", "utf8")));'
node --test tests/pet-context-dev.test.mjs
```

Next bounded task for `junction-dev-context-dev`: independently compare two
fictional worksheets by field ID, value and source digest, keeping missing or
ambiguous evidence visible. Any actual source retrieval, new target policy,
provider integration or recurring monitor needs its own scoped implementation,
host authorization and source-bound receipt. This helper is source-development
proof, not executable code shipped by the skills-only plugin generator.
