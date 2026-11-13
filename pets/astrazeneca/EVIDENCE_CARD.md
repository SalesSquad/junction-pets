# Fictional evidence-card structure proof

This source-only helper checks the **declared structure** of a fictional aggregate
simulation card. It does not appraise real research, authenticate a source, verify a
claim, grant permission, establish privacy or clinical validity, or recommend any
action. It is independently authored, not AstraZeneca research or an endorsement.
No real study, patient data, medical fact, treatment advice, provider call or model
evaluation is included. The six authored behavior-eval cases remain separate.

## Run the supplied fictional example

From the repository root, with Node 22+:

```sh
node --input-type=module -e 'import {readFileSync} from "node:fs"; import {checkEvidenceCard} from "./pets/astrazeneca/evidence-card.mjs"; console.log(JSON.stringify(checkEvidenceCard(readFileSync("pets/astrazeneca/fictional-evidence-card.json", "utf8")), null, 2));'
node --test tests/pet-astrazeneca.test.mjs
```

`checkEvidenceCard(jsonText)` is pure and performs no I/O. The caller supplies only
JSON text; objects/getters are never evaluated. The result has `scope:
"fictional-structure-only"`, a `structuralStatus`, bounded structural findings,
an explicit notice and four always-false validation flags. Findings do not echo
input values or unknown field names.

| Structural status | Meaning only |
| --- | --- |
| `complete` | The required declarations are present and meet this small fixture contract. |
| `incomplete` | An essential field or explicit limitation is absent. |
| `rejected` | Malformed, out-of-contract, contradictory or unsupported input was supplied. |

None of these statuses is an evidence-quality grade. A fabricated but complete
card stays **unverified**. The result always sets `authorizationGranted`,
`sourceAuthenticated`, `evidenceTruthValidated` and `clinicalValidated` to `false`.
Fictional markers are declarations, not a data-loss-prevention or consent check.
Do not supply real or identifiable records, actual studies, private text or secrets.

## Closed input contract

Use `fictional-evidence-card.json` as the complete example. Every listed object
field is required unless a conditional comparator field says otherwise. Unknown
fields are rejected; there is deliberately no arbitrary claim prose, patient
record field, source URL, retrieval capability or evidence-strength score.

| Declaration | Accepted fixture vocabulary or structural rule |
| --- | --- |
| Markers | `schemaVersion: 1`, `fictional: true`, `dataScope: "aggregate-simulation"`, `sampleUnit: "fictional-record"`. |
| `studyDesign` | `randomized-simulation`, `observational-simulation` or `single-group-simulation`. |
| `sampleSize` | Total fictional records: positive safe integer, at most 1,000,000. This is a fixture bound, not a scientifically sufficient sample threshold. |
| `methods` | `allocation` matches the design: `simulated-random`, `simulated-observed` or `not-applicable`, respectively. `measurement: "fictional-score"`, `analysis: "descriptive-summary"`, and integer `timepoints` from 1 to 20 are required. These are declarations, not an implemented experiment or analysis. |
| `comparator` | Comparison designs require `kind: "simulated-group"` and positive integer `sampleSize` smaller than the total. Single-group design requires `kind: "none"` and `reason: "single-group-design"`, with no comparator sample count. Group and absence declarations cannot be combined. |
| `source` | `kind: "fictional-fixture"` and an `id` matching `fictional-fixture-` followed by lower-case alphanumeric segments separated by single hyphens (at most 64 characters total). It is never fetched or authenticated. |
| `uncertainty` | `scope: "simulation-only"`; `missingness` is `none-declared`, `some-declared` or `not-assessed`. `limitations` contains both `no-real-world-inference` and `source-not-authenticated`, with no duplicates or other entries. |
| `claim` | `kind: "descriptive"` or `"association"`, with `outcome: "fictional-score"`. An association requires a declared comparison group. All causal and efficacy claim types are rejected, including on a randomized-simulation card. Presence of fields cannot substantiate such claims. |

Input is bounded to **8,192 UTF-8 bytes** (inclusive) and six nested containers.
Malformed JSON, duplicate keys (including escaped equivalent spellings), invalid
types, unsupported fields and inconsistent declared counts fail closed. Limits
are exported in `LIMITS`; they are resource/fixture limits, not clinical criteria.

This is intentionally a small first source slice, not a general natural-language
claim checker or a research-assessment system. It does not determine whether a
declared design happened, whether data are honest or anonymous, or whether an
association is statistically meaningful. Source review, genuine study methods,
real evidence interpretation, model behavior and host authorization remain
outside its scope. Generated companion plugins remain skills-only; this module
is not exposed as a live tool, connection or recipient-facing integration.
