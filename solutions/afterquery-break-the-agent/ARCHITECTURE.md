# AfterQuery product architecture

## Existing source and new execution boundary

| Layer | Source | Status and boundary |
| --- | --- | --- |
| Companion expertise | `pets/afterquery/`, merged [PR #13](https://github.com/SalesSquad/junction-pets/pull/13) | Existing failure rubric; synthetic, host-independent; never copied into task runtime |
| Reusable agent discovery | `services/pet-adapters/registry.mjs` | Source capability discovery, not active company API access or a distributed evaluation fleet |
| New challenge environment | [`harbor/settlement-reconciliation/`](harbor/settlement-reconciliation/) | New event-born Python Harbor task; agent writes `/app/reconcile.py` |
| Host evaluation | Harbor runner builds `environment/Dockerfile`, uploads hidden verifier after agent work, parses `/logs/verifier/reward.txt` | Real Harbor runner unavailable in author's current executor; not yet qualified |
| Training/analysis product | Future experiment registry, failure visualizer, reward explorer and human judge tools | Planned; must bind future frontier-agent results to source and model IDs |

## Event and evidence contract

The task's action is a bounded file/code edit, not a bank transaction. The input contains approved synthetic orders and chronological charge-attempt/result events. The output is a JSON per-order state and safe action with exact event provenance. Unknown or timed-out outcomes demand verification; repeated charge after success or uncertainty is forbidden.

The verifier uploads only *after* agent execution and runs 37 deterministic scenarios, including generated varying amounts and order IDs. Scores are complete-case weighted correctness, with unsafe invented PAID states, unapproved retries and input mutation forcing zero. Each scenario where the only correct outcome is `ESCALATE` receives reduced weight so an agent cannot score highly by refusing all work; the fixed local baseline for blanket refusal is 0.16. Details JSON and reward.txt distinguish scoring from the application. No external verifier or receipt authentication is claimed.

## Model/runner evolution

No foundation model, OpenCode harness, Chibi host, payment service, private company data or external GPU is involved in the current local checks. Later additions need a **true** Harbor Oracle run with artifact and source receipt, at least three independent frontier-agent runs, do-nothing/early-stop baselines on the actual trial runner and repeated-seed variance. Reward exploits found by real judge-style attacks must be recorded and fixed without rewriting old results.

The generic solution workspace contract is implemented in pending [PR #82](https://github.com/SalesSquad/junction-pets/pull/82), succeeding conflicted [PR #64](https://github.com/SalesSquad/junction-pets/pull/64). This product's `solution.json` and handoff documents are compatible with that contract, but do not import any private Chibi component.
