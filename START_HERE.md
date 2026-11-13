# Start here — Junction company agents

Canonical source: **SalesSquad/junction-pets**, private repository. This is the
common entrypoint for a new Codex, Claude or other authorized developer agent.
Use [the machine-readable index](docs/AGENT_SOURCE_INDEX.json) to select one of
the 34 packages and discover pending implementation sources.

## Develop a product or solution

Use [solution workspaces](docs/SOLUTION_WORKSPACES.md) for a complete application, service, data pipeline or challenge demo that reuses one or more company agents. Run `node scripts/solution-workspace.mjs list` and `node scripts/solution-workspace.mjs brief meta-find-verify`. New products get their own bounded developer scope under `solutions/<id>/`; existing apps/services/agent sources keep their current owners and paths.

## Before editing

1. Resolve authenticated current `main`, open PRs and exact source SHAs. Inspect
   dirty/unpushed work and current path ownership. This page is a dated source
   map, not a live scheduler or permission grant.
2. Read [AGENTS.md](AGENTS.md) and [ARCHITECTURE.md](ARCHITECTURE.md). Runtime
   `pets/<company>/AGENTS.md` files are companion content, not developer authority.
3. Select the assigned company in the JSON index. Read only that company's
   `pet.json`, runtime profile, story, evals and `CHALLENGE_RESEARCH.md`, plus
   the relevant service contract. Do not load every company's private context.
4. Check the current PR/path owner before taking a write scope. Use an isolated
   task branch; preserve existing work and the root integrator's shared paths.
5. Record source SHA, work ID, owned paths, checks and next action in the PR.
   Distinguish authored, synthetic, model-observed and real host/device evidence.

## Research now available directly in main

| Need | Source |
| --- | --- |
| 34 company research packets | `pets/<company>/CHALLENGE_RESEARCH.md`, selected through the JSON index |
| Research overview and 19 recordings/transcripts | [Research index](docs/challenge-research/README.md) |
| 19 official main briefs | [Main briefs](docs/challenge-research/official-briefs.md) |
| 19 technical briefs | [Technical briefs](docs/challenge-research/official-tech-briefs.md) |
| Exact platform material links | [Source links](docs/challenge-research/source-links.md) |
| Per-agent research routing | [Routing record](ops/challenge-source-routing-20261113.json) |
| Discord observations | [Discord source snapshot](docs/challenge-research/discord-refresh.md) |
| Latest source-fit corrections | [Corrections](docs/challenge-research/fresh-source-corrections.md) |
| Fable's complete follow-up critique | [Fable delta](docs/challenge-research/fable-delta-review.md) |
| Meta / glasses / ARKit lane | [Meta start page](docs/META_START_HERE.md) |

Research was integrated from reviewed PR #59 at source
`ab3b1b623e6e97e54436b95a62e292e8488687b0`. Official current brief clauses outrank
rough transcripts, analyst proposals and older generic helpers. A recording,
document, task manifest or review recommendation does not establish a working
provider connection, a running worker or challenge eligibility.

## Pending implementation sources

The [JSON index](docs/AGENT_SOURCE_INDEX.json) pins the observed PR heads and
source locations. Recheck their current state: they can change after this snapshot.

| Work | Source / boundary |
| --- | --- |
| Agent composition and Stoa → NVIDIA drawing workflow | [PR61](https://github.com/SalesSquad/junction-pets/pull/61); its source already contains PR56 and PR58. Proposed graph edges are not runtime grants. |
| Meta Find & Verify scan kernel | [PR60](https://github.com/SalesSquad/junction-pets/pull/60); research is in main, executable service remains pending. |
| Provider pilots | [PR57](https://github.com/SalesSquad/junction-pets/pull/57); development observations do not install production routing. |
| Upstream Aiven provenance | [PR55](https://github.com/SalesSquad/junction-pets/pull/55). |
| Accepted-source progress ledger | [PR54](https://github.com/SalesSquad/junction-pets/pull/54), including PR34; final review disposition remains separate. |

The current main `docs/DEVELOPMENT_QUEUE.md` includes historical checkpoints.
Do not treat an old running/queued count as the current worker state. The private
Chibi repository owns production identity, consent, private memory, model/tool
execution and signed receipts; this repository owns companion sources and
integration contracts.

## Source-bound continuation

For read-only inspection of a pending extension, fetch its PR ref through the
authorized GitHub connection and read the recorded SHA/path. Do not switch a shared
checkout, copy credentials, or silently treat another branch's code as main.
Independent company work may proceed only after current ownership and source are
checked; cross-package integration remains serialized through its owner.

Use the repository's declared checks for the paths changed. A README count is
historical evidence bound to its recorded source, not a fresh test run. Publish
owned changes on a task branch, bind independent review to the final bytes, and
carry any missing live provider/device/host gate as a concrete next action.
