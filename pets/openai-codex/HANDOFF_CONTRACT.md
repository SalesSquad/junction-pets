# Synthetic coding-task handoff consistency — v1

`handoff.mjs` exports `verifySyntheticHandoff(text)` for an **invented, offline**
coding-task/PR handoff. This repository-defined contract is not an OpenAI API or
Codex provider feature. It does not read a repository, execute command text,
open a PR, authenticate a reviewer/log, or issue a permission. The example's
repository, identities, SHA values, digest and test counts are all fictional.

The function accepts a string of at most **32,768 UTF-8 bytes**, then uses ordinary
`JSON.parse` (duplicate JSON object keys take their last value; this is not a
canonical/signature parser). Every object has exactly the fields below, with
no extra properties. Wrong types, omitted fields, unsupported versions,
duplicates in ID/path arrays, and invalid limits throw `TypeError`. There are
no defaults or number coercions. Null is allowed only where explicitly stated.

## Exact input

| Object / field | Type and limit |
| --- | --- |
| Root `schemaVersion`, `kind` | Exactly `1`, `"synthetic-coding-handoff"` |
| `repository` | `fictional/` followed by 1–64 lowercase letters/digits/hyphens, beginning with a letter/digit |
| `workId`, `authorId` | Fictional label: `fictional-` + 1–80 lowercase letters/digits/dots/hyphens, beginning with a letter/digit |
| `headSha` | Exact 40 lowercase hex characters; symbolic refs and abbreviated SHAs are invalid |
| `ownedPaths` | 1–32 unique relative paths; trailing `/` means a directory prefix, otherwise an exact file |
| `changedPaths` | 1–64 unique relative file paths; trailing `/` forbidden |
| Path syntax | At most 240 ASCII characters; segments contain letters/digits/underscore/dot/hyphen; no empty, `.` or `..` segments, absolute paths or backslashes |
| `acceptance` | 1–16 objects, each exactly `{id, command}`; unique `id`: 1–80 lowercase letters/digits/hyphens, beginning with letter/digit |
| `command` | Inert nonblank string of at most 512 JavaScript code units; ASCII controls forbidden; equality is exact, without normalization or execution |
| `receipts` | 0–16 objects, one at most per requested acceptance `id`; unknown or duplicate `checkId` throws |
| Each receipt | Exactly `{checkId, headSha, command, exitCode, tests, originalLog}`; ID/SHA/command syntax as above |
| Receipt `exitCode` | Integer 0–255 or explicit `null` (unknown) |
| Receipt `tests` | Exactly `{passed, failed}`; each integer 0–1,000,000 or explicit `null` (unknown). Skipped tests are not included in these counts |
| Receipt `originalLog` | `null` (not supplied), or exactly `{label, sha256}`: fictional label and 64 lowercase hex digest |
| `review` | `null` (no review), or exactly `{reviewerId, headSha, verdict}`; fictional identity, exact SHA, and `approved`, `changes-requested` or `unknown` |

`originalLog` is a **declaration about an original log**, not the log bytes or a
signature. Neither that declaration nor its digest is authenticated. The
receipt's original SHA must match the requested HEAD; a stale receipt is never
rewritten or silently reused. Identity labels differing only proves different
strings, not independent people. Filesystem existence, symlinks and Git changes
are not inspected. Ownership is compared lexically, so `src/` does not cover
`src-extra/`, and `test.mjs` does not cover `test.mjs.bak`.

## Exact output and decision

Returns `{schemaVersion:1, kind:"synthetic-handoff-report", repository, workId,
headSha, status, findings, boundary}`. `status` is `consistent-declarations` only
if no findings exist, otherwise `needs-review`. This is **not** an execution,
CI, review approval, merge-readiness or security qualification.

Each finding is exactly `{code, subject}`. Findings occur deterministically in
changed-path order, then acceptance order, then review order:

1. `out-of-scope-path` (subject = changed path).
2. `missing-receipt`, or for each present receipt: `receipt-source-mismatch`,
   `receipt-command-mismatch`, `unknown-check-result`, `failed-check`,
   `no-tests-executed`, `missing-original-log` (subject = acceptance ID).
3. `missing-review`, or `self-review`, `review-source-mismatch`,
   `review-not-approved` (subject = `review`).

A nonzero exit or positive failed count produces `failed-check`, even if other
fields are unknown. Null results produce `unknown-check-result`. **Zero passed
and zero failed is no test execution**, never a successful test. A missing
receipt is different from explicit null result fields, and both differ from
zero. Consistency requires an exit of 0, positive passed count, zero failed
count, original-log declaration, exact source/command matches, all paths in
scope, and a distinct reviewer declaring approval on the same HEAD.

`boundary` is always exactly `{synthetic:true, receiptAuthenticated:false,
ciVerified:false, mergeAuthorized:false, codingPermissionGranted:false}`.
Unsupported fields such as tokens, grants, provider outcomes or `ciVerified`
are rejected; even a perfectly consistent payload cannot authorize anything.

## Invented example and tests

[`example-handoff.json`](example-handoff.json) is a complete small input and
returns `consistent-declarations` with an empty findings array and all the
authority booleans above still false. Run the deterministic source checks with
`node --test tests/pet-openai-codex.test.mjs` from the repository root. These
source tests are separate from the six unchanged authored model evals in
`evals.json`; neither the module nor its example activates an OpenAI tool.
