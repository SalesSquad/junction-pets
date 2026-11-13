> Recovered historical analyst draft. Ideas and any pending-transcription statements may be superseded by official-briefs.md and fable-review.md. Referenced original contact-sheet paths were not recovered in this slice.

# Junction video analysis B

Work: junction-video-intake-20261113. Analyst owns no repository writes. Source main: `61f10a44cfd833e02fa64462dfc7429046fff210`. Read all six supplied contact sheets, representative frames and additional frames every five seconds; speech transcript remains pending. Exact requirements below are separated from hypotheses. The recordings show an opening-ceremony video; they do not establish complete challenge rules, dataset access or judging criteria.

## Mapping and observed evidence

| Recording | Agent / Space card | Observation and evidence bounds |
|---|---|---|
| IMG_9217 | `junction.stoa`, `pets/stoa`, CH-12, page_57e6862bd6988191b1fb3aa3258f0e6d | Logo is **Stoa**, not Stara. Construction-site drawings at 00:01 and construction work at 00:10; much subtitle text is blocked by audience/lighting. Current Space preview mentions drawings, 3D models and traceable answers; full spoken ask not yet transcribed. |
| IMG_9218 | `junction.s-pankki`, `pets/s-pankki`, CH-03, page_b3f957f7ae8881919f80c8416c00278e | S-Pankki logo and mobile banking/transactions visible. Most subtitles blocked; no complete requirement sentence transcribed visually. Organizer public description retrieved 13 Nov says Personal Economic Trainer, conversational understanding of synthetic banking transactions; this is a current public preview, not full rules. |
| IMG_9219 | `junction.cala`, `pets/cala`, CH-05, page_95ba92d1e128819198a287c574b4d0af | 00:05 title **Make Unicorns Real**; 00:20 complete visible ask: **Solve a real need for founders, investors or both (with Cala)**. 00:40 describes public data layer/knowledge graph; 00:50 lists startups, founders, investors, funding rounds. 01:05–01:10 prize slide: travel to three hackathons with flights/accommodation, €5,000 value for a team of four; prize interpretation needs full rules. 01:25 Saturday 11am workshop. |
| IMG_9220 | `junction.valio-aimo`, `pets/valio-aimo`, CH-02, page_1f32f0c664ac8191b50b61d45c94e981 | Valio Aimo logo; professional kitchen, ordering interface and buyer/purchasing-agent subtitle fragments. Current Space public preview is Trusted Trade Agents: product finding/comparison/ordering with explanation and human approval. Full spoken ask pending. |
| IMG_9221 | `junction.hostinger`, `pets/hostinger`, CH-01, page_7c8af6bef6a4819181d4287ed2dea333 | Hostinger logo. Full challenge sentence not recoverable from sampled subtitles. Generic hosting/DNS assumptions would be premature. Official organizer site describes Hostinger keynote on validating real demand now building is cheap. |
| IMG_9222 | `junction.exa`, `pets/exa`, CH-07, page_bee8d02dffb48191b261b647ce021845 | Exa logo. 00:10 visible structured JSON research output for AI startups in Helsinki; 00:15 search/agent interface; 00:20 subtitle fragment **RAW LINKS**; 00:25 **THE JOB DONE**. These fragments suggest outcome-focused research, but do not establish exact challenge. |

Dense visual evidence: `research/video_b/9217_dense.jpg` through `9222_dense.jpg`; individual timestamped frames under `research/video_b/frames/<id>/`. Unmodified source hashes/durations in `media/manifest.json`.

## Source-bound agent fit findings

All six `pet.json` files were read at the pinned main SHA; raw connector results are in `pet_sources.json`.

* **Stoa** currently has notes, handoff planning and a fictional revision consistency check. It does not demonstrate grounding a real answer in a drawing or model. Add evidence-grounded drawing/model workflow; do not call the fictional checker a BIM integration.
* **S-Pankki** currently navigates public guidance and groups fictional spending. The Personal Economic Trainer preview needs conversational explanation and counterfactual outcomes backed by actual arithmetic; a category pie chart alone is weak.
* **Cala** currently frames schemas and reviews supplied provenance. The visible challenge asks for a real founder/investor need; correct provenance is enabling infrastructure, not the user outcome.
* **Valio Aimo** currently outlines menus/scales recipes. The Trusted Trade Agents preview points to purchasing decisions, trade execution boundaries and traceable comparison. Recipe scaling should support the trade decision, not stand in for it.
* **Hostinger** currently offers hosting/DNS planning. Keep this useful support capability but bind competition work to the actual brief when speech/platform evidence arrives.
* **Exa** currently produces search plans and supplied-evidence reviews. A real API-backed task with a verifiable completed output is the likely missing product layer; exact challenge still pending.

## Extraordinary concepts to challenge with Fable

These are analyst proposals, not partner requirements or achieved functionality. Scope one successful user journey per product; do not build six unrelated dashboards.

### Stoa: Revision impact lens

A site supervisor points at a room in a drawing and asks what changes because revision C moved a wall. Show an exact old/new overlay, changed quantities, affected door/MEP references and unresolved contradictions, each linked to a drawing region and revision. A conventional RAG answer describes documents; this product makes consequences inspectable. The decisive moment is injecting a newer contradictory note: the lens retracts the affected conclusion and asks the responsible discipline instead of silently choosing a source.

Weekend slice: two supplied model/drawing revisions, three document types, one room and one change. Extract typed entities and coordinates, retain immutable revision IDs, and compute deterministic dependency edges. Use existing Reality Twin geometry only after verifying reusable interfaces and license; no assumed production connection.

Proof: 20 held-out questions and known change annotations; compare answer-region correctness, unsupported-claim rate and time to locate evidence against a plain vector-search baseline. Run stale-revision, wrong-room and contradiction controls. Geometry/model reading must be demonstrated on the supplied files, not a fabricated result card.

### S-Pankki: Money flight simulator

The user asks why savings fell and whether a smaller eating-out budget would fund a goal. Trace the explanation to synthetic transaction rows, then let the user explore next-month scenarios. Deterministic code owns totals, refunds, internal transfers and recurring bills; the model owns accessible questions and explanation. Show ranges and assumptions where the data cannot determine an exact future balance. The striking moment is a hidden transfer/refund trap: ordinary categorization gets the answer wrong, while the simulator shows the exact correction.

Weekend slice: one synthetic household, three months, five conversational questions and one goal. Compare the baseline month with a scenario where one expense policy changes. Preserve transaction IDs so every numerical sentence is inspectable. No live account access or action is implied.

Proof: exact cent-level expected totals, duplicate/refund/transfer tests, counterfactual calculation correctness, and a small blinded comprehension comparison against a standard category chart. A good outcome is a user explaining the tradeoff accurately; conversational fluency alone is insufficient.

### Cala: First revenue map

Give a founder a narrow product thesis and return a dated map of five plausible first customers, their observable trigger, the missing evidence that could invalidate the fit, and the best next discovery question. Cala supplies typed company/person/funding relationships; Exa can verify fresh primary-source triggers. The novel insight is a relationship plus an observed change and a falsifiable need, rather than a generic startup profile or opaque unicorn score. No unsolicited outreach is required.

Demo: choose a founder thesis; surface a less obvious prospect; click through the exact dated facts; then change or remove a stale fact and watch the ranking/explanation change. Show why the highest-profile company was rejected. A founder can use the output immediately for discovery.

Proof: manually labeled small prospect set, held-out signal freshness, entity-resolution correctness, exact claim-source coverage and ranked usefulness judged blind against a generic research memo. Do not equate a network edge with permission to contact, a funding event with purchase intent, or a graph score with causal startup success.

### Valio Aimo: Kitchen recovery negotiation

A professional kitchen has tomorrow's service planned, then a key item becomes unavailable. Buyer and supplier agents construct two feasible replacement baskets that preserve servings, price limits and supplied dietary constraints. The kitchen sees the cost, difference from the original plan, source product facts and exactly what it approves. A quote change after approval invalidates that approval and requires a fresh decision. The strongest demo is not agents chatting: it is lunch remaining viable through a supply shock.

Weekend slice: supplied/mock catalog and inventory, one buyer, one supplier, one shortage, one quote/approval flow. Bind approval to the basket/quote hash and expiry; simulate the purchase or use the challenge's approved mock API. Kättely negotiation may support typed offers only after its actual interface is verified. Do not assert real stock or allergy safety from missing product facts.

Proof: deterministic basket arithmetic, serving feasibility, policy compliance, stale quote rejection, malicious catalog-text resistance and no duplicate order on retry. Compare time and error count with manual catalog search. A tool receipt must be distinguished from a completed order accepted by the mock/real challenge API.

### Hostinger and Exa

Hold final concepts until exact speech/full briefs are available. Two strong provisional directions to test are: Hostinger a customer-demand-to-working-product loop measured by a user's completed task, and Exa a research agent that returns a machine-checkable completed artifact rather than links. Both could share a narrow founder-first-revenue demo with Cala, but each partner's independent requirements and rules must be satisfied before combining entries.

## Fable questions

1. Which concept has a visible, defensible result in 90 seconds and which is just another chatbot wrapper?
2. What single unsupported assumption would destroy each demo, and what input/control proves it before the weekend is spent?
3. Which existing companion capability can actually run at pinned HEAD, and which proposal requires a new tool or provider connection?
4. Which concept has the clearest user benefit beyond the hackathon, and what would a skeptical domain judge reject?
5. Can a held-out input break the demo? Demand one adversarial case and a recovery, not only a scripted happy path.

## Gaps

Full spoken analysis, exact official judging criteria, challenge API/dataset grants, current Discord Q&A and independent Fable critique are pending separate owners. Do not mark this analysis as complete video study before ASR coverage is incorporated.
