# Rahasää architecture

## Components

| Component | Source (SalesSquad/spankki-coach @ `12acbc5a`) | Interface | State |
| --- | --- | --- | --- |
| Deterministic money tools | `apps/api/src/tools.ts` | safe-to-spend, baskets, spend, replay_habit, pay cycles, balance outlook | built, tested |
| Coach turn + firewall | `apps/api/src/agent.ts`, `conversations.ts` | Haiku 5.5 tool use; figures only from tool results; prior turns' tool outcomes as facts | built |
| Router | `apps/api/src/router.ts`, `route-args.ts` | `ROUTER_URL` (comma list, round-robin + failover, 1.5 s timeout); margin rule chosen by two-fold CV | built, off by default |
| Edge answers | `apps/api/src/edge-answer.ts` | card text without a model call | measured, not shipped |
| Gemma router training/serving | `data/gemma/` (MLX on Mac, Unsloth `router_cuda.py` on CUDA, `router_server.py`) | `POST /route` → `{tool, confidence}` | lab |
| Lab and evals | `apps/lab/` (cascade-eval, label audit, boundary data, monitor, chaos-swarm), `eval/` | CLI scripts, JSONL results | lab |
| Agent | `pets/s-pankki/` | existing declared capabilities | content only |

## Reuse and dependencies

| Source | PR | Content |
| --- | --- | --- |
| spankki-coach | [#91](https://github.com/SalesSquad/spankki-coach/pull/91) `c3a2ea9f` | validation halves, product A/B, calibration |
| spankki-coach | [#92](https://github.com/SalesSquad/spankki-coach/pull/92) `50db2b13` | label audit (35 fixes), boundary data, monitor |
| spankki-coach | [#93](https://github.com/SalesSquad/spankki-coach/pull/93) `95903428` | route-args, projection policy, CUDA training |
| spankki-coach | [#94](https://github.com/SalesSquad/spankki-coach/pull/94) `64dbb04b` | v6/v7, edge-answer A/B |
| spankki-coach | [#95](https://github.com/SalesSquad/spankki-coach/pull/95) `12acbc5a` | chaos lab, router server fix, spend future-period fix |

Integration owner: the spankki-coach repository. No code from it is duplicated in this monorepo.

## Design decisions

- Product binding: only prefill tools (get_safe_to_spend, get_pay_cycles, get_balance_outlook) are bound by the router;
  prefill stays off by default because a pairwise judge rated prefilled answers worse (41–44 %).
- Thresholds from cross-validation on gold + mined, not the validation split (too easy).
- Future-balance guesses become a computed projection (replay_habit) instead of a refusal.
- Lab judges and graders: Sonnet + Haiku only.

## Capability composition

No runtime capability is claimed (`capabilityUses` lists planned use only). Chibi owns production identity, consent,
memory and model/tool dispatch.

## Knowledge and learning

Detailed findings: source repository `docs/FINDINGS.md`, `docs/lab/gemma-router.md`, `docs/lab/chaos-lab.md`.
All evaluation data is the synthetic challenge dataset; no personal data.
