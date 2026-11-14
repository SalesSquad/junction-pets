# ProofMatch product slice

Work ID: J26-PF-ESPOO-20261114-A. Only write under `solutions/espoo-proofmatch/`.
This is an event-created standalone product; do not edit companion packs,
shared CLI/schema, docs, root tests, existing solutions or Tieto L9 (#77).
Coordinator owns remote integration. Do not push, open PRs, merge or deploy for
this work item. Keep dependencies at zero and use Node built-ins.

All fixtures are synthetic. Do not introduce real people, private data, model
calls, hiring/rejection decisions, protected-attribute scoring, credentials,
external verification claims or real communications. Demo consent is not real
consent. Preserve unknown skills, auditable scores, exact source provenance,
duplicate protection and candidate/employer conflict checks.

Focused commands from repo root:

```sh
node --test solutions/espoo-proofmatch/matcher.test.mjs
node solutions/espoo-proofmatch/benchmark.mjs
node solutions/espoo-proofmatch/serve.mjs
```

No shared test suite, root package modification or GitHub Actions is needed.
Review modified product files and stop task-owned servers at handoff.
