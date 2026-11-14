# J26-EXA-M2-20261114 continuation

- Work ID: J26-EXA-M2-20261114
- Exact authenticated main/base: `672da2be99edff2fa25c0ab2703e6da88061a62f`
- Clean baseline; task branch: `codex/j26-exa-actionable-butler-20261114`
- Exclusive writer scope: `solutions/exa-internet-butler/**`
- partnerEvidenceKey: `exa`; ownedBriefRefs: `[M298]`
- Source snapshot: `2026-11-14`; latestClarification read before previousDatedGuidance.
- Stage: building, **2/6 at most**. Executable source, not a live API-qualified product.
- Mode: REPLAYED_OFFICIAL_FIXTURE. LIVE / sponsor API: NOT VERIFIED.
- Resource cost: unknown; no dependencies installed or paid provider called.

## Delivered slice

Participant → named Exa opportunity goal → provenance ledger + supported excerpts →
conflict/stale/unknown → suggested and user-supplied checklist → editable clarification
draft → local approval → copy/JSON export. Arbitrary queries get a reliable
connection-needed state. No emails, bookings, purchases, redemption, polling or
external effect. Exact public URLs and dated repo fixture provenance remain visible.

## Actual verification, 14 Nov 2026

Executor: this isolated Mac mini sandbox, Node `v26.13.0`.

- `node --test solutions/exa-internet-butler/tests/guards.test.mjs`:
  **12/12 passed**, no skips. Includes separate held-out authored negatives for
  invented source, stale/altered date, duplicate URL and adversarial injection.
  Fake Exa transport checks validate contracts only, not sponsor API connectivity.
- `node solutions/exa-internet-butler/tests/http-smoke.mjs`: **BLOCKED** at bind:
  `listen EPERM: operation not permitted 127.0.0.1`. No listening process survived.
- Real browser/mobile/keyboard/clipboard journey: **not exercised**, because this
  executor cannot bind the local server. Responsive/accessibility code is implemented,
  not independently qualified. No full suite or external reviewer was run.
- `EXA_API_KEY` environment presence: false. No key discovery/offer redemption.
- Authenticated GitHub connector confirmed main SHA above and open PR heads.
  Local `gh` returned `error connecting to api.github.com`; connector reads succeeded.
  No open competing Exa product PR appeared. Existing companion branch is preserved.
  PR #82 schema read only; still draft/off-main at inspection.

## Next dependency and acceptance

Owner: authorized product integrator. Provide a permitted loopback/browser executor
and run the existing HTTP smoke, then exercise named replay → checklist → edit →
approve → export at mobile and desktop widths. After that, separately qualify an
already-authorized Exa key with an unseen goal and human-checked fresh sources.

Outstanding risk: no real browser acceptance or Exa Search/Contents receipt; the
named replay cannot establish current opportunity eligibility or live judging readiness.
Draft PR must link #80 and controller #77; do not edit controller, merge or release.

## Publication mechanics

Local `git add` / `git commit` are blocked by
`Unable to create .git/index.lock: Operation not permitted`. `git push origin
HEAD:refs/heads/codex/j26-exa-actionable-butler-20261114` is blocked by
`Could not resolve host: github.com`. The existing GitHub connector is the
alternate publication route for these exact owned bytes; the draft PR records
its remote commit/ref and verification. Local HEAD remains at the base because
local Git metadata is read-only. Never discard these local source files.
`verification.json` binds checked implementation files to content hashes.
