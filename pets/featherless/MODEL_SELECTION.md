# Fictional open-weight model selection rubric

`compareModelCandidates(jsonText)` in `model-selection.mjs` compares supplied,
invented candidate measurements with a declared protocol and requirements.
`example.json` contains fictional numbers and names, not a factual model catalog,
Featherless availability list, benchmark, pricing table or provider result. No
network, account, model invocation, throughput estimate or authorization exists.
This module is repository-only; the generated skills-only companion package does
not bundle or execute it. No new company-source verification is claimed.

## Exact input contract

The only input is a primitive string containing at most **32,768 UTF-8 bytes** of
ordinary JSON, including whitespace. JavaScript objects, boxed strings and hooks
are not accepted or invoked. Native `JSON.parse` behavior applies: duplicate
object members use the last value, number spelling is not preserved, and invalid
JSON fails. Validation applies to the parsed values, not discarded duplicate
members. Nonfinite numbers (including parsed `1e400`) fail numeric validation.
There is no custom JSON parser or external-reference resolution.

Root keys are exactly `schemaVersion`, `kind`, `protocol`, `requirements` and
`candidates`, all required. `schemaVersion` is `1`; `kind` must be
`fictional-open-weight-comparison`. This is a declared fictional scenario, not
proof that an input is fictional or that a real model has open weights/license.

Every protocol has exactly these five required keys:

| Field | Declared meaning and limit |
| --- | --- |
| `taskSet` | Opaque identifier for the same task items, scoring rule, prompts, generation settings and output-length conditions. |
| `runtime` | Opaque identifier for the same synthetic hardware/runtime configuration and measurement procedure, including warmup and sampling. |
| `precision` | Opaque identifier for the same synthetic weight/compute precision. |
| `concurrency` | Integer from 1 through 1,000. |
| `sampleCount` | Integer from 1 through 1,000,000; a declaration, not verified sample evidence. |

The three identifiers are 1–80 lowercase ASCII letters/digits separated by
single hyphens, with no leading/trailing hyphen. They are compared exactly,
without normalization. Null, omitted fields and the literal identifier `unknown`
are invalid protocols. Equal protocol declarations do **not** authenticate equal
conditions; the caller must define the identifiers consistently. No statistical
significance, uncertainty interval or minimum scientifically valid sample size
is calculated from these identifiers or counts.

`requirements` has exactly three required, finite numeric fields. No numeric
strings, null, omitted limits or unknown sentinel are accepted here:

| Requirement | Candidate metric | Inclusive rule | Numeric range for both fields |
| --- | --- | --- | --- |
| `minQualityPercent` | `qualityPercent` | Metric ≥ minimum | 0–100 |
| `maxP95LatencyMs` | `p95LatencyMs` | Metric ≤ maximum | 0–1,000,000,000 milliseconds |
| `maxPeakMemoryMiB` | `peakMemoryMiB` | Metric ≤ maximum | 0–1,000,000,000 MiB |

Decimals are allowed. Values are compared using JavaScript numbers, without
rounding. These fields are supplied summaries: the module computes neither a
quality score nor a latency percentile nor memory usage from observations.
Zero is a known numeric value, including the deliberately fictional zero-latency
boundary; it does not establish that zero latency is physically achievable.

`candidates` contains 1–20 objects, each with exactly `id`, `protocol`, `metrics`.
IDs must obey the identifier rule above, start with `fictional-`, and be unique.
Every candidate supplies a complete protocol with the same contract as above.
`metrics` is a required object; its only allowed keys are the three metric names.
Each key may be omitted, `null`, the literal string `unknown`, or a valid number.
An omitted metric, explicit null and declared unknown all remain **unknown**,
with distinct reasons; none is filled with zero or a default. Other strings,
arrays, malformed values and unknown keys anywhere invalidate the entire input.
In particular `throughputTokensPerSecond`, `liveApiSuccess`, provider execution,
endorsement or other result-claim fields are unsupported and rejected, even on
a candidate that would not be ranked. No input facts are authenticated.

## Exact decisions and ranking

Valid input returns `status: "compared"`, `issues: []`, and `candidates` in input
order. Every candidate has `id`, `status`, `rank`, `protocolDifferences`, `checks`.

If any protocol field differs from the requested protocol, status is
`incomparable`, rank/checks are `null`, and `protocolDifferences` lists differing
keys in the table order above. No metric thresholds or cross-protocol ranking
are reported for it. Otherwise, `protocolDifferences` is empty and `checks` has
exactly the three metric keys. A known metric yields
`{status: "met" | "not-met", value: <number>, reason: null}`. An unknown yields
`{status: "unknown", value: null, reason: "missing" | "null" | "declared-unknown"}`.

Any `not-met` check makes the candidate `ineligible` (even with other unknowns).
Otherwise any unknown makes it `insufficient-evidence`. Only three `met` checks
make it `eligible`. All noneligible candidates retain `rank: null`.

Only eligible candidates enter `ranking`, an array of `{id, rank}`. The explicit
local preference is **quality descending, then p95 latency ascending, then peak
memory ascending**. This is a fixed lexicographic rubric, not a learned or
scientifically optimal weighting. Exact three-metric ties share competition
rank (1, 1, 3); IDs sort alphabetically solely for stable tie presentation.
No global winner is asserted over missing, failed or incomparable candidates.
An empty ranking is allowed; the module never invents another candidate.

Invalid input returns `status: "invalid"`, empty `candidates`/`ranking`, and
`issues: ["malformed-or-unsupported-comparison"]`; no partial results or supplied
input text are echoed. Every result, including invalid ones, contains:

```json
{
  "rankingScope": "eligible-supplied-protocol-only",
  "factsVerified": false,
  "providerRequestExecuted": false,
  "liveApiSuccess": false,
  "authorization": false,
  "throughputTokensPerSecond": null
}
```

Throughput stays unknown: it cannot be inferred from supplied p95 latency alone.
No successful API call, actual license, model availability, quality, privacy,
production suitability or real deployment is established by a synthetic rank.

## Worked example and checks

The example requirements are quality ≥80%, p95 latency ≤100 ms, peak memory
≤600 MiB. Fictional Cinder (92%, 80 ms, 500 MiB) ranks first and fictional Oriole
(90%, 60 ms, 450 MiB) second because this rubric puts quality first. Moss has an
explicit null quality and missing latency: insufficient evidence. Fern's higher
fictional quality is **not ranked** because its runtime differs. Stone fails the
quality threshold at 79%. These are illustrative numbers, not measurements of
any real model or service.

From the repository root:

```sh
node --input-type=module -e 'import {readFileSync} from "node:fs"; import {compareModelCandidates} from "./pets/featherless/model-selection.mjs"; console.log(JSON.stringify(compareModelCandidates(readFileSync("pets/featherless/example.json", "utf8")), null, 2));'
node --test tests/pet-featherless.test.mjs
```

Next bounded action: independently review the rubric's chosen objective and
protocol definitions before any separately authorized real evaluation is planned.
The six existing authored companion evals remain unchanged; these Node tests
are deterministic source checks, not executed model/provider behavior evals.
