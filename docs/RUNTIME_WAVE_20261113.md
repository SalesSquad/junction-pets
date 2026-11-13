# Junction agent runtime advancement — 13 November 2026

Work ID: `JUNCTION-WIN-20261113`. Source baseline: `61f10a44cfd833e02fa64462dfc7429046fff210`, tree `9eaf21135397a2506ae797b7c7f267bb1bd348dd`. All 34 company source slices were already merged at admission. Existing PR #54 owns the continuity ledger/docs and PR #55 owns upstream Aiven provenance; this wave preserves those paths.

## Decisions and boundaries

- **Callable analysis:** [the explicit Node registry](../services/pet-adapters/CAPABILITIES.md) binds one existing deterministic analyzer per company. Its fixed imports, strict bounded envelopes and truthful effect/network descriptors make existing code callable without pretending that an Aiven account or a Chibi grant exists. A completed analysis can return a failed review; transport completion is not scenario success.
- **Browser access:** [WebMCP](../apps/catalog/WEBMCP.md) lists and reads public package data and selects a visible companion. The Node registry is not bundled into the browser. No execution tool is registered until a real compatible runtime exists.
- **Durability:** [PostgreSQL replay](../services/council/POSTGRES_REPLAY.md) implements the existing host-injected Council protocol in a separate replay namespace. A reservation is durable only after database commit; source/envelope/handoff digests and tenant/user identities remain bound. Terminal invalidation advances the database fence. This does not authorize model/provider effects or activate Chibi.
- **Measured behavior:** [public behavior capture](../services/eval-runner/PUBLIC_BEHAVIOR_CAPTURE.md) freezes all 204 authored cases, invokes only explicitly selected existing Claude authorization, preserves failures and private response bytes, and supports a no-persona baseline. It does not fine-tune model weights or award itself a passing quality verdict. An independent rubric review and held-out usefulness tasks are separate requirements.

## Product direction

[Fable 5.2's actual advice](reviews/FABLE_5_2_RUNTIME_20261113.md) is to keep these shared improvements and prove one vertical workflow: synthetic slow-query evidence → pinned official Aiven sources → bounded real model response → independent unsupported-claim review → durable PostgreSQL replay. The advice predates the implementation diff; proposed defects require reproduction before being accepted.

Use PostgreSQL first for the demonstrated transactional need. Kafka, OpenSearch and Valkey require a measured stream, retrieval or cache need before admission. Local PostgreSQL verification does not mean an Aiven-managed service is connected.

Keep source, measured usefulness, runtime execution and Junction eligibility as four separate axes. Current commercial companion work is not silently treated as eligible event submission code. The live official Platform confirmed check-in complete on 13 November; challenge and developer-asset controls remained disabled until the scheduled hacking start at 19:30 Europe/Helsinki. Original challenge briefs and judging criteria must be recovered from the official platform before choosing a competition entry.

## Next bounded waves

1. Run the Aiven and AfterQuery pilot cases with preserved responses and no-persona controls; reproduce PostgreSQL contention/restart/revocation and actual browser navigation on exact committed source. Repair observed defects and review final bytes independently.
2. Add held-out, objectively checkable useful tasks for Aiven, MariaDB and AfterQuery. Compare the same model with and without each persona, measuring unsupported claims, citation validity, false abstention and task outcome. Expand only from measured gains.
3. Carry the proven workflow into the existing private Chibi runtime using its actual identity, consent, Cedar, revocation and signing boundaries. A developer demo, model output or catalog listing is never a substitute for that recipient acceptance path.

This is a finite coordinated development wave, not a new scheduler, permanent worker or production deployment. Exact final source and executed checks belong in the task PR; unavailable browser/database/provider gates remain explicitly unverified until run.
