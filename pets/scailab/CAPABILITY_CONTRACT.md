# Fictional perception coverage contract

Source-only function: `reviewPerceptionCoverage(jsonText)` from `perception-coverage.mjs`.
It reviews invented **declared sample counts**, not images, datasets, sensors, model predictions,
accuracy, domain shift, safety or actual sim-to-real transfer. It performs no I/O, imports,
provider calls or host actions. The portable skills-only plugin does not expose or execute it.

## Input

A JSON **string**, at most 32,768 UTF-8 bytes. Objects are not coerced or inspected.
Parsing follows standard `JSON.parse` semantics, including last-key-wins for duplicate JSON keys;
do not use this helper to certify the integrity of untrusted serialized evidence.
The root, `minimumSamples` and each stratum are closed records: all listed keys are required,
and additional keys are rejected. The example is entirely invented, not a Scailab dataset.

| Field | Exact value or bounds |
| --- | --- |
| `schemaVersion` | `1` |
| `fictional` | `true` |
| `scenarioId` | Lowercase ASCII letter/digit first; subsequent letters/digits/hyphens; 1–64 characters |
| `requiredWeather` | 1–4 unique members of `clear`, `rain`, `fog`, `snow` |
| `requiredOcclusion` | 1–3 unique members of `none`, `partial`, `heavy` |
| `minimumSamples` | `{synthetic, real}`; each a safe integer from 1 to 1,000,000 |
| `realEvaluationSplit` | `"held-out"`, `"training-overlap"`, or `null` (unknown); declaration only |
| `strata` | 0–12 records with exactly `{weather, occlusion, syntheticSamples, realSamples}` |
| Stratum axes | Each must belong to the respective required axis; unique weather/occlusion pair |
| Stratum counts | Each a safe integer from 0 to 1,000,000 or `null` (unknown) |

Missing fields, duplicate/unrequested strata, unsupported enums/keys, non-integer or
out-of-range counts and malformed/oversized JSON throw `TypeError`. Errors do not echo inputs.
Omit a stratum to express **missing** coverage; use explicit `null` for an **unknown** count;
zero is a known count and never means missing. A wholly empty `strata` array is valid and
reports all required combinations missing. The Cartesian product, not just axis membership,
defines required coverage (maximum 12 cells). Synthetic counts never replace real counts.

## Output

A fresh deterministic JSON-compatible record with exactly:
`schemaVersion`, `kind`, `scenarioId`, `status`, `summary`, `minimumSamples`,
`realEvaluationSplit`, `strata`, `findings`, `boundary`.

- `schemaVersion: 1`; `kind: "fictional-perception-coverage"`; scenario and thresholds echo validated declarations.
- `status`: `"declared-coverage-complete"` only when every cell has both counts at or above
  its inclusive minimum and split is declared `"held-out"`; otherwise `"needs-attention"`.
  Neither outcome qualifies real data or measures performance, transfer or safety.
- `summary`: integer `requiredStrata`, `declaredStrata`, `missingStrata`, `unknownStrata`,
  `belowMinimumStrata`, `coveredDeclaredStrata`. The last four are disjoint and sum to required.
- `strata`: one record for each required pair, in canonical weather order
  `clear, rain, fog, snow`, then occlusion `none, partial, heavy` (only requested values).
  Each has exactly `{weather, occlusion, syntheticSamples, realSamples, status}`.
  Status precedence: `missing` (both output counts null), `unknown` (any null),
  `below-minimum` (known deficient count), then `covered-declared`.
- `findings`: global split finding first, then canonical cells and synthetic before real.
  Global records have only `{code}`: `real-split-unknown`, `real-split-training-overlap`.
  Cell records have exactly `{code, weather, occlusion}`: `missing-stratum`,
  `synthetic-count-unknown`, `real-count-unknown`, `synthetic-below-minimum`, `real-below-minimum`.
  A cell with one unknown and another deficient count reports **both** findings, while counted
  once in `unknownStrata`. Missing cells report only `missing-stratum`, not invented count findings.
- `boundary`: exactly `fictional: true`, `countsUserDeclared: true`, `realDataInspected: false`,
  `mlPerformanceMeasured: false`, `simToRealTransferVerified: false`, `safetyValidated: false`,
  `providerExecuted: false`.

## Invented example and checks

`examples/fictional-coverage.json` gives a four-cell loading-bay plan: one declared-covered,
one unknown, one below-minimum and one missing cell. It returns `needs-attention`; findings
in order are `real-count-unknown`, `real-below-minimum`, `missing-stratum`. The held-out split
is merely asserted by the fictional input; no samples or split provenance have been inspected.

Run `node --test tests/pet-scailab.test.mjs` from repository root. Ten deterministic tests
cover required intersections, missing/unknown/zero semantics, inclusive thresholds,
synthetic-versus-real separation, held-out declarations, bounded closed input and determinism.
The six original companion evaluation cases remain unchanged and are not live-model runs.
