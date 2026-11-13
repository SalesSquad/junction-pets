# One company, one continuing developer — cloud playbook

**Purpose:** give each of the 34 Junction companions a stable, source-controlled development owner and a recorded Codex Cloud environment identity. This playbook is for the integrator, reviewer and future company agents. The 34 Pro/**Legacy** IDs are in dated source evidence; this is **not** a claim that 34 workers are online or the IDs are selectable in the new Cloud picker. Start with root [`AGENTS.md`](../AGENTS.md), [`ARCHITECTURE.md`](../ARCHITECTURE.md), [`ops/AGENTS.md`](../ops/AGENTS.md), the [durable queue](DEVELOPMENT_QUEUE.md) and the assigned pet only.

## Inventory and current activation truth

[`ops/registry.mjs`](../ops/registry.mjs) validates 34 company manifests under [`ops/environments/`](../ops/environments/) and 34 unique stable agent IDs. For a company slug `mariadb`:

| Identity | Exact convention | Owns |
| --- | --- | --- |
| Companion package | `pets/mariadb/` and `junction-mariadb` | Versioned runtime content and eval definitions |
| Continuing developer | `junction-dev-mariadb` | Logical responsibility for future Mariadb tasks and handoffs |
| Desired Cloud environment | `junction-mariadb` | Reusable published *configuration* when provisioned; not a permanent worker |
| Task branch | `codex/junction-mariadb-<slice>` | One bounded source-committed piece of work |
| Planned code/test/review cohort | Three roles for this pet | **Future staffing**, independent checks; not three currently running jobs |

This produces **34 logical owners, 34 desired configurations and 102 planned roles** across the fleet. It does not create runtime/Cloud access by writing JSON. Each new Cloud task gets an isolated workspace; developer continuity comes from **stable IDs + assigned path + GitHub branch/PR + source-bound receipt + next-action owner**, not a long-lived process or chat.

**Earlier W5 source-bound checkpoint, 13 November 2026:** 33 Cloud manifests were `unprovisioned`; **Aiven** was `published-id-pending`, with owner-observed publication/selectability but `environmentId:null`. At that checkpoint it was **not CLI-dispatch-ready** without an independently observed immutable provider ID. The separate W3 [Codex Cloud Node task](https://chatgpt.com/local/6af64d73-352c-8191-b84d-a8c2dc328042) reported **208/208 Node tests** on source [`be3b9f6`](https://github.com/SalesSquad/junction-pets/commit/be3b9f605752c0d3be790bbb6c1832bda9e96f4c), and a local authorized Python suite reported **104/104**; neither proves the 34 published environments, hosted PostgreSQL/Chibi, or a model evaluation. The independent [W4 Haiku smoke PR #7](https://github.com/SalesSquad/junction-pets/pull/7) is unqualified as a hosted model gate. Always recheck the actual current registry and task HEAD before reporting a new status.

**W8 provisioning update, 13 November 2026:** all 34 Pro/Legacy environments now have actual provider IDs, individual settings readbacks and prior source-bound Cloud task evidence in [the private provisioning record](../ops/cloud-provisioning-20261113.json). The manifests permit dry-run planning; a fresh account/provider/source check and bounded work ownership remain required for each task. This does not qualify Chibi runtime, model evaluations or an autonomous Fleet adapter.

**Actual continuation, 13 November:** the owner used authenticated Pro UI and separately verified `chibi-marketplace-cloud` (containing Junction) for the [first Aiven development task](https://chatgpt.com/local/6af6b453-cd8c-8191-92f7-a8559f0350d3). The per-pet Legacy IDs did **not** appear in the new Cloud task picker. [PR #11](https://github.com/SalesSquad/junction-pets/pull/11) subsequently received an independent source review and was merged at `f1bbd3b7a6b1e93e104a28b559263d068248c332`, after 252/252 full Node tests and 23/23 focused source tests on `48db6f84b504c38cfaa3b03ef1f7638588761f3d`. The [development queue](DEVELOPMENT_QUEUE.md) records Aiven as `reviewed`, **MariaDB/AfterQuery as actual provider-observed tasks**, and **31 queued** with null task URLs. MariaDB source pin was verified at `f1bbd3b7`; AfterQuery was still verifying its requested source in preflight. No live model/Chibi runtime pass is claimed.

## Provision or maintain a dedicated environment

Do these steps **for each company independently**; one blocked company must not halt unrelated work.

1. **Select the actual account and repo.** Use an already authorized authenticated Codex Cloud environment management surface, confirm access to **private** `SalesSquad/junction-pets` and its correct task branch. Never transfer browser session databases, bearer tokens, credentials or personal data between accounts/runners.
2. **Publish the desired configuration.** Name it exactly `junction-<company>`, bind the correct repository and `ops/AGENTS.md` instructions; select a Node 22+ runner with setup `npm ci --ignore-scripts` and project checks `npm run validate`, `npm test`, `npm run build`. Keep optional Python tests isolated. Cloud environment is a reusable setup **not an always-on virtual machine**.
3. **Read back independent provider evidence.** Confirm published/selectable state **and immutable environment ID** plus account/repo/branch access from an authenticated provider surface. If UI shows it published but not the ID, retain `published-id-pending` and `null` ID with an exact observation URL, time, tested SHA and blocker. A plausible name or task URL is **not** an environment ID.
4. **Integrate via the registry owner.** Only the orchestration integrator updates `ops/environments/<company>.json` with schema-valid state, opaque provider ID and evidence. Do not force `ready` for unsupported evidence; validate registry. Keep any source/task-check receipt bound to its original revision.
5. **Run a source-pinned smoke.** Open an actual Cloud task against a dedicated task branch and exact GitHub commit; perform setup, `validate`, `test`, `build` and a safe per-pet read. Record task/job ID, provider evidence URL, runner/tool versions, UTC time and tested SHA. A successful task in a **different** environment does not activate this company.
6. **Assign continuity.** Attach future work requests to the stable `junction-dev-<company>` owner and `pets/<company>/` path. Preserve the last accepted commit, pending PR, failures, next actionable work and review owner. Do **not** persist an unbounded interactive conversation as the only source of truth.

Authenticated Cloud management may require the owner to complete a mandatory sign-in/verification. An unavailable Cloud API is an explicit provisioning blocker, **not** a reason to invent an ID, switch Pro/Plus profiles to evade quotas or silently use a paid external agent API. The [Cloud dispatch script](../scripts/ops-cloud-dispatch.mjs) creates an inspectable **dry-run plan**; it does **not** provision or execute a task.

**Scheduling fallback (13 November):** the owner automation scheduler rejected another always-on fleet task because its **20-active-task limit** was reached. No new recurring company dispatcher exists. The **existing** Junction Mission Control hourly automation now includes a bounded source-completion notification, but it is an event monitor, **not 34 active company developers**. Keep all intended owners and proposed tasks in the [private durable queue](DEVELOPMENT_QUEUE.md); use the authorized integrator, explicit bounded Cloud batches and actual task/PR receipts. Do not disable unrelated automations or infer active execution from the roster.

**Two independent permission planes:** a Codex Cloud task may be allowed to **edit/test repository files** after a verified developer environment, branch and work lease are established. This developer admission grants **zero Chibi recipient/tool/model permissions**. Only the authenticated private Chibi host issues and rechecks tenant-specific runtime consent and Cedar policy. Even a successful developer Cloud run cannot exercise a private Chibi action without separate host authorization.

## Parallel work: ownership, leasing and capacity

| Role | Work mode | Write scope | Acceptance |
| --- | --- | --- | --- |
| Company author (`junction-dev-<slug>`) | Bounded Cloud task per requested slice | `pets/<slug>/` exclusively | Content + citations + tests + commit/PR handoff |
| Company test agent (planned) | Source-pinned independent run | Test fixture/report paths only when assigned | Exact cases, runner and failures; never green by assumption |
| Company reviewer (planned) | Independent, generally read-only | None unless explicitly assigned a repair branch | Findings on actual final diff/evidence |
| Root integrator | One serialized integration lane | Shared schemas, exports, lockfiles, ops registry, cross-pet/service files | No overlap, latest HEAD, decisive tests, staged PR |
| Fleet coordinator (planned/admission owner) | Capacity/ownership control, not an implemented daemon | Durable queue and its own receipts only | Fresh source/lease/task URL and explicit next owner; no phantom running status |

Start with one or two independent pet tasks plus one integrator/reviewer when capacity is verified. Widen based on measured latency, cost, merge rework and authenticated Cloud quotas; **do not launch 34 × 3 jobs** from the mere existence of a roster. Reviewers must be independent of the bytes they verify. Where two specialists touch shared schemas/generators, serialize through the integrator or split by strictly disjoint paths and fixtures.

[`scripts/ops-work.mjs`](../scripts/ops-work.mjs) supports `status`, `claim`, `release`, and guarded `reclaim-stale-lock`. Its atomic lease only coordinates **one shared filesystem**. Two isolated Cloud workspaces do **not** share that mutex. For cross-cloud concurrency, first inspect remote PRs and owner assignments, use disjoint task branches and a **remote expected-HEAD** check before update; on conflict, stop and rebase/review with preserved work. Database fencing tokens (for application dispatch) do not replace Git branch compare-and-swap.

## Source-to-PR cycle and recoverability

1. **Discover:** record GitHub upstream SHA, outstanding PRs, pet version, latest receipts, dirty/unpushed files and owner. If a previous task is paused, inspect its PR and worktree before claiming an overlapping task.
2. **Claim:** create `junction.<slug>.<slice>` work ID and bounded path lease. Pair it with a unique `codex/junction-<slug>-<slice>` branch at the exact base SHA.
3. **Implement:** change only owned paths; update citations/uncertainties and version as appropriate. If host/model or Cloud is unavailable, continue source-only tasks while preserving a `blocked` gate.
4. **Verify:** run the baseline Node commands and targeted services/Python/browser suites as relevant. Mark a missing real model/provider/Chibi gate `blocked` or `not_verified`; **204 authored eval cases are not 204 live passes**. No validator relaxation to hide failures.
5. **Commit and review:** push to the verified task branch, record latest commit SHA/PR HEAD, obtain independent review and rerun decisive checks on final bytes. Previous receipts become `stale` when HEAD changes.
6. **Handoff:** store durable record in task PR/registry, preserve failed logs, set a specific next owner/action and release your local lease. When a new Cloud task starts, it reads this source record and resumes independently of chat history.

Use [`ops/AGENTS.md`](../ops/AGENTS.md) for the **machine-readable YAML handoff schema**, [`ops/README.md`](../ops/README.md) for valid receipts and [`DEVELOPMENT_QUEUE.md`](DEVELOPMENT_QUEUE.md) for the 34 current proposed/observed work items. A minimum handoff includes `work_id`, `agent_id`, exact `source_commit`, dirty baseline, owned paths, branch/committed HEAD, draft PR, checks and evidence URLs, `verified`, `not_verified`, blocker/owner and one next action. Never put user credentials or private conversation transcripts in receipts.

## Recovery and portable fallback

| Failure | Authorized response | Never infer |
| --- | --- | --- |
| Cloud ID is missing | Keep manifest `unprovisioned`/`published-id-pending`; queue a provisioning check with owner and task URL | Desired name or old task means `ready` |
| Cloud task outage/quota | Continue with an **existing authorized** isolated Cloud/local Node runner, pinned SHA and logs; defer provider-qualified work | Portable unit test is a Codex Cloud provider receipt |
| Owner Mac unavailable | Run Node/Python/fixture tests in a verified Cloud; use Mac only for Mac/Apple-specific tasks when actually online and authorized | iCloud storage or SSH automatically wakes an offline Mac |
| PR diverged/another author active | Stop overlap; compare current remote heads, preserve diffs, ask integrator to reassign/rebase safely | Local lease protects every Cloud sandbox |
| PostgreSQL/Aiven/Chibi host unavailable | Run deterministic synthetic contracts and unit tests; mark external gates missing, keep independent pet work moving | Synthetic Council proves signed host receipts |
| Model/reviewer unavailable | Retain authored eval definitions and source/unit evidence; schedule a bounded real provider run/review once available | A Haiku smoke or registration is a finished provider model evaluation |

## First-task prompt template

Supply **actual values**, not placeholders, when dispatching:

```text
Work ID: junction.<company>.<slice>
Repository: private SalesSquad/junction-pets
Verified base SHA: <exact 40-hex commit>
Company/agent: <company> / junction-dev-<company>
Cloud environment: <verified published ID, or explicitly blocked>
Owned paths: pets/<company>/ (no other writers)
Read: root AGENTS.md; ARCHITECTURE.md; ops/AGENTS.md;
      docs/CLOUD_DEVELOPER_PLAYBOOK.md; catalog-contract.md;
      assigned pet's four source files and prior PR/receipt
Deliver: scoped implementation, exact citations/versions,
         task branch, tests, draft PR, independent review findings,
         machine-readable handoff and next_action
Checks: npm ci --ignore-scripts; npm run validate; npm test; npm run build
Do not claim: model execution, Chibi deployment, published Cloud
              environment, company endorsement or user acceptance
              without independent exact-source proof.
```

**Release boundary:** only a separately authorized owner workflow may merge, deploy, publish a private repo, change permissions or spend. The purpose of an autonomous developer fleet is more **verified progress and reproducible recovery**, not reduced consent, weaker gates or fabricated green status. Keep the owner-only [development system](DEVELOPMENT_SYSTEM.md), [Wave 2 historical plan](JUNCTION_SWARM_WAVE2_EXECUTION.md) and root [architecture](../ARCHITECTURE.md) synchronized when real state changes.
