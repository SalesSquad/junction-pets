# Junction Aiven public Haiku smoke — **UNQUALIFIED**

This is a narrow, optional **developer experiment**. It is **not** Chibi pet execution, verified provider attestation, a production runtime, an Aiven account integration, sponsor endorsement, or a completed behavioral evaluation. It does not change `providerInvocationsVerified:0` or the 204 authored-but-unexecuted pet eval cases.

## Fixed inputs and safety gates

- Uses only one hard-coded, public Aiven observability question. No personal, tenant, connection or customer data.
- Before any model call: local Git working tree must be clean; exact 40-character source HEAD must match the caller argument; origin must be `SalesSquad/junction-pets`.
- Fetches exactly two official public Aiven documents from pinned raw GitHub URLs; each must match the exact upstream SHA-256 before its short, original summary and official citation can enter the prompt. It never sends raw documentation bodies.
- Invokes the **already authorized** installed Claude CLI with `--model haiku`, `--max-budget-usd 0.25`, `--restricted`, `--tools ""`, `--strict-mcp-config`, `--no-session-persistence`, and no browser. This does not prove a specific backend model or guaranteed billing.
- Returns only source, prompt, cited-doc and response hashes plus bounded execution metadata. It **never** persists the response text in the source repo. The local receipt is in the ignored `dist/evals` folder, created with exclusive file semantics to prevent accidental overwrite.
- The receipt explicitly retains `chibiHostVerified:false`, `providerInvocationVerified:false`, `signedProviderReceiptVerified:false`, and `qualifiedPasses:0`. Even if a local CLI produced text, only a separate signed Chibi host/provider/reviewer evidence chain could qualify a pet evaluation.

## Reproduce without spending

From a verified clean checkout at the exact commit SHA:

```sh
node --test services/eval-runner/haiku-public-smoke.test.mjs
node services/eval-runner/haiku-public-smoke.mjs --source-commit FULL_40_CHAR_SHA
```

These run offline and execute **zero** models. They report an unverified source shortlist.

## Opt-in single public-model call

Only when existing Claude authorization and budget are verified:

```sh
node services/eval-runner/haiku-public-smoke.mjs --source-commit FULL_40_CHAR_SHA --execute
```

The command fails closed if source, pinning, CLI output or reported cost contradicts the preflight, without printing provider errors or full model text. A tool failure does not authorize switching accounts or exceeding the budget. The local observation is not a provider-signed receipt; independent adjudication is still required.

The canonical Chibi-host eval runner remains `services/eval-runner/runner.mjs`; this smoke does not bypass or modify its mandatory host authorization, source verification or revocation checks.
