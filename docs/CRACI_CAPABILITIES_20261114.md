# CRACI capabilities and the next useful expansion

Work ID: `CRACI-CAPABILITIES-20261114`.

Checked on **14 November 2026**, including authenticated `onemanraid` UI reads at **06:12–06:15 Europe/Helsinki**. This is research and an implementation proposal, not a new workload dispatch or a change to credentials, policies, notifications or deployments. The existing Junction credit authority, its EUR 1,000 ceiling and 15 November 19:00 Helsinki admission stop remain unchanged.

Repository baseline: `SalesSquad/junction-pets` main `a33f525171b6424d39dfc4c889b63e0fc5cb459e`. Owned scope is this new document only. Existing campaign implementation and immutable execution receipts remain in [PR92](https://github.com/SalesSquad/junction-pets/pull/92); its source is `9aaa70e789202748ce214a8218c0937776ca89f7`. The existing Portfolio PR Recovery is the sole integrator.

## Decision

CRACI can take us beyond test execution into actual product builds, native Linux architecture qualification, dependency evidence and continuing vulnerability tracking. The best next slice is a versioned build artifact with a component record that agents can inspect. More identical passing test runs would not deliver that missing capability.

Use three complementary planes: existing development agents author changes; CRACI runs bounded Linux builds and records build evidence; the existing controller joins those observations to the source commit and product. GPU training and Apple-native work retain their established executors.

## What the current account actually shows

All observations below came from the existing signed-in Safari session on the authorized MBP. No browser credentials, session databases or API tokens were extracted. Counts are dated UI observations, not immutable provider attestations.

| Surface | Observed result | Interpretation |
| --- | --- | --- |
| [Home](https://platform.craci.com/home) | Organization `onemanraid`; one project, Junction Pets; 61 builds and 76 tracked packages at the initial read. Home showed zero projects with vulnerabilities. | This summary is not the same scope as branch-specific job findings. It is not a clean-security verdict for every run. |
| [Usage](https://platform.craci.com/settings/usage) | Month to date: **94 jobs**, 65 displayed CI minutes, approximately **250 one-vCPU-equivalent minutes**. Rows: 55 two-vCPU jobs, 33 four-vCPU jobs and six eight-vCPU jobs, all on `ubuntu-24.04`. | No ARM64 or 16/32-vCPU jobs appear in this observed usage table. Displayed values are rounded; not a campaign invoice. |
| [API tokens](https://platform.craci.com/settings/api-tokens) | **No API tokens have been created.** | The working GitHub App/runner connection has not established a public REST API credential. |
| [Runner templates](https://platform.craci.com/settings/runner-templates) | Only built-in `default` and `proxy-passthrough`, both 2 vCPU / 6 GiB in the UI. No organization-authored templates. | Actual workflow overrides still apply. The live passthrough slug differs from the documentation's `audit` example; inspect the account before copying template names. |
| [Alerts](https://platform.craci.com/settings/alerts) | No alert rules. | The account is not currently configured to send these rule-based alerts. This read did not enable notifications. |
| [Caches](https://platform.craci.com/projects/junction-pets/caches) | Zero entries, zero bytes. | Our current campaign has not established reusable tracked caches. |
| [Artifacts](https://platform.craci.com/projects/junction-pets/artifacts) | Zero OCI manifests, zero OCI blobs. | No OCI container delivery lineage has been recorded in this project view. This is not a claim that no local build outputs or GitHub artifacts exist anywhere. |
| Capacity banner | Platform stress testing through Sunday 19:00 Helsinki; queues may be longer than usual. | Eight-way coordination is our campaign setting, not a provider guarantee of available parallel machines. |

### A real finding already available in our completed tests

[Exa WebKit job 132321330676](https://platform.craci.com/projects/junction-pets/jobs/132321330676) belongs to [GitHub run 43553596162](https://github.com/SalesSquad/junction-pets/actions/runs/43553596162), harness commit `63b01d5d489c89075deb04d1f187c656fd5029ff`, product source `2ce520f55a97f2491d34fb4582de728e7f379c1b`.

The job succeeded functionally, while its overview showed **91 vulnerability findings: 2 Critical, 39 High, 44 Medium, 5 Low and 1 Unknown**, associated with 23 vulnerable packages. Examples were Ubuntu `xserver-common`, `xvfb`, GStreamer and `libsoup` packages installed for the browser environment. The [vulnerability graph](https://platform.craci.com/projects/junction-pets/jobs/132321330676/vulnerabilities) is labelled beta. These are provider dependency findings, not 91 independently verified exploitable Exa application defects; advisory IDs, distro patch status, runtime inclusion and exposure still need triage.

The same overview reported a 4-unit runner, approximately 51 seconds running, **peak 1.5 vCPU and 1.2 GiB memory**, and 214 blocked connections. Peaks do not prove that a smaller runner would preserve latency. Blocked connections do not by themselves prove malicious activity. They identify concrete candidates for inspection instead of guessing from test exit codes.

There is a UI consistency issue to preserve: the overview simultaneously displayed **zero packages**, 23 vulnerable packages, and the label **Complete SBOM certified**. Do not promote that label into a completeness or cryptographic claim. A raw SBOM export was not downloaded during this read-only investigation. The existing browser workload also deliberately uses direct TLS connections for browser binaries, so the documented package-monitoring boundary remains relevant regardless of the badge.

## Documented capability map

| Capability | What is currently documented | Useful application |
| --- | --- | --- |
| CPU and memory | 1–32 compute units; 1 vCPU and 3 GB memory per unit, up to 32 vCPU / 96 GB. Reusable organization runner templates select image, size and network policy. [Configuration](https://docs.craci.com/reference/runner-configuration/) | Benchmark a genuinely parallel corpus/build at a few sizes; choose from measured throughput. |
| Architecture | Ubuntu 24.04 on x64; native ARM64 via `craci-slim-arm`; fuller x64 image also available. [Images](https://docs.craci.com/reference/runner-images/) | Build the same Linux service for both architectures and exercise its actual critical path. ARM64 Linux is not an Apple SDK environment. |
| Build tooling | Docker Engine, Buildx, Compose, CMake, Ninja and common language tools are included. Slim has no systemd. [Images](https://docs.craci.com/reference/runner-images/) | Assemble a real container, or run temporary app/database/queue services inside a bounded integration job. |
| Workflow control | Existing GitHub Actions workflows and UI; jobs choose `runs-on: craci`. [Workflow guide](https://docs.craci.com/guides/runner-workflows/) | Pin source, dispatch a bounded matrix, retain actual run/job IDs. |
| Components and licenses | Build-time package evidence, transitive dependencies, declared licenses and cache evidence; CycloneDX/SPDX exports. [SBOM](https://craci.com/features/sbom-generation) | Associate a release candidate with its actual dependency record and stated completeness. |
| Vulnerability lifecycle | Monitored SBOMs are checked against newly published advisories; cross-build/repository views, VEX and vendor SBOM support are advertised. [Tracking](https://craci.com/features/vulnerability-tracking) | Give a finding a component/version, affected product, owner and resolution evidence. No unchanged test rerun is needed merely to learn about a new advisory. |
| Network policy and trace | Monitored package sources and bounded TLS/TCP/UDP/ICMP rules; trace data for diagnosing connections. Default behavior without an explicit policy allows unmatched traffic. [Network](https://docs.craci.com/guides/setup-action-network/) | Diagnose an unexpected download and constrain the next build to required sources. |
| Build lineage | API lookups connect caches and OCI manifests/blobs to producing jobs; OCI SBOM aggregation is experimental. [API](https://docs.craci.com/api/reference/) | Connect a container digest to source and build evidence. CRACI's SBOM page explicitly says it does not provide signed provenance. |
| Embedded Linux | Official Raspberry Pi pi-gen and Yocto examples; Yocto example uses 32 units. [pi-gen](https://docs.craci.com/guides/examples/pi-gen/), [Yocto](https://docs.craci.com/guides/examples/yocto/) | Package a genuine robot/edge Linux image when the product needs one; the build is not physical-device qualification. |
| Evidence export | Component/vulnerability/build data for the manufacturer's own documentation and reporting process. [Evidence](https://craci.com/features/compliance-reports) | Retain inspectable records for customers and partners. This does not establish regulatory conformity or submit an official report. |

CPU data preparation, simulations, fuzzing and classical-model evaluation are workload ideas enabled by the runner; they are not separate ready-made CRACI product features. Likewise, kubectl or a cloud CLI being installed does not create a hosting account, cluster, credential or deployment authority.

## API, CLI, MCP and agent skills

The [public REST/OpenAPI reference](https://docs.craci.com/api/reference/) documents nine GET operations: job SBOM, experimental OCI SBOM, three cache/OCI provenance lookups, logs, active jobs, network trace and usage. It does not document a public write endpoint to start a build, deploy a product or edit policy. Keep job orchestration in GitHub. The [jobs endpoint](https://docs.craci.com/api/reference/operations/listjobs/) only accepts active status, so historical enumeration needs GitHub or an explicitly retained index.

[Authentication](https://docs.craci.com/api/authentication/) uses an admin-created bearer token, displayed once and expiring after 90 days. Our live account has none. Token creation and secure host wiring are a separate implementation action, not done by this research. Do not put a token in this report, agent instructions, a shared prompt, or the repository.

The [usage API](https://docs.craci.com/api/usage/) reports organization-wide completed-job vCPU seconds. It is asynchronous, excludes unfinished jobs and is not a live credit-balance endpoint. Budget admission needs reserved running/queued usage in addition to reported totals. [API lifecycle](https://docs.craci.com/reference/api-lifecycle/) marks preview endpoints with at least a week's retirement notice; experimental endpoints may change without notice.

There is an official [agent-skills page](https://docs.craci.com/skills/) with a Markdown workflow-migration skill. I found no documented general-purpose CRACI CLI installation or publicly usable official ChatGPT plugin. `curl` and GitHub CLI are documented/current ways to access the API and workflows respectively; they are not evidence of a separate CRACI CLI.

CRACI explicitly advertises **MCP for package security** and pre-install protection on its [AI development security page](https://craci.com/solutions/ai-development-security), which invites users to request **early access**. No public MCP endpoint/setup contract or enabled MCP connection on our account was verified. A future internal read-only wrapper over the documented REST API is an implementation option; it is not an already installed official MCP.

## Important boundaries

- **Linux only today:** CRACI states no current GPU, Windows or macOS runners; Windows/macOS are roadmap. Keep GPU work on the existing Verda lane and Apple SDK/signing on verified Apple executors. [Provider FAQ](https://craci.com/ci-runner-pricing)
- **Worker, not proven persistent hosting:** no documented permanent VM, production database or website-hosting product was found. Temporary job-local services are a different capability. Provider account-wide concurrency, job-duration and disk-capacity limits were not publicly established in this review.
- **SBOM coverage is conditional:** custom `network.connections` bypass package-aware monitoring. `Complete with connections` does not prove that direct SDK, NuGet or browser downloads were identified. Use supported monitored sources where possible, disclose the remaining gap, and supplement it deliberately. [Completeness](https://docs.craci.com/guides/cache-sbom-completeness/)
- **Caches need lineage:** complete cache evidence requires one produced cache per job and complete producing-job evidence. Key by lockfile/toolchain/architecture; old cache evidence can broaden later SBOMs. A targeted cache-miss rebuild can resolve a concrete dependency-history question. [Completeness](https://docs.craci.com/guides/cache-sbom-completeness/)
- **Detection is not exploitability:** no documented reachability analysis or built-in MTTR/backlog metrics. Severity alerts, vulnerability webhooks and Slack/Teams alerts are roadmap. Current alerts cover egress-policy violations. [Tracking](https://craci.com/features/vulnerability-tracking)
- **No signed-provenance assumption:** component lineage through the API is different from a cryptographically signed artifact attestation. The provider's current SBOM comparison explicitly lists no signed provenance. [SBOM](https://craci.com/features/sbom-generation)

## Proposed implementation order

These are proposed next slices, not jobs launched by this document. Keep the existing integrator and bounded campaign admission. Do not expand the Junction-specific credit authority to other repositories by inference.

1. **Resolve one real dependency finding end to end.** Start from the Exa WebKit job above. Export its SBOM, bind advisory IDs to distro package versions, determine test-runner versus shipped-product scope, and record the outcome. If an actual affected dependency has a valid available patch, update only that component and perform one decisive rebuild. Preserve the original record. Do not label every distro-version match exploitable or suppress it merely because tests pass.
2. **Produce a real release candidate with provenance fields.** Pick one existing runnable Node/Python product. Build a versioned OCI image for x64 and ARM64, record the artifact digest, source commit, runtime, applicable test evidence, component record and completeness limitations. Use an existing approved artifact destination; publication/deployment remains separate. The current zero-artifact UI gives a measurable baseline.
3. **Connect the evidence to the existing run register.** Once a separately authorized API credential is installed in its approved secret store, read the documented endpoints into a narrow internal adapter. Suggested read operations are job status, SBOM, provenance, trace and usage. Preserve endpoint version and raw observation time. Do not invent public API writes or borrow browser session cookies.
4. **Measure one useful heavy workload.** Examples: a larger S-Pankki sponsor-customer cohort with independent expected answers; unseen Stoa DXF geometry cases; Valio concurrent order/inventory events; predeclared shifted-data evaluation after a Meta model improvement. Compare 4/8/16/32 units only where CPU parallelism or memory demand warrants it. Record throughput and quality, not just spend.
5. **Make reusable build settings after the first successful slice.** An organization template for a monitored build, architecture-bound cache keys and a separately scoped integration configuration can reduce duplicated setup. Retain the explicit per-job network boundary and stop deadline; do not weaken policy to hide a failed download.

For a broader future portfolio, Rust/Python/Node portions of Taimi, Chibi, Factory and analysis pipelines are technically suitable candidates. This is a capability assessment, not new spending or permission to transfer private application data.

## Cost and capacity interpretation

At the current [public price](https://craci.com/pricing), EUR 0.0017 per vCPU-minute, a 32-vCPU hour is EUR 3.264 and EUR 1,000 corresponds to approximately 9,804 vCPU-hours. These are arithmetic estimates, not our invoice. The approximately 250 equivalent minutes displayed in the account correspond to roughly EUR 0.43 at that list price; rounding, delayed reporting and contractual billing make it an estimate only.

A larger runner is worthwhile if it improves measured useful output. The observed browser job's low CPU/memory peaks do not justify scaling that same short test to 32 units. The account's weekend capacity banner also means queue delay must be observed rather than assuming unlimited instantaneous capacity. External API calls and GitHub artifact/registry storage must not be presumed covered by CRACI credits.

## Delivery and limits of this investigation

Reviewed official sources and the current account's home, runs, one completed job, vulnerability graph, API-token metadata, templates, alerts, usage, cache and OCI-artifact views. No new CRACI jobs, API tokens, policies, alerts, deployments or registrations were created. No SBOM download or authenticated public API call was performed. The completed campaign remains qualified only for its earlier recorded source and behavior.

This document is independently useful to the next agent: current evidence links, actual unused features, source pins and the next bounded action are all retained. Documentation only; no software tests are needed for this change. The sole integrator can merge it independently of the still-open campaign PR stack.
