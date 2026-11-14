# AfterQuery product architecture

## Existing source and new execution boundary

| Layer | Source | Status and boundary |
| --- | --- | --- |
| Companion expertise | `pets/afterquery/`, merged [PR #13](https://github.com/SalesSquad/junction-pets/pull/13) | Existing failure rubric; synthetic, host-independent; never copied into task runtime |
| Reusable agent discovery | `services/pet-adapters/registry.mjs` | Source capability discovery, not active company API access or a distributed evaluation fleet |
| New challenge environment | [`harbor/settlement-reconciliation/`](harbor/settlement-reconciliation/) | New event-born Python Harbor task; agent writes inert `/app/output/decisions.json` (implementation may be any agent-authored program) |
| Host evaluation | Harbor 1.4 separate verifier builds `tests/Dockerfile`, transfers only declared static artifacts, scores private golden ledger and writes `/logs/verifier/reward.txt` | Real Harbor runner unavailable in author's current executor; not yet qualified |
| Training/analysis product | Future experiment registry, failure visualizer, reward explorer and human judge tools | Planned; must bind future frontier-agent results to source and model IDs |

## Event and evidence contract

The task's action is a bounded file/code edit, not a bank transaction. The input contains approved synthetic orders and chronological charge-attempt/result events. The output is a JSON per-order state and safe action with exact event provenance. Unknown or timed-out outcomes demand verification; repeated charge after success or uncertainty is forbidden.

The live Harbor trial scores one agent-finished JSON artifact for **38 distinct ledger orders** (the acting agent sees the input ledger but not the answer key). It does **not** invoke the agent's Python solver inside the verifier. A separate verifier image never contains agent-authored executables; it reads only bounded JSON, compares the agent-visible input with a pinned SHA-256 and evaluates against a verifier-private key. The local oracle additionally passes **37 independent regression scenarios**, which are *not* replayed as hidden inputs by Harbor after the agent phase. Unsupported `PAID`, unsafe retries or input tampering zero the score. Each correct `ESCALATE` receives 0.25 weight, so blanket refusal only scores 0.115044 on the live 38-order fixture. Details JSON and reward.txt distinguish scoring from the application. No external verifier or receipt authentication is claimed.

**Security incident and closure:** First draft PR #83 allowed an attacker-controlled `/app/reconcile.py` to import mounted `/tests/evaluate.py` and obtain a perfect fake 1.0. This was reproduced by an independent reviewer. The repaired architecture requires agent-authored *static* output before the verifier starts, task-level `artifacts`, Harbor `environment_mode="separate"`, test-only Docker build context, a verifier with no agent-code execution, and a regression in `tests/local_regression.py` expecting 0 for that attack. This is a local design-level mitigation; actual Harbor artifact transfer still requires a hosted trial.

## Model/runner evolution

No foundation model, OpenCode harness, Chibi host, payment service, private company data or external GPU is involved in the current local checks. Later additions need a **true** Harbor Oracle run with artifact and source receipt, at least three independent frontier-agent runs, do-nothing/early-stop baselines on the actual trial runner and repeated-seed variance. Reward exploits found by real judge-style attacks must be recorded and fixed without rewriting old results.

The generic solution workspace contract is implemented in pending [PR #82](https://github.com/SalesSquad/junction-pets/pull/82), succeeding conflicted [PR #64](https://github.com/SalesSquad/junction-pets/pull/64). This product's `solution.json` and handoff documents are compatible with that contract, but do not import any private Chibi component.
