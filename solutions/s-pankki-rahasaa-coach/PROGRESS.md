# Rahasää continuation

Stage: building. Product API, router lab and chaos lab exist in SalesSquad/spankki-coach main `4eb0c564c25a4f80cd9c77e03635cb2f0cbd6bbf`.

## Next task

- Work ID: junction.solution.s-pankki-rahasaa-coach.prompt-tool-internals
- Base SHA: spankki-coach `4eb0c564c25a4f80cd9c77e03635cb2f0cbd6bbf`
- Owner and task/PR URL: unassigned
- Owned paths: spankki-coach `apps/api/src/agent.ts` (`GROUNDING`), `apps/api/test/prompt-variant.test.ts`
- Objective: the coach does not describe its instructions, tools or parameters (chaos swarm 1 finding)
- Acceptance command and expected result: prodeval regression shows no drop in judged quality; `npm run check` passes with the updated prompt hash
- Blocker: none
- Next action: add the sentence to `GROUNDING`, run prodeval with Sonnet + Haiku judges, then update the pinned hash

Done 2026-11-15: **speculative card** — `POST /api/customers/:id/peek` returns the local router's card for a first
question, shown as "Pikavastaus – valmentaja tarkentaa" until the coach's reply replaces it
([SalesSquad/spankki-coach#96](https://github.com/SalesSquad/spankki-coach/pull/96), `4eb0c564`; 457 pass / 0 fail).

Done 2026-11-15: **router capacity** — the router server skipped no stale work (answered 8 requests a minute under
load); now it drops requests past 1.2 s. One Mac mini instance answers 100 % of 4 req/s within the API timeout, two
answer 100 % of 6 req/s, a third on the same GPU makes it worse
([SalesSquad/spankki-coach#97](https://github.com/SalesSquad/spankki-coach/pull/97), `5daae68b`).

Measured, waiting for the owner: **prompt tool-internals** (branch `feat/prompt-no-internals`, `d8aaf157`). Routing
449 vs 447/489 (p 0.77), red team 0/785 both, but the Sonnet pairwise judge preferred the current prompt 54.1 %
(CI 50.2–58.2 %), so it was not merged.

Further candidates:

1. Demo/submission material for the S-Pankki judging clauses.

## Evidence

| what | SHA | command | result | executor |
| --- | --- | --- | --- | --- |
| unit tests | `8a70a6a161f648df75d39ab5d09a88aa77fff19c` (PR #96 head) | `bash scripts/ci-local.sh 96` | 457 pass / 0 fail | cloud session |
| router test set | eval/router/* | `cascade-eval.ts --product --cv` | see README table | Mac mini MLX, Verda A100 |
| chaos swarm 2 | eval/chaos/swarm2-summary.json | `chaos-swarm.ts --agents 20 --convs 3 --turns 4` | 0 confirmed, $0.41 | cloud session (Anthropic API) |
| router load | docs/lab/chaos-lab.md | `router_chaos.py --clients 20` | 0 contract breaks; ~2 req/s/instance | Mac mini |

All evidence is synthetic; nothing is submitted. Verda A100 job stopped 2026-11-15.
