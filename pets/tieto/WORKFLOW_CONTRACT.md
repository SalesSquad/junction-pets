# Fictional workflow handoff review

`reviewWorkflow(jsonText)` in [workflow-review.mjs](workflow-review.mjs) is a pure
Node helper, not a Tieto API, workflow runner or Chibi tool binding. It checks
only an invented caller declaration and returns a responsibility map and issues.
It does not authenticate actors, approve transfers, contact systems or execute
retries. It does not claim to implement an unpublished Junction challenge.

## Input contract

Use the complete [invented example](examples/workflow.json). Input is JSON text
of at most 65,536 UTF-8 bytes (also at most 65,536 UTF-16 code units), parsed with
ordinary `JSON.parse`: duplicate JSON keys use the last value. Objects must have
exactly the listed fields; omitted fields, unknown keys, malformed values and
duplicate identifiers/references throw `TypeError` without echoing the input.
Arbitrary JavaScript objects, getters and executable hooks are not accepted.

- Root: `schemaVersion:1`, `fictional:true`, `workflowId`, `actors`, `systems`,
  `steps`, `transfers`.
- Every identifier is a maximum-64-character lowercase ASCII label matching
  `fictional-[a-z0-9]+(-[a-z0-9]+)*`. This is an input convention, **not proof**
  that a caller's data is anonymous, invented or permitted to be processed.
- `actors` and `systems`: 1–16 unique labels each. `steps`: 1–16 unique step IDs;
  `transfers`: 0–32 unique transfer IDs.
- Step fields: `id`, `system`, `responsible`, `accountable`, `consulted`,
  `informed`, `failureOwner`, `retry`, `handoffs`. The three plural RACI roles
  are unique lists of 0–16 actor labels. Accountable and failure owner are one
  actor label or explicit `null` for unknown. A person may occupy several roles;
  the helper does not prove organizational independence or actual authority.
- Retry fields: `maxRetries` (integer 0–3 or `null`), `timeoutSeconds` (integer
  1–3600 or `null`), `idempotent` (boolean or `null`). Zero retries means no retry;
  null is unknown, never a default. Positive retries require declared
  idempotency. These are per-step declarations, not proof that retries occurred,
  are safe or guarantee whole-workflow termination. Graph cycles and runtime
  scheduling are outside this static check.
- Handoffs: 0–16 records per step, unique by `toStep`; fields `toStep` and
  `transferId` (label or `null`). Null means a **declared no-data control handoff**
  inside one system only. A cross-system handoff must identify a transfer. A
  same-system handoff carrying data must also identify a transfer. Undeclared
  out-of-band activity or concealed real data cannot be detected from this JSON.
- Transfer fields: `id`, `fromStep`, `toStep`, `dataCategories` (1–16 unique
  fictional labels), `approval` (`declared-approved`, `denied` or `unknown`),
  `approver` (actor label or `null`). Each transfer must be referenced once by
  a handoff with exactly matching source and target. Caller-declared approval
  and a registered actor are **not verified permission**.

## Output contract

Returns `schemaVersion:1`, `workflowId`, `status`, `issues`, `responsibilityMap`
and `boundary`. Map rows contain `stepId`, `system`, the four RACI fields and
`failureOwner`. Issues contain a fictional `scope`, stable `code` and severity
`blocked` or `unknown`. Input order defines deterministic issue/map order.

`blocked` dominates without erasing unresolved issues. Blocks include an empty
responsible role, unregistered actor/system, unknown step/transfer endpoint,
self-handoff, undeclared cross-system transfer, missing/reused/mismatched/unused
transfer, denied transfer, unregistered approver and repeated non-idempotent
work. Explicit null owners, retry/timeout/idempotency uncertainties and unknown
transfer approval yield `needs-clarification` in the absence of a block.
`declared-consistent` means only that the supplied declaration met these rules.

The boundary is constant: `fictionalOnly:true`, `executionAuthorized:false`,
`transferAuthorized:false`, `executed:false`. No status grants permission. Use
trusted host consent and authorization for real operations; no credentials,
customer data, free-form process text or real system identifiers belong here.

The package's six original authored model-evaluation cases remain unchanged.
Focused helper checks are separate and do not certify a model, host, customer
workflow, deployment, compliance or company endorsement.
