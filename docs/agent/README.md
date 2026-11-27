<!-- agent-layout:map:v1 -->
# Agent guide for SalesSquad/junction-pets

## Purpose and ownership

This guide covers work in `SalesSquad/junction-pets`.
Company companions for Junction: versioned pet packages and Chibi marketplace integration
Start with the project description in [`README.md`](../../README.md).
Confirm the responsible maintainer through the current project assignment or pull request.

## Source map

- Project contents — [`lib`](../../lib), [`apps`](../../apps), [`services`](../../services), [`templates`](../../templates), [`scripts`](../../scripts).
- Project documents — [`START_HERE.md`](../../START_HERE.md), [`catalog-contract.md`](../../catalog-contract.md), [`docs/AGENT_COMPOSITION.md`](../../docs/AGENT_COMPOSITION.md).
- Project definition — [`package.json`](../../package.json).
- Verification — [`tests`](../../tests), [`.github/workflows/craci-ci.yml`](../../.github/workflows/craci-ci.yml), [`.github/workflows/craci-exa.yml`](../../.github/workflows/craci-exa.yml), [`.github/workflows/craci-hf-intents.yml`](../../.github/workflows/craci-hf-intents.yml).
- Local instructions — [`CLAUDE.md`](../../CLAUDE.md).

## Develop and verify

Read [`README.md`](../../README.md) before selecting a change.
The root [`package.json`](../../package.json) declares `npm run test`. Review its implementation and run the relevant check for the change.

## Research and handoff

Check prior issues, pull requests, source material and verified results before repeating work. Keep private inputs with their authorized owner. Record the source revision, result, evidence and remaining limits in the current task or pull request.
<!-- agent-layout:map:end sha256=8211d1b224d1eecf31f956d040792d0691cf49514f2c28538c230192b7f39d9c -->

## Land a change

From a clean task branch, install the locked dependencies with `npm ci --ignore-scripts` and run `npm run land`. The project helper validates the current source, runs the parallel test suite and squash-merges the PR pinned to its tested head. GitHub Actions and the historical CRACI workflows listed above are disabled. See [the active contributor contract](../../AGENTS.md) and [the landing helper](../../scripts/land.mjs).
