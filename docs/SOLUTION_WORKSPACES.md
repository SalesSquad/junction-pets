# Build a product or solution with developer agents

This monorepo is a shared development home for Junction solutions. A solution can
contain an application, backend, data pipeline, device integration, research,
demo and submission material, with one or several agents. A company companion
is one reusable part of a solution. Chibi is its production agent host/distribution
integration, not a requirement for building every product component.

## Five-minute start

1. Read root `AGENTS.md`, resolve current main/PR source and check existing owners.
2. Discover products: `node scripts/solution-workspace.mjs list`.
3. Get the selected product's handoff: `node scripts/solution-workspace.mjs brief meta-find-verify`.
4. Read its brief, architecture and progress, then the assigned challenge research.
5. Claim a bounded task in the PR/coordination record; use an isolated task branch.
   Fill the next-task acceptance command before implementation.

For a new product, run on its own task branch from the repository root:

```sh
node scripts/solution-workspace.mjs new my-solution --agent meta --challenge meta
node scripts/solution-workspace.mjs brief my-solution
node scripts/solution-workspace.mjs check
```

Omit `--challenge` for a product without a selected competition. `--agent` selects
an existing company slug under `pets/`. This command creates five files and never
overwrites a prior workspace. It does not start a worker, provision cloud compute,
change provider settings or grant runtime authority. Use an existing authorized
Claude, Codex or other developer executor to work from the generated handoff.

## Where the work belongs

| Concern | Source and owner |
| --- | --- |
| Product-specific implementation, assets, fixtures, demo and submission | `solutions/<solution>/`, assigned solution developer |
| User problem, judging fit, acceptance | Product `README.md` |
| Component boundaries and exact reused PR dependencies | Product `ARCHITECTURE.md` |
| Next task, owner, source, checks, blockers, handoff | Product `PROGRESS.md` plus task PR |
| Discoverable product metadata and planned capability uses | Product `solution.json` |
| Company agent expertise and behavioral evals | Existing `pets/<company>/`, assigned company owner |
| Existing/shared apps, services and collaboration contracts | Existing `apps/`, `services/`, `contracts/`; integrator-owned scope |
| Production identity, consent, private memory and tool/model execution | Private Chibi host |

Existing implementations stay at their current paths; reference their immutable
source and PR instead of copying them into a new solution. Do not move pending
Meta/NVIDIA/Council work or start overlapping writers just to populate a folder.
A solution developer owns its solution directory by default. Widening that scope
requires explicit coordination with the current shared/company owner.

## Combine expertise without coupling all products

Add another existing agent ID to `agentIds`, then a `capabilityUses` entry naming
its declared `capabilityId`, purpose and `status: "planned"`. `check` rejects
unknown, unselected or duplicate references. These references are discovery data;
they neither implement transport nor establish live execution. Concrete pending
Stoa → NVIDIA implementation remains in PR #61 and must be inspected at its current
head/base before reuse. Use the existing collaboration protocol and Chibi host
authority for actual cross-agent calls; do not introduce another message protocol.

Grow reusable expertise through sourced findings, test fixtures, behavioral evals
and bounded changes to the owning agent/service. Product-specific findings remain
in the product workspace until reviewed for reuse. Shared learning is explicit
versioned development, not automatic mixing of private user memories.

## Validation and delivery

| Change | First feedback | Before handoff |
| --- | --- | --- |
| Product metadata/handoff | `node scripts/solution-workspace.mjs check` | Check referenced files and exact source/owner |
| Workspace tooling | `node --test tests/solution-workspace.test.mjs` | Workspace check plus root JS checks |
| Product implementation | Product's explicit acceptance command | Its tests/demo and root gates relevant to changed paths |
| Shared agent/service | Owning module's declared tests | Existing root contributor gates and independent review |

Root checks remain `npm ci --ignore-scripts`, `npm run validate`, `npm test`,
`npm run build`; use existing authorized runners rather than adding GitHub Actions.
Record timings as measured, never as an invented SLA. A `stage` is a developer
declaration, not a verified release or challenge submission. A valid scaffold can
still contain TODOs: the first developer task replaces them with a testable slice.

## Send a developer agent this task

> In SalesSquad/junction-pets, develop solution `<id>`. Resolve current source and
> open PR owners. Run `node scripts/solution-workspace.mjs brief <id>` and follow
> its read list. Take the next task from PROGRESS.md, agree exact owned paths and
> acceptance, implement and verify one vertical slice, push a task branch and
> return a draft PR with source-bound evidence and the next executable task.

The workspace works with any authorized developer executor that can read this
private GitHub repository. It is portable source/tooling, not a newly provisioned
always-on cloud service. Cloud capacity, runtime collaboration and hardware
qualification remain separate observed gates.
