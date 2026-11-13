# CRACI pilot for Junction

This is the manually started CI lane for `SalesSquad/junction-pets` and the
CRACI side challenge. It runs the repository's existing validation, Node tests
and catalog build. It does not deploy Chibi or execute companion/provider calls.

## First run

1. Finish CRACI sign-in at <https://platform.craci.com>. In its billing/credit
   view, verify the offered Junction credit, currency, balance and expiry before
   submitting compute. The sponsor's €1,000 offer is not an observed account balance.
2. In CRACI **Settings → Builds**, verify that its GitHub App connection covers
   **only the intended repository**, `SalesSquad/junction-pets`. An owner must
   approve any new GitHub App permission/repository grant in GitHub's own flow.
   Never post sign-in codes, API tokens or browser cookies into this repository.
3. Once this workflow is present on `main`, select **Actions → CRACI portable CI
   pilot → Run workflow** and choose the exact source branch. The CLI equivalent is:

   ```sh
   gh workflow run craci-pilot.yml --repo SalesSquad/junction-pets --ref main
   gh run list --repo SalesSquad/junction-pets --workflow craci-pilot.yml --limit 5
   ```

4. Check that the job actually acquires a CRACI runner, and record the GitHub run
   URL, run attempt, checked-out commit and CRACI job ID. A queued job or successful
   dispatch request is not an executed build. If no runner appears, inspect App
   coverage/capacity and cancel the pending run rather than repeatedly dispatching.
5. Require all four stages to pass: dependency installation, validation, tests and
   build. Retain the executor/source log and CRACI findings for this exact attempt.

The workflow is manual-only, `contents: read`, CRACI-only and bounded to 15 minutes.
Checkout credentials are not persisted. It requests no provider secrets, cache,
artifact upload, deployment or GitHub-hosted fallback. It starts with CRACI's
2-vCPU default; larger runners require an observed bottleneck and available credit.

## Network and dependency evidence

The pinned `cracicorp/setup` action selects the documented full `ubuntu-24.04`
image, including the hosted tool cache used by Node setup. The explicit policy
allows the GitHub and npm software presets and denies unmatched egress. GitHub's
CI management traffic remains allowed by CRACI independently of these presets.
The job does not override CRACI's certificate/trust environment variables.

Inspect the CRACI job configuration and log for rejected inputs or fallback
warnings before relying on the image or policy. On a blocked download, read the
network trace first. Correct a package source or supported preset narrowly;
do not change the default to `allow` merely to obtain a passing build.

SBOM generation and network tracing are CRACI features, not extra scan commands
in this workflow. Download the job's CycloneDX SBOM and inspect its recorded
completeness. A complete SBOM additionally depends on CRACI observing the packages
and any restored cache provenance; the YAML policy alone does not establish it.
This initial lane restores no Actions cache. A later cache experiment should use
one lockfile-keyed cache, record its producing job and compare cold/warm run time,
compute usage and SBOM completeness before claiming a benefit from NVMe caching.

## A useful side-challenge demonstration

Use actual build evidence for a small **build → explain → repair → rebuild** loop:

1. Show this project's successful CRACI run, source commit and build artifact hash.
2. Explain the observed dependency downloads using the network trace and CycloneDX
   component identifiers. Keep denied requests and unexplained destinations visible.
3. Triage an actual CRACI vulnerability finding against the exact component/version
   and use path. Record the advisory, affected range, exposure, proposed fix and
   remaining uncertainty. A clean npm audit is not a CRACI vulnerability verdict;
   an SBOM alone does not establish exploitability. If there is no finding, report
   that observation and leave the repair step unexercised.
4. Prepare a bounded dependency-fix PR, run the existing checks and inspect a new
   CRACI SBOM/finding state for the rebuilt source. Keep human/provider merge and
   release controls. Do not intentionally add a vulnerable dependency to this app.
5. Present measured before/after evidence, including failure/recovery. If the
   CRACI Chibi companion explains a redacted export, label it as supplied evidence;
   this CI lane does not install a live CRACI API connection into that companion.

Bind each observation to: source SHA, lockfile SHA-256, GitHub run URL/attempt,
CRACI job ID, runner configuration, command outcomes, built artifact SHA-256,
SBOM digest/completeness, trace reference, advisory/triage disposition and measured
compute usage. Keep raw private exports in the owner's approved private event
storage; publish only an explicitly approved, redacted submission. A local test
receipt, authored plan or synthetic example must never be labelled a live CRACI run.

## Official references

- [GitHub connection](https://docs.craci.com/guides/github-connection/)
- [Runner workflows](https://docs.craci.com/guides/runner-workflows/)
- [Runner images](https://docs.craci.com/reference/runner-images/)
- [Network policy and presets](https://docs.craci.com/guides/setup-action-network/)
- [SBOM and cache completeness](https://docs.craci.com/guides/cache-sbom-completeness/)
- [Network troubleshooting](https://docs.craci.com/guides/network-troubleshooting/)
- [Compute usage](https://docs.craci.com/guides/compute-usage/)

References were read on 13 November 2026. Account credit, App installation, actual
runner pickup, SBOM completeness and vulnerability outcomes require live evidence.
