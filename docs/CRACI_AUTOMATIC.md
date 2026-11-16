# Automatic CRACI checks

## Update 16 November 2026: test-credit window, usage check, leaner runs

The owner supplied a new CRACI test credit (about EUR 10, free) and asked for
leaner CI that uses the CRACI API. The earlier campaigns were tests.

- **Window from variables.** `CRACI_WINDOW_END` now comes from the repository
  variable of that name, defaulting to **30 November 2026 22:00 UTC**.
  `CRACI_CREDIT_WINDOW_OPEN=true` still admits jobs before runner allocation.
- **Usage check with the API.** With the secret `CRACI_API_TOKEN` (a read-only
  token from CRACI Settings → API tokens), the portable job reads
  `GET /v1preview1/usage` since `CRACI_WINDOW_START` (variable, default
  16 November 00:00 UTC), writes the vCPU-minutes to the job summary and stops
  when the optional `CRACI_VCPU_MINUTES_BUDGET` variable is reached. Without
  the secret, or if the API is unavailable, only the window check applies. The
  job's network policy allows `api.craci.com:443` in addition to GitHub and npm.
  CRACI's own credit limit remains the hard stop; this check runs after runner
  allocation.
- **Fewer runner minutes.** The Exa Internet Butler checks moved to
  `craci-exa.yml` and run only when `pets/exa/internet-butler/**` or that
  workflow changes (previously on every PR and push). Both workflows use the
  `setup-node` npm cache and `npm ci --prefer-offline --no-audit --no-fund`;
  the separate `npm audit` gate is unchanged.

Historical record of the first window follows.

## 15 November 2026

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

## Baseline registration repairs

The first automatic execution found six existing workspace directories missing
the required manifest and entrypoint files. Their registrations now point to
their existing README and retain building status and current product owners.
The AstraZeneca manifest now uses the actual catalog slug `astrazeneca` and has
its missing scope entrypoint. Stoa's manifest had labeled a nonexistent agent
capability as implemented; that invalid agent-use association is removed.
Stoa's product implementation and actual sponsor-DXF evidence are untouched;
workspace capability references cannot serve as implementation receipts.
Validators and test assertions remain unchanged.
