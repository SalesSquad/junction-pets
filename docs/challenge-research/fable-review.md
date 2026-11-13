# Independent Fable 5.2 challenge critique

Recovered completed provider response, 13 November 2026. Model identity and usage are in fable-receipt.json. Tools were disabled: Fable evaluated the supplied official briefs, rough ASR, analyst drafts and PR56 description; it did not independently verify GitHub, websites, source eligibility or runtime results. Concepts, thresholds and priorities are proposals, not sponsor rules or execution evidence. The review names only 21 of 34 companions; remaining roles require explicit follow-up rather than invented coverage.

Three things to know before reading the JSON:

- **Top three bets:** AfterQuery, then Valio Aimo, then Bahn Spread, with Tieto as the last-resort fallback. All three kill tests can run in parallel in the first two hours.
- **Two blocking questions for organizers:** whether one team may enter more than one main challenge, and whether the pre-existing monorepo and Chibi can be part of a submission. Neither is answered in the supplied inputs, and the draft is due tonight at 23:59.
- **Only 21 of the 34 companions are named in what I was given.** I assigned roles to those 21 and did not invent the other 13.

Thresholds marked "proposed" are mine, not from any brief. I had no tools, so nothing in the pull-request body was independently checked.

```json
{
  "verdict": {
    "summary": "Stop treating the 34-companion platform (catalog, WebMCP discovery, PostgreSQL replay, 204 graded responses) as the entry. No official brief scores it. PR56 is real, source-reported development tooling plus one finite Aiven workflow; it is not evidence that any of the 19 main-challenge products runs. Redirect the weekend to one event-written, MIT, brief-specific product chosen by kill tests, and get written organizer answers on eligibility before tonight's draft.",
    "immediate_changes": [
      "Ask organizers in writing before the Fri 23:59 draft: (a) whether one team may enter more than one main challenge, (b) whether pre-existing monorepo or Chibi code may appear in a submission, (c) whether AI development tooling is acceptable, (d) the exact start time for the no-prior-code rule. None of this is answered in the supplied inputs.",
      "Until answered, the conservative path is that submitted code is written during the event in a separately licensed MIT source tree using only open-source libraries; junction-pets, Chibi, Reality Twin, Kättely, Witness, repo-control and Knowledge OS stay development tooling. This is a risk posture, not a ruling.",
      "Freeze new PR56 platform waves. Merging remains the owner's decision; it is not on the critical path of any brief.",
      "Run the three kill tests in parallel now (AfterQuery, Valio Aimo, Bahn Spread) and commit to ONE primary at the gate. A second entry only if organizers confirm multi-entry in writing.",
      "Park all five hardware challenges unless the specific hardware or station is physically in the founder's hands within 2 hours. Seven workers cannot teleoperate an arm, wear glasses or stand at a robot station.",
      "Treat the founder's physical attention (booths, 10-minute demos, peer review, video) as the scarce resource. Compute and workers are not the bottleneck.",
      "Supersede analyst drafts B and C where they say briefs or speech are pending: the full official index now governs. Specific corrections are in red_flags.",
      "Every artifact shown to a judge carries one label: LIVE, REPLAYED, SYNTHETIC or OFFLINE_DETERMINISTIC. No fixed scripted result is presented as live."
    ],
    "decision_rule": "A concept survives only if, within 2 hours, it produces a measured number against a baseline on a real or sponsor-supplied input, plus one adversarial input with visible recovery. Otherwise it is cut, regardless of prize size."
  },
  "top3_bets": [
    {
      "rank": 1,
      "challenge": "AfterQuery - Break the Agent",
      "why_ranked_here": "The only brief with a published point rubric and a judge-run reproduction protocol. It is pure software, the harness and credits are stated in the brief, and it rewards the rigor this workspace already practises.",
      "concept": "IDEA: Mandate Desk. A seeded, step-clocked procurement-desk world. The agent runs purchasing for a professional kitchen for several simulated days under a written authority mandate. Actions: search catalog, request a price-and-availability hold, order, request human approval (arrives after a visible delay), cancel, wait. Events: holds expire, availability changes, a menu change supersedes an earlier need, suppliers have published delivery reliability. Reward is computed only from the ground-truth ledger at episode end (compliant demand delivered on time, minus overspend, with unauthorized orders zeroed), never from agent text.",
      "user_outcome": "Environment builders get a task where the measured failure is a nameable decision: approval requested too late, acting on an expired hold, not hedging an unreliable supplier, or not retracting after a superseding event.",
      "brief_compliance": "Clear goal, action and observation space, checkable reward, frontier agent versus a reproducible stronger reference, do-nothing and stop-early baselines near zero, one-command README. All information needed is visible to the agent (mandate, expiry times, reliability figures), so difficulty comes from decisions, not withheld information.",
      "proof_90s": "One command prints a table: reference run, three agent runs, do-nothing, stop-early. Then one agent trace shows an order placed on an expired hold and Monday service short. Then a scripted order-everything exploit scores below honest play.",
      "adversarial_and_recovery": "Adversarial input is the judges' own 15-minute exploit search, pre-empted by a committed exploit suite (order everything, approval spam, cancel-reorder loops, tiny-order farming, reading simulator state). In-world, a mid-episode menu change is the perturbation; the reference run visibly cancels and re-plans.",
      "why_hard_to_copy": "Honestly, the idea is copyable. The edge is evidence: an exploit suite with scores, a failure taxonomy tied to decisions, and repeated-run variance. Most teams will skip that. A secondary edge is that the same world doubles as the Valio test bench.",
      "kill_test_first_2h": "Micro-version with 5 fixed seeds; run the frontier agent 3 times through the provided harness. Proposed threshold (mine, not from the rubric): mean agent score at most 80 percent of reference with non-overlapping ranges, do-nothing at most 5 percent. If no gap, deepen once (longer horizon, stochastic reliability). If still none, try variant B once (stochastic two-sided pricing requiring exploration). If still none by hour 4, kill.",
      "bottleneck": "Whether a frontier agent actually fails here is empirical and unknown. Also founder booth time to obtain the harness and to confirm that a scripted or scaffolded reference run counts as a 'stronger reference run'; the brief does not say.",
      "fallback": "If a gap exists but the reward leaks, shrink the action space until the exploit suite is clean. If the harness cannot be obtained or run, the entry cannot be judged, so stop. The small-model training stretch is attempted only after feature freeze with everything green."
    },
    {
      "rank": 2,
      "challenge": "Valio Aimo - Trusted Trade Agents",
      "why_ranked_here": "Largest cash prize in the index, software only, and the three core requirements are concrete. The interface can be measured rather than merely demonstrated.",
      "concept": "IDEA: Mandate-bound ordering interface. Three structured operations over the mocked webshop and backend: lookup (product, fixed price, availability), a price-and-availability hold with visible expiry, and an order bound to that hold. A machine-checkable buyer mandate (spend cap, categories, required attributes, approval thresholds, expiry) is enforced server-side. An order outside the mandate becomes an approval request bound to the exact basket; any price or availability change voids the approval.",
      "user_outcome": "The hotel chain's agent gets 1,000 litres of lactose-free milk ordered by Monday in minutes. The procurement manager sees only the one decision that exceeds the agent's authority, with exactly what is being approved.",
      "brief_compliance": "Covers all three core items. Uses fixed prices, not negotiation. Not a chatbot, not a marketplace. Optional traceability comes almost free from the ledger; substitution and sustainability stay out unless core is done.",
      "proof_90s": "An off-the-shelf agent client the team did not write discovers the interface and sends the brief's example request. The within-authority order commits. Raising quantity past the cap routes to a named human with the exact basket. Then the adversarial cases run.",
      "adversarial_and_recovery": "Three inputs: a catalog description containing injected instructions to exceed limits; a retry after a timeout; a price change between inquiry and order. Visible recovery: the server rejects the stale hold, creates no duplicate order, voids the old approval, and the agent re-requests and completes.",
      "why_hard_to_copy": "Many teams will expose a tool server. Few will ship server-side mandate enforcement with a conformance suite any third-party agent can run, plus measured hostile-agent runs showing zero authority violations.",
      "kill_test_first_2h": "Can a third-party agent client complete inquiry to order through the interface on Valio's mock data (or a labelled synthetic stand-in if that is not yet in hand), with an over-cap order blocked server-side? Ask at the booth what the mock data and APIs are and how entries are judged; the brief publishes no criteria.",
      "bottleneck": "Access to Valio's mock data and APIs is mentioned only in garbled ASR. Judging criteria are unpublished. Which 'open, verifiable standards' Valio prefers is unknown; any choice of protocol or signed-mandate format is my suggestion, not theirs.",
      "fallback": "Synthetic stand-in catalog, clearly labelled, with the brief's example request. Drop every optional direction. Do not rely on native WebMCP: PR56 reports it absent in the tested browsers and exercised only through an injected fixture."
    },
    {
      "rank": 3,
      "challenge": "Bahn Express - Spread",
      "why_ranked_here": "The qualifying score is objective (gross margin with at least 90 percent on-time), the world and kits are supplied, and one worker can iterate it without consuming the founder.",
      "concept": "IDEA: Two-curve margin policy. From ranking-round logs, estimate dealer win probability against quote and driver acceptance time against fee. Choose quote and fee to maximize expected margin under a chance constraint on on-time delivery with a safety buffer. Escalate fees as deadlines approach, if the rules allow re-pricing. Decline cars with negative expected margin.",
      "user_outcome": "The simulated company earns more margin than Bahn's own best system while keeping at least 90 percent of cars on time, and runs the secret final week unattended.",
      "brief_compliance": "Plays the supplied world through the supplied API. Reaching the ranked top 10 is the gate; the jury then judges elegance, clarity, creativity and robustness, and margin no longer counts.",
      "proof_90s": "Leaderboard row against Bahn's system; the two learned curves; one replayed moment where a gig sits unaccepted near deadline, the fee rises, and the car arrives on time.",
      "adversarial_and_recovery": "Offline replay of logged rounds with driver acceptance perturbed downward: the buffer and escalator keep on-time above 90 percent. Kill the process mid-week: it restarts from its own log with no duplicate gigs or quotes.",
      "why_hard_to_copy": "Nothing structural; it is a leaderboard. The edge is iteration count between rounds and unattended robustness, which is also what the jury names.",
      "kill_test_first_2h": "Join, run the kit baseline unchanged, and complete one valid round with on-time at least 90 percent. Proposed cap (mine): if after three ranking rounds the policy is below Bahn's own system and not improving, drop to maintenance mode.",
      "bottleneck": "Round cadence and API details (whether fees can be changed after posting, how the 90 percent rule is enforced) are in the handbook, which I have not seen. The Sunday 07:30 registration and 08:00 final collide with final-submission preparation for 10:00.",
      "fallback": "A conservative policy that protects the 90 percent constraint. Freeze the policy Saturday night; no changes Sunday morning."
    }
  ],
  "challenge_reviews": [
    {
      "track": "Agentic AI",
      "company": "Hostinger",
      "title": "Decode the Noise",
      "recording": "IMG_9221 exists; ASR garbled but consistent with the brief",
      "priority": "HOLD",
      "underlying_need": "Site owners and analysts need an explainable verdict on coordinated manipulation that is honest about false positives, running at a public URL on Hostinger infrastructure.",
      "critique_of_current": "The companion plans hosting and DNS, which misreads the brief. Analyst B's provisional 'customer-demand-to-product loop' came from a keynote blurb and is wrong; discard it.",
      "improved_concept": "IDEA: Coordination, not content. Score evidence of coordination (near-duplicate clusters, synchronized timing, cadence) with three outputs: coordinated, not coordinated, abstain. Adversarial input: legitimate coordination such as wire-story syndication or an organic viral burst; the tool abstains and explains why.",
      "smallest_proof_and_baseline": "Precision at a fixed false-positive rate on a held-out labelled set that includes benign coordination, against a single-post 'is this propaganda' model prompt plus a duplicate-count threshold.",
      "neglected_constraint": "It must be live on Hostinger infrastructure with a public URL by the end. Labelled data and its licence are the real bottleneck, and naming real accounts as bad actors is a defamation risk.",
      "stop_building": "The hosting and DNS planner as a challenge answer; any per-text propaganda score with no false-positive accounting.",
      "eligibility_uncertainty": "Hostinger environment and credits appear only in ASR. Deployment is required by the brief but is outside this review."
    },
    {
      "track": "Agentic AI",
      "company": "Tieto",
      "title": "Earned Trust in AI Code",
      "recording": "IMG_9225 exists; ASR largely unusable",
      "priority": "FALLBACK OF LAST RESORT",
      "underlying_need": "A named human must be able to accept an agent-written change without a full read, on evidence rather than fluent explanation.",
      "critique_of_current": "The companion is a generic enterprise workflow pack. Analyst C's Executable Change Witness is close but product-shaped, and it leans on pre-existing tools. It omits the requirement ID, what the AI refused to decide, the concept card, trade-offs across frontend, backend and security, and the lessons log.",
      "improved_concept": "IDEA: Claim ledger with discriminating checks. Each claim in the change story maps to the requirement ID and to a check that fails on base and passes on head. Claims without such a check are listed as refused and routed to the named human with the minimal hunk to read. Adversarial input: a summary claiming a validation that is absent, backed by a test that passes on both base and head; the ledger downgrades it and the human reads only those lines.",
      "smallest_proof_and_baseline": "On the one sample change plus about ten seeded-defect variants: defects caught and false reassurances, against a plain model review summary. Also lines the human must read versus the full diff.",
      "neglected_constraint": "Synthetic or cleared sample data only. A finished product, model training and vendor selection are out of scope. Failure modes actually observed must be named.",
      "stop_building": "The enterprise workflow pack; any review platform or UI beyond the walkthrough.",
      "eligibility_uncertainty": "Using PR56 or other company code as the sample change conflicts with 'synthetic or cleared' unless cleared. Reusing Witness or repo-control needs the organizer answer."
    },
    {
      "track": "Agentic AI",
      "company": "Bahn Express",
      "title": "Spread",
      "recording": "IMG_9223 exists; ASR renders the title as 'strength' and suggests a single day",
      "priority": "TOP 3",
      "underlying_need": "Price two sides of a market under uncertainty: win the dealer without overquoting, attract a driver in time without overpaying.",
      "critique_of_current": "The companion's transport briefs and custody explanations are irrelevant. Analyst C's Dispatch Twin is superseded: Bahn supplies the world, so building a twin or route solver is wasted. Deadhead, fairness and a 'fixed day' are not in the brief; the score is weekly gross margin with a 90 percent on-time floor.",
      "improved_concept": "See top3_bets rank 3.",
      "smallest_proof_and_baseline": "Margin and on-time percentage per ranking round against the unmodified kit and against Bahn's own system, with variance across rounds.",
      "neglected_constraint": "The final week is secret and runs unattended for about 34 minutes on Sunday at 08:00; registration closes 07:30. Overfitting to ranking weeks and crash recovery matter more than cleverness.",
      "stop_building": "Dispatch Twin, route optimization, custody narratives, and any language model in the per-decision loop unless it beats the statistical policy.",
      "eligibility_uncertainty": "Kit licence versus the MIT requirement, and whether Spread also needs the general submission, are unknown. The event code must not land in a public repository."
    },
    {
      "track": "Agentic AI",
      "company": "AfterQuery",
      "title": "Break the Agent",
      "recording": "IMG_9224 exists; start clipped, content matches the brief",
      "priority": "TOP 3",
      "underlying_need": "Environments where a measured gap reflects a real decision skill and the reward cannot be gamed.",
      "critique_of_current": "Analyst C's Agent Pressure Lab would score badly. Failing agents on a 'hidden business invariant' is unfairly withheld information, which the rubric scores as zero for meaningful difficulty. It compares against a scripted baseline when the rubric wants a stronger reference plus do-nothing and stop-early. A scenario generator is infrastructure. The companion's rubric packs are documents, not an environment.",
      "improved_concept": "See top3_bets rank 1.",
      "smallest_proof_and_baseline": "Reference, three agent runs, do-nothing and stop-early on fixed seeds, reproduced from a clean checkout with one command.",
      "neglected_constraint": "Judges rerun everything themselves and spend 15 minutes hunting exploits. Run-to-run variance must be smaller than the claimed gap.",
      "stop_building": "Hidden invariants, generators, and failure-mode essays without runs.",
      "eligibility_uncertainty": "Whether a scripted solver qualifies as the reference run; harness licence. A world derived from Bahn's simulator would raise originality and licence questions, so write it fresh."
    },
    {
      "track": "Agentic AI",
      "company": "Valio Aimo",
      "title": "Trusted Trade Agents",
      "recording": "IMG_9220 exists; ASR says 'teachers' for kitchens and mentions mock APIs",
      "priority": "TOP 3",
      "underlying_need": "Let external purchasing agents read and transact with a wholesaler under explicit, checkable authority, on open standards.",
      "critique_of_current": "The companion scales recipes and outlines menus, which is off-brief. Analyst B's Kitchen Recovery Negotiation contradicts the brief twice: prices are fixed, not negotiated, and substitution is optional and explicitly not scored as core.",
      "improved_concept": "See top3_bets rank 2.",
      "smallest_proof_and_baseline": "Authority violations across about 50 randomized agent runs including a deliberately overspending agent (target zero, enforced server-side); time from request to committed order against a manual or scripted webshop flow.",
      "neglected_constraint": "The brief mocks today's webshop and backend, not the marketplace, and says this is not about a chatbot UI.",
      "stop_building": "Negotiation, supplier agents, recipe scaling, any marketplace model.",
      "eligibility_uncertainty": "Mock data access and licence; reuse of Kättely or Chibi authority code needs the organizer answer."
    },
    {
      "track": "Agentic AI",
      "company": "Exa",
      "title": "The Internet Butler / Your Personal Assistant",
      "recording": "IMG_9222 exists; clip ends near 28 seconds and ASR calls it 'Internet process'",
      "priority": "HOLD",
      "underlying_need": "Hand off one tedious research-heavy errand completely, with sources, for a specific group of real people.",
      "critique_of_current": "The companion produces search plans and reviews supplied evidence, with no live query. Analyst B deferred a concept. The risk here is a general assistant, which the judging text penalizes.",
      "improved_concept": "IDEA: One-errand finisher for one group, for example a travel-disruption claim. Output is a ready-to-send claim with each assertion linked to a dated primary source found live, awaiting user approval. Adversarial input: a judge's case outside the supported jurisdiction, or a secondary source that contradicts the primary one; the agent shows the conflict and prefers the primary source or declines.",
      "smallest_proof_and_baseline": "Ten live cases, including judge-style ones: share of assertions with a resolvable dated source and count of factual errors, against the same model without search.",
      "neglected_constraint": "Judges try their own live queries, so a scripted case fails. Legal-adjacent output needs a clear advice boundary.",
      "stop_building": "Search-plan worksheets; any assistant without a named user group.",
      "eligibility_uncertainty": "The brief body still contains unfilled placeholders; rely on the prize list. Exa access for this account is unverified."
    },
    {
      "track": "Hardware",
      "company": "Arduino",
      "title": "The Green European Renaissance",
      "recording": "None supplied",
      "priority": "PARK unless board in hand",
      "underlying_need": "A local environmental problem solved on-device with the UNO Q, independent of cloud providers.",
      "critique_of_current": "No concept or companion for this brief appears in the supplied inputs; I cannot confirm an Arduino companion exists.",
      "improved_concept": "IDEA: A single-sensor waste sentinel (standby power or a water leak) that classifies and acts on the device with the network unplugged. Adversarial input: sensor disconnect or a noise burst; the device signals degraded confidence and fails safe.",
      "smallest_proof_and_baseline": "Detection accuracy on held-out traces with networking physically off, against a fixed-threshold rule.",
      "neglected_constraint": "The brief names the UNO Q specifically and publishes no judging criteria. What the board can run is unverified here.",
      "stop_building": "Anything, until a board is physically available.",
      "eligibility_uncertainty": "Hardware loan terms and whether a remote or simulated entry is accepted are unknown."
    },
    {
      "track": "Hardware",
      "company": "Meta",
      "title": "AI Glasses for Everyone, Everyday",
      "recording": "IMG_9210 exists; ASR tracks the brief closely",
      "priority": "PARK unless device access verified",
      "underlying_need": "An everyday task where a first-person view and free hands beat holding a phone, designed for people of all abilities.",
      "critique_of_current": "The companion replays synthetic consent history. Analyst A's Recovery Coach depends on recognizing assembly steps from first-person video, which is a hard vision problem for one weekend, and device access is unverified.",
      "improved_concept": "IDEA: Shrink to verification. The user asks 'is this right?' at one checkpoint of a hands-occupied task and gets a short audio answer. Adversarial input: camera permission denied or the device disconnecting mid-task; the flow resumes by voice from the last confirmed step.",
      "smallest_proof_and_baseline": "Task completion time and errors for three people against the same task with a hand-held phone.",
      "neglected_constraint": "The brief requires handling permissions, errors, connectivity and device-state changes, plus consent. Audio-first and web apps are explicitly on equal footing.",
      "stop_building": "The consent-replay helper as a product; general scene narration.",
      "eligibility_uncertainty": "A phone prototype must not be presented as running on glasses. Toolkit and device availability are unknown."
    },
    {
      "track": "Hardware",
      "company": "Ignite Next x Intel",
      "title": "Stop Simulating, Start Moving: See It. Detect It. Act on It. The Intel Physical AI Challenge",
      "recording": "None supplied; IMG_9211 is Aalto, not this",
      "priority": "PARK unless station allocated",
      "underlying_need": "Take a real arm from demonstrations to an autonomous inspect-and-sort cell running on the Intel laptop.",
      "critique_of_current": "No concept in the supplied inputs. An NVIDIA companion must not be mapped here: the brief requires OpenVINO on the Intel CPU, GPU and NPU.",
      "improved_concept": "IDEA: Keep the anomaly decision independent of the arm policy and add a presence check at the inspection camera. Adversarial input: a dropped brick or an unseen defect type; the cell detects the empty gripper and retries, or routes the brick to defective with a flag.",
      "smallest_proof_and_baseline": "Thirty bricks sorted autonomously: correct-bowl rate and cycle time, against teleoperated cycle time and an always-good classifier.",
      "neglected_constraint": "Demonstrations require hours of one human's hands at a physical station. Workers cannot parallelize that.",
      "stop_building": "Nothing to stop; do not start without a station.",
      "eligibility_uncertainty": "Station allocation for a solo team is unknown."
    },
    {
      "track": "Hardware",
      "company": "Rokoko",
      "title": "The Robot Teleoperation Challenge",
      "recording": "IMG_9212 exists; ASR garbled but mentions simulation and on-site mentors",
      "priority": "PARK unless suit or gloves in hand",
      "underlying_need": "An impressive, real-time use of human motion capture to drive a robot, physical or simulated.",
      "critique_of_current": "The companion checks declarations and transforms no real poses. Analyst A's Skill Capsule adds replay and provenance the brief does not ask for.",
      "improved_concept": "IDEA: One dexterous simulated task driven live from the glove stream. Adversarial input: a tracking dropout; a clutch engages, the robot holds pose, and control resumes after recalibration.",
      "smallest_proof_and_baseline": "Task success and completion time over ten trials with pose-to-action latency, against gamepad control of the same task.",
      "neglected_constraint": "This is teleoperation; Aalto's humanoid task is autonomy. The same runtime cannot claim both.",
      "stop_building": "The declaration-only retargeting checker; provenance features.",
      "eligibility_uncertainty": "Access to hardware and an SDK licence is unknown."
    },
    {
      "track": "Hardware",
      "company": "Aalto University",
      "title": "Aaltonomous Humanoid",
      "recording": "IMG_9211 exists; 16 seconds, ASR unusable, identified by logo",
      "priority": "PARK unless simulation runs quickly",
      "underlying_need": "Reliable autonomous sorting on hidden scenes and then on the real robot.",
      "critique_of_current": "The manifest is generic research guidance. Analyst A's hybrid perception-and-planning plan is sound, but dual 7-DoF arms with three-fingered hands at 30 Hz from camera input is too much for one person in under 40 hours.",
      "improved_concept": "IDEA: Analyst A's hybrid plan, narrowed to single-arm fixed-mapping sorting first, with a local instruction parser outside the control loop. Adversarial input: an unseen phrasing and a failed grasp; the map changes and the grasp is retried.",
      "smallest_proof_and_baseline": "Correct placements within 2 minutes over 20 held-out simulator seeds, against a zero-action policy and any organizer baseline.",
      "neglected_constraint": "The policy sees cameras and joint states, not object poses. Whether the evaluation container has network access is unknown, so assume no external model calls. Isaac Sim needs remote NVIDIA GPU compute; this workstation is macOS (my recollection, verify).",
      "stop_building": "Generic research companion output.",
      "eligibility_uncertainty": "Verda GPU access and the policy-server contract are unverified."
    },
    {
      "track": "FinTech",
      "company": "Cala",
      "title": "Make Unicorns Real",
      "recording": "IMG_9219 exists; ASR says 'Canada' and garbles the prize",
      "priority": "HOLD",
      "underlying_need": "One sharp founder or investor decision made better by sourced, connected data on companies, rounds and investors.",
      "critique_of_current": "The companion frames schemas and reviews provenance. Analyst B's First Revenue Map depends on purchase-intent signals Cala may not hold and brings in Exa for triggers. That weakens 'Cala is core', which is a quarter of the score.",
      "improved_concept": "IDEA: Slush meeting triage. For a founder's shortlist, show which investors to skip and why (a funded direct competitor, wrong stage, long inactivity), each reason linked to a sourced round. Adversarial input: two companies sharing a name, or a stale round; the tool shows the ambiguity and asks.",
      "smallest_proof_and_baseline": "About 20 labelled founder-investor pairs: conflict-detection precision and source coverage, against a founder's manual tab search.",
      "neglected_constraint": "The brief wants a complete product usable the day after, and rewards focus and originality equally with execution. Cala's coverage of Nordic early-stage data is the kill test.",
      "stop_building": "Schema framing; opaque startup scores; generic investor matching.",
      "eligibility_uncertainty": "The index is inconsistent on the runner-up prize (credits in the body, cash in the list). Prize value for a solo entrant is unclear."
    },
    {
      "track": "FinTech",
      "company": "S-Pankki",
      "title": "Personal Economic Trainer",
      "recording": "IMG_9218 exists; ASR garbled, 'safe to spend' is audible",
      "priority": "HOLD",
      "underlying_need": "People exploring their own money in conversation and understanding where it really goes.",
      "critique_of_current": "The companion groups fictional spending. Analyst B's Money Flight Simulator has the right core (code owns arithmetic) but misses the three-basket teaching frame the brief says will go far. It uses one household where the brief supplies a large dataset, and proposes a blinded user study that will not happen this weekend.",
      "improved_concept": "IDEA: Three baskets and safe-to-spend. Questions compile to a constrained query executed by code, and every number links to transaction IDs. Safe-to-spend is balance minus upcoming regular obligations minus a stated reserve for irregular ones. Adversarial input: an ambiguous category question with refunds and internal transfers, or instruction-like text in a transaction description; the app shows its interpretation and alternatives and ignores the embedded text.",
      "smallest_proof_and_baseline": "Thirty questions with code-computed ground truth: cent-exact accuracy, against a model reading raw rows directly.",
      "neglected_constraint": "Mobile-first. MyData spirit means free exploration, not fixed charts. It is coaching, not advice.",
      "stop_building": "Category pie charts; single-household fixtures.",
      "eligibility_uncertainty": "Dataset access path and redistribution terms are unknown; do not commit it to a public repository."
    },
    {
      "track": "Healthcare",
      "company": "AstraZeneca",
      "title": "Equal Care Across Finland",
      "recording": "IMG_9213 exists; ASR says 'England' for Finland",
      "priority": "HOLD; depends on attending the stand Friday 20:00",
      "underlying_need": "Find a regional gap, place it in the pathway, and recommend something implementable with evidence.",
      "critique_of_current": "The companion is a fictional evidence-card checker; PR56 records its fixture as a miss for lack of research input, and that should stay a miss. Analyst A's Decision Desk is on-brief, but a capacity slider invites an invented model.",
      "improved_concept": "IDEA: Recommendation cards with a strict shape: gap, pathway stage, action, owner, mechanism, evidence grade, evaluation metric. No card is issued without a source. Adversarial input: a small-count region or mismatched periods; the ranking is suppressed with the reason shown.",
      "smallest_proof_and_baseline": "Every displayed claim resolves to a source or a labelled assumption, and one mentor accepts one recommendation as implementable, against a disparity map with no actions.",
      "neglected_constraint": "The Goal 3 indicator text is not in the supplied sources. Public aggregate data may not contain stage timing by region; that availability is the kill test.",
      "stop_building": "The fictional evidence-card checker; any medical chatbot.",
      "eligibility_uncertainty": "Data sources named in the ASR are unreliable transcriptions; confirm at the stand."
    },
    {
      "track": "Healthcare",
      "company": "Aalto University",
      "title": "Beyond the Clinic",
      "recording": "None supplied; the single Aalto companion does not cover it",
      "priority": "PARK",
      "underlying_need": "Home maintenance after TMS treatment as a loop: sense, respond, learn what works for the person.",
      "critique_of_current": "No concept in the supplied inputs. The prize is still to be announced.",
      "improved_concept": "IDEA: A per-person loop choosing among low-risk stimuli from brief self-report and passive signals, with a stop rule. Adversarial input: a simulated non-responder who deteriorates; the loop stops optimizing and escalates to a clinician contact.",
      "smallest_proof_and_baseline": "In a disclosed simulator only: time to identify the best stimulus and escalation correctness, against a fixed rotation schedule.",
      "neglected_constraint": "A simulator result is not clinical evidence and must be presented as such. Relapse escalation and consent are the product.",
      "stop_building": "Generic wellness chat.",
      "eligibility_uncertainty": "No real patient data; no efficacy claims."
    },
    {
      "track": "AI Infrastructure (by Verda)",
      "company": "Stoa",
      "title": "Make Blueprints Talk",
      "recording": "IMG_9217 exists; ASR mishears the name; the logo reads Stoa",
      "priority": "HOLD",
      "underlying_need": "Correct answers about drawings that a site engineer can verify in seconds from the indicated location.",
      "critique_of_current": "The companion is a fictional revision checker. Analyst B's Revision Impact Lens answers a question the brief does not ask and assumes revision pairs exist in the dataset. Reusing Reality Twin is an eligibility risk.",
      "improved_concept": "IDEA: Answer with a box. Extract text and geometry from vector files where present, tile and read raster sheets, ground symbols to the legend, and measure from geometry and scale. Every answer returns sheet, region and the extracted primitive. Adversarial input: a question whose answer is absent or sits on a different-language sheet; the system abstains or cites the correct sheet.",
      "smallest_proof_and_baseline": "On Stoa's example questions: answer accuracy and whether the cited region contains the answer, against a frontier multimodal model given the whole sheet.",
      "neglected_constraint": "Many formats and languages, and the brief wants approaches next year's models will not make obsolete. Judging hints in the ASR are too garbled to treat as criteria.",
      "stop_building": "The fictional revision checker; revision-diff features.",
      "eligibility_uncertainty": "The dataset is real drawings, so redistribution is likely restricted. Verda's separate award is not this brief."
    },
    {
      "track": "Data",
      "company": "Context.dev",
      "title": "The Web Is Your Real-Time Database",
      "recording": "IMG_9228 exists; ASR garbled",
      "priority": "HOLD",
      "underlying_need": "A narrow product whose decision changes because the live web changed.",
      "critique_of_current": "The companion writes extraction and freshness plans. Analyst C's Reality Delta is abstract, with no named user; the brief's own examples are concrete and narrow.",
      "improved_concept": "IDEA: Terms-change tripwire for a small company's vendors. Substantive pricing or terms changes map to the affected budget line. Adversarial input: a cosmetic layout change; no alert. A mis-extraction caught by a cross-field check is visibly retracted.",
      "smallest_proof_and_baseline": "About 30 labelled page pairs: meaningful-change precision and recall, against a plain text diff.",
      "neglected_constraint": "Real pages rarely change during a demo. A staged change on your own page is scripted and must be labelled, alongside live extraction of a judge-chosen URL.",
      "stop_building": "Schema worksheets; a generic decision assistant.",
      "eligibility_uncertainty": "API credits and capabilities beyond the brief's one-line description are unverified."
    },
    {
      "track": "Data",
      "company": "City of Espoo",
      "title": "Rethinking Recruitment",
      "recording": "IMG_9227 exists; ASR garbled",
      "priority": "HOLD",
      "underlying_need": "At Espoo's matchmaking events, companies and talent find relevant counterparts despite AI-polished materials on both sides.",
      "critique_of_current": "The companion finds city services, which is off-brief. Analyst C's Proof of Fit is directionally right but centres on work samples and treats 'synthetic fixture' and 'without automated screening' as facts; both come only from frames and rough ASR.",
      "improved_concept": "IDEA: An event meeting planner. Employers post one real task from the role, talent answers briefly from experience, and the output is a schedule of short meetings with the evidence behind each pairing. Adversarial input: a keyword-stuffed generated profile; its claims are marked unevidenced and it receives one concrete question, never a rejection.",
      "smallest_proof_and_baseline": "A synthetic set with planted polished-but-empty and plain-but-evidenced profiles: how often evidenced profiles rank above polished ones, against keyword or embedding matching.",
      "neglected_constraint": "The brief is about events, not job boards. Employment matching is a sensitive, regulated use (my recollection; verify the applicable rules).",
      "stop_building": "The city-service finder; any CV scorer.",
      "eligibility_uncertainty": "No real candidate data; fixture availability unconfirmed."
    },
    {
      "track": "Data",
      "company": "MariaDB",
      "title": "Wikipedia Through Time.",
      "recording": "IMG_9226 exists; ASR almost unusable, do not derive versions or features from it",
      "priority": "HOLD",
      "underlying_need": "A Wikipedia tool that does not exist, with MariaDB vector search and/or system-versioned tables at the core.",
      "critique_of_current": "The companion reviews query plans and indexes. Analyst C's Time Machine is nearly the brief's own 'both tracks' example, so originality is low, and its cross-language slider adds scope.",
      "improved_concept": "IDEA: Claim stability for readers and editors. Per sentence, show how often it was rewritten or reverted, and answer 'what did this say on a date' from versioned rows. Adversarial input: a date inside a short-lived vandalism window; the answer shows the text and that it was reverted minutes later.",
      "smallest_proof_and_baseline": "Twenty dated questions with known revision IDs: as-of correctness and latency at the provided dataset scale, against current-revision keyword search.",
      "neglected_constraint": "Versioned tables record database time, so loading past revisions needs explicit history insertion (I recall MariaDB supports this in recent versions; verify). PR56's replay is PostgreSQL and its first model answer contained a MariaDB syntax error, so execute every statement on real MariaDB.",
      "stop_building": "The index-review companion as a challenge answer.",
      "eligibility_uncertainty": "Whether the provided datasets include edit history is unknown."
    }
  ],
  "agents34": {
    "honest_limit": "Only 21 of the 34 companions are named in the supplied inputs. I assign roles to those and give a rule for the other 13 rather than inventing names.",
    "evidence_contract_for_every_companion": [
      "brief_clause: the exact official sentence the task serves, or 'no main brief'",
      "real_input: sponsor-supplied or public input with its licence, never an authored fixture alone",
      "output: an artifact a person would use, not a plan or schema check",
      "baseline: the simpler method it is compared against",
      "adversarial_case: one hostile or ambiguous input and the visible recovery",
      "receipt_label: LIVE, REPLAYED, SYNTHETIC or OFFLINE_DETERMINISTIC, with commit and input hash",
      "retained_failures: misses are kept and never regraded",
      "eligibility_flag: whether any of it may appear in a submission"
    ],
    "promotion_rule": "A companion is challenge-ready only with a LIVE receipt on sponsor data, a baseline comparison and an adversarial recovery. Nothing in the supplied evidence shows any of the 34 at that level; Aiven has one real finite workflow, and Aiven is not a main challenge.",
    "named_companions": [
      {"companion": "junction.afterquery", "recording": "IMG_9224", "role": "Reward exploit hunter", "real_task": "Write runnable exploit policies against the primary environment and report each score against honest play."},
      {"companion": "junction.valio-aimo", "recording": "IMG_9220", "role": "Hostile purchasing agent", "real_task": "Attempt over-mandate, stale-hold and duplicate orders against the interface; report violations (target zero)."},
      {"companion": "junction.bahn-express", "recording": "IMG_9223", "role": "Round analyst", "real_task": "After each ranking round, refit the two curves and propose one parameter change with before and after margin."},
      {"companion": "junction.tieto", "recording": "IMG_9225", "role": "Claim-ledger reviewer", "real_task": "For each change in the event-written repository, list claims, the discriminating check for each, and what it refuses to decide."},
      {"companion": "junction.hostinger", "recording": "IMG_9221", "role": "False-positive auditor", "real_task": "Maintain a benign-coordination negative set and report false-positive rate; drop the hosting planner role."},
      {"companion": "junction.exa", "recording": "IMG_9222", "role": "Primary-source verifier", "real_task": "For a stated errand, return dated primary sources and flag conflicts; no private data in queries without owner approval."},
      {"companion": "junction.cala", "recording": "IMG_9219", "role": "Entity and freshness auditor", "real_task": "Measure coverage and staleness on a known list of Nordic companies and investors."},
      {"companion": "junction.s-pankki", "recording": "IMG_9218", "role": "Arithmetic oracle", "real_task": "Compute cent-exact ground truth for money questions from transactions, to grade any conversational answer."},
      {"companion": "junction.astrazeneca", "recording": "IMG_9213", "role": "Source binder and Goal 3 gatekeeper", "real_task": "Refuse any recommendation lacking a source; its PR56 fixture stays a miss until the indicator text is supplied."},
      {"companion": "junction.stoa", "recording": "IMG_9217", "role": "Evidence-region checker", "real_task": "Verify that a cited drawing region actually contains the answer."},
      {"companion": "junction.mariadb", "recording": "IMG_9226", "role": "SQL truth-checker", "real_task": "Execute every proposed statement on a real MariaDB instance before it is shown."},
      {"companion": "junction.context-dev", "recording": "IMG_9228", "role": "Brief-change monitor", "real_task": "Detect substantive changes to official challenge pages and report which plan they affect; access unverified."},
      {"companion": "junction.city-of-espoo", "recording": "IMG_9227", "role": "Planted-profile test keeper", "real_task": "Maintain synthetic polished-versus-evidenced profiles and score any matcher on them."},
      {"companion": "junction.meta", "recording": "IMG_9210", "role": "Device-state failure scripter", "real_task": "Parked without hardware; otherwise script permission denial and disconnect cases."},
      {"companion": "junction.rokoko", "recording": "IMG_9212", "role": "Latency and jitter logger", "real_task": "Parked without hardware."},
      {"companion": "junction.aalto-university", "recording": "IMG_9211 covers the humanoid brief only", "role": "Simulation scorekeeper", "real_task": "Score held-out seeds if the simulator runs. Its second brief, Beyond the Clinic, has no recording and needs a separate scope."},
      {"companion": "junction.verda", "recording": "IMG_9214 (under one second) and IMG_9216", "role": "Compute-receipt keeper", "real_task": "Record real job receipts only if the primary needs GPU work, such as the small-model stretch. Verda has no main-index brief of its own."},
      {"companion": "junction.oxylabs", "recording": "IMG_9229", "role": "Parked acquisition layer", "real_task": "None until its terms are read; it is not in the main index."},
      {"companion": "Aiven", "recording": "None supplied", "role": "Reference example of the evidence contract", "real_task": "Keep the one finite workflow honest: local PostgreSQL is not Aiven hosting and OAuth is disconnected."},
      {"companion": "DeepMind", "recording": "None supplied", "role": "Parked", "real_task": "No main-index brief; the PR56 fixture miss stays until a real input exists."},
      {"companion": "NVIDIA", "recording": "None supplied", "role": "Parked; possible simulator support", "real_task": "HYPOTHESIS: could support Isaac Sim setup for the Aalto humanoid brief. Must not be mapped to the Intel challenge."}
    ],
    "unnamed_13": "Apply the same contract. If a company has no main-index brief and no confirmed side-challenge terms, park its companion this weekend rather than writing a generic assistant role for it.",
    "recording_coverage": {
      "main_challenges_without_recording": ["Arduino - The Green European Renaissance", "Ignite Next x Intel - Physical AI Challenge", "Aalto University - Beyond the Clinic"],
      "recordings_without_main_index_brief": ["Verda (IMG_9214, IMG_9216)", "Oxylabs (IMG_9229)"],
      "named_companions_without_recording": ["Aiven", "DeepMind", "NVIDIA"],
      "unknown": "Whether Arduino or Ignite Next x Intel have companions, and the recording status of the 13 unnamed companions."
    }
  },
  "wave_plan": {
    "assumptions": "I do not know the current time. T0 is when this review is read; fixed deadlines are Helsinki time. No deployment, purchase or submission is instructed here.",
    "fixed_deadlines": [
      "Fri 19:30 Bahn ranking rounds open",
      "Fri 20:00 AstraZeneca insights at their stand",
      "Fri 23:59 draft submission",
      "Sun 07:30 Bahn final registration closes; 08:00 final runs",
      "Sun 10:00 final submission: video of at most 2 minutes, PDF deck, demo and MIT source"
    ],
    "shared_spine": "Event-written and small: a seeded world kernel with an append-only ledger; scores computed only from the ledger; a run receipt (seed, commit, model, config hash, label); a one-command evaluator with baselines; a registry of adversarial cases. It serves AfterQuery and Valio directly. PR56's replay design may inform it, but copying that code waits for the organizer answer.",
    "worker_allocation": [
      {"worker": 1, "T0_to_2h": "AfterQuery micro-environment and harness run", "after_gate": "Primary build"},
      {"worker": 2, "T0_to_2h": "Reference policy and variant B", "after_gate": "Primary evaluation and variance runs"},
      {"worker": 3, "T0_to_2h": "Valio interface slice with a third-party agent client", "after_gate": "Primary or secondary build, per gate"},
      {"worker": 4, "T0_to_2h": "Bahn kit baseline in a ranking round", "after_gate": "Bahn loop, alone, to Saturday night"},
      {"worker": 5, "T0_to_2h": "Intake of current official pages and Discord for datasets, criteria and access; attach a research record to each companion", "after_gate": "README, clean-clone reproduction on a separate machine"},
      {"worker": 6, "T0_to_2h": "Eligibility questions and draft-submission text for the owner", "after_gate": "Deck, lessons log, video script"},
      {"worker": 7, "T0_to_2h": "Independent verifier: tries to break each kill-test result", "after_gate": "Exploit suite and adversarial cases; never edits author code"}
    ],
    "phases": [
      {"window": "T0 to T0+2h", "work": "Three kill tests, intake, eligibility questions.", "gate": "Gate A: pick ONE primary by measured result, before the draft deadline. Order of preference if several pass: AfterQuery, Valio, Bahn."},
      {"window": "T0+2h to +12h", "work": "Primary vertical slice end to end on the spine; Bahn loop continues with one worker.", "gate": "Gate B: primary runs from a clean checkout with one command, or scope is cut."},
      {"window": "+12h to +24h", "work": "Baselines, repeated runs, exploit suite, adversarial recovery, first rough video as a safety copy.", "gate": "Gate C, Saturday about 18:00: feature freeze on the primary."},
      {"window": "+24h to +34h", "work": "Reproduction on a second machine, deck, lessons log, final video. Stretch items only if everything is green.", "gate": "Saturday about 22:00: Bahn policy frozen; any secondary entry cut unless already passing."},
      {"window": "Sunday morning", "work": "Bahn registration and unattended final if pursued; final checks; owner submits.", "gate": "No code changes after 08:00."}
    ],
    "integration_tests": [
      "Same seed gives the same trajectory hash",
      "Score derives from the ledger only; agent text cannot change it",
      "Do-nothing and stop-early score near zero",
      "Retry after timeout creates no duplicate order; an expired hold is rejected; a changed basket voids approval",
      "Every exploit policy scores below honest play",
      "Clean checkout on a second machine reproduces reported numbers with one command",
      "Restart mid-run resumes without duplicate actions"
    ],
    "stopping_points": [
      "AfterQuery: no reproducible gap by T0+4h means stop",
      "Valio: no third-party agent completing the flow by T0+2h means demote",
      "Bahn: below Bahn's own system after three rounds and flat means maintenance mode",
      "Any hardware challenge: no hardware in hand by T0+2h means parked for the weekend",
      "Any optional feature not passing by Gate C is removed, not half-shown"
    ],
    "safe_fallback": "If all three bets fail their tests, switch to Tieto: its deliverables (concept card, live walkthrough on one synthetic change, lessons log, video) need no sponsor data, hardware or leaderboard. The Saturday safety video guarantees something submittable exists.",
    "explicitly_not_doing": "No further catalog, WebMCP or replay platform waves; no per-company dashboards; no work on parked companions; no deployment steps in this plan, although Hostinger's brief would require one if chosen."
  },
  "red_flags": {
    "factual_misreadings": [
      "Hostinger is a detection challenge that must run live on Hostinger infrastructure; it is not hosting or DNS help. Analyst B's provisional concept is void.",
      "Verda hosts the AI Infrastructure track, whose one main challenge is Stoa's. 'Best use of Verda' comes from a Verda blog relayed by Analyst A and is not in the main index. The companion's resource-plan arithmetic is not Verda usage.",
      "Oxylabs is not in the main index. A frame reading 'main challenge project' suggests it attaches to another entry; that is a hypothesis.",
      "IMG_9211 is Aalto's humanoid brief, not Ignite Next. Aalto has two briefs and one companion.",
      "Valio specifies fixed prices and treats substitution as optional and unscored; the negotiation concept contradicts it.",
      "Bahn is a week, scored on gross margin with a 90 percent on-time floor. Dispatch fairness, deadhead and a single fixed day are not in the brief.",
      "AfterQuery's rubric gives zero for gaps caused by withheld information; a hidden invariant is exactly that.",
      "Tieto asks for a concept with a reference illustration and says it is not a product.",
      "Analyst drafts B and C describe briefs and speech as pending. That is superseded.",
      "The older critique that no real runtime exists is superseded: PR56 reports one finite real workflow and 204 captured responses. The reverse error is also wrong: that is not 34 live challenge products."
    ],
    "asr_errors": [
      "Stoa heard as 'story'; Finland heard as 'England'; AstraZeneca heard as 'senator'; Cala heard as 'Canada'; Spread heard as 'strength'; Internet Butler heard as 'Internet process'; Valio's kitchens heard as 'teachers'",
      "Hostinger 'handle all positives' is false positives",
      "Verda credit amount is unintelligible; IMG_9214 is under one second",
      "The MariaDB and Tieto transcripts are too degraded to support any requirement",
      "'Without automated screening' (Espoo) and the Stoa judging hints exist only in rough ASR; they are not criteria"
    ],
    "hardware_and_access_assumptions": [
      "Unverified: UNO Q boards, Meta glasses and toolkit, the Intel station, Rokoko suit and gloves, the humanoid simulator and GPU credits",
      "Unverified: Valio mock data, S-Pankki dataset, Stoa drawings, MariaDB datasets, AfterQuery harness, and API credits for Exa, Cala and Context.dev",
      "Sponsor datasets and the Bahn event code must not be committed to a public MIT repository",
      "Bahn's brief points agents to an instructions file on its site. It is legitimate reading for that challenge, but workers should treat it as third-party data."
    ],
    "eligibility_risks": [
      "The guide, as relayed, describes prior idea-specific code and related existing-company projects as disqualifying. The monorepo and Chibi may be both. I cannot decide this.",
      "The index capture shows 'Closed' with a countdown of about 16 hours; I cannot tell what it counts toward, so I cannot place the monorepo commits relative to the official start.",
      "Whether one team may enter several main challenges is not stated anywhere in the inputs.",
      "MIT licensing of everything submitted may conflict with sponsor kits or data.",
      "The main prize is peer-reviewed, so the video and deck must be legible to non-specialists."
    ],
    "evidence_quality": [
      "PR56's 204 cases are an authored development set with provisional grades, not held-out or human qualification.",
      "The PostgreSQL and browser checks ran at earlier commits; equivalence to the final head is asserted, not shown to me.",
      "The persona pilot is 12 pairs. It was judged by Fable 5.2, the same model writing this review, so neither is independent of the other. The identity of the four 'independent' reviewers is not stated."
    ]
  },
  "review_scope": {
    "supported_by_official_index": "Challenge titles, companies, tracks, requirements, prizes, the AfterQuery rubric and the Bahn schedule.",
    "supported_only_by_user_relay": "Participant Guide rules, deadlines and submission format. I did not see the guide text.",
    "supported_only_by_analyst_reports": "Frame observations, logo identifications, what each companion currently does at the pinned commit, and the Verda blog content. I read no source code and saw no frames.",
    "source_reported_not_checked_by_me": "Everything in the PR56 body: test counts, database and browser checks, the Aiven workflow, the 204 responses, the Chibi PR117 state.",
    "used_only_as_weak_corroboration": "The rough transcripts.",
    "my_unverified_recollection": "MariaDB history-insertion and vector features, the simulator's GPU requirement, and the regulatory sensitivity of employment matching.",
    "not_available_to_me": "Discord, the Bahn handbook, any dataset, the technical-challenges index, the names of 13 companions, the current time. No tools were used.",
    "labels": "Concepts are marked IDEA and unconfirmed readings HYPOTHESIS. Thresholds marked 'proposed' are mine. Nothing here submits an entry or decides eligibility."
  }
}
```