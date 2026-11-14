# CRACI CI for Junction

## Active owner-authorized CRACI window — 14 November 2026

Work ID: `CRACI-ACTIVATE-20261114`. Mikael explicitly requested substantial use
of existing CRACI credits for the next two days. This is the scoped exception to
the usual GitHub Actions opt-out for **SalesSquad/junction-pets only**.

The authenticated existing `onemanraid` billing page showed **EUR 1,009.97
starter credit remaining** on 14 November. The owner authorized at most
**EUR 1,000 of existing credits**, with no top-up, cash charge or new provider.
The page did not display credit expiry. The conservative operational cutoff is
**2026-11-15 17:00 UTC / Sunday 19:00 Europe/Helsinki**, matching CRACI's announced
Junction weekend window; this is not a claim about the credit's legal expiry.

Repository Actions was read back enabled after checking that its only workflow
was CRACI portable CI (ID `417767938`). Existing PR events now launch actual
CRACI jobs. Three previously unqualified source heads completed successfully:

| Source / purpose | Source SHA | Actual GitHub run | CRACI job / runner |
| --- | --- | --- | --- |
| PR76 Linux environment qualification | `10c5b2df57e1ad3bbdeedf69ec23906a1be4c34d` | [43548053684](https://github.com/SalesSquad/junction-pets/actions/runs/43548053684) | `132303867708` / `craci-3-4c175445` |
| PR85 S-Pankki Node integration | `8baf32ebbe4c50e92f3230fa38c843b92b48a0b4` | [43548058431](https://github.com/SalesSquad/junction-pets/actions/runs/43548058431) | `132303882860` / `craci-0-a1618a21` |
| PR87 Valio Node integration | `db003d1fd491381e7ce2409eefb1807a0c7ef0de` | [43548062533](https://github.com/SalesSquad/junction-pets/actions/runs/43548062533) | `132303896493` / `craci-2-305400a7` |

These jobs passed install, audit, validation, Node tests, catalog build and
digest recording. They do not prove browser behavior, actual banking data,
Harbor isolation, live model use or deployment. Exact account-billed cost for
these individual jobs remains unknown.

### Fixed browser workload

The existing workflow now has manual choices `portable` and `product-browser`.
Browser dispatch requires a full `source_sha` and `product=stoa|valio`; there is
no arbitrary command input. It checks out the harness and product separately
and verifies the product commit before importing any product code.

```sh
gh workflow run craci-pilot.yml --repo SalesSquad/junction-pets \
  --ref codex/junction-craci-burst-20261114 \
  -f workload=product-browser -f product=stoa \
  -f source_sha=bfb4e363879b9125b10ed8a8a14f77ea5ed8af70
```

Use the live reviewed harness branch/HEAD and current intended product SHA;
the example is a dated initial source, not a permanent current-head assertion.
The three browser jobs are Chromium, Firefox and WebKit, at most three parallel
jobs per dispatch, each explicitly **4 vCPU, 20 minutes maximum**. Each checks
1440×900 and 390×844 viewports. The narrow viewport is not a physical phone test.

- **Stoa:** room count, area, evidence selection and polygon highlight,
  unsupported-question refusal, local DXF import, and the official sponsor DXF
  fetched through bounded range requests and independently checked against
  `4070c5f19eb921bc08e2f5a23e957086f76abcca03fafbb8b62ca30c8a60b58d`.
- **Valio:** quantities and cent-exact quote, human-approval gate, replay of the
  actual browser-emitted order payload with one audit event, cancellation and
  restored stock, price-change invalidation, and budget refusal. All suppliers,
  orders and payments in this test are synthetic; no real purchase occurs.

Browser runtime requests are restricted to the test's own loopback origin.
Installation uses the locked Playwright version, npm/Ubuntu/GitHub presets,
the two version-documented Playwright download hosts and the specific public
Stoa sponsor hostname. Direct TLS download exceptions are not a claim that
CRACI has package-aware SBOM visibility into browser binaries.
JSON outcome records remain in GitHub logs. Screenshots/traces are temporary
runner diagnostics; no persistent artifact upload is claimed.

### Continuing use and stop

The existing Junction Product Factory and sole Portfolio PR Recovery
automations received this bounded CRACI exception without a schedule change.
They must select missing evidence or an actual failure, check current source
and existing runs, and avoid repeating a successful unchanged workload.
Start at most three jobs per batch; do not create a 34-agent fanout or burn
credits with idle/repeated work.

The repository variable `CRACI_CREDIT_WINDOW_OPEN=true` admits these workflow
jobs before runner allocation. Missing/false closes new jobs. Each job also
checks the UTC cutoff before installing dependencies. This second check occurs
after initial allocation and is not a provider hard spending cap.

A one-time shutdown automation `Automation_563ad488d07081919594286152d28d46`
is scheduled for **15 November 19:00 Europe/Helsinki**. It sets the flag false,
disables only workflow417767938, checks the resulting state and cancels only
this window's unfinished work. The two existing automations carry the same
expiry instruction as a fallback. Scheduling is verified; future execution
must still be observed. The shutdown uses existing authorized administration
access and cannot be claimed successful if that access is unavailable.

The CRACI billing page and delayed completed-job usage meter must be rechecked
before expanding load. Do not treat a successful YAML write, dispatch request,
green npm audit or old receipt as a new runner/SBOM/budget attestation.

### Explicit unresolved lane

The proposed AfterQuery Harbor reference/no-operation and adversarial workload
was not activated. Automated tool safety checks blocked that authoring task,
including its reduced benign follow-up. No blocked payload or Harbor runner
job was installed. The existing AfterQuery owner retains the actual
separate-container qualification gap; local regression remains distinct from
that proof. Other independent CRACI workloads continue.


This is the CRACI CI lane for `SalesSquad/junction-pets` and the CRACI side
challenge. It automatically runs dependency security checks, the repository's
validation, Node tests and catalog build on pull requests and pushes to `main`.
It does not deploy Chibi or execute companion/provider calls.

## Automatic runs

- Every pull request, regardless of its target branch, runs on opening, new head
  commits and reopening (GitHub's standard `pull_request` activities). Draft PRs
  are included. Existing open PRs run on their next such event; enabling triggers
  does not retroactively dispatch all of them.
- Every push to `main` runs, with no path filters. Main/manual runs have distinct
  concurrency groups so a newer run cannot replace a pending main run. For the
  same PR, newer source cancels obsolete queued/running work.
- PR jobs use GitHub's tested merge commit and record its exact SHA. They use
  `pull_request`, read-only repository permissions and no provider secrets;
  GitHub's own fork approval controls remain in force.
- After locked installation, `npm audit --audit-level=high` fails the job on high
  or critical dependency findings (including development/build dependencies),
  or an audit error. Lower-severity findings remain in the report. It does not
  change dependencies or run an automatic fix.
- CRACI generates its own SBOM, vulnerability view and network trace for every
  job. The npm audit gate is separate from those provider findings and does not
  by itself prove SBOM completeness or that the software is secure.

## Manual rerun and connection checks

1. Finish CRACI sign-in at <https://platform.craci.com>. In its billing/credit
   view, verify the offered Junction credit, currency, balance and expiry before
   submitting compute. The sponsor's €1,000 offer is not an observed account balance.
2. In CRACI **Settings → Builds**, verify that its GitHub App connection covers
   **only the intended repository**, `SalesSquad/junction-pets`. An owner must
   approve any new GitHub App permission/repository grant in GitHub's own flow.
   Never post sign-in codes, API tokens or browser cookies into this repository.
3. Once this workflow is present on `main`, select **Actions → CRACI portable CI
   → Run workflow** and choose the exact source branch. The CLI equivalent is:

   ```sh
   gh workflow run craci-pilot.yml --repo SalesSquad/junction-pets --ref main
   gh run list --repo SalesSquad/junction-pets --workflow craci-pilot.yml --limit 5
   ```

4. Check that the job actually acquires a CRACI runner, and record the GitHub run
   URL, run attempt, checked-out commit and CRACI job ID. A queued job or successful
   dispatch request is not an executed build. If no runner appears, inspect App
   coverage/capacity and cancel the pending run rather than repeatedly dispatching.
5. Require every stage to pass: dependency installation, vulnerability audit,
   validation, tests, build and digest recording. Retain the executor/source log and CRACI findings for this exact attempt.
   The final step logs the lockfile digest, a sorted SHA-256 manifest of built
   files and its digest; it does not upload or retain the built files themselves.

The workflow is `contents: read`, CRACI-only and bounded to 15 minutes.
`workflow_dispatch` remains available alongside the automatic triggers.
Checkout credentials are not persisted. It requests no provider secrets, cache,
artifact upload, deployment or GitHub-hosted fallback. The portable lane explicitly requests
2 vCPU; the browser lane requests 4 vCPU for browser/system installation and
three-engine qualification. Available credit and observed capacity still bound admission.

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
- [Compute usage](https://docs.craci.com/api/usage/)
- [GitHub PR and push events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
- [npm audit failure threshold](https://docs.npmjs.com/cli/v10/commands/npm-audit/)

The original CRACI reference baseline was read on 13 November 2026. Runner and
network guidance, GitHub event/concurrency rules and npm audit were checked for
this automatic-CI change on 14 November. Account credit, App installation, runner
pickup, SBOM completeness and vulnerability outcomes require live evidence.

