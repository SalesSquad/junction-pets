# Junction Company Companions

**34 independently authored, versioned company companions for Junction, with one auditable monorepo and a separate Chibi runtime.** This is the private source repository [`SalesSquad/junction-pets`](https://github.com/SalesSquad/junction-pets). A companion can explain public technical documentation, inspect material supplied by its user and suggest a bounded next step. It is **not** an official company representative, endorsement, published ChatGPT agent or automatically functioning Chibi account.

Start with [ARCHITECTURE.md](ARCHITECTURE.md) for boundaries, [AGENTS.md](AGENTS.md) for contributor rules, and the [cloud developer playbook](docs/CLOUD_DEVELOPER_PLAYBOOK.md) for assigning and continuing independent company work. Finnish overview: *34 yrityskohtaista, itsenäisesti laadittua kumppania; yritys- tai Chibi-julkaisua ei pidä päätellä valmiista lähdekoodista.*

## Meta scanning: start here

For the Meta challenge, glasses/ARKit research, official Discord resources and the Chibi Lens agent lane, read [META_START_HERE.md](docs/META_START_HERE.md). It links the original messages, SDK repositories, simulator, full technical research, architecture, runnable demo and exact-source validation. This is a developer source map; it grants no device or runtime permissions.

## Source-bound status

**W8 provisioning update, 13 November 2026:** all 34 Pro/Legacy environments now have actual provider IDs, individual settings readbacks and prior source-bound Cloud task evidence in [the private provisioning record](ops/cloud-provisioning-20261113.json). The manifests permit dry-run planning; a fresh account/provider/source check and bounded work ownership remain required for each task. This does not qualify Chibi runtime, model evaluations or an autonomous Fleet adapter.

**Continuation checkpoint, 13 November 2026:** the [private 34-pet work queue](docs/DEVELOPMENT_QUEUE.md) records one completed/reviewed Aiven source slice ([PR #11](https://github.com/SalesSquad/junction-pets/pull/11), merged at `f1bbd3b7a6b1e93e104a28b559263d068248c332`), **two owner-observed running Cloud development tasks** (MariaDB, AfterQuery) and **31 queued/unstarted** slices. The first [actual Pro Cloud Aiven developer task](https://chatgpt.com/local/6af6b453-cd8c-8191-92f7-a8559f0350d3) used the separately selected `chibi-marketplace-cloud` executor; the historical 34 Pro/Legacy environment IDs were not visible in the newly observed Cloud task picker. Aiven's reviewed author HEAD `48db6f84b504c38cfaa3b03ef1f7638588761f3d` had 252/252 full Node tests and 23/23 focused checks, **not** model/recipient acceptance. MariaDB's source checkout was worker-verified at `f1bbd3b7`; AfterQuery's checkout verification remained pending when its task URL was observed. The queue is a versioned work-item record, not a scheduler.

The table below describes the **13 November 2026 source checkpoint**, including the W8 provisioning records. Recorded configuration is not a fresh provider readback, an active task or a production deployment. Recheck the exact checkout and provider state before dispatch.

| Capability | Verified or authored | Still not proven |
| --- | --- | --- |
| Companion content | 34 package directories, four source files per companion, three use cases per package; 34 private Plugin Creator registrations | Company sponsorship, recipient installation, live Chibi use |
| Development ownership | 34 distinct `junction-dev-<company>` logical IDs, 34 recorded provider environment IDs and a planning-only 102-role continuity roster | Fresh task admission, a cross-cloud writer lease, or 34 currently running developers |
| Evaluation | 204 authored behavior cases, deterministic source suites and an opt-in [public Haiku smoke](services/eval-runner/HAIKU_PUBLIC_SMOKE.md) | 204 real model evaluations or independent live provider/recipient acceptance; a dry-run smoke is not model execution |
| Council and contracts | Versioned collaboration schemas and an experimental Aiven-inspired LangGraph host-injected adapter | Production delegation, tenant grants, model execution, PostgreSQL continuity and host-signed receipts |
| Chibi integration | Export/adapter interface; private [Chibi PR #113](https://github.com/SalesSquad/chibi/pull/113) merged at `5913e0aa` with 119 Rust unit tests passed, four PostgreSQL tests ignored and 12 targeted collaboration checks passed; [PR #116](https://github.com/SalesSquad/chibi/pull/116) merged the disabled seam into the source catalog | Active authenticated host route, database/recipient integration, adoption, activated grants, signed runtime receipts or real delegated model task |

Historical evidence is preserved separately: W3 commit [`be3b9f6`](https://github.com/SalesSquad/junction-pets/commit/be3b9f605752c0d3be790bbb6c1832bda9e96f4c) reported 208/208 Node checks in [its Codex Cloud task](https://chatgpt.com/local/6af64d73-352c-8191-b84d-a8c2dc328042) and 104/104 Python checks in an authorized local runner. PR #9 commit [`92a0be0`](https://github.com/SalesSquad/junction-pets/commit/92a0be0ef0f0e9066ec2672a320530eecdb12cec) has a later [Cloud task receipt](https://chatgpt.com/codex/tasks/task_e_6af679f222048326be81704ff0c93d9d). These receipts qualify only their recorded source and commands; they do not establish current worker activity or qualify a later commit. Current host status remains in [`config/host-config.json`](config/host-config.json); authored behavior cases are specified in [BEHAVIOR_EVALS.md](docs/BEHAVIOR_EVALS.md).

## Quick start

Requires Node.js 22+, npm and access to this private repository:

```sh
npm ci --ignore-scripts
npm run validate
npm test
npm run build
```

`npm run dev` starts the catalog development UI. `npm run test:wave2` runs the focused contract/service/owner UI suites. `npm run ops:status` derives a **private, dated snapshot** from source manifests and receipts. `npm run ops:developers` prints the source-bound, **planning-only** 34-developer/102-role continuity roster from a clean Git checkout. The separate [durable development queue](docs/DEVELOPMENT_QUEUE.md) preserves actual-versus-planned company slices. `npm run ops:preview` builds the separate owner-only Mission Control and synthetic Council previews. No command above starts the queued tasks, deploys Chibi, grants user access or executes the 204 model cases.

The optional Python Council test environment is documented in [`services/council/README.md`](services/council/README.md). It needs a separate Python 3.12/3.13 environment and host-injected security dependencies; a passing unit test does not create an authenticated host.

## Repository map

| Path | Source of truth / purpose | Owner |
| --- | --- | --- |
| [`pets/<company>/`](pets/) | `pet.json`, `AGENTS.md`, `STORY.md`, `evals.json` and cited public source; independent package version | Assigned single pet writer |
| [`evidence/company-roster.json`](evidence/company-roster.json) | The 34-company roster, categories and uncertainty | Research/integrator |
| [`catalog-contract.md`](catalog-contract.md), [`schemas/`](schemas/) | Shared package and adapter contracts | Integrator |
| [`contracts/pet-collaboration/v1/`](contracts/pet-collaboration/v1/) | Portable request/receipt schemas; no identity or grant issuer | Contract integrator |
| [`services/council/`](services/council/), [`services/dispatch-ledger/`](services/dispatch-ledger/) | Experimental delegated orchestration and durable ledger interfaces | Service specialists/integrator |
| [`apps/catalog/`](apps/catalog/) | Public-facing discovery UI, previews and QR link | Catalog owner |
| [`apps/mission-control/`](apps/mission-control/), [`ops/`](ops/) | Private orchestration UI, desired Cloud fleet, leases and receipts | Orchestration integrator |
| [`plugins/`](plugins/) | Generated, source-bound skills-only companion plugin packages | Plugin integrator |
| [`lib/`](lib/), [`scripts/`](scripts/), [`tests/`](tests/) | Shared model, exporters, generators and test gates | Integrator; a pet test writer may own only explicitly leased `tests/pet-<company>.test.mjs` |
| [`config/host-config.json`](config/host-config.json) | Chibi host address/readiness; no user credentials | Host integrator |

Generated `dist/` outputs are **not** authored source. A pet's `AGENTS.md` is its **runtime persona**; root `AGENTS.md` and [`ops/AGENTS.md`](ops/AGENTS.md) instruct **development workers**. Do not confuse these three roles.

## One company, one continuing development lane

Every company has a stable logical developer ID (`junction-dev-<company>`), desired environment name (`junction-<company>`), an owned path (`pets/<company>/`) and a branch pattern (`codex/junction-<company>-*`). These are machine-validated in [`ops/registry.mjs`](ops/registry.mjs). Each developer resumes from a **GitHub SHA + work ID + receipt + open PR**, never from an assumed persistent VM or a remembered chat. A Codex Cloud environment is reusable configuration; a new task is an isolated workspace. Environments must be actually published, their opaque IDs verified, and repo access checked before dispatch.

The wider plan describes **102 eventual code/test/review roles** (three per company), **not 102 concurrently running workers**. Start with a small verified cohort, limit execution to real capacity, use isolated task branches and disjoint paths, and let one integrator own cross-package files. The [playbook](docs/CLOUD_DEVELOPER_PLAYBOOK.md) contains onboarding, lease limits, evidence and fallback rules; the [development system](docs/DEVELOPMENT_SYSTEM.md) contains Mission Control contracts. The [Wave 2 execution plan](docs/JUNCTION_SWARM_WAVE2_EXECUTION.md) is a **dated plan**; verify its targets against the current GitHub source rather than treating them as achieved.

## Product boundary and next proof

This repository owns independently authored companion content, the catalog, typed Council contracts, synthetic demos and Chibi export adapters. The private [`SalesSquad/chibi`](https://github.com/SalesSquad/chibi) repository **alone** owns accounts, tenant separation, consent, Cedar policy, offer/adoption, tool/model execution, conversations and private memory. LangGraph coordinates proposed steps but cannot mint Chibi grants. QR codes select a product URL; they carry no credentials or authorization.

The next recipient-facing proof is one exact version of one companion passing the full **Chibi sign-in → explicit offer acceptance → permitted activation → real bounded task → auditable receipt** path. Until then, label catalog, Council, model and adoption examples as authored/synthetic/test-only. See [CHIBI_INTEGRATION.md](docs/CHIBI_INTEGRATION.md), [JUNCTION_SUBMISSION.md](docs/JUNCTION_SUBMISSION.md), [EVENT_GUIDE.md](docs/EVENT_GUIDE.md), the [34 companions](docs/COMPANIONS.md) and [the private worker system](docs/DEVELOPMENT_SYSTEM.md).

The Junction package source is private. Any challenge submission, public export, licensing change, Chibi installation, spend, merge or deployment requires its own approved workflow; a passing build is not that approval.
