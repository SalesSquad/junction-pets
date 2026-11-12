# Junction Mission Control

Owner-private, portable development dashboard for the 34 Junction company
companions. It is **not** part of Chibi.pet, the public catalogue, or the pet
bundle sent to the Chibi host.

## Input and build boundary

The page reads the sibling `status.json` at request time. The registry builder
owns that file; the UI **never** makes provider or GitHub API requests itself.
It deliberately has no credentials, user profiles, write controls or background
workers. It does not provision cloud environments or run model evaluations.

Layout expected by any static host:

```text
mission-control/
  index.html
  style.css
  app.js
  status-model.mjs
  server-projection.mjs # optional backend feed sanitizer (browser: advisory only)
  status.json     # generated from source + reported receipts
  fleet-projection.json # OPTIONAL owner-private backend-generated sidecar, not bundled
```

The integrator must run `npm run ops:build` to regenerate the machine-readable
snapshot and copy this app's five runtime files (including
`server-projection.mjs`) to `dist/mission-control`. The integrator owns this
build/export mapping. The optional `fleet-projection.json` sidecar must come
from an authenticated, owner-private server path; do not publish it in the
public Junction bundle.
Serve `dist/mission-control` through an **owner-private, access-controlled**
static preview. Do not publish this directory to the public event catalogue,
the Chibi host bundle, or an unauthenticated URL. A `robots` tag is not access
control.

There is already an owner-private **Junction Mission Control** Site at
`https://junction-mission-control-mikael.ervamaamikael.chatgpt.site`.
Reuse that owner-approved destination for future integration after verifying
its access controls and data contract. **This repository does not claim that
the existing Site currently consumes this JSON, nor that this module has
been deployed there.** Do not create a competing Site or overwrite the
existing owner's work as a side effect of a build.

Use Node's built-in test runner for the presentation model:

```sh
node --test apps/mission-control/status-model.test.mjs
node --test apps/mission-control/server-projection.test.mjs
```

For a separate synthetic UI acceptance check (Playwright and a Chromium binary
are optional development-only prerequisites):

```sh
node apps/mission-control/browser-smoke.mjs
```

This test serves a temporary local fake status source, checks desktop/mobile
overflow and interaction, and does **not** exercise any provider, adopted pet,
Junction submission, or remote Codex Cloud instance.

## Optional backend feed (currently advisory)

On each manual Refresh, the browser first reads `status.json`, then optionally
reads same-origin `fleet-projection.json` with
`kind: junction-fleet-control/server-projection/v1`. It rejects wrong source
SHA, incomplete/duplicate 34-row rosters, stale receipt bindings, future clocks
and any runtime-execution claim. It strips unknown/raw provider, grant, CI and
secret fields; only allowlisted state labels reach the UI.

**No fetched JSON is a browser-verifiable trust anchor.** Even when a trusted
server generated it, the page labels the information *backend-reported* and
does not upgrade Cloud, CI or model-eval counters to green. Missing/invalid
feeds leave the original static 34-row snapshot intact. A verified owner-private
auth channel and independent server receipt verifier are rollout gates, not
properties created by a JSON flag or static Site publication.

## Honest status display

- `204 authored` cases are not treated as model runs.
- **No cloud state can be shown green today.** This static UI has no trusted
  provider reader, signing-key trust anchor or source-bound cryptographic
  attestation channel. Even a JSON record claiming `verification:
  provider-attested` with a valid-looking environment ID, timestamp and embedded
  `attestation.signature` is a *claim*, not proof. It displays as unverified.
  A later backend adapter may introduce verified readiness only after validating
  a provider-origin receipt, exact environment ID, expected source SHA and a
  signature under an owner-controlled pinned trust anchor **outside** the JSON.
  The UI must then consume that independently verified proof rather than an
  editable marker.
- Evaluation execution and pass counts are presented as *reported* until a
  separate source/model-bound, independently verified evaluator receipt exists.
- Each pet's **plugin source**, **recorded private registration**, and
  **verified host installation** are three different states. A source-matched
  receipt remains an advisory self-report until an independently verified
  provider-host readback exists; this dashboard never labels it live.
- Plugin URLs are rendered as links only when they exactly match the canonical
  `https://chatgpt.com/plugins/plugins_*` path and its recorded opaque plugin ID,
  without query parameters, fragments, alternate hostnames or credentials.
- A source commit is displayed only when it is an exact 40-character SHA.
- Snapshots two hours old are marked stale; a missing/invalid registry is an
  error state, never a green default.
- All rendered data is inserted through DOM `textContent`, not arbitrary HTML.

The repository's `pets/<company>/AGENTS.md` governs companion behavior, whereas
`ops/AGENTS.md` governs developer work, source ownership, leases and evidence.
These two trust boundaries must remain separate.
