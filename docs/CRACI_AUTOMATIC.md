# Automatic CRACI checks — 15 November 2026

The owner explicitly restored automatic tests, build and dependency-security
checks for **SalesSquad/junction-pets**. This is a fresh repository-specific
exception to the default Actions opt-out and lightweight development rule.

`.github/workflows/craci-ci.yml` runs one 2-vCPU CRACI job for every PR opening,
head update or reopening, and every push to `main`, without path filters.
Existing PRs run on their next event. PRs test GitHub's merge commit; logs record
its exact SHA. New source cancels obsolete runs for the same PR. Every main
push has a distinct concurrency group, preserving its queued run.

The job installs locked dependencies without install scripts, runs
`npm audit --audit-level=high` (including development dependencies), validates
source contracts, runs the Node suite and builds the catalog. Audit service
errors and high/critical findings fail the job. Lockfile and build-manifest
digests are logged. After successful installation, audit, validation, tests
and build each run even if another check fails; the job still reports failure. CRACI supplies network traces, SBOM and vulnerability views;
those provider findings and SBOM completeness must be inspected separately.
This does not exercise all browser, Python, native, scientific or model lanes.

Pinned actions, read-only contents permission, no persisted checkout credential,
and default-deny GitHub/npm networking are retained. No provider secret,
deployment, artifact upload, GitHub-hosted fallback or account grant is added.
Heavy qualification remains in the existing manual `craci-pilot.yml` unchanged.

## Existing spending and shutdown controls

The existing EUR1,000 credit-only ceiling, no-top-up rule and shutdown remain
authoritative. `CRACI_CREDIT_WINDOW_OPEN` must equal `true` before runner
allocation; missing/false skips the job. The runtime deadline check refuses
qualification unless more than 16 minutes remain before **15 November 2026
17:00 UTC / 19:00 Europe/Helsinki**. Jobs time out after 15 minutes.

The already scheduled shutdown closes the shared variable and disables the
manual workflow. Closing that same variable also blocks this new automatic
workflow. The runtime cutoff still refuses work if the scheduler is delayed,
but initial runner allocation precedes that guard; this is not a provider hard
spending cap. This change neither extends the credit window nor authorizes
cash charges. See [the original controls](CRACI.md#continuing-use-and-stop).
