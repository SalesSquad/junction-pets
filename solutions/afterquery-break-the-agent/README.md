# AfterQuery — Break the Agent

**Product line J26-AQ-HARBOR-001.** This is an event-born, provider-neutral Harbor task that grows the existing AfterQuery failure-rubric companion into an executable agent evaluation environment. The previously merged `pets/afterquery/failure-rubric.mjs` and its 9 focused tests remain unchanged.

## The task

An AI coding agent must reconcile a 38-order synthetic payment ledger and write a final, machine-readable report. It receives an event stream and must distinguish safe to retry, known successful, blocked, unknown after timeout, and escalation cases. The task deliberately combines business invariants, idempotency and provenance: one superficially plausible answer or a blanket refusal should not achieve a high reward.

The task directory is [`harbor/settlement-reconciliation/`](harbor/settlement-reconciliation/). It follows the [current Harbor 1.4 task configuration](https://github.com/harbor-framework/harbor/blob/main/docs-mintlify/tasks/configuration.mdx): a fully specified agent instruction, a standalone Python Docker image, a **separate verifier image** writing `/logs/verifier/reward.txt`, a deterministic oracle and adversarial baselines.

### Verification security boundary

The agent must write `/app/output/decisions.json` **during its own run**. Harbor shuts that container down and copies only the declared final JSON/output directory and observed input into a fresh verifier container built from `tests/Dockerfile`. The verifier checks the input against a pinned SHA-256, scores the *already written JSON* against a private 38-order answer key, and does **not** load or execute `/app/reconcile.py` or any other agent-authored code. This closes a demonstrated exploit in the first draft where a malicious solver imported `/tests/evaluate.py` during verification to read hidden correct answers and earn 1.0. The original exploit is retained as a local regression expecting reward 0.0.

The agent can write any implementation it wants during its phase, but a good algorithm is needed to reconcile conflicting attempts, ambiguous timeouts, duplicate receipts/IDs, rejected approvals, unauthorized charges, and untrusted notes. The verifier preserves partial credit for correct decisions and provenance, while unsupported `PAID` or unsafe charge actions zero reward. Blind escalation receives only 0.115044 on the current scenario.

## Run it

When Harbor and Docker are available in an authorized environment:

```sh
harbor run -p solutions/afterquery-break-the-agent/harbor/settlement-reconciliation -a oracle
```

Run an actual frontier agent separately using Harbor's configured agent/model integration and the same task version. Preserve source SHA, agent/model ID, seed, run output, reward, duration and failure trace. Do not infer a frontier gap from the oracle alone.

For a no-Docker, no-model offline test (not a Harbor run):

```sh
python3 solutions/afterquery-break-the-agent/harbor/settlement-reconciliation/tests/local_regression.py
```

The script checks 37 independent generated/handwritten oracle cases, then scores the actual 38-order final artifact in the same way as Harbor's verifier, compares it with no-op/stop-early/all-paid/all-escalate/input-tamper attacks and verifies the hidden-test-import exploit no longer influences reward. None is a frontier-model run. It should print `PASS_LOCAL_ONLY`, `oracleReward:1.0`, `p0HiddenTestExfil:0.0`.

## Honest limits

- Existing source: AfterQuery companion and offline synthetic failure taxonomy are implemented in the existing monorepo; this task adds a separate evaluation artifact and does not connect to the private Chibi host.
- Current qualification: deterministic local static-artifact verifier and reference/baseline checks. The **separate-container artifact-forwarding behavior has not yet been run on Docker/Harbor**; real frontier-agent trials (three required for the challenge), organizer evaluation, external receipts and claimed model failures remain **unverified** until real run records exist.
- No payment system is called. `receiptId` is a synthetic input field, not an authenticated financial receipt. The environment scores the correctness of reasoning *given the event log*, not whether a bank or processor truly settled a payment.
- Task creation and deterministic checks alone do not prove the benchmark is hard for frontier agents. A meaningful gap requires a repeatable stronger reference and poorer verified frontier-agent runs, with a full review of whether failure comes from decision difficulty rather than missing information.
- Keep any eventual public event export separate from private `ops/`, company runtime and unrelated SalesSquad/Chibi code; do not publish this private monorepo without authorization.

## Next product increments

1. One real Oracle Harbor run, preserve the exact score and logs.
2. Three independent frontier-agent runs with the same source and task setup; measure reward gap, stop-early performance and exploit resistance across repeated seeds.
3. Add a real environment adapter with explicit tools/observations and a human-facing evaluation dashboard; avoid turning verifier internals into a privileged agent input.
4. Package judge-ready reproducible instructions, failure taxonomy and demo only after actual execution evidence is collected.
