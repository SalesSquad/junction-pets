# Proposal: routed guidance modules and typed responses in the Chibi export

Owner of the decision: Junction integrator (export, plugin, bundle) together with
the Chibi host owner (`crates/chibi-manifest`, `crates/chibi-api`). This file is a
proposal from the `junction.aiven` lane. It changes no shared tooling and no Chibi
code.

## Why

Measured on unseen, AstraZeneca-authored cases with an opus judge
(`solutions/aiven-model-tournament/RESULTS-20261114-astra.md`), compared with the
monolithic AGENTS.md (19,978 of 20,000 characters, no room left), the modules plus
typed response v2 raised:
- haiku's mean score from 0.73 to 0.85
- haiku's correct use of human-decision proposals from 14/20 to 19/20.

## What is exported

`node pets/aiven/modules/build-manifest.mjs` writes
`dist/chibi/junction-aiven.guidance-modules.json` (`chibi.companion.guidance-modules/v1`):

- `modules[]`: `core` (alwaysLoad) and topic modules, each with its text, sha256,
  character count and trigger pattern.
- `responseSchema`: `pets/aiven/schemas/response.v2.json` with its sha256.
- `maxComposedChars` (9.4k with every module), `manifestLimitChars` (20,000).
- `routerVectorsSha256`: 41 request → modules vectors (`router-vectors.json`) for
  a host-side port. The build fails if the JavaScript router drifts from them.

## Two adoption options

**A. No host change (available now).** Compose core plus every module (9.4k) into
the existing `persona.system_prompt`. Chibi's manifest validator already accepts it
(≤ 20,000). Configure the provider call with `responseSchema` as structured output.
The `allmodules` arm in `astra-challenge.mjs` measures this option.

**B. Routed (host change).** Extend the persona with `guidance_modules`. The
current validator rejects any persona key other than `system_prompt` and
`temperament`.
- The host selects modules from the user's message only, never from tool output,
  so injected text cannot steer selection. Selection is deterministic regex, not a
  model call.
- Port `router.mjs` to Rust and keep `router-vectors.json` as its contract test.
- Pin every module and schema hash in the Passport version.
- Keep `AGENTS.md` as the fallback for hosts without module support.

## Host flow for typed responses (both options)

1. The provider returns `response.v2` via structured output. The host validates it.
   `solutions/aiven-decision-bridge/bridge.mjs` is the reference: non-empty
   `executed_actions`, a LIVE handoff label or a non-official source fails closed.
2. The host first matches each proposal's exact operation, target and parameters
   to an independently supplied intent from the user's own explicit request, then
   applies its policy. Eligible proposals may become a `PendingAction`; the
   canonical hashes and idempotency key map to `chibi-store` `action_decisions`.
3. A human approves or declines with `ActionDecisionBinding`
   (`proposal_hash`, `version`, `authority_revision`). Only then may the gateway run
   the operation, under its own policy.

## Decision requested

Measured on the fresh `astra-cases-heldout4.json` (opus judge, 2 repeats; see
RESULTS-20261114-astra.md, rounds 5–6):

| Arm | haiku pass / score | sonnet pass / score |
|---|---|---|
| full AGENTS.md + v1 | 30 % / 0.756 | 50 % / 0.825 |
| A: all modules + v2 | 70 % / 0.900 | 65 % / 0.863 |
| B: routed modules + v2 | 63 % / 0.908 | 75 % / 0.925 |

These are historical developer measurements, not a host qualification. The later
injection evaluation did not meet its 95% target. Keep the integration disabled
until the changed model path and actual host trust boundary have been evaluated.
