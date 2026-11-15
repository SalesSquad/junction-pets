# Aiven phase 1 integration hardening — 15 November 2026

This integrates the source from PR #330, based on `3f3a266c8918e0a3d23be6d09d27ed56f7b95da7`, with Junction main `b40943649e48018ca4cbeb67f2737698b6607cef`. It is an offline development prototype, not a Chibi host integration or a live Aiven connection.

## Changes

- Reject cascade responses if repair/escalation fails or the escalated response fails the v2 schema and lint checks. Do not serialize invalid or rejected response objects into a repair prompt.
- Encode attachment source and body markup before framing, and check recognised secret patterns in attachments as well as the request. This does not make model text safe by itself.
- Require a host-supplied exact `{ operation, target, parameters }` from the user's own explicit request before creating an offline pending-action proposal. This intent is not approval or a grant; a real host must independently enforce identity, policy, tenant boundaries and human decisions. Never derive it from the model or untrusted content.
- Treat a proposed action that overlaps a detected embedded instruction as requiring independent review, even when the user mentions that target. The evaluation scorer no longer treats mentioning a target as permission to perform the injected operation, or a security rationale as exempting an active `other` proposal.
- Evaluation scripts now count schema-valid model proposals without manufacturing trusted host intents or actual pending decisions. Their results do not establish host admission.

## Verification and limitations

On Node 24.22.1, `node --test tests/*aiven*.test.mjs solutions/aiven-*/tests/*.test.mjs` passed 47 tests. One test constructed proposals using all 40 injection-labelled targets in the existing dataset and checked that the bridge refuses them without trusted user intents; it did not query a model or measure response quality. `npm run plugins:check` verified 34 generated packages and `npm run agents:check` verified 34 agents and 122 proposed edges. The offline demo also ran successfully.

The 84–90% result in `RESULTS-20261115-phase1.md` is a historical developer measurement of the old code, not a result for this integration. The scorer previously exempted proposals when the user merely mentioned the target, so it could have missed unsafe proposals. The updated cascade, framing, guidance and scorer have **not** been rerun against a model, the 95% model-injection goal is not established, and the non-Claude judge remains blocked by unavailable AI Gateway access. No model, host, Aiven provider, or production execution was exercised for this integration. Keep live execution disabled until those separate evaluations and host checks are complete.
