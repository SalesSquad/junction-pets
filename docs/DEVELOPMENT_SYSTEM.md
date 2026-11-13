# Development system

Canonical source: private `SalesSquad/junction-pets`.
Runtime boundary: separate private `SalesSquad/chibi`.
This document describes the control plane; [AGENTS.md](../AGENTS.md) is the
contributor contract and the [Cloud playbook](CLOUD_DEVELOPER_PLAYBOOK.md) is the
operational procedure.

## Authoritative records

| Order | Record | Use |
| --- | --- | --- |
| 1 | Authenticated GitHub source and PR HEAD/tree | Resolve what code actually exists and who owns overlapping work |
| 2 | [Development progress](../ops/development-progress.json) plus linked PR receipts | Recover each accepted finite task, original tests/review, actual executor and next unstarted action |
| 3 | [Environment manifests](../ops/environments/) and dated provider observations | Discover desired configuration; recheck current account/repo/selectability before execution |
| 4 | Generated Mission Control/page/status output | Display a dated projection, never grant authority or assert live worker activity |

The progress reader's local digest check is not authentication of GitHub, the
receipt or the executor. A native attached-cloud run remains `native`, not
Codex Cloud merely because the machine is hosted. Model eval, deployment and
Chibi recipient evidence are separate kinds of proof.

## Ownership map

| Scope | Writer | Notes |
| --- | --- | --- |
| `pets/<company>/**`, its company test, three generated plugin outputs | One admitted company developer | Runtime persona is content, not developer authority |
| Shared schema/contracts, libraries, producers, root manifests/locks | Integrator or explicitly assigned disjoint specialist | One owner for overlaps and generated integration |
| `ops/development-progress.json` and current docs/index | Integrator | Rebind only independently reviewed source; preserve original counts and receipts |
| `ops/environments/`, `ops/receipts/`, `ops/work/` | Orchestration integrator | Historical configuration, source evidence and bounded work/lease records |
| `apps/mission-control/` and `scripts/ops-*.mjs` | Assigned private control-plane owner | Never public-export the internal ledger |
| `apps/catalog/` | Catalog owner | Public-safe discovery/preview only |
| Chibi account/runtime code and secrets | Separate Chibi owner | Not vendored or implicitly authorized by Junction work |

Every company has stable `junction-dev-<company>` responsibility, but each task
is finite. A logical owner, reusable Cloud configuration, active process and
runtime companion are four different things. The older 102-role roster is a
staffing plan, not 102 active jobs.

## Bounded execution loop

1. Read the compact summary and assigned record via
   `node scripts/ops-development-progress.mjs --pet <company>`.
2. Resolve fresh remote source/PR heads and surviving work. Admit one work ID,
   actual executor, expected branch HEAD, disjoint scope, checks and budget.
3. Claim local ownership where applicable; use separate branches and guarded
   remote updates for isolated Clouds. A filesystem lease is not distributed.
4. Implement and test a bounded slice under [the worker brief](COMPANY_WORKER_BRIEF.md).
   Keep unknown/external gates explicit. Preserve genuine failures.
5. Publish source-bound evidence, independently review final bytes and rerun on
   canonical remote HEAD. One integrator validates the combined tree before an
   authorized merge; never equate local statuses with hosted CI.
6. Release the writer. The integrator updates the accepted progress record and
   relevant docs, computes scope from those reviewed bytes, runs `--check`, and
   preserves one **proposed-not-started** continuation.

The final combined gate is `npm run verify:source`: existing portable checks
plus the real ledger drift check. It never auto-refreshes accepted hashes.

An executor failure blocks its lane, not disjoint portable work. Existing
authorized Node/Python/Rust environments can verify synthetic source without
the owner's Mac. A missing host/model/database is not solved by invented IDs,
copied sessions, account rotation, synthetic production claims or weaker tests.

## Historical Cloud and scheduling evidence

The [13 November provisioning record](../ops/cloud-provisioning-20261113.json)
preserves 34 Pro/Legacy environment IDs and prior source-bound observations.
They were not selectable as those same IDs in the subsequently observed new
Cloud picker. Actual first tasks selected the separately verified
`chibi-marketplace-cloud`; later portable fallback tasks record their native
executor explicitly. Each future task must recheck its actual selected runner.

The [dated early queue](../ops/development-queue-20261113.json) preserves the
earlier Aiven/MariaDB/AfterQuery checkpoint. It is not the current work register.
Do not overwrite that historical evidence or keep its old “running” state alive.

A separate recurring fleet task was not created when the scheduler reported its
20-active-task cap. The existing Junction Mission Control monitor gained a
bounded completion check, **not** a job dispatcher. Do not disable unrelated
automations or imply that a JSON roster launches work.

## Private presentation and runtime separation

`npm run ops:status`, `ops:developers`, `ops:preview` and `ops:page:build`
derive snapshots/plans. They do not refresh authenticated Cloud state, execute
the 204 model cases, activate a Chibi grant or deploy a product.
The public catalog build remains separate from private Mission Control and
synthetic collaboration previews.

The existing Junction Mission Control Site has included an external viewer;
never post this private development ledger there. Any later Site feed needs an
authorized, sanitized read-only projection and verified sharing. Source/PR
records—not a chat, Page or embedded snapshot—remain the recoverable handoff.

Council orchestration and dispatch persistence are host-injected interfaces.
A valid request/receipt schema, private plugin registration or source catalog
entry grants no Chibi account, tenant access, memory or real provider execution.
See [architecture](../ARCHITECTURE.md), [Chibi integration](CHIBI_INTEGRATION.md)
and [submission boundary](JUNCTION_SUBMISSION.md).

## Review influence and measurement

[Earlier Claude advice](CLAUDE_ARCHITECTURE_REVIEW.md) supported separating
logical ownership, scheduling and host permission. It was not a current source
approval. Actual author/reviewer identities and exact HEADs live in PR receipts.
Keep completion, delivery, integration and rework separate; preserve measured
calls/counts and report unknown cost as unknown. No universal model ranking or
perpetual worker assumption is part of this architecture.
