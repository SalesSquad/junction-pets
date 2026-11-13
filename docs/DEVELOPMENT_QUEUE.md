# Junction developer queue — 13 November 2026

This is the **durable work-item register**, not a Codex Cloud launcher, a recurring scheduler or an attestation. Its machine-readable source is [`ops/development-queue-20261113.json`](../ops/development-queue-20261113.json). The stable identities follow [`ops/environments/`](../ops/environments/) and [`ops/AGENTS.md`](../ops/AGENTS.md); the queue is private operational metadata and **must not be included in the public Junction submission**.

## Source-bound checkpoint

| Fact | Checkpoint | Limit |
| --- | --- | --- |
| Planning baseline | [Junction main `62a63ce8`](https://github.com/SalesSquad/junction-pets/commit/62a63ce8b5c560c5e55fdffe16fa7507382f4fd2) | A queued item must fetch fresh remote main before execution. |
| Aiven first actual Pro Cloud development task | [Owner-observed task](https://chatgpt.com/local/6af6b453-cd8c-8191-92f7-a8559f0350d3) | Task URL is provider task evidence, **not** an environment ID or a model-evaluation/Chibi permission receipt. |
| Aiven source result | [Junction PR #11](https://github.com/SalesSquad/junction-pets/pull/11), reviewed author HEAD `48db6f84b504c38cfaa3b03ef1f7638588761f3d`, merged at `f1bbd3b7a6b1e93e104a28b559263d068248c332` | Source checks: 252/252 full Node and 23/23 focused; no real hosted model/Chibi acceptance. |
| MariaDB | [Actual running Cloud task](https://chatgpt.com/local/6af6b88c-3af4-8191-a1f3-84bb3805b0e3), branch `codex/junction-mariadb-explain-evidence-20261113` | Worker verified requested source `f1bbd3b7`, task running; no PR/pass yet. |
| AfterQuery | [Actual running Cloud task](https://chatgpt.com/local/6af6b96a-4ed0-8191-9f36-61dcf4ac70cf), branch `codex/junction-afterquery-failure-rubric-20261113` | Requested source `f1bbd3b7`; worker checkout preflight not yet evidenced at observation; no PR/pass yet. |
| Remaining 31 companies | Queued, distinct proposed branches and owned paths | No task URL, PR, running developer or source-test pass is claimed. |
| Dedicated environment bindings | 34 dated Pro/**Legacy** IDs from [the provider record](../ops/cloud-provisioning-20261113.json) | Legacy IDs were not selectable in the newly observed Cloud task picker. Aiven actually used separately verified `chibi-marketplace-cloud`. |
| Monitoring | Existing hourly Junction Mission Control automation has source-completion monitoring | The 20-active-task scheduler cap blocked a **new** automation. Monitoring is not 34 continuing development jobs. |

This register has 34 unique `petSlug`, `agentId`, `branch` and legacy environment IDs. Status is **one reviewed, two running, 31 queued** at the observation. `reviewed` means Aiven's source slice was merged and reviewed, not that its model or recipient ran. `running` is based on observed Cloud task URLs; it does not itself certify each runner's source verification, test outcomes or completed code. The two evidence classes—recorded Legacy environment settings and actual new-Cloud development tasks—are intentionally separate. Source-only fixtures and 204 authored behavior-evaluation cases are not executed model evaluations.

## Ownership and task admission

- One company code writer owns `pets/<company>/` only. Its separately authorized test writer owns only `tests/pet-<company>.test.mjs`. These two roles share one **exclusive company writer lease**; do not dispatch both to write concurrently. All proposed test files were absent from the planning-base main, except Aiven's new test file arrives in merged PR #11.
- The integrator owns shared `ops/`, `schemas/`, `scripts/`, `plugins/`, root manifests and generated outputs. Pet workers must not regenerate and commit shared plugin files as part of their independent scope without explicit integration ownership.
- A planned branch is **not created** by this JSON. For each actual admission: independently verify current GitHub main/PRs, provider account and selected executor, exact base SHA, clean task branch, quota/capacity and spend authority. The coordinator records one exclusive company-writer assignment in the durable queue/PR; writers use disjoint branches/paths and guarded remote expected-HEAD updates. No distributed lease issuer is deployed, and a local lease is not a cross-cloud mutex. Record the actual Cloud task URL, new task branch HEAD, tests and PR. If Legacy `junction-<company>` is absent in the current picker, use an already verified authorized environment only when that environment contains this repo; preserve the Legacy binding without pretending it was selected.
- Run `npm ci --ignore-scripts`, the exact per-pet focused Node test, `npm run validate`, `npm test`, `npm run build`. Mark failures or unavailable gates with exact source and command; do not turn authored eval cases into model PASS claims.
- The author commits within its branch, an **independent** reviewer checks exact final bytes, and the integrator owns shared generated output and the guarded merge. Keep the durable PR/handoff link so the next task can resume without a chat session.

## Recommended bounded order

1. **Aiven:** already source-reviewed and merged; no second author. Live model and recipient integration are separate, not yet admitted.
2. **MariaDB and AfterQuery:** read-only synthetic SQL EXPLAIN/evidence analysis; synthetic failed-agent trace/rubric. They enable an evidence-focused Aiven → MariaDB → AfterQuery council demonstration without claiming live cross-pet execution.
3. **NVIDIA, Meta and Rokoko:** synthetic 3D workload benchmark, wearable permission/fallback, and motion-retargeting quality proofs. Connect them only through the existing synthetic Council contract until Chibi host authorization and signed runtime receipts exist.
4. **Remaining 28:** individual scoped tasks from the queue, admitted in batches after measured capacity and integration rework.

Start with **one or two company development tasks** plus one independent reviewer/integrator, widen only when actual hosted provider throughput, source tests and nonoverlap are evidenced. 34 environment manifests and 102 logical code/test/review roles are *not* 34 active jobs or 102 autonomous processes.

## Safe continuation record

Each completed slice must update the queue (integrator-owned) with: exact plan base and newly admitted source SHA, work ID and unique attempt, coordinator assignment and expected remote HEAD, selected actual environment, actual task URL, task branch and reviewed HEAD, PR/merge URL, executed checks/results, blocker and next owner. A future distributed lease/fence may be recorded only after an actual issuer is deployed and verified; it is not a current prerequisite. Preserve dated historic receipts; don't overwrite them with green status from a different SHA. Use [`docs/CLOUD_DEVELOPER_PLAYBOOK.md`](CLOUD_DEVELOPER_PLAYBOOK.md) for the handoff contract and [`docs/BEHAVIOR_EVALS.md`](BEHAVIOR_EVALS.md) for the separate model-evaluation evidence standard.
