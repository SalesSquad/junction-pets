# RoundLens / Lead Investor Evidence Desk

**Maturity 2/6. FICTIONAL_FIXTURE. Offline deterministic prototype, not live financial advice.**

Work-ID `J26-PF-CALA-M2-20261114`; base source `a33f525171b6424d39dfc4c889b63e0fc5cb459e`.
Owned standalone product directory; no changes to merged Cala pet capability (PR23/26).

A first-time Nordic climate-software seed founder needs **examples of investors explicitly sourced as leads**, without mistaking a filing, issuer, circular blog claim or namesake for investment evidence. This milestone implements the complete local journey: set goal → inspect evidence graph → read dated source cards and exclusions → edit shortlist notes → explicitly approve → download citation-preserving JSON. No outreach, auth, email, payments, telemetry, provider request, credential read, external dependency or persistent browser storage. Reviews disappear on reload; download to preserve them. Editing notes revokes approval; changing the goal clears reviews.

## Run (Node 22+)

```sh
cd solutions/cala-founder-opportunity-graph
npm start
# Open http://127.0.0.1:4173
npm run test:unit
npm run build
# Socket-enabled environment only:
npm run test:http
# Both suites together: npm test
```

`PORT=4174 npm start` selects another unprivileged localhost port. Server always binds IPv4 loopback; Host is allowlisted. Native ES modules need no installation/bundler. Build checks JS syntax and static asset presence; no generated files. Stop with Ctrl-C. All runtime actions are local. Fictional citation links are explicit opt-in navigations to reserved `example.invalid` (not real evidence); they do not resolve. There are no real source websites to fetch.

## Evidence policy

- Deterministic score: 10 per supported economic round matching sector, seed stage, geography and inclusive date window. Equal scores sort by stable entity ID. Score is evidence coverage, never suitability or predicted investment willingness.
- Resolve by exact ID and canonical HTTPS entity URL; unresolved namesakes, duplicate IDs and URL collisions abstain. Never merge by display name.
- Deduplicate by explicit `(issuerId, economicRoundId)`. A filing cannot independently establish a lead; repeated source copies never increase score. Missing round identity or unknown issuer abstains. No heuristic money/date/name join.
- Explicit `INVESTOR` + `lead === true` + primary source with source/origin IDs required. `ISSUER` is not an investor. Circular secondary repetition is not primary lead evidence. Contradictory lead or event dates withhold that round; unaffected rounds remain eligible and warnings remain visible.
- Event date must be within the founder window; source publication must be a valid date on/after the event and no later than fixed fixture snapshot 2026-11-14. Invalid/missing dates cannot establish a lead. “Active” means a supported lead event in the preceding 365 days relative to that snapshot, not a claim of live activity.
- Missing is `UNKNOWN`/null, never zero. No aggregate funding amount is inferred; same-round amount reconciliation and currency conversion are not implemented.
- Export rebuilds canonical evidence from the fixture; accepts only eligible stable IDs, bounded notes and explicit approval. It preserves goal, source SHA, event/source dates, citations, dedup key and local human approval state. Approval is a local user assertion, not authenticated attestation. Freeform notes remain user assertions. JSON escapes HTML delimiters.

The fixture contains ten entities, same-name identity collisions, repeated round/filing, issuer record, unknown lead/amount, stale evidence, circular claim, and contradictory lead claims. All are invented, including URLs and excerpts. Exact links are fixture references, **not real citations supporting real companies**. Supported result is two investors / one round each for the default goal. The graph is a semantic investor → economic round → issuer/source trail; source cards expose exact round and issuer IDs.

## Security and accessibility

Strict static file allowlist, GET/HEAD only, loopback binding, rebinding Host refusal, no network fetch path, CSP (no outbound connections, inline scripts, frames or forms), no credentials, HTML escaping, safe URL protocols, bounded export input and explicit review state. Unknown goal/review keys are rejected, including prototype keys. No imported datasets or untrusted provider responses are accepted. Fixtures are source-controlled, not a general ingestion API. No-secret test verifies absence of network/secret-read primitives in browser/data/contract modules; it is not a universal secret scanner.

Responsive layout includes a 390px single-column flow, semantic landmarks/headings, explicit labels, native details controls, keyboard buttons, visible focus, skip link, live feedback, and status text alongside color. Browser/screen-reader claims require actual matching evidence; see VERIFICATION.md. UI uses local system sans, restrained Georgia headings, marine blue, cloud panels and teal evidence labels; no remote fonts or assets.

## Cala integration boundary and exact next external gate

Partner evidence key **cala**, owned brief **M350**, catalog snapshot 2026-11-14. Latest clarification was read before dated prior guidance:

- `docs/challenge-research/current-source-catalog.json`, Cala partner and M350 record.
- [M350: Make Unicorns Real](https://hackjunction.app/participate/45/challenges/350): one focused founder/investor need, sourced structured connections, end-to-end product.
- [Latest sponsor data-guide message](https://discord.com/channels/1268184974784336004/1564622246407045181/1570958986432356352): search/lookup → introspection → retrieval; missing ≠ zero; ISSUER and filing duplication distinctions. Attachment SHA256 `f11961fcb6d9febcf4a8630e4e2c5302bbd8c9fe0323df56796445b10aaaaa2d` recorded in catalog; original attachment bytes were not accessed.
- `pets/cala/CHALLENGE_RESEARCH.md`: identity/freshness adversarial cases and real access dependency.

`cala-contract.mjs` and `.d.ts` define a bounded proposed adapter contract, not a verified Cala SDK wire schema. Stub always refuses, even caller-asserted authority. It has no transport, key loader or provider URL. Proposed limits: 5s, 256KiB response, 25 entities; a future adapter must **enforce** these with abort, streaming byte cap, schema validation, exact entity binding, data rights and host authorization checks at each stage. Limits are declarative while transport is absent. Future host alone holds the key (sponsor describes X-API-KEY); never supply it to browser/local form or exported JSON.

**Exactly next external gate: approved Cala account + host-managed key, then held-out live entity_search/entity_lookup → entity_introspection → entity_retrieval qualification**, including duplicate round/filing, source-date and identity-conflict labels. No account, key, credits, data rights or live quality is assumed. This milestone does not meet live Cala execution qualification. Atlas technology T55 could later store materialized evidence; no Atlas integration or call is present.
