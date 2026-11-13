# Invented multimodal evaluation plan checker

`checkEvaluationPlan(jsonText)` in `evaluation-plan.mjs` checks a small, invented
scene-record plan offline. It detects declared training/held-out group overlap,
counts planned coverage and keeps every capability explicitly **untested**.
It does not read images, audio or video; train or call a model; authenticate
provenance; assess answers; calculate accuracy; or authorize real evaluation.
This is independent companion source, not a Google DeepMind tool or endorsement.

## Exact input contract

Pass a primitive JSON string of 1–65,536 UTF-16 code units. Parsing uses ordinary
`JSON.parse` with no reviver: duplicate object member names retain the **last**
value, escape sequences are decoded, and numeric values use JavaScript numbers.
This checker does not detect duplicate raw member names or authenticate the text.
Objects, boxed strings and executable input hooks are not accepted or coerced.
Malformed JSON, unsupported fields/types and out-of-bounds values are `invalid`.

All fields below are mandatory and exclusive at their level. See `example.json`
for a complete invented input, containing two held-out visual groups and no
planned sound-cue records. No real dataset, model, training run or result is used.

| Object | Required fields and bounds |
| --- | --- |
| Root | `schemaVersion: 1`, `kind: "invented-evaluation-plan"`, `capabilities` (1–32), `records` (0–200) |
| Capability | Unique `id`, `requiredModalities` (1–4 unique modality names), `minHeldOutGroups` (integer 0–200 or null) |
| Record | Unique `id`, `sourceId`, `sceneId`, `split`, `modalities`, `capabilityIds` (1–32 unique declared capability IDs) |

IDs are 1–48 lowercase ASCII letters/digits/hyphens, starting with a letter;
the exact ID `unknown` is reserved and rejected. Source and scene IDs may instead
be null, meaning unknown provenance. They occupy separate namespaces and compare
by exact equality. These are supplied grouping labels, not content hashes.
Renamed aliases, false labels, undeclared duplicates and actual model-training
contamination cannot be discovered from this invented plan.

Modalities are exactly `text`, `image`, `audio`, `video`. A record's `modalities`
is a unique array of 0–4 names, or null. `[]` means known missing inputs; null
means unknown inputs; omission is invalid. The split is exactly `training`,
`held-out` or `unknown`. These labels describe proposed roles, not actual runs.
Capability targets distinguish zero (not requested), null (unknown target),
positive integers (requested independent groups) and omission (invalid).
No `results`, `accuracy`, `model`, training attestations or other extra fields
are accepted, including nested claims. Free-text assertions are not an input.

## Grouping, leakage and coverage

Records are grouped by the transitive closure of equal non-null source IDs **or**
equal non-null scene IDs, even across different capability tags and modalities.
Thus a source-sharing record can connect two scene groups. A group containing
both training and held-out labels is leakage, including when an unknown-split
bridge connects them. Each leakage report names its lexically smallest record ID
as `groupId`, all `recordIds`, `trainingRecordIds` and `heldOutRecordIds`.

A group supplies eligible held-out coverage only when every member has known
source and scene IDs and is labeled held-out. Training, unknown-split and
unknown-provenance members exclude the entire group. For each capability, at
least one tagged member must declare **all** required modalities in that same
record. Separate incomplete records do not combine into a multimodal input.
An eligible group counts once per capability, regardless of the number of copies
or scenes it contains. This conservative grouping is a planning rule, not a
claim of statistical independence or sufficient evaluation power.

Each coverage row reports the capability ID, target, three declared split-record
counts, eligible held-out group count, `planCoverage`, and `evaluationStatus`.
`planCoverage` is `unknown-target` for null, `not-requested` for zero, `uncovered`
for a positive target with zero eligible groups, `insufficient` below a positive
target, or `covered` when that target is met. `covered` means **planned inputs**,
never observed capability. `evaluationStatus` is always `not-run`, and
`untestedCapabilities` always lists every declared capability for valid input.

Valid plans return `consistent-plan` only with no issues; otherwise `needs-review`.
Issues are sorted unique strings: `leakage:<groupId>`, `unknown-split:<recordId>`,
`unknown-provenance:<recordId>`, `unknown-modalities:<recordId>`,
`missing-modalities:<recordId>:<capabilityId>` and
`coverage:<capabilityId>:<planCoverage>` for non-covered targets. Missing modalities
on a training record are also flagged. Malformed input returns `invalid`, one
`malformed-or-unsupported-plan` issue, null `declaredSplits`, and empty lists.
Null/unknown fields therefore remain reviewable; malformed/missing fields do not
produce partial calculations. IDs, coverage rows and groups are sorted, making
output independent of input ordering. Each call returns fresh output objects.

All results contain `basis: "invented-declarations"`,
`grouping: "transitive-source-or-scene"` and false `trainingPerformed`,
`actualEvaluationPerformed`, `modelPerformanceVerified`, `authorization` flags.
There is no performance result or execution permission, even for a consistent
plan. The six existing `evals.json` cases remain separate authored definitions.

## Try the invented example

```sh
node --input-type=module -e 'import {readFileSync} from "node:fs"; import {checkEvaluationPlan} from "./pets/google-deepmind/evaluation-plan.mjs"; console.log(JSON.stringify(checkEvaluationPlan(readFileSync("pets/google-deepmind/example.json", "utf8")), null, 2));'
node --test tests/pet-google-deepmind.test.mjs
```

The example yields `needs-review`: visual grounding has two eligible groups,
while sound-cue coverage is zero; both capabilities remain untested. Next, add
invented missing/contradictory-input cases and review the grouping labels before
separately authorizing any real dataset, model, evaluator or provider work.
