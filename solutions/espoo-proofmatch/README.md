# ProofMatch W2 · private conversation demo

Choose a fictional event role, inspect exact and transferable skill evidence,
ask about unknowns, and simulate a separate proposal and response for a
**15-minute conversation on fictional 15 November 2026**. All five candidates
remain visible and selectable in fixture order, including Ren without a
portfolio or stated role preference. No person score or aptitude ranking appears.

**PRIVATE / SYNTHETIC / OFFLINE_DETERMINISTIC / SIMULATED.** This version adapts
pre-existing PRIVATE Workbase IP. It is **not automatically cleared for competition
submission**; read [WORKBASE_REUSE.md](WORKBASE_REUSE.md). No real participants,
verified portfolios, production system or municipal endorsement is represented.

## Run

Node 22+; no dependencies, install, build, API or internet needed. From repo root:

```sh
node solutions/espoo-proofmatch/serve.mjs
```

Open `http://127.0.0.1:4173`; optional `PORT=4180` changes the port. Ctrl-C stops
the loopback-only, read-only, file-allowlisted server. A first visit requires the
server. The service worker caches named shell assets for subsequent offline
reloads on the same origin; offline reload is not yet browser-verified for v2.
Keeping the local server running works without internet. Proposals live only in
tab memory and vanish on reload/reset; the cache never stores meeting records.

## Demo path

1. Choose **Build a repair-service prototype**. Inspect Mira's exact supplied
   labels and source cards. “Exact” does not establish proficiency; artifacts,
   walkthroughs and statements are explicitly self-declared, fictional material.
2. Select **Ari**. Inspect **TypeScript → JavaScript**: the direct seed edge is
   0.85, so related requirement credit is 0.6 × 0.85 = 0.51. This is partial
   discussion support, not an exact match or a probability. Preferred
   documentation evidence is separate from required skills.
3. Select **Ren**. No portfolio and unknown interest remain visible; offer a
   conversation or shared exercise. Ren's authored availability has no common
   time with either role. Lack of time does not remove the candidate.
4. Change the event role. Candidate-declared topic interest, other stated
   interests and unknown preference are explained without filtering anyone.
   Inspect structured reasons/cautions or use the human-authored questions.
5. Select Mira and the repair role. Choose a shared UTC time and use
   **Simulate employer: Propose 15-minute meeting**. The notebook shows
   **SIMULATED · PENDING**; no candidate acceptance is implied.
6. In the separate **Simulate candidate · Mira** controls, choose **Accept** or
   **Decline**. Either intended party can **Cancel** a pending or accepted
   proposal. Pending/accepted hold time across roles for both parties;
   declined/cancelled release it and permit a new proposal. An active pair
   cannot receive a duplicate proposal, even at another time.

One demo operator can switch parties. These controls are neither authentication
nor real mutual consent. No Workbase application, invitation, message, calendar
event or real reservation is created. Two tabs do not coordinate.

## Focused checks

```sh
node --test solutions/espoo-proofmatch/skill-graph.test.mjs solutions/espoo-proofmatch/event-meetings.test.mjs solutions/espoo-proofmatch/matcher.test.mjs
node --check solutions/espoo-proofmatch/app.mjs
node --check solutions/espoo-proofmatch/skill-graph.mjs
node --check solutions/espoo-proofmatch/event-meetings.mjs
```

Current local result: **39 passed, 0 failed** (21 new checks plus the preserved
18 matcher tests). All 12 local JS files also passed `node --check`. Exact scope,
executor and unavailable HTTP/browser checks are recorded in `PROGRESS.md`.

The unchanged v1 `matcher.mjs` and its 18 tests remain compatibility fixtures;
the UI uses the new `skill-graph.mjs` and `event-meetings.mjs`. V1 scheduling is
not used by v2. The collapsed legacy benchmark shows **only 2 illustrative
cases**, intentionally authored and non-independent: legacy evidence heuristic
2/2 fixed labels versus keyword-only 0/2. It does not qualify v2 matching,
interest, scheduling, fairness, authenticity or hiring effectiveness. Run it with
`node solutions/espoo-proofmatch/benchmark.mjs`.

## Source and limits

This private W2 slice starts at ProofMatch PR86 source
`92d3f48efe94c9547a77963371f49102bee4fb61`; Workbase reuse is pinned to
`4c5ce6e2edb41b83360dd7d0227da9ded06a566b`. The W2 implementation is delivered on a separate private task branch. No deployment, public release or Junction submission is made.

Challenge context is the repository's dated
`pets/city-of-espoo/CHALLENGE_RESEARCH.md` and official brief snapshot. No fresh
organizer confirmation, live city data or endorsement is claimed. This version
contains pre-existing private IP and cannot be described as wholly event-created.
`solution.json` retains its original base/stage metadata; `stage: idea` and
capability status `planned` are declarations, not runtime or release evidence.

Availability, interests and portfolios are fictional. Relation weights and source
forms are heuristics, not validated evidence of aptitude. No protected-attribute
inference, automated hiring/rejection, model, external provider or real event
participant path exists. See `ARCHITECTURE.md` for boundaries and missing
production controls.


## Safari browser QA (macOS, private demo only)

Start the local Node server, then open a **new, task-owned Safari window** to its
loopback URL. Obtain that window's ID from your authorized local automation; do
not target another user's window or enable new browser permissions to make a
test pass. On a Mac where Safari Apple Events JavaScript is already authorized:

```sh
python3 solutions/espoo-proofmatch/safari-e2e.py \
  --window-id <TASK_CREATED_SAFARI_WINDOW_ID> \
  --url http://127.0.0.1:4173/
```

This dependency-free script checks nine real Safari DOM interaction checkpoints,
including the explicit employer/candidate actions, the mobile heading text and
horizontal overflow. It does **not** test authenticated consent, physical
iPhone Safari, screen-reader speech or hardware device behavior. Safari 27.0
was additionally inspected with macOS accessibility snapshots and real
keyboard Tab/Space events. See `PROGRESS.md` for the exact source-bound
2026-11-14 desktop, 390 × 844 responsive, and offline-cache readbacks.
