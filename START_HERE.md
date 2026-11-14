# Start here — Junction company agents

Canonical source: **SalesSquad/junction-pets**, private repository. This is the
common entrypoint for a new Codex, Claude or other authorized developer agent.
Use [the machine-readable index](docs/AGENT_SOURCE_INDEX.json) to select one of
the 34 packages and discover source provenance. For live implementation and PR
state, read GitHub's current main HEAD and PRs, then follow
[the sync contract](docs/SPACE_SYNC_CONTRACT.md).

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
5. For ordinary development, note branch/commit, changed scope and next action.
   Checks or independent review are optional unless concrete risk or real
   qualification requires them. Never conflate synthetic and actual host evidence.

## Google Junction temporary event account (14–15 November)

The organizer issued a temporary high-quota **Google account/password, not an API key**, to the registered Junction team. For permissible use, expiry, export and **secure per-agent executor routing without raw credentials**, see [Google Junction event account](docs/GOOGLE_JUNCTION_EVENT_ACCOUNT.md). No Google API key, console login, active quotas or agent connection is verified merely by this source note.

## Personal Gemini API CLI — Verda-style trusted-host route (14 November)

The owner's **personal** Google AI Studio key `Junction-2026-Gemini-Agent-Mesh` is distinct from the **temporary** Google Junction event account above. The personal key was verified on MBP (authenticated model list HTTP 200, prior tiny inference HTTP 200) and kept in owner-local macOS Keychain. Agent guidance and runnable source are in private [SalesSquad/agents PR #120](https://github.com/SalesSquad/agents/pull/120), especially `docs/gemini-junction.md` and `cloud-services/google-gemini-personal/README.md`.

**Authorized agents:** discover RDC `list_devices`, select the actually online MacBook Pro, read its RDC skill/shared rules, then on that MBP call `/Users/mikaelervamaa/.local/bin/gemini-agent status` or `inventory` (one read-only model catalog request). `probe` makes **one explicit, bounded** generation test and is never automatic/hourly. Agents without separately verified RDC cannot invoke the key merely by reading this page. No key, Mac Keychain material, env token or account session is copied to Mini, Claude, Codex Cloud or Chibi. This is not a deployment or a global API grant.

## Shared source snapshot for every agent

Read [current shared sources](docs/challenge-research/CURRENT_SOURCES.md) and its [portable JSON catalog](docs/challenge-research/current-source-catalog.json) before company implementation. The 14 November snapshot contains full briefs and newer sponsor clarifications, including AfterQuery's Harbor delivery requirement and withdrawal of inference credits. Each agent in the source index has a `partnerEvidenceKey`; existing sessions must fetch and reread the current source. Raw discussions remain separately authorized Space evidence.

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

## Source integration status (verified 14 November 2026, 01:28 EET)

The [JSON index](docs/AGENT_SOURCE_INDEX.json) pins source SHA and last observed
PR states. They can change; resolve live PR and main HEAD before a task. In
particular, a still-open origin PR does not mean its code is absent from main.

| Work | Verified source / boundary |
| --- | --- |
| Agent composition and Stoa → NVIDIA drawing workflow | Original [PR61](https://github.com/SalesSquad/junction-pets/pull/61) still **open**, but implementation source **already in main via merged [PR66](https://github.com/SalesSquad/junction-pets/pull/66)** (commit `cfe5b3ea7107c3f4f4a2422e71e51121fd466471`). Graph edges are proposals, not runtime grants. |
| Meta Find & Verify scan kernel | Original [PR60](https://github.com/SalesSquad/junction-pets/pull/60) **merged**, source also integrated via [PR68](https://github.com/SalesSquad/junction-pets/pull/68) (commit `92c107468f06ca810ec711480057353ddda3e64c`). Live device/provider behavior is not automatically verified by merged source. |
| NVIDIA / companion tooling | [PR58](https://github.com/SalesSquad/junction-pets/pull/58) and [PR56](https://github.com/SalesSquad/junction-pets/pull/56) **merged**. Verify the precise resulting code and tests separately from production host wiring. |
| Provider pilots | [PR57](https://github.com/SalesSquad/junction-pets/pull/57); development observations do not install production routing. |
| Upstream Aiven provenance | [PR55](https://github.com/SalesSquad/junction-pets/pull/55) **merged**. |
| Accepted-source progress ledger | [PR54](https://github.com/SalesSquad/junction-pets/pull/54), including PR34; final review disposition remains separate. |

At the same authenticated readback, additional open work included
[PR70](https://github.com/SalesSquad/junction-pets/pull/70) (Meta trained
candidate scoring), [PR67](https://github.com/SalesSquad/junction-pets/pull/67)
(Verda trials), [PR64](https://github.com/SalesSquad/junction-pets/pull/64)
(product workspaces), [PR57](https://github.com/SalesSquad/junction-pets/pull/57)
(provider pilots), [PR54](https://github.com/SalesSquad/junction-pets/pull/54)
(continuity), and [PR34](https://github.com/SalesSquad/junction-pets/pull/34)
(private developer reader). Do not mistake this observed list for a live queue.

The pinned main at this readback was
`1774ac8d7b6dcee58d8516fcbf923c52a1f71088`.
The current main `docs/DEVELOPMENT_QUEUE.md` includes historical checkpoints.
Do not treat an old running/queued count as the current worker state. The private
Chibi repository owns production identity, consent, private memory, model/tool
execution and signed receipts; this repository owns companion sources and
integration contracts.

## Space sync and machine-readable verification

One Page-managed controller maintains the 53-page Junction Space. Its scheduled
reconciler polls current GitHub state hourly; a separate PR-event worker reacts
to supported pull-request lifecycle, new-commit and review events. A PR event
does not cover unrelated direct pushes to main, so the hourly pass is essential.
Source status in this file is **not a live monitor**.

After source-map changes, run `npm run source-sync:check` (included in
`npm run validate`). The offline check covers 34 agent routes, 19 main and
19 technology brief links, and the current 19+16 canonical Space card IDs.
It cannot prove Pages API access, a hosted automation run, cloud CI, model
behavior or a live Junction submission.

## Source-bound continuation

For read-only inspection of a pending extension, fetch its PR ref through the
authorized GitHub connection and read the recorded SHA/path. Do not switch a shared
checkout, copy credentials, or silently treat another branch's code as main.
Independent company work may proceed only after current ownership and source are
checked; cross-package integration remains serialized through its owner.

Use a relevant focused check only if the changed behavior poses a real risk;
ordinary docs/company-agent development needs no testing cycle. A README count is
historical evidence bound to its recorded source, not a fresh test run. Publish
owned changes on a task branch, bind independent review to the final bytes, and
carry any missing live provider/device/host gate as a concrete next action.

