# Current view and learned help

Work: LENS-DEVICE-MEMORY-20261114. Base source:
`ae5b4dcbeb380d1aafcb5ef8154efdadec38e130` in SalesSquad/junction-pets.

The original observation panel and approved learning preference now participate
in the same Resume episode. A current, admitted suggestion appears in the Learn
card, with the amount of explanation selected by the existing learning core.
Quiet preferences withhold guidance until the user asks. Observation alone
changes neither task progress nor stored memory.

## Use the reference journey

Start the existing development server from the repository root:

```sh
node services/meta-spatial/observation-server.mjs --mode synthetic
```

Open the displayed loopback address. Start learning, choose and approve a help
preference, then load a fresh observation sample and choose Analyze this moment.
The Learn card combines the suggestion with that preference. Confirming a task
step clears the old context. A quiet preference requires Ask for the next step
before visual guidance appears in the Learn card. Forgetting learning, pausing
learning, revoking capture, changing an episode or leaving the page clears the
transient context. The original confirmation controls retain their authority.

The fixture pixels and model interpretation are synthetic. Imported declared
SAM observations retain their own label; the learning reference always stays
synthetic. Neither a matching checksum nor a model label proves physical identity.
The browser still does not call model providers itself.

## Binding before an asynchronous request

`createLearningObservationBridge({read, now})` in
`apps/meta-resume-web/learning-observation.mjs` exposes four methods:

| Method | Behavior |
| --- | --- |
| `begin(request)` | Before fetch, bind the current task, capture and learning state; return an opaque local ticket or null. |
| `accept({request,result,ticket})` | Require the original ticket and request metadata, validate the response and actual image digest, then recheck current state after asynchronous hashing. |
| `context(recommendation)` | Combine only a fresh admitted observation with the existing core recommendation. |
| `clear()` | Clear the transient view and invalidate every pending acceptance. |

The trusted local read port returns `{state, policy, learning}` from the existing
Resume and learning sessions. Binding includes scope, episode, learning revision,
memory epoch, consent generation, task revision/status/step, capture session and
generation. The frame must be current, no more than 30 seconds old and not from
the future. The panel schedules a clear at expiry; an idle screen does not retain
old guidance indefinitely.

The ticket carries no image, request text, scope or grant. A response that began
before Forget learning cannot attach to a newly started episode. A superseded
or forged ticket cannot erase newer accepted context. Changes during image
hashing are checked separately from changes while awaiting the network.

The bridge never calls `dispatch`. `physicalIdentityVerified`,
`taskCompletionAuthorized` and `memoryMutationAuthorized` remain false.
Frame bytes are used transiently to check the digest; images, OCR and visual
proposals are absent from the learning save and reload path.

## Focused checks

```sh
node services/lens-learning/observation-simulation.mjs --output /tmp/lens-observation-simulation.json
node services/lens-learning/observation-browser-check.mjs /tmp/lens-observation-browser
```

The simulation exercises the actual original sessions and validators, including
forget-before-response, revoke-during-hash, stale task/scope, quiet preference,
tampered image bytes and request metadata. The browser journey uses the existing
synthetic service, three different actual task revisions and a held network
response. Its report distinguishes executed checks from browser startup failure.
Neither command uses a provider API or private account. Browser execution needs
an existing Playwright/browser installation; `CHROMIUM_PATH` can select it.

### Executed evidence

Implementation source `6cad8dd19a9ac343465679f26a0d54c6e826f019` passed all
eight focused simulation checks and all five browser journey checks. The actual
Mac Mini journey used existing Node 24.22.1, Playwright 1.62.1 and Chrome
157.0.8103.80, took 15.252 seconds and received three synthetic proposed
responses, with no page errors or provider calls. All 20 staged source files
matched their exact-commit digests before and after execution.

The first cloud attempt failed before opening the page: Chromium could not
create its process singleton socket (`EPERM`). That attempt executed no browser
checks and remains recorded as an environment failure. The Mini's generic
receipt cannot attest Git state for an API snapshot; its separate source
manifest and before/after digest record supply the source binding. These are
local execution records, not signed or hosted qualification.

See the [verification index](evidence/observation/VERIFICATION.json),
[original browser report](evidence/observation/observation-browser-report.json),
[simulation report](evidence/observation/simulation.json) and
[actual browser screenshot](evidence/observation/lens-observation-learning.png).
Scoped independent review found no P1/P2 issue in the bridge and callback,
reset, consent and expiry integration. Later documentation-only commits retain
the recorded implementation bytes; they do not imply a fresh execution.

## Private host and native boundaries

The existing private Chibi continuity store is in
[Chibi PR123](https://github.com/SalesSquad/chibi/pull/123), source
`1037e8dee06a53838363cb4b78bd1f5b471dd1a0`. Its actual disposable PostgreSQL
scenario passed using encrypted storage and scoped account/adoption checks.
That source remains the existing durable task boundary for production
integration; this change neither copies it into Junction nor activates it.

Current Chibi main `101089e4f5b170e4930d69d9cc17c18c2a2edc47` still requires an
independently verified production service bundle. In particular, no production
ResumeAdmission adapter supplies current Cedar policy, capture consent/session,
exact evidence/subject authority and held revocation guards. Browser-generated
scope IDs or an environment flag cannot replace those dependencies. This
increment therefore does not activate production storage or create a parallel
private-memory backend. See the private host's
[integration contract](https://github.com/SalesSquad/chibi/blob/101089e4f5b170e4930d69d9cc17c18c2a2edc47/docs/integration/junction-event-host.md).

[Native PR75](https://github.com/SalesSquad/junction-pets/pull/75) separately
qualifies official DAT mock-device video, local OCR and revocation. A native
mock run does not prove physical glasses capture or the SAM/NVIDIA image route.
Native execution and this browser journey retain separate source-bound evidence.
Actual device-to-host operation needs its original capture contract, current
host authority and explicitly supported observation adapter; no synthetic
grant or fabricated SAM result is introduced here.
