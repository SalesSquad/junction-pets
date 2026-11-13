# Fictional FI/EN service-routing and accessibility card

`service-routing.mjs` exports the pure, deterministic `checkServiceRouting(input)`
checker. `example.json` is invented teaching data: its service, text alternatives,
source URL and timestamps do **not** describe an actual Espoo service, resident,
source retrieval or service availability. The reserved `.invalid` source cannot
be used as an official city reference. No application, booking or account action
is performed. This is not a recovered Junction challenge or city endorsement.

## Exact input contract

Use parsed JSON matching the example. Every illustrated key is required and
exclusive at its level. No implicit type conversion, missing-field default,
language fallback, fuzzy service matching or caller-supplied verdict is accepted.

| Field | Required meaning |
| --- | --- |
| `schemaVersion`, `dataKind` | Exactly `1`, `fictional-fixture` |
| `request` | Exactly `language` (`fi` or `en`) and a `serviceId` |
| `asOf` | Explicit reference time; the checker never reads the system clock |
| `maxSourceAgeHours` | Integer from 0 to 720; an exercise policy, not a city recency standard |
| `services` | 1–30 uniquely identified invented service cards |
| `unknownFallback` | Non-routing fallback defined below; always required |

Service IDs are lower-case ASCII letters/digits separated by hyphens, at most
80 characters, starting `fictional-`. Channel IDs follow the same syntax without
that prefix requirement. Each service has exactly `id`, `source`, `localizations`
and `channels`. Every service and fallback has **both** `fi` and `en` localizations.
Each localization's explicit `language` matches its key. A service localization's
`serviceId` matches its parent. Titles, summaries and nonempty `nextSteps` are
nonblank text. `unknowns` requires separate nonblank `availability`, `eligibility`
and `accessibility` descriptions in both languages.

Source has exactly `kind: "invented-fixture"`, `url` and `checkedAt`. A known URL
is canonical `https://fixtures.example.invalid/…` with a lower-case ASCII
letters/digits/slashes/hyphens path and no credentials, port, query or fragment.
No official or other live source URL is accepted in this fictional contract.
Timestamps are valid canonical UTC strings with exactly millisecond precision,
such as `2026-11-13T12:00:00.000Z`. Impossible or normalized dates, alternate
formats and future source times are invalid. Freshness is computed only from the
selected service's supplied timestamp against supplied `asOf`; no claim that the
source was fetched follows. The maximum age boundary is inclusive. Zero allows
only an equal timestamp. Source `url: null` and `checkedAt: null` mean explicit
unknowns and withhold a route; omitted fields are invalid. No other null source
field is allowed.

Each channel has exactly `id`, `kind` (`text`, `image`, `audio` or `video`) and
`accessibleText: {fi, en}`. Each text value is nonblank text or explicit null for
absence. A selected service needs at least one **same** channel with text in both
languages. An image/audio/video-only path without those alternatives withholds
the route. This tests declared content availability, not whether the alternative
is meaningful, equivalent, rendered, keyboard-usable or screen-reader accessible.

`unknownFallback` must have `action: "ask-for-service-detail"`, `serviceId: null`
and both localizations. Each fallback localization has exactly `language`,
`serviceId: null`, `title`, `message` and `nextStep`. Its text must be nonblank.
Unknown IDs never silently select a known service or change language. Missing,
stale or inaccessible known cards instead receive a generated, localized
`verify-official-guidance` fallback with no service target.

## Results and limits

| Status | Meaning |
| --- | --- |
| `routed-fictional` | Exact synthetic ID matched; bilingual content, supplied freshness and text-alternative requirements pass |
| `unknown-service` | No exact ID in the invented catalog; return requested-language non-routing fallback |
| `needs-review` | Selected card has unknown/stale source or no complete bilingual text channel; no route/card is returned |
| `invalid` | Any required structure, scalar, ID, URL, date or safe-data constraint fails; no route or supplied text is returned |

Every result states `synthetic: true`, with `realServiceAvailabilityVerified`,
`accessibilityCertified`, `sourceFetched`, `authorization` and `companyEndorsed`
all **false**. The checker cannot prove translation quality, truth of prose,
actual service eligibility/availability, accessibility compliance or absence of
personal data hidden in text. Human content and accessibility review remain
required. Do not submit resident data; use only invented fixtures. Existing
official citations in the companion manifest are unchanged, not freshly checked.

Ordinary Object-prototype records and dense Array-prototype arrays are supported.
Descriptors are inspected before values: accessors, custom prototypes, symbols,
hidden fields, sparse/extended arrays, functions, hooks, cycles, undefined and
nonfinite numbers are rejected without invoking caller getters or methods.
Resource bounds are depth 12, 10,000 visited values, 20 keys per object, 30 array
entries and 2,000 characters per string. Proxies are unsupported executable
objects, not a sandbox boundary. Returned data is detached from the input.

## Offline exercise

```sh
node --input-type=module -e 'import {readFileSync} from "node:fs"; import {checkServiceRouting} from "./pets/city-of-espoo/service-routing.mjs"; console.log(checkServiceRouting(JSON.parse(readFileSync("pets/city-of-espoo/example.json", "utf8"))));'
node --test tests/pet-city-of-espoo.test.mjs
```

The example routes `fictional-reading-room` in Finnish, with source age 24 hours
against 48 allowed, the `plain-text` channel and explicit unknowns. Change the
request language to `en` for the paired English card. Change the requested ID to
`fictional-unknown` for a non-routing fallback. Set `maxSourceAgeHours` to zero
to withhold the 24-hour-old fixture. None of these outcomes is a real service test.

The six authored model-evaluation definitions in `evals.json` remain byte-exact;
these Node tests do not execute them. Next bounded work: independently review
the Finnish/English wording and exact final source, then propose any real-source
adapter separately with current official evidence and explicit privacy scope.
