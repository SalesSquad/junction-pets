# Offline wearable permission and accessible fallback

This independently authored, non-endorsed design example makes no claim about
Meta hardware, SDK support or platform permission behavior. No device, camera,
microphone, biometrics, identification or provider call is involved. The official
discovery links in pet.json remain dated references; no new provider fact or
fresh source review is claimed.

`evaluateWearableHistory({scope, now, events})` replays a complete synthetic
history. Scope is exactly `synthetic-reminder-preview`; timestamps are safe,
nonnegative integer milliseconds on a fictional clock. Zero is valid; missing,
null, fractions, strings, future, reversed and older-than-60-second events fail
closed. Each event has exactly its documented keys; unknown data is rejected.
The 60-second maximum consent duration and history freshness limit are example
choices, not provider rules. Histories are bounded to 128 events.

```js
import {evaluateWearableHistory} from './wearable-permission.mjs';
const scope = 'synthetic-reminder-preview';
const events = [
  {decision:'snapshot', scope, at:0, available:true,
   permission:'unknown', bystanders:'clear'},
  {decision:'consent', scope, at:1, id:'consent-1', expiresAt:100},
  {decision:'revoke', scope, at:2},
  {decision:'snapshot', scope, at:3, available:true,
   permission:'granted', bystanders:'clear'}
];
evaluateWearableHistory({scope,now:10,events});
// state: revoked, simulationAllowed: false, realActionAuthorized: false
```

An empty history starts unavailable with unknown platform permission. A snapshot
may report `unknown`, `denied` or `granted`, availability and `clear`, `present` or
`unknown` bystander context. It cannot create consent. Explicit consent enables
only a fictional preview when available, not denied and bystander context clear.
Platform permission may remain unknown: synthetic preview consent does not alter
it. An unsafe/unknown subsequent snapshot clears consent. Cancel/revoke events
clear it immediately; a fresh snapshot cannot resurrect it. Expiry is exclusive
(`now >= expiresAt` blocks). Only another explicit, unique consent can start a new
preview after a stop. Reused IDs invalidate the history even after revocation.

The text fallback is always available: manually type/edit a reminder, receive a
plain text preview announcement, and use named Cancel/Clear controls. It needs no
camera, voice, color cue, gesture or bystander information. Unknown/present
bystanders block the synthetic wearable preview rather than assuming their
consent. The fallback is data for an illustrative UI, not a rendered or tested
assistive-technology experience; no reminder is stored or scheduled.

Trust boundary: caller-provided events are unauthenticated and can omit history.
Replay protection applies only to the supplied complete history. This is not a
production policy engine or durable revocation ledger. A real host alone must
bind identity/scope, persist consent and revocation, check platform permissions
and current bystander/privacy policy, and recheck at every privileged effect.
Every result sets `realActionAuthorized:false`, including a valid synthetic
preview. No external permission or grant is created by this module.

Six evals.json cases remain authored definitions, not model runs. The Node tests
exercise actual data transitions and adversarial malformed/replay inputs.
