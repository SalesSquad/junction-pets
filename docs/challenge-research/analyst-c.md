> Recovered historical analyst draft. Ideas and any pending-transcription statements may be superseded by official-briefs.md and fable-review.md. Referenced original contact-sheet paths were not recovered in this slice.

# Junction video C challenge analysis

Pinned pet baseline: 61f10a44cfd833e02fa64462dfc7429046fff210

Visual contact sheets plus dense 3-second samples; speech transcript pending. All concepts below are proposals, not sponsor requirements.

This draft compares the current companion packs with observed video themes. All named product concepts and metrics are proposals; a sponsor brief may further constrain them.

## Bahn Express · IMG_9223(1).MOV

Agent: `junction.bahn-express` / `pets/bahn-express`

Observed topic: Driver acceptance and dispatch economics.

**Current gap.** Transport briefs and custody explanations are support capabilities; the visible driver language suggests an operational decision problem to confirm from audio.

**Proposed concept: Dispatch Twin.** A dispatch decision world that compares plausible driver acceptance, pickup windows, return journeys and operational costs, with the actual reasons a match failed.

**Judge demo.** Replay a small fixed day of car moves. Compare current first-fit dispatch with a constraint solver, then inject a late cancellation and watch the proposal change with an explicit tradeoff.

**Proof.** Accepted assignments, on-time arrivals, deadhead distance, net contribution and fairness of work allocation; separate simulated from actual measured results.

**Challenge the premise.** Do not confuse a route optimum with a driver willingness prediction. A weekend model needs real labelled historical acceptance or an explicitly synthetic simulator.

**Reuse.** Aiven for event/state timeline; AfterQuery for dispatch environment and reward gaming tests.

Visible evidence:

- 00:15: Subtitle fragment: too little / takes the car; logo Bahn. Exact full request awaits audio.
- 00:30: Visible caption refers to what driver wants.

Open questions: Full spoken request, official brief and judging rubric need confirmation. Access to actual provider/API/data remains unverified.

## AfterQuery · IMG_9224(1).MOV

Agent: `junction.afterquery` / `pets/afterquery`

Observed topic: Agent evaluation environments.

**Current gap.** Current failure/rubric/adversarial packs fit the domain, but need an executable environment, an independently checked reward and actual model-versus-script results.

**Proposed concept: Agent Pressure Lab.** A deterministic business environment and adversarial scenario generator that exposes the shortest path to reward gaming and teaches why the failure occurred.

**Judge demo.** One seeded dispatch/order world: an agent completes easy tasks, receives high nominal reward, and then fails a hidden business invariant. Show the patched evaluator rejecting the shortcut and compare against a scripted baseline.

**Proof.** Held-out task success under perturbation, invariant violations, reward-outcome correlation, shortcut exploitation rate, cost and episode reproducibility.

**Challenge the premise.** A more elaborate benchmark is weak if the reward can be optimized without solving the actual problem. Show causal failure localization and one novel, reproducible exploit.

**Reuse.** Use Bahn dispatch as the real-world environment or Tieto PR review as a second domain. Keep task metrics separate from agent self-reports.

Visible evidence:

- 00:00: Caption fragment: action space.
- 00:09: Caption fragment: ...environment.
- 00:15: Caption fragment: models fall short.
- 00:18: Caption fragment: ...and open sou...

Open questions: Full spoken request, official brief and judging rubric need confirmation. Access to actual provider/API/data remains unverified.

## Tieto · IMG_9225(1).MOV

Agent: `junction.tieto` / `pets/tieto`

Observed topic: Trustworthy AI code change review.

**Current gap.** Current generic enterprise workflow pack misses a clearly visible PR/code-review trust topic.

**Proposed concept: Executable Change Witness.** Turn every AI-generated change claim into a source-linked, reproducible before/after check. Present the behavioral difference and its remaining evidence gaps to a human reviewer.

**Judge demo.** Open a small PR. Summary says a validation fix is complete. Click the claim to replay a failing case against base and head; expose a missing edge case; repair and rerun; show the now-supported claim and exact commit.

**Proof.** Seeded regression detection, false reassurance rate, source-link correctness, reviewer time to understand, unsupported claim rate.

**Challenge the premise.** A fluent code explanation is not proof. Screenshots, green subsets and a model saying tests passed are insufficient to establish the requested behavior. Bind checks to exact source and keep the decision human-owned.

**Reuse.** Reuse existing Witness, repo-control, capability graph or Knowledge OS through clearly owned interfaces instead of creating a fourth coordination system.

Visible evidence:

- 00:03: new pull request
- 00:15: ...was done, what it is...
- 00:51: ...generated by the AI so that
- 00:54: THE HUMANS CAN TRUST IT?

Open questions: Full spoken request, official brief and judging rubric need confirmation. Access to actual provider/API/data remains unverified.

## MariaDB Foundation · IMG_9226(1).MOV

Agent: `junction.mariadb` / `pets/mariadb`

Observed topic: Wikipedia and modern database features.

**Current gap.** Current EXPLAIN/index-review companion is useful database support, but video shows Wikipedia dataset and the specific Foundation demo.

**Proposed concept: Wikipedia Evidence Time Machine.** Ask what Wikipedia said about a topic at a date, across languages, and trace precisely which revision changed the answer; combine retrieval with database time travel rather than only generating an answer.

**Judge demo.** A slider moves between two supplied historical revisions. The same question changes its answer and highlights the changed passages; switching language reveals differing coverage. Every answer links to exact article/revision and makes uncertain coverage visible.

**Proof.** Revision/time selection correctness, citation span accuracy, retrieval quality on held-out questions, reproducible latency at a declared dataset scale.

**Challenge the premise.** A historical encyclopedia revision is evidence of what was written then, not ground truth. Full edit histories include noisy changes and deletes. Do not present temporal provenance as truth verification.

**Reuse.** Official MariaDB datasets and vector/time-versioning tutorials reduce setup; Context or Oxylabs could optionally add a present snapshot, not silently blend it with historical data.

Visible evidence:

- 00:12: peer-reviewed ...articles (partly occluded)
- 00:27: MariaDB terminal selecting wikipedia database
- 00:33: SQL shown: SELECT lang, COUNT(*) AS articles ... FROM art...

Open questions: Full spoken request, official brief and judging rubric need confirmation. Access to actual provider/API/data remains unverified.

## City of Espoo · IMG_9227(1).MOV

Agent: `junction.city-of-espoo` / `pets/city-of-espoo`

Observed topic: Recruitment and demonstrated fit.

**Current gap.** Current city-service finder is materially misaligned with the visible recruitment/matchmaking challenge.

**Proposed concept: Proof of Fit.** A two-sided matching workspace where a candidate demonstrates one job-relevant skill and an employer expresses the real task; matching explains supporting evidence, missing proof and a concrete next step.

**Judge demo.** Use the organizer synthetic recruitment fixture when supplied. A nontraditional candidate opts into a job-relevant discovery conversation, opens one work-sample proof, and sees the requirement it supports plus one unanswered must-have. The employer sees the same evidence and chooses the next human conversation. No automatic applicant rejection or covert screening.

**Proof.** Traceable skill-evidence coverage, unsupported fit claims, human-rated discovery relevance, time to an informed mutual introduction and next-step completion. Do not claim hiring suitability from an algorithmic score.

**Challenge the premise.** Do not build another keyword CV scorer. A predicted fit without demonstrated evidence cannot establish candidate suitability. The candidate must control what evidence is shown; evaluation needs real user feedback eventually.

**Reuse.** Capability/skill graph can map transferable skills; Context/Oxylabs only for explicitly public company/job context; no scraping private profiles.

Visible evidence:

- 00:15: through matchmaking ...events
- 00:18: rethinking recru...
- 00:21: this synthetic...
- 00:30: demonstrate real...
- 00:33: ...generic resumes.
- 00:45: genuine fit...
- 00:48: transpa...

Open questions: Full spoken request, official brief and judging rubric need confirmation. Access to actual provider/API/data remains unverified. Tiny ASR may explicitly say without automated screening around 00:45–00:55; full wording needs stronger ASR/brief confirmation. Proposal already avoids screening.

## Context.dev · IMG_9228(1).MOV

Agent: `junction.context-dev` / `pets/context-dev`

Observed topic: Live web as structured changing context.

**Current gap.** Current extraction/freshness plans need an actual working product that reacts to semantic change, rather than a schema worksheet.

**Proposed concept: Reality Delta.** A decision assistant whose recommendations point to source facts, detect meaningful changes, and show exactly which previous conclusion was invalidated.

**Judge demo.** A public supplier/job/product page changes. The pipeline extracts typed fields with source timestamps, distinguishes a layout edit from a substantive change, and updates the affected recommendation while preserving the previous decision trail.

**Proof.** Extraction field accuracy, meaningful-change precision/recall, latency from observation to updated decision, stale dependencies, bounded request cost.

**Challenge the premise.** A fresh scrape is not automatically a relevant change. Source update time may differ from observation time; recommendations must not silently persist when their source facts expire.

**Reuse.** Use Context API for live collection; Redis/Aiven for event/cache state only if existing access works. The hook is source-change-to-decision accountability.

Visible evidence:

- 00:00: THE LIVE WEB IS VERY MESSY.
- 00:06: TURN ANY WEBSITE, COM...
- 00:15: YOUR REAL-TIME DATABAS...
- 00:24: REAL-TIME WEB CHANGES.
- 00:27: REAL-TIME NEWS ARTIC...
- 00:33: ...IS A FUNCTIONAL PRODUCT...

Open questions: Full spoken request, official brief and judging rubric need confirmation. Access to actual provider/API/data remains unverified.

## Oxylabs · IMG_9229(1).MOV

Agent: `junction.oxylabs` / `pets/oxylabs`

Observed topic: Internet/web API infrastructure.

**Current gap.** Existing collection-plan/quality-check pack describes the domain but needs a concrete product journey using their technology.

**Proposed concept: Evidence Supply Line.** The bounded acquisition and verification layer for the other challenge demos: canonicalize records, preserve source/time, detect duplicates and stale pages, and return traceable extraction rather than ungrounded facts.

**Judge demo.** One visible job or product decision traverses a small allowed source set. Show the source passage per typed value, an extraction error rejected by a schema, a duplicate merged, and the downstream decision retaining provenance.

**Proof.** Field precision/recall on a manually labelled source set, duplicate handling, stale detection, end-to-end latency and request budget.

**Challenge the premise.** Infrastructure alone is an enabling component rather than a compelling final product. Pair the layer with one high-value decision and show the consequence of wrong data.

**Reuse.** Use with Espoo demonstrated-fit context or Context source-change product; avoid duplicate collection pipelines with conflicting source identities.

Visible evidence:

- 00:01: BUILD THE PROXY NETWORKS
- 00:15: ...INTERNET USING WEB API...
- 00:30: ...MAIN CHALLENGE PROJECT...

Open questions: Full spoken request, official brief and judging rubric need confirmation. Access to actual provider/API/data remains unverified.

## Portfolio synthesis

The strongest entry is a product with a measurable decision loop, not a collection of planning chatbots. Reuse one evidence model across the prototypes: source or event → typed claim → business invariant → reversible proposal → observed outcome. Tieto shows the evidence for an AI code change; AfterQuery breaks the reward; MariaDB preserves what evidence existed at a time; Context and Oxylabs supply live context; Espoo turns demonstrated skill into a mutually understood next conversation; Bahn exposes the pricing and acceptance tradeoff in an executable environment. Each must still meet its own sponsor brief.

## Fable challenge request

Attack these concepts for sponsor-fit, weak differentiation, reward gaming, weekend feasibility, user value and demo strength. Rank them using explicit evidence. Identify the smallest 90-second demo that would falsify each main claim. Reject concepts that merely wrap a generic model, treat historical claims as truth, infer hiring suitability from a black box, or claim actual provider execution from a synthetic example. Say which existing project capabilities are reusable and which assumptions require sponsor confirmation.
