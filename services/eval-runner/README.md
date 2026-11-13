# Junction provider-evaluation capture (Wave 2)

This is an **unprivileged, provider-injected adapter**, not a hosted model-evaluation service. Its sole purpose is to turn the 204 authored evaluation prompts into source-bound, sanitized capture receipts. It does not certify a model or grant an agent access to tools.

## Current trust boundary

- The canonical case manifest and rubric remain in `../../lib/behavior-eval.mjs` and `../../docs/BEHAVIOR_EVALS.md`.
- `runBatch` requires the **exact full repository source commit** and a manifest carrying that commit. The caller must verify its case/package hashes against the canonical checkout using the existing verifier.
- With no `invoke` callback, it is a zero-network preview; the default selection is 24 cases, with an explicit maximum of 204.
- The runner recomputes **each case SHA-256** and the **top-level manifest SHA-256** using the same canonical JSON algorithm as `lib/behavior-eval.mjs`. A self-consistent forged manifest is still possible; a separate source-verifier callback must compare the exact `SalesSquad/junction-pets` repository/commit/manifest and package bytes against independently trusted source before any provider calls.
- A **Chibi host** authorization callback must grant `model.invoke` for the exact `runId`, case, pet, source SHA, request digest and action. It must echo those bindings, identify the Chibi issuer, explicitly report `revoked: false` and supply an unexpired receipt. Generic `allowed: true`, scope mismatch, missing or unreachable policy fails closed.
- The host policy is checked again **after** provider work; revocation withholds even the response digest and leaves a denial receipt. Authorization is not delegated to LangGraph or the pet prompt.
- The caller explicitly provides `invoke` with a real provider transport. No credentials, cost-incurring calls or provider-specific SDK are bundled.
- Invocation IDs, model versions and provider strings returned by a callback are **unverified claims**. They are checked against a strict, bounded safe-identifier grammar; the public receipt stores **SHA-256 hashes** for the exact invocation, model and provider IDs, plus only a known provider class. Unknown providers become `other`. Keep raw IDs exclusively in the authorized private provider ledger. All results report `providerInvocationsVerified: 0`, `qualifiedPasses: 0`, `qualified: false`, and `evidenceLevel: 'supplied-unverified'`, even when a mock calls itself real. A later provider- and host-attestation verifier is needed before Mission Control may count a live qualified evaluation.
- The result contains only response SHA-256 and size, **not raw model text, tokens, secrets, arbitrary provider metadata, or user conversations**. Store detailed transcripts in an authorized private evidence system if required for human rubric adjudication.

## Use

Prepare a manifest from an independently verified PR commit:

```sh
node scripts/behavior-eval.mjs prepare --source-commit <full-40-char-github-sha>
```

Offline preview:

```sh
node services/eval-runner/cli.mjs preview --manifest dist/evals/cases.json --source-commit <full-40-char-github-sha> --limit 24
```

Developer-facing JavaScript interface:

```js
import {runBatch} from './services/eval-runner/runner.mjs';

const result = await runBatch({
  manifest,
  sourceCommit,
  maxCases: 24,
  runId: 'wave2-pilot',
  verifySource: verifiedGitHubAndManifestAdapter, // caller-owned, authenticated
  authorize: chibiHostPolicyAdapter,             // caller-owned, fail-closed
  reauthorize: chibiHostPolicyAdapter,
  invoke: actualProviderAdapter,                // caller-owned, explicit execution
});
```

No callback is implemented as a bypass or a fake permission. For a genuinely live demo, provide a Chibi Rust/Cedar permission endpoint, authenticated provider invocation receipt and independent reviewer attestation, then upgrade the aggregate `modelExecutionsVerified` in the **separate** verifier. Synthetic runs from `lib/pet-collaboration.mjs` never count.

Unit tests:

```sh
node --test services/eval-runner/runner.test.mjs
```

These tests use controlled mocks and verify non-escalation; they do **not** constitute real model execution, voice, tool acceptance or Chibi runtime publication.
