# CRACI CI for Junction

> **Status 17 Nov 2026: CRACI is off and historical.** The owner turned CRACI off: every CRACI
> workflow is disabled, `CRACI_CREDIT_WINDOW_OPEN=false`, and GitHub Actions is disabled for the
> repository. Checks run in the agent's own environment (`npm ci --ignore-scripts`,
> `npm run validate`, `npm test`); see the CI policy at the top of [AGENTS.md](../AGENTS.md).
> Nothing below is an active instruction.

## Independent CRACI challenge lane

**Logical owner:** `junction-dev-craci`. This lane owns CRACI's own
[Best use of CRACI](https://hackjunction.app/participate/45/tech-challenges/42)
challenge work: build provenance, SBOM completeness, advisory triage and
reproducible fixes with source-bound evidence. The independently existing
[synthetic SBOM review](../pets/craci/SBOM_REVIEW.md) is a starting point,
not authenticated provenance or a vulnerability fix. The provider UI
observation of a complete SBOM for Valio job `132303896493` is documented
below; the SBOM bytes were not independently exported or validated.

The next proposed CRACI-owned step is a synthetic transitive dependency update
and advisory-match comparison, followed separately by obtaining and validating
real build evidence when available. These are proposals, not running work.
CRACI can also be the compute executor for other lanes: for example, G1 Moves
belongs to [Rokoko's motion research](../solutions/rokoko-teleoperation-gym/learning/G1_MOVES.md).
Provider identity does not change the research owner.

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

The existing workflow now has manual choices `portable`, `product-browser` and `sbank-sponsor`.
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

### First browser execution and environment repair

The first real matrix [run43548723279](https://github.com/SalesSquad/junction-pets/actions/runs/43548723279)
used harness `a6b8e0cd22a909a728da7eacce06a3181d32cb24` and Stoa source
`bfb4e363879b9125b10ed8a8a14f77ea5ed8af70`. All three browser jobs acquired CRACI
runners, then failed in Playwright's system-dependency installation because the
runner's Microsoft Ubuntu24.04 APT source returned403 under the selected policy.
No product assertion ran in this attempt. The repair adds only the documented
package-aware custom APT source `https://packages.microsoft.com/ubuntu/24.04/prod`;
all other unmatched egress remains denied. This failed receipt is retained.

The repaired [run43549188651](https://github.com/SalesSquad/junction-pets/actions/runs/43549188651)
on harness `d99035ec053381d299a1968974c2fc00ded29b87` passed Stoa's complete
Firefox and WebKit journeys at both widths, including the official sponsor
sample and source hash. Chromium still failed before product assertions:
its pinned Chrome-for-Testing download redirected from `cdn.playwright.dev`
to `storage.googleapis.com`, which the CRACI trace recorded as denied.
An independent public HEAD request confirmed the same307 redirect and a200
response at the exact official object. Only that TLS host is added; there is
no Google wildcard or default-allow policy. The fixed `browser` selector admits
one engine so this repair does not repeat the already-passed Firefox/WebKit
product assertions. Their browser-harness bytes are unchanged.

The actual CRACI UI for portable Valio job132303896493 reported
**Complete SBOM certified** and no known vulnerabilities among its76 packages.
That is a provider UI observation for this job; no exported SBOM was independently
validated, and browser jobs have a different dependency/network scope.

### Official S-Pankki synthetic data import

Manual `workload=sbank-sponsor` checks out official sponsor commit
`fbdecdedf1a1f49dd641c2e6b9f2b62d0dc0cc8f` with Git LFS and the intended product
`source_sha` separately. The 2-vCPU/15-minute job verifies **362,796,501 bytes**
and SHA256`49b3265d8e44e751de305a074dcffcda732bb79aa1e07b46fcca774ce76f1e63`.
An independent standard-library CSV parser computes one synthetic customer's
expected fields and original source rows, compares them to the real importer,
and checks that a repeated export refuses to overwrite the existing result.
Only counts and digests are logged; no dataset/export is committed or published.
This qualifies import/provenance, not banking advice, forecasting, browser
behavior or real customer integration. The successful actual execution is
recorded below.

The first sponsor [run43549430489](https://github.com/SalesSquad/junction-pets/actions/runs/43549430489)
failed before import: the CRACI trace recorded18 denied requests to GitHub's
LFS object host `github-cloud.githubusercontent.com`. The sponsor lane now
allows only that observed TLS hostname in addition to the GitHub preset.
The independent complete-file size/SHA256 check still rejects a pointer, error
page, partial object or different dataset before invoking the importer.

### Completed first qualification batch

All observations below came from actual CRACI runners and decoded GitHub job
logs. Source product commits are distinct from the harness/workflow commits.

| Qualification | Product/source SHA | Harness SHA | Actual evidence |
| --- | --- | --- | --- |
| Stoa Firefox and WebKit, both widths, official sponsor DXF | `bfb4e363879b9125b10ed8a8a14f77ea5ed8af70` | `d99035ec053381d299a1968974c2fc00ded29b87` | [Firefox job132307459979](https://github.com/SalesSquad/junction-pets/actions/runs/43549188651/job/132307459979), [WebKit job132307459800](https://github.com/SalesSquad/junction-pets/actions/runs/43549188651/job/132307459800) |
| Stoa Chromium, both widths, official sponsor DXF | `bfb4e363879b9125b10ed8a8a14f77ea5ed8af70` | `4ef6480f70812d5a42ee009b3246cec0a3d28c37` | [run43549650998 / job132308900519](https://github.com/SalesSquad/junction-pets/actions/runs/43549650998/job/132308900519) |
| Valio all three engines and both widths | `db003d1fd491381e7ce2409eefb1807a0c7ef0de` | `7089e7f656703a1a1fca1ac7145de3dc52dab54e` | [run43549859840](https://github.com/SalesSquad/junction-pets/actions/runs/43549859840), jobs132309562895/132309563215/132309563241 |
| Official S-Pankki synthetic CSV importer and provenance | `8baf32ebbe4c50e92f3230fa38c843b92b48a0b4` | `7089e7f656703a1a1fca1ac7145de3dc52dab54e` | [run43550002068 / job132310037843](https://github.com/SalesSquad/junction-pets/actions/runs/43550002068/job/132310037843) |
| Updated CI branch portable integration | branch `7089e7f656703a1a1fca1ac7145de3dc52dab54e`, tested PR merge `05c6ba01483e4219bdb090e87cf7a0737da3e89a` | same branch | [run43549821226](https://github.com/SalesSquad/junction-pets/actions/runs/43549821226) |

The browser matrix produced **12 passed viewport journeys**, no uncaught page
errors and no horizontal overflow. Stoa's sponsor source hash matched the
independently pinned DXF hash. Valio's approval/replay/cancellation/changed-price
and budget gates all passed. Browser-harness SHA256 remained unchanged across
the network repairs:
`ca13830f06f260e0b10485a08279854d71a96db69c3172a6cb2bd0e9d833dd4e`.

S-Pankki downloaded and hash-verified the complete362,796,501-byte CSV,
independently scanned **3,626,755 records**, and compared **581 selected rows**
including their original physical line numbers. It checked1,162 exact-cent
values and refused a second export with the original bytes unchanged.
The exported sample stayed on the ephemeral runner; its SHA256 was
`361b2e003018f63a62d518cdcbf13c04c65ce10b15611df7f25dcf66cde4ddc4`.
This is actual sponsor-synthetic data evidence, not a real bank/customer test.

Independent final read-only review found no blocking issue in workflow SHA256
`84f4f31773a72c1abc39211c1108b315ae894684b5398c0be83612de1190f100`, the browser
harness above, and sponsor checker SHA256
`803d04a377324b2eb76c817ed196158d0c6821170182a8de129ab2e789701393`.
These receipts do not automatically qualify later code, model behavior,
physical devices or production integration.

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



## Expanded portfolio campaign

The owner subsequently requested much broader use of the same credits. See [CRACI_PORTFOLIO_20261114.md](CRACI_PORTFOLIO_20261114.md) and [its exact run receipts](craci/portfolio-20261114.json) for the expanded fixed lanes, source-pinned browser coverage, 880,008 independent arithmetic checks, real PostgreSQL, Meta seed study and official Tieto compiler compatibility results. The earlier evidence above remains historical and unchanged; the portfolio campaign supersedes the earlier three-job admission limit while retaining the credit ceiling and shutdown.
