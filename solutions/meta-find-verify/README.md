# Chibi Lens — Find & Verify

User problem: finding an important object previously seen, then checking a fresh candidate.

Demo outcome: one user-controlled capture produces an evidence-bound candidate and an explicit verified/uncertain answer. This native outcome is **planned**, not an observed device result.

Challenge fit: read [Meta research](../../pets/meta/CHALLENGE_RESEARCH.md), [official brief](../../docs/challenge-research/official-briefs.md) and [Meta start](../../docs/META_START_HERE.md). Preserve exact judging clauses in the task acceptance before implementing the native slice.

## Existing work and source dependencies

| Component | Source | Current boundary |
| --- | --- | --- |
| Research and product architecture | [Meta start](../../docs/META_START_HERE.md) | In main at scaffold base 5852fa4 |
| Inspect/find/verify kernel and synthetic tests | [PR60](https://github.com/SalesSquad/junction-pets/pull/60), recorded source fb90ab5a6206aac12f96862dbdd486d593656843 | Pending implementation source; recheck head and owner |
| Native DAT capture/audio and private memory | Architecture next-native lane | Planned; no physical-device qualification |
| Meta subject companion | [Agent package](../../pets/meta/) | Source content, not automatic live capture |

Reuse PR60 code at its current source; do not recreate it in this directory.
This workspace adds product ownership and continuation, not another scan kernel.

## Start a developer

Run `node scripts/solution-workspace.mjs brief meta-find-verify`.
Read [instructions](AGENTS.md), [architecture](ARCHITECTURE.md) and [progress](PROGRESS.md).

## First task acceptance

Produce an exact native-adapter implementation plan from current PR60 contracts:
identify one DAT frame boundary, one audio reply boundary, current owner, target
paths, authorized Apple executor and the decisive fake-adapter/native test commands.
Preserve provider/hardware blockers separately. Do not claim the scaffold or a
plan completes the real capture demo.
