# Fictional compute job specification review

`reviewJobSpec(jsonText)` from `job-spec.mjs` is a pure, dependency-free local
consistency checker. It does not call Modal, execute code, acquire capacity,
approve spending, inspect inputs, authenticate facts or enforce limits at runtime.
The invented example is `examples/fictional-job.json`. All values in it are made
up, including the digest-shaped strings and credits; they are not provider facts.

## Exact input

The sole argument is a primitive JSON string of at most **16,384 UTF-8 bytes**.
Ordinary `JSON.parse` behavior applies: a duplicate object member uses its last
value. This is not a canonical JSON, signature or duplicate-key security parser.
Malformed input, missing/extra keys, wrong types and out-of-domain values throw
`TypeError`. Objects are closed at every level. No executable objects are accepted.

All of these root members are required:

| Member | Exact domain |
| --- | --- |
| `schemaVersion` | `1` |
| `scenario` | `"fictional"` |
| `jobId` | String matching `[a-z0-9][a-z0-9._-]{0,63}` |
| `items` | 1–64 records, exactly `id` and `inputSha256`; IDs follow the same pattern and are unique; digests are exactly 64 lowercase hex characters |
| `retry` | Exactly `maxRetries`, `maxAttempts`, `keyPolicy`; retries integer 0–1000, attempts integer 1–1001; policy `"stable-per-item"`, `"per-attempt"` or explicit `null` |
| `resources` | Exactly the five integers in the table below |
| `ceilings` | Exactly the same five fields; each integer in the same domain or explicit `null` for unknown |
| `budget` | Exactly `unit: "fictional-credit"`, `creditsPerAttempt` (integer 0–1,000,000 or null), `maxCredits` (integer 0–1,000,000,000 or null) |

| Resource field | Accepted integer domain | Meaning |
| --- | --- | --- |
| `timeoutSeconds` | 1–86,400 | Declared maximum duration per attempt |
| `cpuUnits` | 1–256 | Requested CPU units per attempt |
| `memoryMiB` | 1–65,536 | Requested memory per attempt |
| `gpuUnits` | 0–16 | Requested GPU units per attempt; zero is meaningful |
| `parallelism` | 1–64 | Requested simultaneous attempts |

These parser bounds and the review ceiling of **8 retries / 9 attempts per
item** are local fictional policy, not Modal limits. No negative zero,
fractional/non-finite number, implicit default or real currency is accepted.
Unknown desired resources/retry counts are malformed; explicit unknown declared
capacity, budget or key policy is accepted but always requires review.

## Exact output and accounting

Output has `schemaVersion: 1`, `kind: "fictional-job-spec-review"`, the supplied
`jobId`, `verdict`, `findings`, `bounds`, `identities`, and three booleans permanently
false: `executionVerified`, `providerConnected`, `spendAuthorized`.

`verdict` is `"within-declared-bounds"` only when no findings exist; otherwise
`"needs-review"`. Neither verdict is approval, safety qualification or proof of
actual capacity, billing, runtime enforcement or exactly-once execution.

`bounds` contains exactly:

- `items`: manifest length.
- `attemptsPerItem`: `max(maxRetries + 1, maxAttempts)`, deliberately conservative
  when declarations disagree; an inconsistency still produces a finding.
- `totalAttempts`: items × attempts per item, assuming every item uses all attempts.
- `aggregateAttemptSeconds`: total attempts × timeout, an aggregate duration of
  attempts, **not elapsed/wall-clock time**, scheduling or backoff prediction.
- `fictionalCredits`: total attempts × declared credits per attempt, or `null`
  when attempt cost is unknown. This assumes the stated per-attempt cost covers
  the complete attempt. It does not model storage, egress, billing or real pricing.

Findings are records `{code, field}` in deterministic order: retry checks,
resource checks in the table order, then budget checks. Codes are
`retry-ceiling-exceeded`, `attempt-count-mismatch`, `unknown-retry-key-policy`,
`unstable-retry-key`, `unknown-capacity`, `resource-ceiling-exceeded`,
`unknown-attempt-cost`, `unknown-budget`, `fictional-budget-exceeded`.
Retry-ceiling findings use `field: "retry"`; count mismatch uses
`retry.maxAttempts`; key findings use `retry.keyPolicy`. Unknown resource fields
use `ceilings.<name>`, exceeded fields `resources.<name>`, unknown attempt cost
uses `budget.creditsPerAttempt`, and budget findings `budget.maxCredits`.

`identities` contains `{itemId, key}` for every item, sorted by ascending ASCII
item ID. `key` is the JSON encoding of
`["junction.modal.job.v1", jobId, itemId, inputSha256]`. It is a **candidate**
stable retry identity, independent of attempt number, retry count or manifest
order. Changing job/item/input identity changes it. It is not a secret, hash of
verified input, authorization token or proof of implemented deduplication. The
caller must scope identities and enforce idempotency in any separately
authorized implementation. `per-attempt` or unknown policy is still flagged.

The example yields 6 attempts, 360 aggregate attempt-seconds and **30 fictional
credits**, no findings, and two proposed identities. It has never run a job.

## Verify this source

Run `node --test tests/pet-modal.test.mjs`. The ten tests cover exact accounting,
identity stability/revision changes, retry runaway/mismatch, unknown capacity and
budget, all resource ceilings, zero-versus-unknown, malformed data, manifest
boundaries and ordinary JSON semantics. Six authored persona evals remain
unchanged and are not live model eval executions.
