# CRACI experiments — 14 November 2026

Work ID: **J26-CRACI-EXPLORE2-20261114**  
Repository: **SalesSquad/junction-pets**  
Review: [PR #106](https://github.com/SalesSquad/junction-pets/pull/106)  
Base: `98d5a524d61e431ca36acd62b268ede343fc7fe2`

## Result

CRACI executed **12 jobs across five workflow runs** for this experiment: six browser jobs, two native architecture jobs, two cache jobs, and two MariaDB attempts. The browser, architecture and cache jobs passed. The first database attempt stopped before SQL at a missing Docker download rule. After a narrowly scoped rule correction, the actual database test completed and exposed **five product SQL identity defects**, with **72 other checks passing**. The failed results remain preserved.

These tests extend the existing Junction company lanes and environments. They add shared qualification tools; they do not create replacement product lanes or modify any `solutions/**` source.

| Experiment | Actual execution and result | Evidence |
| --- | --- | --- |
| Cala and Context browser journeys | Chromium, Firefox, WebKit × desktop/narrow viewports: **12/12 journeys passed** in six jobs | [Run 43564118119](https://github.com/SalesSquad/junction-pets/actions/runs/43564118119) |
| Native Linux architectures | x64 and ARM64 each passed nine independently checked cases; canonical answers match | [Run 43564116021](https://github.com/SalesSquad/junction-pets/actions/runs/43564116021) |
| Cold/warm npm cache | Actual cold miss, one saved cache, exact warm hit, offline reinstall and matching dependency graph; validation passed twice | [Run 43564229034](https://github.com/SalesSquad/junction-pets/actions/runs/43564229034) |
| MariaDB first attempt | Image configuration download denied before SQL | [Run 43564231865](https://github.com/SalesSquad/junction-pets/actions/runs/43564231865) |
| MariaDB corrected networking | Actual MariaDB 11.8.9; 72 checks passed and five SQL identity checks failed; restart/history/cleanup passed | [Run 43564983185](https://github.com/SalesSquad/junction-pets/actions/runs/43564983185) |

The machine-readable [results](craci/experiments-20261114/results.json) retain source pins and individual browser/native/cache receipts. The database [event log](craci/experiments-20261114/mariadb-runtime-events.json) preserves every emitted check, expected and actual values, hashes, database metadata and final result.

## What this establishes about CRACI

| Capability | What we actually verified | Useful next application |
| --- | --- | --- |
| GitHub workflow execution | Existing `runs-on: craci` and pinned setup action dispatched the experiment jobs | Qualify each product owner's exact candidate commit |
| Native ARM64 and x64 | Native kernel/Node architecture was checked in each job; the same product returned the independently expected answers | Portable Node/Rust/Python architecture checks with relevant fixtures |
| Browser matrices | Three actual browser engines navigated local HTTP applications at two viewport widths | Verify review, refusal, export, keyboard and persistence behavior for new product milestones |
| Disposable databases and Docker Compose | A pinned official MariaDB container ran the original SQL and survived a restart with identical current/history contents | Real SQL semantics, transaction rollback, migration and durability checks |
| Monitored package installation and caches | The cold job created the cache; the warm job restored it and installed offline | Faster repeated builds with traceable dependency origin |
| SBOM export and lineage | Downloaded CycloneDX 1.7 files contain job/source metadata, package URLs, licences and dependency references; all 74 warm npm components are marked restored | Attach dependency evidence to a precisely identified candidate build |
| Network diagnosis | Trace distinguished an allowed Docker registry/auth path from one denied delivery hostname | Diagnose an exact missing rule while keeping default-deny networking |
| Resource inspection | Job UI displayed CPU, memory, disk and network curves; cold cache job showed peak 1.3 vCPU and 795.7 MiB | Choose runner sizes from measured workloads after enough representative samples |

The observed developer entry points are the GitHub workflow/setup action and the authenticated CRACI web UI. CRACI also documents an authenticated [SBOM API](https://docs.craci.com/api/reference/operations/getsbom/). This experiment exported SBOMs through the existing UI session; it did not create API credentials or establish a new CLI/MCP integration.

Official [runner documentation](https://docs.craci.com/reference/runner-images/) describes Slim x64 (`default`), Slim ARM (`craci-slim-arm`) and included Docker/Compose tools. Our actual architecture and container runs corroborate those specific capabilities. They do not qualify Apple SDK/signing/device work, GPUs, every available runner size, every language toolchain, or an external sponsor service.

## Source and execution binding

| Scope | Product/dependency source |
| --- | --- |
| Cala, PR #102 | `ff6b0bacb1d796a098dba6798d61f59dc977420c` |
| Context, PR #105 | `76f0405ac49f2017129ec11d891c2a2cbe7d1838` |
| MariaDB CLI and SQL, PR #103 | `d0be3abf66c86d6817f82ca5ae5598ae003b5360` |
| Cache experiment | `98d5a524d61e431ca36acd62b268ede343fc7fe2` |

Initial experiments ran harness commit **`0e03dc2c5ce27ee2e46400e71ed3d12ad2af3063`**. The database retry ran **`6d85bb9a1b02cb06eef2d1da77f7cd86008a7e25`**. That second commit adds only six workflow lines for the observed Docker CDN destination; the four executable harness files are unchanged.

| Executable file | SHA-256 |
| --- | --- |
| `scripts/craci/new-products-browser.mjs` | `3c47bf0d4d1966f92d76cf75642c4a2bf6a651bde19453b2f6647dafcd2c579b` |
| `scripts/craci/platform-probe.mjs` | `e97e193255473b920524d21558d5cf5207e9ba2ac2923908cfb09a2aabb08594` |
| `scripts/craci/mariadb-runtime.py` | `26c50dd67281c2af4a6532a8e37805d22f3ed0944cfa5e2656e123bb3a75ed92` |
| `scripts/craci/mariadb-compose.yml` | `05d2c3e34e1a997b43b0f008be90b6d4bdd1c76698084a4f0773c9273ef1fbea` |
| Initial workflow | `0db7e459c56a55b71fde1ee64b4e8ee6b59c3de9111a9cadcf6838df5dbdb041` |
| Workflow with Docker CDN rule | `7cf17663b4e1aa9452e9dadb87957d554bd5bd8e68177a93fb7f79f7894ef421` |

An independent reviewer found no blocking issue in the bounded harnesses or in the six-line network correction, and checked the exact file hashes. Node syntax, Python AST, workflow YAML and embedded network YAML were checked. Later result/document commits preserve these executable bytes; passing historical runs are bound to the commits above, rather than being relabelled as runs on a documentation commit.

## Browser evidence

Each product ran in Chromium, Firefox and WebKit at **1440×1000** and **390×844**. All twelve receipts report empty page-error and denied-request arrays, and pass the horizontal overflow assertion.

**Cala** exercised supported versus withheld investors, issuer/filing deduplication, namesake refusal, contradictory round exclusion, keyboard focus, per-candidate review approval, review invalidation after editing, inclusive dates, reload reset, and an actual downloaded JSON file. Export citations and round IDs, escaped notes and an independently computed evidence digest were checked. Its evidence digest was `28d12b5e69bc709fc55b6a6b30cb91bde509f70b4bfa71008518fb56cb6517c7`.

**Context** exercised before/after decisions (North €480, Coast €540), inventory filtering, cosmetic changes that preserve decisions, failed response bodies even when HTTP status is 200, independent input/policy/evidence digests, review invalidation, keyboard use, reload/last-selected behavior and four actual memo downloads per viewport.

Cala remains **FICTIONAL_FIXTURE** and Context remains **SYNTHETIC_REPLAY**. These are actual browser executions of synthetic product workflows, without live Cala MCP or Context API qualification. Screenshots were generated only in ephemeral runner directories and were not uploaded; the retained evidence consists of logs and JSON receipts.

CRACI's browser-run UI displayed **91 vulnerability findings** despite functional success. These include the browser/system dependency environment; this experiment did not establish application exploitability or remediate each finding. Browser success is not a security clean bill.

## Native architecture evidence

Jobs **132354100492** (x64) and **132354100786** (ARM64) both used Node **v22.23.5**. The harness checked expected architecture and kernel output, then independently asserted nine known answers against the pinned synthetic MariaDB CLI fixture.

Cases covered no prior revision, exact boundaries, before-change/revert boundaries, another page, an unknown page and refusal of an invalid calendar date. Both produced canonical digest:

`6f323fd6052fa020c02de088673774a7373cbc07b5a55a8da5d9779bb0853a6e`

This proves the tested CLI behavior on two native Linux architectures. It does not establish a MariaDB connection, production performance or architecture compatibility for untested programs.

## Cold/warm cache and SBOM evidence

Cold job **132354436993** verified an empty isolated npm cache and a cache miss, installed through the npm preset, validated the repository and saved exactly one cache. Warm job **132354538189** required an exact cache hit, installed with **`npm ci --offline`**, and had only the GitHub network preset.

The graph hash matched:

`33627b52c24cc0b804b940b2d668772e574679eb6908ac2d8cb3a3349bc48977`

The lockfile hash matched:

`fca1e4c5f201ef8f43bcdda22c79190cd3f3d4679bc8b705ae2c40cb7fd627bb`

Installation took **1857 ms cold** and **1516 ms warm** in this one sample. These measurements exclude cache-restore overhead and are not a statistically supported speed claim.

The npm graph contains **138 entries**, including duplicate dependency paths and **57 unversioned optional entries**. It has **68 distinct versioned name/version pairs**, including one local workspace package; do not call this 138 distinct installed packages.

The actual [cache entry](https://platform.craci.com/projects/junction-pets/caches/6629298651489501153) showed **42.2 MiB**, a link to the cold creator, and a warm restoration at **2026-11-14T06:01:27Z**. Downloaded exports:

- [Cold SBOM](craci/experiments-20261114/sbom-132354436993.json)
- [Warm SBOM](craci/experiments-20261114/sbom-132354538189.json)
- [Comparison and dependency mapping](craci/experiments-20261114/cache-sbom-comparison.json)

Both CycloneDX **1.7** exports have **81 components: 74 npm, six GitHub sources/actions and one cache**. They contain the same package URL set, 31 dependency nodes, no duplicate component references and no dangling dependency references. The warm export marks all **74 npm components** `craci:source:restored=true`; the cold export marks them false.

All **67 distinct external npm name/version pairs** in the installed graph appear in both exports. The local workspace node is not an npm registry component. Seven additional npm components appear in the SBOM, so downloaded/observed package evidence must not be treated as an exact inventory of application packages installed at runtime.

**Observed UI discrepancy:** both job overviews displayed **0 packages** and **Complete SBOM certified**, while the downloaded files contained 81 components. Preserve the raw exports and metadata when auditing; the dashboard count alone is unreliable in this observation. Reference-integrity checks are not full CycloneDX schema validation or an independent completeness/security certification.

An additional [older baseline SBOM](craci/experiments-20261114/sbom-132226162145.json) was successfully downloaded from job **132226162145**, run **43524317464**, source **1774ac8d7b6dcee58d8516fcbf923c52a1f71088**. It has 76 components and is explicitly separate historical evidence.

CRACI's [cache completeness guide](https://docs.craci.com/guides/cache-sbom-completeness/) explains the producer/restoration lineage and why unmonitored downloads can weaken coverage. This experiment directly verified the one-producer npm cache path.

## Actual MariaDB findings and handoff to PR #103

The original source DDL and prepared as-of query were executed unchanged. The pinned official linux/amd64 image was:

`mariadb@sha256:75b300c790eec33cd4386d80fc1a938e27604ba70f3eeda25e52874be2aae424`

The runtime identified **11.8.9-MariaDB-ubu2404**, `utf8mb4` client/server encoding and **`utf8mb4_uca1400_ai_ci`** on its text columns. The test uses a unique disposable Compose project, a private internal network, no published host ports and synthetic inputs. Source-byte preservation and cleanup passed.

### Five preserved failures

| Case | Expected by independent oracle and product CLI | Actual unchanged SQL |
| --- | --- | --- |
| `case:Harbor` latest revision | 301 | **302**, belonging to `case:harbor` |
| `case:harbor` before its first revision | NO_EVIDENCE | **301**, belonging to `case:Harbor` |
| `accent:cafe` latest revision | 303 | **304**, belonging to `accent:café` |
| `accent:café` before its first revision | NO_EVIDENCE | **303**, belonging to `accent:cafe` |
| `RuntimeDataset` and `runtimedataset`, revision 801 in each | Both distinct datasets can be inserted | **Duplicate key error 1062** on the second dataset |

The page fixtures use 1 March 2025 UTC; the dataset fixture uses 5 March. The source's `at()`, `reverts()` and `compare()` use strict string identities and preserve the identifiers. Its lowercasing applies to article words, not page/dataset IDs. An independent reviewer confirmed these expectations match the product contract.

**Impact:** the proposed SQL store can return another page's content or invent earlier history for a different accepted identifier. It can also reject an otherwise distinct dataset. This is a product SQL defect discovered by real execution, not a CRACI infrastructure error.

**Recommended owner correction, not yet implemented or verified:** explicitly set `COLLATE utf8mb4_nopad_bin` on `dataset_id` and `page_id`. A query-only binary comparison would leave the primary-key collision. MariaDB's [collation documentation](https://mariadb.com/docs/server/reference/data-types/string-data-types/character-sets/supported-character-sets-and-collations) explains case/accent behavior and NO PAD treatment of trailing spaces; the latter better matches the current exact-string contract. The owner should check all identity columns and add trailing-space and composed/decomposed Unicode regressions.

The successful second dataset insertion enables three additional checks in this harness. An entirely passing follow-up should therefore report **80 checks**, not 77. Preserve this failing source/run and bind a new run to the owner's corrected source commit.

Passed checks included revision boundaries, milliseconds, Unicode parameter round-trip, ambiguous timestamps, duplicate rollback, the distinction between revision and database ingestion time, history after a correction, and preservation of all **15 current/history rows** across an observed container restart. The current/history digest remained `80007aae25c5bb88266f11035de7a296547dff6b034f4c4598dd8a3768e1a5e9`.

Actual disposable MariaDB execution is now verified. A live sponsor database, a licensed Wikipedia dataset, a production importer or external provider integration remains unverified.

### Network finding

The initial [Trace](https://platform.craci.com/projects/junction-pets/jobs/132354442895/trace) allowed `registry-1.docker.io` and `auth.docker.io`, but recorded **12 denied requests** to `production.cloudfront.docker.com` with **no rule**. Docker's [official release notes](https://docs.docker.com/docker-hub/release-notes/) document this CloudFront delivery host, and its [allowlist](https://docs.docker.com/desktop/enterprise/allow-list/) lists it for image pull/push.

Only that exact hostname on TLS port 443 was added to this experiment job. Default-deny, existing presets and the image digest remained unchanged. The retry then downloaded and ran the image. The [initial failure events](craci/experiments-20261114/mariadb-initial-failure.log) remain preserved.

CRACI's [network troubleshooting guide](https://docs.craci.com/guides/network-troubleshooting/) documents missing-rule diagnosis. A direct TLS connection is outside package detection: digest pinning preserves content identity but does not restore package observation. This experiment makes no complete container SBOM claim.

## Running the existing bounded workloads

Use the existing authorized repository and task branch. Each workload checks `CRACI_CREDIT_WINDOW_OPEN` and the cutoff **2026-11-15 17:00 UTC / 19:00 Helsinki**.

```sh
gh workflow run craci-pilot.yml --repo SalesSquad/junction-pets \
  --ref codex/junction-craci-experiments-20261114 \
  -f workload=new-products-browser -f product=all -f browser=all

gh workflow run craci-pilot.yml --repo SalesSquad/junction-pets \
  --ref codex/junction-craci-experiments-20261114 \
  -f workload=native-probe

gh workflow run craci-pilot.yml --repo SalesSquad/junction-pets \
  --ref codex/junction-craci-experiments-20261114 \
  -f workload=cache-proof

gh workflow run craci-pilot.yml --repo SalesSquad/junction-pets \
  --ref codex/junction-craci-experiments-20261114 \
  -f workload=mariadb-runtime
```

These commands reproduce experiments; they are not a request to repeat already verified runs. For a corrected Cala/Context source, select that single product and provide a full `source_sha`; browser selection can narrow a specific repair. The native/cache/MariaDB experiments intentionally pin their baseline source in the workflow, so qualifying a new MariaDB source requires an explicit reviewed source-pin update. The current MariaDB baseline is expected to remain red until the product correction is tested.

## Budget, limitations and next useful work

This task reserved **€10 of the already authorized CRACI credits**. Billing showed **€1,009.48 remaining** at **2026-11-14T06:13:19.588Z**. This is an organization balance, unchanged at the displayed precision; **actual per-job costs remain unknown**, and the display is not evidence that the runs were free. The user-authorized budget/window and stop mechanism remain unchanged.

The useful next work is:

1. **MariaDB owner / PR #103:** correct SQL identity semantics and verify the corrected source with this real database harness. This has an observed defect and a clear expected result.
2. **Existing product owners:** apply the browser journey pattern to meaningful new milestones, with refusal/export/review assertions and current source commits.
3. **Dependency evidence owner:** resolve the zero-package dashboard discrepancy using the retained raw exports; separately assess the browser environment's vulnerability findings.
4. **Shared CI owner:** use measured cache/resource data to choose runner sizes and reuse monitored caches. Measure representative end-to-end times before claiming performance gains.

Product correctness and evidence gaps now provide better targets than repeating the same passing fixtures. Portfolio PR Recovery remains the sole integrator. This PR contains harnesses and evidence; the SQL product correction belongs to its existing owner.

