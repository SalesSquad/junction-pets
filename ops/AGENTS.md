# Junction companion development agents

Work ID: JUNCTION-ORCHESTRATION-20261112.

This file governs **developer agents** in the Junction-only monorepo. The
company-specific files at pets/<slug>/AGENTS.md govern **runtime companion
behavior**; they never grant a developer cloud, provider or user permission.

Read [the challenge-source routing](challenge-source-routing-20261113.json) and the assigned company's `CHALLENGE_RESEARCH.md` before admitting another slice. Exact official clauses and recorded coverage are now attached for all34 developers; this record starts no jobs.

## Start from authoritative evidence

1. Read root AGENTS.md, catalog-contract.md, this file, and only the selected
   pet's own pet.json / AGENTS.md / STORY.md / evals.json.
2. Resolve the latest authoritative GitHub branch SHA. If an unrelated PR is
   modifying this pet, coordinate before writing. Chat history and status JSON
   are discovery hints, not authority.
3. Read ops/environments/<company>.json. An environment definition with
   environmentId=null means it is **not dispatch-ready**. The 13 November Pro
   bindings now record 34 actual provider IDs and dated settings readbacks in
   cloud-provisioning-20261113.json. These declarations permit dry-run planning;
   recheck the provider/account and exact source before an authorized task.
   Never fabricate IDs, publish a private repo or transfer credentials.
4. Claim one work item for one pet. ops-work.mjs provides a **single-workspace
   local lease**; it does not coordinate across isolated clouds. For concurrent
   Codex Cloud tasks use separate task branches, strict path ownership and
   remote expected-HEAD checks before publishing.

## Ownership and deliverable

- A pet developer owns pets/<company>/ files only when expressly assigned.
- Shared schemas, package manifests, source locks, exporter, registry, cloud
  environment declarations, CI and dashboard belong to the integrator.
- No developer writes Chibi private runtime. Chibi owns user identity, grants,
  adoption, model execution, memory, payments and policy. This repo publishes
  only an independent companion package and public adapter contract.
- A company pet is never an official representative or an implicit endorsement.
- Do not bypass unavailable CI with another provider, copied private code,
  alternate account, synthetic green status, or relaxed assertions.

## Portable verification

Follow the root AGENTS.md lightweight rule: ordinary code, docs and features
need no required tests, repeat reviews, separate QA workers or per-commit CI
receipts. For a concrete bug or material credentials, company/source provenance,
tenant consent or privileged-integration risk, choose one targeted check or
reviewer when useful. Retain actual project safeguards and merge/release authority.

Available milestone commands are npm ci --ignore-scripts, npm run validate,
npm test, npm run build and node scripts/ops-build-status.mjs. Full suites are
optional; environment checkCommands do not make them mandatory for every task.
Record the exact source commit and actual scope for any results you report.
Model evaluations are a **separate gate**; 204 authored test cases do not mean
204 executed or passed tests. Browser, PostgreSQL, Chibi host, adoption and
provider gates must be marked absent until independently evidenced.

For a failed step classify source defect, missing fixture, environment outage,
credential barrier or protected dependency. Continue independent scoped work
and preserve the failed receipt rather than hiding it.

## Required handoff

For routine changes, put a brief commit/changed-path/risks handoff and next
action in the task PR. For consequential or qualification work, use the
machine-readable record below with only actual check results. Durable
continuation belongs in the PR, not merely a conversation:

~~~yaml
work_id: junction.<company>.<slice>
pet_slug: junction-<company>
agent_id: junction-dev-<company>
source_commit: <exact GitHub SHA>
dirty_baseline: <clean / detailed ownership list>
owned_paths: [pets/<company>/]
branch: codex/junction-<company>-<slice>
committed_head: <SHA or null>
pr_url: <draft PR URL or null>
checks:
  - {name: validate, result: pass|fail|blocked, evidence_url: <URL>}
verified: [<facts proven for this SHA>]
not_verified: [<gates still missing>]
blocker: <owner and exact cause, or null>
next_action: <one executable next step>
~~~

Do not claim an environment is running, a model evaluator has passed or a
recipient has used Chibi unless the related provider/host evidence is linked,
source-bound, and independently rechecked.
