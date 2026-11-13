# Fictional GPU run planning card

`reviewGpuRunPlan(jsonText)` from `gpu-run-plan.mjs` is a pure offline consistency
checker. It neither connects to Verda nor provisions, schedules, executes or
charges a run. All quantities, capacities, credits, limits and owner IDs are
invented declarations. This source helper is not automatically installed as a
runtime plugin tool.

## Exact input v1

Input is primitive JSON text, at most **12,288 UTF-8 bytes**. Objects have exactly
the listed required keys. Omitted or extra keys, malformed JSON, invalid enums
and numbers throw `TypeError`; nothing is coerced or silently defaulted. Ordinary
`JSON.parse` semantics apply: the last parsed value wins for duplicate JSON
member names. This is not a duplicate-member detector, signed format or
canonicalization protocol.

| Object | Required fields |
| --- | --- |
| Root | `schemaVersion: 1`, `kind: "fictional-gpu-run-plan"`, `runId: ID`, `mode: "plan-only"`, `resources`, `limits`, `execution`, `credits` |
| `resources` | `gpuCount: 1..64|null`, `cpuCount: 1..256|null`, `memoryGiB: 1..4096|null` |
| `limits` | `gpuCount: 0..64|null`, `cpuCount: 0..256|null`, `memoryGiB: 0..4096|null`, `wallTimeSeconds: 0..604800|null` |
| `execution` | `timeoutSeconds: 1..86400|null`, `maxRetries: 0..8|null`, `retryBackoffSeconds: 0..3600|null`, `shutdownOwnerId: ID|null`, `stopCondition: "timeout-or-complete"|null` |
| `credits` | `unit: "fictional-credit"`, `perAttemptCeiling: 0..1000000|null`, `available: 0..100000000|null` |

Ranges are inclusive integers. Negative zero, fractions, strings, non-finite
numbers and out-of-domain values are invalid. `null` means unknown, not zero.
An **ID** matches `^fictional-[a-z0-9]+(?:-[a-z0-9]+)*$` and has at most 64 ASCII
characters. IDs are invented opaque labels, not account or identity proof.
Requests for `execute` or claimed authorization fields are rejected. Real
currency, advertised event grants and actual account balances are out of scope.

The checked-in [example](examples/fictional-gpu-run.json) is entirely invented.

## Model and arithmetic

The declared model is **one serial run**, with an initial attempt and up to
`maxRetries` retries. Each attempt may consume its entire timeout and entire
fictional credit ceiling; retries use constant backoff. There is no overlap,
parallelism or real scheduler. The timer model has no startup/shutdown overhead:
real systems need separate measurements and enforcement. GPU seconds exclude
backoff, when this fictional model assumes no GPU work.

- `attempts = maxRetries + 1`
- `computeSeconds = attempts × timeoutSeconds`
- `wallTimeSeconds = computeSeconds + maxRetries × retryBackoffSeconds`
- `gpuSeconds = computeSeconds × gpuCount`
- `worstCaseFictionalCredits = attempts × perAttemptCeiling`
- `remainingFictionalCredits = available − worstCaseFictionalCredits`

Any unknown operand yields `null` for its derived field. Even zero retries do
not silently fill an unknown backoff declaration; duration remains unknown.
Credits do not depend on measured runtime or device count: the input ceiling
claims to cover the entire attempt and is never independently authenticated.
A negative remaining amount is retained as evidence of an over-budget plan.
All permitted arithmetic remains exactly representable as safe integers.

## Deterministic findings

Findings are `{code, field}` in this order: resource requests/limits in GPU, CPU,
memory order; unknown timing fields; owner/stop declarations; wall time; credits.
Multiple issues remain visible.

| Condition | Codes |
| --- | --- |
| Unknown resource or limit | `unknown-<resource>`, `unknown-<resource>-limit`, where resource is `gpuCount`, `cpuCount` or `memoryGiB` |
| Resource above its known limit | `<resource>-exceeds-limit` |
| Unknown timing input | `unknown-timeoutSeconds`, `unknown-maxRetries`, `unknown-retryBackoffSeconds` |
| Unknown shutdown owner or stop condition | `unknown-shutdown-owner`, `unknown-stop-condition` |
| Unknown wall limit or duration above it | `unknown-wall-time-limit`, `wall-time-exceeds-limit` |
| Unknown credit ceiling or available amount | `unknown-attempt-credit-ceiling`, `unknown-available-credits` |
| Negative remaining fictional credits | `fictional-credits-exceed-available` |

The result has exactly `schemaVersion: 1`, `kind: "fictional-gpu-plan-card"`,
`status`, `findings`, `summary` and `boundary`. `status` is
`consistent-declarations` only with no findings; otherwise `needs-review`.
`summary` has `runId` and the six derived quantities above, each number or null.

The boundary is always:

```json
{
  "synthetic": true,
  "capacityVerified": false,
  "creditsVerified": false,
  "executionAuthorized": false,
  "executionStarted": false,
  "spendIncurred": false
}
```

**Consistency is not approval or a guarantee.** This helper has no provider,
network, file, account, credential, timer or GPU side effects. It cannot prove
capacity, redeem credits, enforce timeout, stop a machine or establish actual
cost/safety. Any real execution needs a separately authorized host with current
source-bound account, quota, credit and shutdown evidence.

## Verification

Run `node --test tests/pet-verda.test.mjs`. Twelve deterministic source tests
cover the model, unknown/zero distinctions, bounds and refusal behavior. The six
original Verda behavior-evaluation definitions are preserved; they are authored
cases, not executed model tests or provider receipts.
