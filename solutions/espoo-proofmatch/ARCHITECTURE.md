# Private ProofMatch v2 boundaries

`data.mjs` → `skill-graph.mjs` → `app.mjs` → semantic static HTML/CSS.
`event-meetings.mjs` owns the separate simulated event lifecycle.
`demo-validation.mjs` provides bounded identifiers/lists, strict fictional event
UTC windows and immutable output snapshots. No dependencies, database, action
API, providers or outbound communications exist.

This source adapts pre-existing PRIVATE Workbase IP at
`4c5ce6e2edb41b83360dd7d0227da9ded06a566b`; exact lineage and uncleared contest
scope are in `WORKBASE_REUSE.md`. Private IP is no longer absent from this slice.
No auth, credentials, real data, core DB or global discoverability is imported.

## Skill and interest evidence

The bounded symmetric graph normalizes canonical skill IDs, keeps the strongest
duplicate edge and performs direct-edge lookup only. Exact matches precede the
strongest related skill at threshold 0.5; related credit is 0.6 × relation.
Ties use lexical canonical IDs, independent of input order. The one seeded
TypeScript↔JavaScript edge at 0.85 is authored transfer context, not an external
taxonomy or verified proficiency. Invalid/nonfinite weights, self-edges,
oversized inputs and duplicate normalized role requirements fail validation.

Workbase required-count coverage is separate from weighted preferred coverage
(default preferred weight 0.6). Absent requirement groups yield `null`, not a
claim of perfection. No aggregate v2 person score is computed or shown. Existing
v1 positive role weights remain only for legacy benchmark compatibility.

Only eligible self-provided cards at/before the injected observation date supply
skill labels. An exact skill label on a statement stays a statement, not proof
of proficiency; related labels stay explicitly related. No bio, protected
characteristic, current clock, model or inferred preference enters this path.
Structured `{code,args}` reasons and cautions have a separate English renderer;
the UI exposes sources, uncertainty and direct transfer paths. Nothing claims
external verification. Missing evidence is unknown ability, never rejection.

Two-sided context consists of role needs and the candidate's explicit synthetic
event-role IDs in `interests`. Absent/null/empty interest is unknown; another
listed role is explained as other interests. Neither removes or sorts people.
All candidates remain selectable in fixture order, including no-portfolio Ren.
This is event-local context, not permission to share profiles with employers.

## Separate simulated event proposals

The event is fixed to fictional 15 November 2026. Strict round-tripped UTC
strings, whole-minute availability and a fixed UTC-aligned 15-minute grid
produce canonical half-open slots. Only complete shared slots may be proposed;
overlapping availability windows deduplicate. Inputs are bounded: 24 windows per
party, 256 records, 64-character IDs; times must be on the fictional event day.

| Action | Intended simulated actor | Allowed source state | Result / time hold |
| --- | --- | --- | --- |
| Propose | Role's employer | No active role/candidate pair | pending / held |
| Accept | Proposal's candidate | pending | accepted / held |
| Decline | Proposal's candidate | pending | declined / released |
| Cancel | Proposal's employer or candidate | pending or accepted | cancelled / released |

Employer and candidate IDs must be distinct. A role cannot change employers in
one ledger. Pending and accepted records prevent duplicate active pairs and
conflicting times across roles/employers for either participant; adjacent slots
are allowed. Decline/cancel preserve history and permit a fresh unique proposal.
Terminal states cannot transition. Every public command validates ledger shape,
known states, IDs, event, slot and consistency. Immutable cloned outputs prevent
later caller mutation from altering a previous snapshot.

These are local command checks, **not authentication or trusted consent**. One
operator can select either party; a caller could fabricate a ledger or identity.
Records have no signed authority, persistent audit log, transactional storage,
clock freshness or cross-tab coordination. Reload/reset clears the simulation.
No Workbase job application or external booking is made. A real system requires
verified actors, event-scoped sharing, revocable consent, fresh calendars and
atomic conflict/duplicate controls. Those capabilities are not implemented.

## Serving, offline and presentation

`serve.mjs` exposes only named product shell files, GET/HEAD and 127.0.0.1, with
MIME/nosniff, no-referrer and restrictive CSP headers. Modules are served as JS.
The v2 service worker caches all named transitive app modules and removes the
known v1 cache when activated; it never deletes unrelated caches or persists
meeting records. Fetch is network-first with same-origin named-asset offline
fallback. A first visit requires the server; browser offline lifecycle is not
qualified by source or syntax checks. Two shell versions may coexist until an
old tab closes and the new worker activates. Clear site data for a fresh shell.

UI strings are escaped before HTML insertion. Fixture references are text, not
executable URLs. Native selects, buttons, fieldsets, details, labelled controls,
selected-state candidate buttons, skip link, live announcements and explicit
focus restoration support keyboard use. Party actions have visible actor labels,
text statuses and 44px targets. Layout collapses to one column on narrow screens;
reduced-motion rules avoid nonessential animation. Browser, screen-reader,
physical-device and accessibility qualification remain unverified in this run.

`matcher.mjs` and its 18 old tests remain unchanged, including their legacy draft
policy. `benchmark.mjs` uses it for only 2 illustrative fixed cases and is not a
v2 quality measurement. `skill-graph.test.mjs` and `event-meetings.test.mjs` cover
new pure boundaries. No full monorepo suite or provider/runtime test is implied.
