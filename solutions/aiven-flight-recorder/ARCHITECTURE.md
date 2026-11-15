# aiven-flight-recorder architecture

## Components

| Component | Existing source or new owned path | Interface | State |
| --- | --- | --- | --- |
| Event flight recorder (baseline vs Aiven run, relay, idempotent consumer, replay) | `solutions/aiven-flight-recorder/` (`core.mjs`, `memory.mjs`, `live.mjs`, `cli.mjs`) | `node cli.mjs` (in-memory) and `node cli.mjs --live` (Aiven PostgreSQL + Kafka via `run-live.sh`) | in-memory adapter for tests; live state only in the operator's Aiven services |
| Agent | `pets/aiven/` | Existing declared capabilities | content only; execution separately qualified |

## Reuse and dependencies

Record source SHA, PR/base/dependencies, contract, integration owner and next action for each reused pending implementation. Keep source in its existing location.

## Capability composition

List planned agent capability references in solution.json. That list grants no execution authority. Reuse [existing collaboration contracts](../../docs/INTER_PET_COLLABORATION.md); Chibi owns production identity, consent, memory and model/tool dispatch. Record measured provider/host evidence separately.

## Knowledge and learning

Keep challenge/product findings here with sources. Propose reusable expertise updates to the owning pet/service through a separate bounded PR and evaluation; never silently merge private user memories.
