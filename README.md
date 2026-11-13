# Junction Company Companions

34 independently authored, versioned company companions in one private monorepo.
Each has a stable development owner, a bounded source/test slice and a durable
handoff. These are not official company agents, endorsements or live Chibi accounts.

Start with [architecture](ARCHITECTURE.md), [contributor rules](AGENTS.md), then
only the assigned company's [continuation record](docs/DEVELOPER_CONTINUITY.md).
Finnish: *34 yrityskohtaista kumppania; lähdekoodi ja testit eivät tarkoita
julkaistua agenttia, palveluyhteyttä tai jatkuvasti käynnissä olevaa työntekijää.*

## Run and inspect

Requires Node.js 22+, npm and access to this private repository.

```sh
npm ci --ignore-scripts
npm run verify:source
node scripts/ops-development-progress.mjs
node scripts/ops-development-progress.mjs --pet aiven --check
```

`verify:source` runs plugin/content validation, tests, build, ops snapshot,
real company-scope drift checking and whitespace verification. It fails if the
accepted ledger is missing or stale; it never rewrites that ledger to pass.
The last two commands read a
private source checkpoint; they do not dispatch work or contact a provider.
`--check` fails on stale or missing selected company bytes. The full fleet check
is `node scripts/ops-development-progress.mjs --check`.

## Current evidence, one source of truth

[`ops/development-progress.json`](ops/development-progress.json) records every
accepted finite company task: logical owner, actual executor, original reviewed
HEAD/tree/base, PR/integration, original focused/full test receipts, source-scope
digest and one **proposed, not started** follow-up. The
[human index](docs/DEVELOPMENT_QUEUE.md) points to the same records.

Do not copy its historical counts into a claim about current CI or worker
activity. `source-matched` means only that local tracked company bytes/modes/paths
match the recorded digest. It is not authenticated provider, model, host,
browser or recipient acceptance. The reader's qualification fields state this.

| Available source | Not established by it |
| --- | --- |
| 34 independently versioned companion packages and scoped deterministic helpers/tests | Live services, real model quality or company endorsement |
| 204 authored behavior-eval definitions | 204 executed model evaluations |
| Generated skills-only plugin packages and dated private registrations | Current installed versions, Chibi adoption or tool permission |
| Typed Council/dispatch interfaces and synthetic tests | Hosted database, authenticated delegation or signed runtime receipts |
| 34 stable logical developer IDs and historical Cloud environment records | 34 running jobs, a distributed scheduler or fresh environment selectability |

Each company has four required content files (`pet.json`, `AGENTS.md`,
`STORY.md`, `evals.json`) and scoped source tests. Most slices add a deterministic
helper, exact contract and invented example; Aiven's initial slice strengthens
its source/citation contract instead. Helpers are **source-only**: a Node module does not
automatically expose it as a generated plugin tool or Chibi runtime capability.

## Repository map

| Path | Purpose | Write owner |
| --- | --- | --- |
| [`pets/<company>/`](pets/) and `tests/pet-<company>.test.mjs` | Company content, bounded helper, example, contract and tests | One assigned company writer |
| [`plugins/`](plugins/) | Three generated skills-only outputs per company | Assigned company producer scope; shared generator belongs to integrator |
| [`catalog-contract.md`](catalog-contract.md), [`schemas/`](schemas/), [`lib/`](lib/) | Shared package identities, validation and exports | Integrator |
| [`apps/catalog/`](apps/catalog/) | Discovery/preview UI; `npm run dev` | Catalog owner |
| [`contracts/pet-collaboration/v1/`](contracts/pet-collaboration/v1/) | Portable request/receipt interfaces | Contract owner |
| [`services/council/`](services/council/), [`services/dispatch-ledger/`](services/dispatch-ledger/) | Experimental host-injected orchestration and persistence interfaces | Assigned service specialist |
| [`ops/`](ops/), [`apps/mission-control/`](apps/mission-control/) | Private development records, local leases and derived snapshots | Integrator |
| [`config/host-config.json`](config/host-config.json) | Explicit Chibi host readiness; no credentials | Host integrator |

`dist/` is generated, not authored source. Company `AGENTS.md` files are
runtime persona content; root/ops `AGENTS.md` files govern developers.

## Continuation and boundaries

The [worker brief](docs/COMPANY_WORKER_BRIEF.md) is the reusable task contract.
The [Cloud playbook](docs/CLOUD_DEVELOPER_PLAYBOOK.md) covers admission,
capacity, exact-source tests and portable fallback. The
[development system](docs/DEVELOPMENT_SYSTEM.md) maps private control-plane
responsibilities. Every task ends with an independently reviewed PR, preserved
raw evidence, released finite ownership and a new unstarted proposal.

Historical evidence is retained, not rewritten: the
[dated queue](ops/development-queue-20261113.json),
[Cloud provisioning observations](ops/cloud-provisioning-20261113.json),
[baseline integration PR #10](https://github.com/SalesSquad/junction-pets/pull/10)
and [earlier Claude architecture advice](docs/CLAUDE_ARCHITECTURE_REVIEW.md).
These are not current execution approvals.

The separate private [SalesSquad/chibi](https://github.com/SalesSquad/chibi)
repository owns identity, consent, Cedar policy, tenant separation, real
model/tool calls and private memory. Its tested [PR #113](https://github.com/SalesSquad/chibi/pull/113)
seam and [PR #116](https://github.com/SalesSquad/chibi/pull/116) catalog integration
remain disabled for real host/recipient execution. The next runtime proof is an
explicitly authorized sign-in → offer acceptance → bounded task → signed receipt
→ revocation flow, not another synthetic green status.

Optional Council Python checks are documented in its
[README](services/council/README.md). Model, browser, PostgreSQL, recipient and
release gates require their own actual authorized environments. No document,
build or checkpoint authorizes new spending, credential changes, public export,
deployment or a merge outside the owner's approved workflow.
