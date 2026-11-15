# Earned Trust packet contract v1

One JSON document describes one pinned change. The macOS application is an offline
review desk. It never executes an imported command, calls a model, pushes code or
merges a change. A user decision is a local declaration, not authenticated approval.

```json
{
  "schemaVersion": 1,
  "packetId": "tieto-2283",
  "title": "Metadata generics without generator crashes",
  "generatedAt": "2026-11-15T00:00:00Z",
  "source": {
    "repository": "https://github.com/te-industry-tech-office/junction26-messagepack-csharp",
    "baseSha": "32258fdbee4bcd653c79f51b4376b5103c6f4d27",
    "headSha": "9df83c38409c8bfad0517aebffe48211eda4a5b4",
    "issueId": "2283",
    "issueURL": "https://github.com/MessagePack-CSharp/MessagePack-CSharp/issues/2283",
    "branch": "ju26-issue-2283"
  },
  "requirement": {
    "id": "MP-2283",
    "summary": "A consumer of a generic value type in an external assembly gets a generated resolver without a generator crash.",
    "details": "A successful ordinary build alone is insufficient."
  },
  "checks": [],
  "claims": [],
  "files": [],
  "provenance": {
    "toolchain": "Not executed",
    "origin": "structural-inspection",
    "note": "Source inspection is not behavioral proof."
  },
  "limitations": []
}
```

Check fields (all required, nullable evidence strings below):

- `id`, `title`, `requirementId`: nonempty strings.
- `kind`: `differential`, `regression`, or `structural`.
- `evidence`: `observed`, `historical`, or `synthetic`.
- `baseOutcome`, `headOutcome`: `pass`, `fail`, `notRun`, or `error`.
- `baseSourceSha`, `headSourceSha`: 40 lowercase hex characters.
- `baseHarnessSha256`, `headHarnessSha256`: 64 lowercase hex or null.
- `baseLog`, `headLog`: relative evidence paths under the packet directory, or null.
- `baseLogSha256`, `headLogSha256`: 64 lowercase hex or null.
- `limitations`: string array.

Claim fields: `id`, `title`, `requirementId`, `kind` (`fix`, `invariant`,
`structural`), `checkIds` (nonempty string array), `paths` (string array).

File fields: `path`, `role` (`source`, `generatedSnapshot`, `documentation`,
`test`, `other`), `additions` (nonnegative integer), `deletions` (nonnegative
integer), `group` (nonempty string).

## Decision semantics

- A `fix` can be ready for human review only when at least one attached
  `differential` check has observed fail→pass outcomes, identical nonnull harness
  hashes, matching requirement and source SHAs, and locally verified bytes for
  both log digests. Any attached contradictory/error/stale/synthetic check blocks
  readiness; a pass→pass regression is supporting evidence, not fix proof.
- An `invariant` requires an observed `regression` pass→pass with the same
  source/harness/log integrity checks.
- A `structural` claim is always labeled `INSPECTION ONLY`: categorizing a diff
  is useful for review effort, not proof of behavior. A claim without proof is
  `NEEDS EVIDENCE`, never silently accepted.
- Log hashes establish local byte integrity, not runner identity, truthfulness,
  signatures or authentication. Show this distinction in the provenance view.
- A `fail` must be the expected requirement-specific failing observation.
  Restore, build, setup, timeout and zero-test failures are `error`/`notRun`,
  never a qualifying red baseline. The harness digest covers frozen test inputs,
  runner and relevant execution/overlay configuration, not only a launch script.
- Reject unknown enum cases, duplicate IDs, missing check references, oversized
  packets, invalid SHAs/digests, absolute paths, traversal and symlink escapes.
- Loading changed packet bytes resets the local human decision; decision export
  binds to the exact packet SHA-256 and includes declared reviewer, decision,
  rationale and timestamp. No authentication, merge or remote write is implied.
- Revalidate the packet and referenced evidence before recording/exporting a
  decision, or explicitly bind export to a cached immutable verified snapshot.
  Source links must be approved HTTPS links; never open executable file paths.

## UI expectations

English first, native macOS sidebar/detail/inspector. Four official changes in
the sidebar, large clear verdict, requirement and evidence comparison, grouped
file changes (generated snapshots collapsed), refusal reasons, provenance and
an explicit local decision sheet. Import packet, export review, filter files,
copy source reference, keyboard shortcuts, light/dark accessibility. Bundle
verified example packet(s) and associated logs as SwiftPM resources; imported
packets receive identical validation. No fake percent confidence, fake reviewer
or fake live model label.
