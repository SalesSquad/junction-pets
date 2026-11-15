# CRACI repository bug and quality audit reference

> **15 November routing update:** Junction is public and retains this audit
> harness. Approved snapshots from other repositories must stay in the separate
> private [SalesSquad/craci-repo-audit](https://github.com/SalesSquad/craci-repo-audit)
> execution repository. Use that private checkout and its operator instructions;
> the public copy's privacy guard intentionally refuses source publication here.
> The original private-Junction setup described below is historical context.


The owner stopped the HF training campaign on 15 November and requested that
the ten CRACI workers inspect his repositories for bugs and poor code instead.
This is a read-only static-analysis campaign, not a product release or an
automatic code fixer. Only the existing Junction CRACI connection is used.

## Source and privacy

`bundle.py` runs on the already authorized MacBook Pro using its existing `gh`
credential handling. It resolves each owned repository's live default-branch
commit, reads a bounded filtered Git snapshot and exports only allowlisted text
source/dependency manifests. It never exports the Mac credential or executes
project code, hooks, imports, package scripts or repository scanner config.
Application data, records, transcripts, private directories, credentials,
binary/generated/vendor files and over-limit files are excluded. Likely
embedded credentials exclude the whole file; only path, line and detector name
are recorded. This heuristic is not proof that every sensitive value is found.

The existing private `SalesSquad/junction-pets` destination is verified to have
only the owner as a collaborator before any cross-repository source upload.
Frozen bundles, rules and reports live in a dated private research prerelease
`craci-repo-audit-20261115-01` (later batches use 02–12). Nothing is published to
a public repository or a hosted scanning service. The source archive retains
excluded-path reasons so incomplete coverage cannot be reported as clean code.
Excluded-path names are hashed to avoid copying personal filenames into the
cloud inventory. Secret candidates retain code locations, never values.
Repositories containing owner records/archives are excluded from discovery.
If sensitive content is discovered after publication, stop the campaign and
use the owner's GitHub asset-deletion control with the required deletion
approval. Tool immutability does not remove that owner recovery path.

## Bounded execution

The manual main-only workflow admits an exact manifest SHA256 and atomically
claims one source/run-bound admission asset. Re-dispatching another run against
the same batch fails closed. Ten 8-vCPU CRACI jobs can execute concurrently;
each repository gets one at most 45-minute job. All batches share a concurrency
group, so a second batch waits for the first. Submit at most one pending batch.
The per-batch worst-case reserve is capped at EUR100 of the existing authorized
credit (128 repositories would reserve EUR78.4368 at EUR0.0017/vCPU-minute plus
small setup/collection allowance). No cash top-up, hosted runner or new provider
exists. This is a conservative resource estimate, not a provider hard budget.

Admission accounts for all queued waves and refuses insufficient time before
**15 November 2026 17:00 UTC / 19:00 Helsinki**. Each analyzer and its process
group is bounded; scans reserve time for private report publication. The
existing `CRACI_CREDIT_WINDOW_OPEN` stop also remains authoritative.

Tools are installed from pinned, integrity/hash-locked dependencies before
the other repositories' snapshots are downloaded. Semgrep runs with a frozen
local rulepack, metrics/version checks off; Ruff uses isolated settings and
ESLint uses only the harness config. Analyzer subprocesses do not receive
GitHub/provider credentials. The trusted controller retains only the scoped
current-repository job token for private transport; same-user process
separation is not an OS security boundary.

## Results and limits

Each report binds repository, source SHA, harness SHA, actual run ID, source
bundle digest and rulepack digest. Reports distinguish candidate bugs,
maintainability findings, analyzer failures/timeouts, unsupported languages and
excluded files. Static candidates need source triage; counts or a successful
job do not prove exploitability or absence of bugs. No application build,
runtime, Apple SDK/device, production or compliance claim is made.

## Operator commands

```sh
python3 tools/craci-repo-audit/bundle.py --repos SalesSquad/junction-pets SalesSquad/chibi --output /new/task/batch01
python3 tools/craci-repo-audit/publish.py --directory /new/task/batch01 --batch 01
gh workflow run craci-repo-audit.yml --repo SalesSquad/junction-pets --ref main -f batch=01 -f manifest_sha256=THE_PRINTED_64_HEX_DIGEST
```

The manifest and source
bundles are immutable after publication; never clobber a prior batch or rerun
an unchanged scan just to consume credit. Actual source/run URLs, focused
privacy/control checks and advisory review disposition are recorded in the PR.
