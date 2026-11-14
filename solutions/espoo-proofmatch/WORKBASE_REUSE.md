# Workbase reuse — private provenance, no submission clearance

Work ID: **J26-ESPOO-WORKBASE-REUSE-20261114**.

**Workbase is pre-existing PRIVATE IP.** Owner-authorized reuse for this private
ProofMatch W2 demo does **not** make the reused implementation or this derivative
automatically eligible for a competition submission. No contest clearance,
publication license, production release or municipal endorsement is claimed.
Keep this slice private until its source rights and competition rules have been
reviewed by the coordinator/owner. This is not all event-original implementation.

Read-only Workbase checkout:
`/Users/mikaelmini/Developer/j26-workbase-reference-20261114`.
Exact verified source commit: `4c5ce6e2edb41b83360dd7d0227da9ded06a566b`.
ProofMatch starting HEAD: `92d3f48efe94c9547a77963371f49102bee4fb61` (PR86
source supplied by coordinator, confirmed locally). The W2 implementation is confined to `solutions/espoo-proofmatch/` and delivered on its own private task branch. PR metadata records final integration status.

## Concrete implementation lineage

Target paths in this table are relative to `solutions/espoo-proofmatch/`.
The source files were read as code, not inferred from their documentation.

| Workbase source at the pinned commit | Demo target | Reuse/adaptation |
| --- | --- | --- |
| `services/matching-rs/src/skills.rs`: `SkillGraph::from_pairs`, `relatedness`, `align`, `SkillAlignment` coverage methods | `skill-graph.mjs`: `createSkillGraph`, `alignSkills`; `skill-graph.test.mjs` | Bounded JavaScript adaptation of pure semantics: lowercase canonical IDs, symmetric strongest duplicate edge, exact first, strongest direct related match at threshold 0.5, related credit 0.6 × relation, separate required-count and weighted-preferred coverage. One existing TypeScript↔JavaScript seed weight 0.85 is reused. No full Rust file or seed table copied. |
| `docs/architecture/2026-09-23-matching-v2-reciprocal-ranking.md` | `skill-graph.mjs`: `conversation`; `data.mjs`; `app.mjs` | Adapt two-sided reasoning into explicit synthetic event-topic interests alongside role needs. No harmonic person ranking, location/pay constraints, sensitive inference or preference-based filtering. Unknown or other interests keep the candidate visible. |
| `apps/web/lib/evidence.ts`; `services/matching-rs/src/models.rs`: `Evidence`, `codes` | `skill-graph.mjs`: `EVIDENCE_CODES`, structured reasons/cautions, English renderer; `app.mjs` | Retain `{code,args}` boundary and the names `skill_match`, `related_skill_match`, `role_interest_matches_intent`. Add event-specific unknown/other/portfolio codes. Author new English uncertainty text. Exact means a supplied skill label, not authenticated skill possession. Unknown codes remain visible. |
| `db/migrations/0011_work_graph_vertical_slice.sql`: invite enum, pending uniqueness, `create_opportunity_invite`, `respond_opportunity_invite`; `apps/web/app/worker/opportunities/page.tsx` | `event-meetings.mjs`; `event-meetings.test.mjs`; `app.mjs` | Adapt intended-party response and pending/accepted/declined/cancelled vocabulary. The migration defines cancelled but its inspected response function implements accept/decline; event cancellation, fixed slots and conflict checks are newly authored here. No SQL, application creation, RLS/auth, organization permission or global discoverability policy is ported. |
| `apps/web/components/CandidateBrowser.tsx`: separate evidence/caution lists and inspectable detail | `app.mjs`; `index.html`; `styles.css` | Adapt reason/caution and detail disclosure UX to plain semantic HTML. Preserve candidate choice, source cards and questions. No Workbase React component or design assets copied. |

## Deliberate differences and private-IP boundary

The port remains a derivative use of pre-existing private matching logic and
patterns. Rewriting Rust as JavaScript does not clear its provenance. Required
skills contribute equally to required-count coverage, as in Workbase; preferred
skills use explicit normalized weights or the 0.6 default. Existing legacy role
weights stay solely for the old matcher benchmark. Missing requirement groups
return `null` coverage rather than Workbase's internal perfect-coverage default;
there is no aggregate v2 person score or ranking.

The graph is an authored one-edge fixture, not ESCO, a learned taxonomy, external
verification or evidence of transferable proficiency. Ties resolve by canonical
skill ID. Bad edges, duplicate requirements, nonfinite weights and oversized
inputs are rejected rather than silently repaired. Source cards remain fictional
and self-provided; statements never become verified portfolios. Human-authored
questions invite clarification without making aptitude conclusions.

No Workbase auth, credentials, real people, customer data, database, core API,
application submission, global `employers`/`public` visibility or provider
integration is included. Availability and interests are event-local fixtures,
not sharing grants. A single demo operator selects simulated actors; intended
actor checks validate commands inside the demo, not real identities or consent.
The event meeting state machine is separate from Workbase opportunity/job
applications. No outbound communication or external booking occurs.

No Workbase source or Git refs were edited. Coordinator owns delivery and any
future source-rights/competition eligibility decision. See `PROGRESS.md` for
executed checks and explicitly missing runtime evidence.
