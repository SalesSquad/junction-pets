# Fictional supplied-result ranking exercise

`rankSuppliedResults(jsonText)` from `search-ranking.mjs` is a deterministic,
offline exercise over invented, user-supplied observations. It never searches,
opens a URL, invokes Exa or another provider, or authenticates evidence. It links
each output row back to its supplied ID, URL and excerpt. That traceability is
not verification of a source, quotation, publication date, claim or truth.
No new company/product fact, source-review date or endorsement is claimed.

## Exact input contract

The only input is a **primitive JSON-text string**, at most 100,000 JavaScript
UTF-16 code units. No object coercion, reviver, custom parser or executable
objects are supported. Native `JSON.parse` behavior applies: duplicate object
keys keep their last value; ordinary JSON number rounding occurs before
validation. The text-length limit bounds parsing; this is not a JSON signature
or duplicate-key detector. Malformed JSON and unsupported fields fail closed.

All fields in `search-example.json` are required and exclusive, including every
result field. Missing fields are invalid, not unknown. There is no implicit clock.

| Field | Accepted value / meaning |
| --- | --- |
| `query` | Nonblank supplied question, at most 300 code units. Not interpreted or searched. |
| `terms` | 1–10 distinct lowercase ASCII alphanumeric tokens, each 1–30 characters. Caller-chosen vocabulary, not inferred relevance. |
| `asOf` | Actual calendar day `YYYY-MM-DD`, years 0001–9999; the comparison clock supplied by the caller. |
| `maxAgeDays` | Safe integer 0–3650; inclusive publication-age window. Zero means the same calendar day, not unknown. |
| `results` | 0–50 observations. Empty means no supplied results, not proof that a search found none. |
| Result `id` | Unique 1–40 ASCII letters, digits or hyphens. |
| `url` | At most 2048 code units; HTTPS with a hostname ending in `.example`, no credentials, whitespace or control characters. Fictional URL only. |
| `title` | Nonblank, at most 300 code units. Display context only; never scored. |
| `excerpt` | Nonblank supplied text, at most 2000 code units, when retrieval is `supplied`; otherwise exactly null. |
| `publishedOn` | Actual `YYYY-MM-DD` calendar day, or null for unknown. A future publication is flagged, not treated as fresh. |
| `retrieval` | Exactly `supplied`, `missing` or `unknown`: declarations, not provider receipts. |
| `retrievedOn` | Calendar day no later than `asOf`, or null for unknown, when `supplied`; otherwise exactly null. |

## Ranking, deduplication and evidence

For `supplied` excerpts only, lowercasing followed by `[a-z0-9]+` tokenization
finds the distinct requested tokens present. Each requested token contributes
once: repeated words cannot boost the count. This deliberately limited ASCII
vocabulary measure ignores titles, query interpretation, synonyms, meaning,
source authority and truth. Embedded instructions remain uninterpreted text.

Rank by descending `matchCount`, with original input order breaking ties.
A known zero is scored and precedes null, which means retrieval is missing or
unknown and no score can be computed. `matchedTerms` retain caller term order.
Dates never influence the score, and rank is not a recommendation to trust a URL.

Deduplicate by the standard `URL` serialization after removing the fragment.
This normalizes, for example, host case, the default HTTPS port and dot paths;
path case and meaningful query strings remain distinct (query order is not
sorted). It does not detect copied text, mirrors, redirects or equivalent sites.
The **first observation wins**, even if it is missing text and a later duplicate
has an excerpt. Later observations remain intact in `duplicates` and cause
`duplicate-observations-unreconciled`; they never boost or replace the retained
score/date. Conflicting or unknown duplicate dates remain visible, not silently
merged into a verified publication. The caller must reconcile them separately.

`publication` returns the retained observation's supplied date, integer
`ageDays` and `state`: `fresh` for ages 0 through `maxAgeDays`, `stale` above that,
`future` for negative ages, and `unknown` with null age for null date. Calculations
use UTC midnight on the supplied days. A recent retrieval does not make an old
publication fresh. `gaps` explicitly name missing/unknown retrieval, unknown
retrieval date, unknown/future/stale publication and unreconciled duplicates.
These gaps are prompts for human review, not a diagnosis of a real website.

Valid input returns `status: "ranked"`, ranked rows, unique/duplicate counts,
supplied query/terms/window and empty `issues`. Any malformed/unsupported input
returns `status: "invalid"`, an empty ranking, null counts and the generic issue
`malformed-or-unsupported-input`; no partial score escapes. Every response sets
`searchExecuted`, `evidenceVerified`, `semanticRelevanceVerified` and
`authorization` to false. Arbitrary assertions such as `verified`, relevance
scores or provider execution flags are unsupported input keys.

## Worked example and verification

The supplied fictional orchard excerpt covers `apple` and `harvest`: count 2,
age 7 days, fresh at the inclusive boundary. Its second URL fragment is retained
as an unreconciled duplicate. The invented commentary covers only `apple`:
count 1, age 12 days, stale. The unfetched title covers neither token for scoring:
count null, publication unknown. No basket count, real harvest or retrieved page
has been verified. The six existing model-evaluation definitions remain authored,
unexecuted cases; these Node tests exercise only deterministic source code.

From the repository root:

```sh
node --input-type=module -e 'import {readFileSync} from "node:fs"; import {rankSuppliedResults} from "./pets/exa/search-ranking.mjs"; console.log(JSON.stringify(rankSuppliedResults(readFileSync("pets/exa/search-example.json", "utf8")), null, 2));'
node --test tests/pet-exa.test.mjs
```

Next: a separately authorized human/source review should reconcile duplicates
and obtain the exact primary-source content and publication evidence before
extending this exercise to a real research question. No retrieval is requested
or performed by this module.
