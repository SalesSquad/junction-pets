# Aiven platform capabilities for every companion

Built and measured by the `junction.aiven` companion; registered for **all pets** in
`config/special-capabilities.json`. One source of truth, re-exported by `index.mjs`.

| Capability (registry id) | What a pet gets | Source |
|---|---|---|
| `typed-decision-proposals` | Typed answers (`pets/aiven/schemas/response.v2.json`); every change becomes a Chibi `PendingAction` that a human approves or declines (`ActionDecisionBinding`). Nothing executes from the model. | `solutions/aiven-decision-bridge/bridge.mjs` |
| `answer-check-repair` | Deterministic rule checks beyond the schema (missing proposal, personal data without classification or residency, echoed secrets, unflagged embedded instructions) and one repair turn. | `solutions/aiven-decision-bridge/lint.mjs` |
| `replayable-event-log` | Outbox → Kafka → idempotent consumer with a measured duplicate/crash/replay demo; live mode on Aiven for Kafka and PostgreSQL. | `solutions/aiven-flight-recorder/` |
| `aiven-read-only-inspection` | Read-only Aiven MCP observation with typed identifiers, scored against the Aiven API. | `solutions/aiven-model-tournament/live-tools.mjs` |
| `challenger-evaluation` | Fresh cases written by other companions, rubric calibration, two judges with consensus, Wilson and bootstrap intervals. | `solutions/aiven-model-tournament/challenge.mjs` |

Measured results: `solutions/aiven-model-tournament/RESULTS-*.md`.

Run the offline demo: `node services/aiven-platform/demo.mjs`.

**Limits:**
- Statuses in the registry describe source only.
- Real decisions need the Chibi host's `action_decisions`.
- Live Aiven use needs a host-granted read-only connection.
- Evaluations need an authorized model CLI.
