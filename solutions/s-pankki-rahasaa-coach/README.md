# Rahasää — S-Pankki money coach

## Product brief

User and problem: an S-Pankki customer who wants to know, in plain words, whether their money lasts to payday and
which habit would change that — without reading a transaction list.

Demo outcome: the customer asks in Finnish, Swedish or English; the coach answers from their own (synthetic) banking
data with figures that come from deterministic tools and show how they were computed:

- **Forecast to payday** — safe to spend and whether this cycle heads below zero.
- **Time machine** — replay past months with one habit changed ("−20 % restaurants") and see avoided overdrafts.
- **Three baskets** — fixed costs, irregular needs, everyday spending.
- **Receipts** — every number links to its computation and transactions.

Challenge fit: start at [company research](../../pets/s-pankki/CHALLENGE_RESEARCH.md). The coach never gives
investment or credit advice, never invents figures and never shows another customer's data (tested by the chaos lab).

Non-goals for this slice: real customer data, production deployment, payments.

## Source

The implementation lives in the private repository [SalesSquad/spankki-coach](https://github.com/SalesSquad/spankki-coach) and is not copied here.
Pinned source: main `12acbc5af307cc605850c50ca791884b32ea64e4` (2026-11-15). See [architecture](ARCHITECTURE.md) and [progress](PROGRESS.md).

## Results (measured, synthetic dataset)

**Tool router** — picks the first tool before the coach model runs; 489-question test set (226 gold + 263 mined):

| router | correct / 489 | note |
| --- | --- | --- |
| Claude Haiku 5.5 (tool-use) | 440 | baseline |
| Gemma 3 4B LoRA v4 | 420 | two-fold CV cascade 442 |
| Gemma 3 12B LoRA v7 (Verda A100) | 420 | larger did not help |
| Gemma 3 1B LoRA (CUDA, r32) | 409 | best edge model |
| TF-IDF + logistic regression | 384 | CPU baseline |

**Edge answers** (card-only, no model call): 29 % of questions, −34 % cost, but a Sonnet judge preferred Haiku's
answer in 93.6 % → not shipped; proposal is a speculative card shown while the model answers.

**Chaos lab** — 20 Haiku red-team attackers × 3 conversations × 4 real coach turns (240 turns), Haiku grader, Sonnet
confirmer: swarm 1 found 7 (5 harness artefacts, 1 real bug — a future period answered "0 €", fixed, 1 prompt
proposal); swarm 2 after fixes: **0 confirmed**, 0 crashes, $0.41. Router load test with 20 concurrent clients found
that the local Gemma router server answered no request (MLX thread affinity); fixed with one worker thread and a
bounded queue (503 when full). Capacity ≈ 2 req/s per Mac mini instance.

## Start a developer

Read [the workspace guide](../../docs/SOLUTION_WORKSPACES.md), [local instructions](AGENTS.md), [architecture](ARCHITECTURE.md)
and [progress](PROGRESS.md). Code changes go to the source repository; this workspace holds the brief and evidence.

## Acceptance

- User-visible outcome: `npm run dev:api` in the source repository, then `POST /api/customers/:id/chat` returns a
  grounded answer with receipts (needs Anthropic credentials).
- Decisive test: `npm run check` in the source repository at `12acbc5af307cc605850c50ca791884b32ea64e4` → 454 pass / 0 fail (local CI, PR #95).
- Demo/submission material: not yet prepared.
