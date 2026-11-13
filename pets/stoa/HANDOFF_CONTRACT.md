# Fictional construction-document revision and handoff proof

`reviewHandoff(jsonText)` from `handoff-proof.mjs` is a pure, offline checker of
invented declarations. It does not read BIM geometry, drawings, construction
documents or live Stoa systems. There are no files, network calls, providers,
credentials, dependencies or side effects in the helper.

## Input v1

Pass a primitive JSON string, at most **12,288 UTF-8 bytes**. All objects below
have exactly the listed required keys. Missing and extra keys, malformed JSON,
unknown enum values and invalid types throw `TypeError`; none are coerced or
defaulted. Ordinary `JSON.parse` semantics apply, including **last parsed value
wins** for duplicate JSON object member names. This is not a duplicate-member
detector or a signature/canonicalization protocol.

| Record | Exact keys and values |
| --- | --- |
| Input | `schemaVersion: 1`, `kind: "fictional-document-handoff"`, `document`, `handoff`, `acceptance` |
| `document` | `documentId: ID`, `currentRevision: Revision`, `owners: null` or an array of 0–8 IDs |
| `handoff` | `null`, or `{documentId: ID|null, revision: Revision, fromOwnerId: ID|null, recipientId: ID|null}` |
| `acceptance` | `null`, or `{documentId: ID|null, revision: Revision, recipientId: ID|null, state: null|"accepted"|"pending"|"rejected"|"unknown"}` |

- **ID:** at most 64 ASCII characters, matching
  `^fictional-[a-z0-9]+(?:-[a-z0-9]+)*$`. IDs are opaque invented labels, not
  URLs, real customer/person identifiers or proof of identity.
- **Revision:** `null` (unknown), or an integer 0–999999. Zero is a valid explicit
  revision; negative zero, fractions, strings, infinity and overflow are invalid.
- An empty owners array means no owner was declared; `null` means ownership is
  unknown. Multiple distinct IDs conflict. Repeating an ID is a duplicate owner
  finding, not a means of satisfying single ownership.
- The example [`examples/fictional-handoff.json`](examples/fictional-handoff.json)
  is invented coordination-model metadata, not an imported BIM file.

## Checks and deterministic findings

Every finding is `{code: string, field: string}`. Findings appear in this order:
document revision, ownership, handoff identity/revision/sender/recipient, then
acceptance identity/revision/recipient/state. Multiple independent issues are
retained; no accepted label overrides a contradiction or missing declaration.

| Check | Finding codes |
| --- | --- |
| Current revision unknown | `unknown-current-revision` |
| Owner array unknown, empty, repeated or conflicting | `unknown-owners`, `missing-owner`, `duplicate-owner`, `conflicting-owners` |
| Handoff absent | `missing-handoff` |
| Handoff document unknown or different | `unknown-handoff-document`, `handoff-document-mismatch` |
| Handoff revision unknown, older or newer than declared current | `unknown-handoff-revision`, `stale-revision`, `unrecognized-revision` |
| Sender unknown or different from the sole declared owner | `unknown-sender`, `sender-owner-mismatch` |
| Recipient unknown or equal to sender | `unknown-recipient`, `self-handoff` |
| Acceptance absent | `missing-acceptance` |
| Acceptance document unknown or different | `unknown-acceptance-document`, `acceptance-document-mismatch` |
| Acceptance revision unknown or different from handoff revision | `unknown-acceptance-revision`, `acceptance-revision-mismatch` |
| Acceptance recipient unknown or different from handoff recipient | `unknown-acceptance-recipient`, `acceptance-recipient-mismatch` |
| Acceptance state not accepted | `unknown-acceptance`, `pending-acceptance`, `rejected-acceptance` |

Document comparisons bind both handoff and acceptance to `document.documentId`.
Revision ordering is meaningful only within these invented numeric labels; a
newer submitted number is not automatically authoritative. Owner comparison
requires exactly one array entry. Acceptance revision/recipient comparisons run
only when the corresponding handoff value is known; the missing/unknown handoff
finding already prevents consistency. These semantics cannot prove currentness
against an external source, authenticity of acceptance or ownership.

## Output v1

The returned object has exactly:

```json
{
  "schemaVersion": 1,
  "kind": "fictional-handoff-proof",
  "status": "consistent-declarations",
  "findings": [],
  "summary": {
    "documentId": "fictional-coordination-model",
    "currentRevision": 4,
    "submittedRevision": 4,
    "ownerDeclarations": 1,
    "acceptanceDeclaration": "accepted"
  },
  "boundary": {
    "synthetic": true,
    "documentInspected": false,
    "ownershipVerified": false,
    "acceptanceVerified": false,
    "siteActionAuthorized": false
  }
}
```

`status` is `consistent-declarations` exactly when there are no findings;
otherwise it is `needs-review`. `summary.documentId` and `currentRevision` echo
their declared fields. `submittedRevision` is the handoff revision or `null`;
`ownerDeclarations` is the array length (including duplicates) or `null`;
`acceptanceDeclaration` is `missing` for a null record, `unknown` for a null
state, otherwise the declared state. Boundary flags are constant.

**Consistent is never approved:** no document inspection, verified owner,
verified acceptance, construction-safety certification, site authorization,
deployment or actual handoff is established. The next real-world step is a
separately authorized human document-owner review against authoritative project
records. No such data or action is part of this source slice.

## Reproducible source checks

Run `node --test tests/pet-stoa.test.mjs` from the repository root. Twelve
deterministic boundary tests exercise this helper; six existing authored Stoa
behavior eval cases remain unchanged and are **not** executed model tests.
