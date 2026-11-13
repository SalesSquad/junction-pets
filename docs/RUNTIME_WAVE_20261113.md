# Junction agent runtime advancement — 13 November 2026

Work ID: `JUNCTION-WIN-20261113`. Source baseline: `61f10a44cfd833e02fa64462dfc7429046fff210`, tree `9eaf21135397a2506ae797b7c7f267bb1bd348dd`. All 34 company source slices were already merged at admission. Existing PR #54 owns the continuity ledger/docs and PR #55 owns upstream Aiven provenance; this wave preserves those paths.

## Decisions and boundaries

- **Callable analysis:** [the explicit Node registry](../services/pet-adapters/CAPABILITIES.md) binds one existing deterministic analyzer per company. Its fixed imports, strict bounded envelopes and truthful effect/network descriptors make existing code callable without pretending that an Aiven account or a Chibi grant exists. A completed analysis can return a failed review; transport completion is not scenario success.
- **Browser access:** [WebMCP](../apps/catalog/WEBMCP.md) lists and reads public package data and selects a visible companion. The Node registry is not bundled into the browser. No execution tool is registered until a real compatible runtime exists.
- **Durability:** [PostgreSQL replay](../services/council/POSTGRES_REPLAY.md) implements the existing host-injected Council protocol in a separate replay namespace. A reservation is durable only after database commit; source/envelope/handoff digests and tenant/user identities remain bound. Terminal invalidation advances the database fence. This does not authorize model/provider effects or activate Chibi.
- **Measured behavior:** [public behavior capture](../services/eval-runner/PUBLIC_BEHAVIOR_CAPTURE.md) freezes all 204 authored cases, invokes only explicitly selected existing Claude authorization, preserves failures and private response bytes, and supports a no-persona baseline. It does not fine-tune model weights or award itself a passing quality verdict. An independent rubric review and held-out usefulness tasks are separate requirements.

## Product direction

[Fable 5.2's actual advice](reviews/FABLE_5_2_RUNTIME_20261113.md) is to keep these shared improvements and prove one vertical workflow: synthetic slow-query evidence → pinned official Aiven sources → bounded real model response → independent unsupported-claim review → durable PostgreSQL replay. The advice predates the implementation diff; proposed defects require reproduction before being accepted.

The [finite public developer workflow](../services/demo-host/README.md) now joins those components behind an explicit opt-in CLI. It uses a fixed synthetic caller, a disposable local database and an isolated model process. Its original public result is stored immutably and an identical replay returns that result without a second invocation. It is not the private Chibi host. Independent source review found and repaired ambiguous legacy run-ID encoding and a libpq multi-host escape in the new demo's local-only database guard. Run-ID v2 compatibility requires explicit migration or rejection, as documented in the replay module.

Use PostgreSQL first for the demonstrated transactional need. Kafka, OpenSearch and Valkey require a measured stream, retrieval or cache need before admission. Local PostgreSQL verification does not mean an Aiven-managed service is connected.

Keep source, measured usefulness, runtime execution and Junction eligibility as four separate axes. Current commercial companion work is not silently treated as eligible event submission code. The live official Platform confirmed check-in complete on 13 November; challenge and developer-asset controls remained disabled until the scheduled hacking start at 19:30 Europe/Helsinki. Original challenge briefs and judging criteria must be recovered from the official platform before choosing a competition entry.

## Next bounded waves

1. Run the Aiven and AfterQuery pilot cases with preserved responses and no-persona controls; reproduce PostgreSQL contention/restart/revocation and actual browser navigation on exact committed source. Repair observed defects and review final bytes independently.
2. Add held-out, objectively checkable useful tasks for Aiven, MariaDB and AfterQuery. Compare the same model with and without each persona, measuring unsupported claims, citation validity, false abstention and task outcome. Expand only from measured gains.
3. Carry the proven workflow into the existing private Chibi runtime using its actual identity, consent, Cedar, revocation and signing boundaries. A developer demo, model output or catalog listing is never a substitute for that recipient acceptance path.

This is a finite coordinated development wave, not a new scheduler, permanent worker or production deployment. Exact final source and executed checks belong in the task PR; unavailable browser/database/provider gates remain explicitly unverified until run.

## Observed results and next owners

The [full 34-company evaluation](evidence/all-companion-behavior-20261113.json) preserves all 204 actual public/synthetic CLI response hashes and four independent rubric reviews at `a43ac2195a39ac5a3fc9261a3b05faeea52281dc`. All 204 responses were captured without transport failure. Reviewers marked 201 as provisional rubric passes and three as misses; 14 need review, overlapping those pass/fail counts. That leaves 190 clear candidate passes. This is the authored development set, not a held-out product benchmark or host qualification.

The three misses concern absent supplied research/demo/hardware context in the AstraZeneca, Google DeepMind and NVIDIA cases. The evaluation owner must supply concrete synthetic artifacts or explicitly resolve the rubric ambiguity; never invent results or retroactively change these grades. Other flagged rows identify exact documentation, event-credit, database terminology, motion-capture and food-service claims requiring source/domain review. Per-case owners and acceptance actions remain in the report. Add three held-out useful tasks per priority companion before claiming measured product advantage.

[Aiven's fresh blinded repair review](evidence/aiven-repair-review-20261113.json) compares six prior and six new answers: version 0.1.2 meets six of six authored criteria versus four of six previously, with the new answer preferred in four of six pairs. Two earlier answers remain preferred for brevity or clearer scope. Preserve those limits; the review does not establish generalization.

The actual public demo at `6112461` completed its transport/replay path but an independent content review found incorrect MariaDB diagnostic wording. Preserve response digest `793b419fba424db48655b41b99115265c86966e1f9088aa30efa32c7cb47215c` as a failed usefulness sample. The separately committed prompt repair at `e5f5ae5f296c58091aba8c637419a04849bb1986` keeps Kafka/PostgreSQL references separate from the MariaDB fixture, requests existing redacted evidence and its unknown version, and avoids diagnostic SQL. Its fresh actual response digest `57ad57172c0005ab7f4adde42cab22a2aafbd78df04623cfd1951e23c3fa81e9` passed independent content review for this one sample; immutable replay again returned the exact original response without a second invocation.

Existing private Chibi continuation is isolated in [PR #117](https://github.com/SalesSquad/chibi/pull/117), source `8781a97d16c37ca2a6bcf1c2de20d8731fc61cb7`: awaited host ports with authority/expiry checks and disabled defaults preserved. Independent source review approved the admission-only scope; the actual targeted Rust gate passed 18 tests with zero failures/ignored and 111 unrelated library tests filtered. No real recipient route, model dispatch or atomic cross-service authorization is enabled. Check current PR state before integration. A provider environment name or a queued task is not a working runtime.

[Runtime validation receipts](evidence/runtime-validation-20261113.json) bind the actual source, check scope, log/response digests, retained failures, cleanup and remaining runtime gaps. Source tests, model rubric judgments and one developer demo must remain distinct.
