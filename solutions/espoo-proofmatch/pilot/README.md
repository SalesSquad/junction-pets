# SIMULATED · ProofMatch conversation notebook

Task `J26-PF-ESPOO-20261115-1328`. Private, fictional, self-contained local pilot
for the **after-meeting** stage: distinguish acknowledgement, reflection-sharing
choice, each person’s reflection, and what remains unavailable. It complements
W2 matching rather than calculating another match or person score.

## Run locally

From the repository root, Node 22+; no dependencies, installation or internet:

```sh
node solutions/espoo-proofmatch/pilot/serve.mjs
```

Open **http://127.0.0.1:4187/**. Use a separate origin from W2’s port 4173;
this pilot has no service worker or persistent cache. Optional `PORT=4188`.
The static file allowlist includes only the pilot shell and its two reused
modules. The server binds to loopback, accepts GET/HEAD only, and has no record
API, request-body processing, telemetry, cookies, remote assets or writes.
Run it in the foreground and stop with Ctrl-C; no daemon is installed.

## Try the complete journey

1. Start with fictional Mira and Rowan’s accepted 09:00–09:15 UTC meeting on
   fictional 15 November 2026. Choose in-person, online or hybrid and explicitly
   start a new scenario to apply a different format. Before/during guidance
   makes the shared question and equal participation concrete.
2. Explicitly simulate the conversation ending. This is not a clock or evidence
   of an actual meeting. Record **each** participant’s acknowledgement with its
   separate checkbox and action; one acknowledgement does not supply the other.
3. In each person’s panel, explicitly accept or decline sharing that person’s
   reflection for review in this tab. No choice is preselected. Acknowledgement
   and meeting acceptance do not grant reflection sharing. One operator can
   play both people: actor IDs are fixture selectors, **not authentication or
   actual real-person consent**.
4. For accepted sharing, choose a non-numeric takeaway, next-step preference and
   support need. Only authored fictional options are accepted, with no free
   text, private records or proficiency inference. Use different next steps to
   see disagreement preserved. Decline is equally valid and carries no personal
   verdict. A reflection is never collected for a declined choice.
5. Inspect progress: awaiting acknowledgements → choices → missing reflections
   → both fictional reflections available, or no reciprocal evidence. Even the
   complete state establishes **no real-world outcome**. Matching next steps
   do not schedule an action; different next steps do not overrule either voice.
6. Revoke either accepted sharing choice. Its reflection disappears immediately
   from the active state, form and review; reciprocal evidence becomes
   unavailable. The other person’s choice remains intact. Revocation cannot be
   silently reversed within this session. Delete the session to remove the
   active meeting and both participant records, or start a new fictional session.

All records live only in the current tab’s JavaScript memory. No localStorage,
sessionStorage, IndexedDB, files, messages or exports hold records. Reload starts
anew; leaving the page also resets the active session and forms, and form
autocomplete is disabled. Tabs do not coordinate. Deletion drops the active state and rendered/form
values; JavaScript garbage collection is **not secure memory erasure**, and a
caller of the pure module can retain its own earlier immutable state. No history
is retained by the UI. Native form controls, visible labels, focus rings, a skip
link, a polite status region and a narrow-screen layout support keyboard use;
actual browser, screen-reader and device qualification are not claimed.

## Rules and focused verification

`outcomes.mjs` is pure and bounded: one fixed meeting, two fixed actors, three
fixed reflection fields, strict payload fields, immutable outputs and at most
128 versioned transitions. Every command binds the expected session version,
requires `simulation: 'SIMULATED'`, and confirmations accept only boolean `true`.
Stale commands, unknown actors, duplicate acknowledgements, premature evidence,
unaccepted reflections, invalid states, arbitrary text and numeric scores fail.
These checks maintain simulation consistency; they are not an authorization
system. No production consent or identity path is implemented.

The single focused positive/negative test command is:

```sh
node --test solutions/espoo-proofmatch/pilot/pilot.test.mjs
```

It covers the journey, false consent, separate/duplicate acknowledgements,
accepted/declined independence, revocation/deletion, version conflicts, malformed
states/payloads, no personal ranking, immutable inputs and the static route
handler’s file/method/origin restrictions. Route tests invoke the handler with
synthetic requests; they do not claim a listening-server or browser pass. No root
suite or external qualification is needed or represented for this task.

Executed on 15 November 2026 in this local isolated checkout with Node
`v26.13.0`: **10 passed, 0 failed**, exit 0. This result covers the uncommitted
rules and handler sources on the admission base below. UI focus, layout and
page-lifecycle behavior remain source-reviewed, not browser-tested. No server,
browser tab or background process was started during verification.

## Provenance and export boundary

- Admission/base: `cea0089f06a179047244872bd98529eafa2167ee`, isolated branch
  `codex/j26-espoo-human-feedback-20261115`; initially pristine, locally verified.
  The coordinator supplied authenticated admission; this offline task does not
  claim a fresh network read of GitHub main.
- Source route: `junction.city-of-espoo`, partner `espoo`, owned brief `M319` in
  [`current-source-catalog.json`](../../../docs/challenge-research/current-source-catalog.json)
  at that base. Snapshot 14 November, `latestClarification: null`; preceding
  13 November guidance covers before/during/after online, in-person and hybrid
  meetings. M319 permits one journey stage, requires synthetic data and excludes
  automated decisions about individuals. This is dated context, not live city
  integration, official endorsement, organizer feedback or measured effectiveness.
- Imports reuse [`event-meetings.mjs`](../event-meetings.mjs): shared event slot,
  proposal and explicit separate candidate acceptance, plus its validation
  module. No scheduler, skill graph, matching semantics, schema or shared API is
  duplicated or changed. The existing skill graph and its tests were read;
  numerical alignment does not belong in this post-meeting reflection pilot.
- W2 inherits **pre-existing Workbase PRIVATE IP** at
  `4c5ce6e2edb41b83360dd7d0227da9ded06a566b`; see
  [`WORKBASE_REUSE.md`](../WORKBASE_REUSE.md). This derivative is **not authorized
  for Workbase private IP competition export or competition submission**. No
  publication, new license, private-source export or eligibility clearance is
  implied by local execution or test results.

Scope is `pilot/**` only. No real people, private data, credentials, tracking,
messages, hiring actions, eligibility scores, inferred proficiency or external
services are used. Coordinator owns commit, push, PR and integration; this task
leaves source uncommitted as explicitly requested.
