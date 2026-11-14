# AfterQuery — Break the Agent

**Product line J26-AQ-HARBOR-001.** This is an event-born, provider-neutral Harbor task that grows the existing AfterQuery failure-rubric companion into an executable agent evaluation environment. The previously merged `pets/afterquery/failure-rubric.mjs` and its 9 focused tests remain unchanged.

## The task

An AI coding agent must implement a robust payment-settlement reconciliation command. It receives an event stream and must distinguish safe to retry, known successful, blocked, unknown after timeout, and escalation cases. The task deliberately combines business invariants, idempotency and provenance: one superficially plausible answer or a blanket refusal should not achieve a high reward.

The task directory is [`harbor/settlement-reconciliation/`](harbor/settlement-reconciliation/). It follows the public [Harbor task format](https://github.com/harbor-framework/docs/blob/main/cli/tasks.mdx): a fully specified agent instruction, a standalone Python Docker image, an independent verifier writing `/logs/verifier/reward.txt`, a deterministic oracle and adversarial baselines.

## Run it

When Harbor and Docker are available in an authorized environment:

```sh
harbor trials start --path solutions/afterquery-break-the-agent/harbor/settlement-reconciliation --agent oracle
```

Run an actual frontier agent separately using Harbor's configured agent/model integration and the same task version. Preserve source SHA, agent/model ID, seed, run output, reward, duration and failure trace. Do not infer a frontier gap from the oracle alone.

For a no-Docker, no-model offline evaluator smoke test (not a Harbor run):

```sh
python3 solutions/afterquery-break-the-agent/harbor/settlement-reconciliation/tests/evaluate.py \
  --solver solutions/afterquery-break-the-agent/harbor/settlement-reconciliation/solution/reconcile.py
python3 solutions/afterquery-break-the-agent/harbor/settlement-reconciliation/tests/local_regression.py
```

The first command prints an offline score, but it does **not** execute a Harbor agent trial. The second compares a reference solution against do-nothing, stop-early, all-paid and all-escalated baselines. None is a frontier-model run.

## Honest limits

- Existing source: AfterQuery companion and offline synthetic failure taxonomy are implemented in the existing monorepo; this task adds a separate evaluation artifact and does not connect to the private Chibi host.
- Current qualification: deterministic local verifier and reference/baseline checks. Docker/Harbor, real frontier-agent trials (three required for the challenge), organizer evaluation, external receipts and claimed model failures remain **unverified** until the corresponding real receipts exist.
- No payment system is called. `receiptId` is a synthetic input field, not an authenticated financial receipt. The environment scores the correctness of reasoning *given the event log*, not whether a bank or processor truly settled a payment.
- Task creation and deterministic checks alone do not prove the benchmark is hard for frontier agents. A meaningful gap requires a repeatable stronger reference and poorer verified frontier-agent runs, with a full review of whether failure comes from decision difficulty rather than missing information.
- Keep any eventual public event export separate from private `ops/`, company runtime and unrelated SalesSquad/Chibi code; do not publish this private monorepo without authorization.

## Next product increments

1. One real Oracle Harbor run, preserve the exact score and logs.
2. Three independent frontier-agent runs with the same source and task setup; measure reward gap, stop-early performance and exploit resistance across repeated seeds.
3. Add a real environment adapter with explicit tools/observations and a human-facing evaluation dashboard; avoid turning verifier internals into a privileged agent input.
4. Package judge-ready reproducible instructions, failure taxonomy and demo only after actual execution evidence is collected.
