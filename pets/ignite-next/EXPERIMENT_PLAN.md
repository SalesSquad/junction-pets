# Invented risky-assumption experiment card

`reviewExperimentPlan(jsonText)` in `experiment-plan.mjs` checks a small proposed
experiment using explicitly fictional declarations. It links a risky assumption
to a metric, separate success/stop rules, a planned sample and resource ceilings.
It never runs an experiment, contacts a customer, authenticates evidence, chooses
a statistically sufficient sample, establishes causality or validates a market.
This is independent companion source, not an Ignite Next product or endorsement.

## Closed input contract

Pass a primitive JSON string of at most 32,768 UTF-8 bytes. All keys below are
mandatory and exclusive. Unknown fields, malformed values and missing fields
return `invalid`, a single `malformed-or-unsupported-plan` issue and null `card`.
Ordinary `JSON.parse` semantics apply: duplicate member names use the final value.
This is not a canonical JSON/signature verifier. Executable objects and boxed
strings are rejected without coercion or input hooks.

| Object | Fields and bounds |
| --- | --- |
| Root | `schemaVersion:1`, `kind:"invented-experiment-plan"`, `assumption`, `metric`, `budget`, `customerEvidence` |
| Assumption | `id`, `category` (`technical`, `customer` or `delivery`), `statement`, `customerEvidenceIds` (0–16 unique declared evidence IDs) |
| Metric | `id`, `unit` (`count`, `ratio`, `ms`), `baseline`, `success`, `stop`, `sampleSize` |
| Rule | Null, or exactly `operator` (`at-least` / `at-most`) and `value` in the metric's domain |
| Budget | `maxHours` (null or 0–168), `maxCredits` (null or 0–10,000 fictional resource credits, not money) |
| Evidence | Array of 0–16 records, each with unique `id`, `kind` and `statement` |

IDs use 1–48 lowercase ASCII letters/digits/hyphens, starting with a letter.
Statements use 1–240 UTF-16 code units, no surrounding whitespace or ASCII control
characters. Text is unverified supplied content, never an instruction or proof.
Evidence kinds are exactly `invented-interview`, `invented-observation` and
`invented-commitment`; none represents an actual interview, measurement or sale.
Dangling or duplicate evidence links are invalid. Unlinked evidence is not
included in the output card and cannot satisfy its customer-evidence requirement.

Metric values are finite nonnegative numbers: `count` requires integers through
1,000,000; `ratio` is 0–1; `ms` is 0–1,000,000,000. The baseline may be null
(unknown) or a value in that domain. Baseline zero is known zero, not missing.
Sample size is null or an integer 0–10,000. Budget ceilings allow finite fractions;
zero credits is a valid no-credit plan, not proof of a free real service.
Omitting any nullable field is invalid rather than silently supplying a default.

## Review rules and output

Success and stop thresholds must have opposite directions and a strictly
separating undecided interval: success at least `s` requires stop at most `t`
with `s > t`; success at most `s` requires stop at least `t` with `s < t`.
Equality, overlap and equal directions produce `overlapping-or-unseparated-rules`.
This is a transparent planning convention, not statistical inference. Values
between thresholds would be inconclusive under the proposal; no observed value
is accepted or classified by this helper.

Explicit null fields produce `unknown-baseline`, `unknown-success`,
`unknown-stop`, `unknown-sample-size`, `unknown-maxHours` or
`unknown-maxCredits`. Sample size zero produces `no-planned-observations`;
zero hours produces `no-effort-budget`. No evidence links produces
`no-linked-customer-evidence`. Valid plans with any issue return `needs-review`.
Otherwise the status is `ready-for-review`, **not ready to execute or validated**.
Issues and linked evidence IDs are sorted; returned objects are fresh per call.

The card preserves the declared metric, baseline, sample size, ceilings and linked
fictional statements, with `evidenceAuthenticity:"not-verified"` and a review
proposal. Every result, including invalid input, has `basis:"invented-declarations"`
and false `experimentPerformed`, `marketValidationEstablished`,
`hypothesisProven` and `authorization` flags. A coherent card cannot establish
representative customer demand, success, funding, minimum cost, safe execution
or an official challenge requirement. No network, provider or account is used.

## Reproduce the fictional example

`example.json` returns `ready-for-review`: its declared rules are separated,
customer-note link exists, ten observations are proposed and effort is capped.
All values, including its baseline and interview note, are invented.

```sh
node --input-type=module -e 'import {readFileSync} from "node:fs"; import {reviewExperimentPlan} from "./pets/ignite-next/experiment-plan.mjs"; console.log(JSON.stringify(reviewExperimentPlan(readFileSync("pets/ignite-next/example.json", "utf8")), null, 2));'
node --test tests/pet-ignite-next.test.mjs
```

The helper and tests are separate source-only artifacts. Generated companion
plugins remain skills-only; no tool endpoint is added. The six original
`evals.json` cases remain authored definitions, not executed model evaluations.
Next: extend a separately reviewed fictional case with contradictory customer
notes before considering any independently authorized real experiment.
