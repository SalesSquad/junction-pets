# Aiven platform capabilities for every companion

Built and measured by the `junction.aiven` companion; registered for **all pets** in
`config/special-capabilities.json`. One source of truth, re-exported by `index.mjs`.

| Capability (registry id) | What a pet gets | Source |
|---|---|---|
| `typed-decision-proposals` | Typed answers (`pets/aiven/schemas/response.v2.json`). The offline bridge requires an exact host-supplied user intent before producing a pending decision; this is not a host connection or an execution grant. | `solutions/aiven-decision-bridge/bridge.mjs` |
| `answer-check-repair` | Deterministic rule checks beyond the schema (missing proposal, personal data without classification or residency, echoed secrets, unflagged embedded instructions) and one repair turn. | `solutions/aiven-decision-bridge/lint.mjs` |
| `replayable-event-log` | Outbox → Kafka → idempotent consumer with a measured duplicate/crash/replay demo; live mode on Aiven for Kafka and PostgreSQL. | `solutions/aiven-flight-recorder/` |
| `aiven-read-only-inspection` | Read-only Aiven MCP observation with typed identifiers, scored against the Aiven API. | `solutions/aiven-model-tournament/live-tools.mjs` |
| `challenger-evaluation` | Fresh cases written by other companions, rubric calibration, two judges with consensus, Wilson and bootstrap intervals. | `solutions/aiven-model-tournament/challenge.mjs` |

Measured results: `solutions/aiven-model-tournament/RESULTS-*.md`.
The 15 November integration changes and their limits are recorded in
`solutions/aiven-model-tournament/INTEGRATION-20261115.md`.

Run the offline demo: `node services/aiven-platform/demo.mjs`.

**Limits:**
- Statuses in the registry describe source only.
- Real decisions need the Chibi host's `action_decisions`.
- Live Aiven use needs a host-granted read-only connection.
- Evaluations need an authorized model CLI.
- Injection detection is heuristic, not an authorization boundary. The previous
  model evaluation remains below its 95% target and has not been rerun after the
  changes. Do not enable this cascade for production decisions on that evidence.
- The host must supply `trustedUserIntents` from the user's own explicit request,
  independently of model output, attachments and tools. Each intent contains the
  exact operation, target and complete parameters. Matching is required even when
  no injection is detected. This is a local guard, not authentication or approval;
  the real host must enforce policy, tenant isolation and human decision binding.
