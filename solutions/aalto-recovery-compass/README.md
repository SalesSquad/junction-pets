# Recovery Compass — voluntary wellbeing after treatment

**Junction 2026 M343 · Aalto `aalto` partner key · synthetic product milestone 2/6.** Beyond the Clinic is specifically about supporting people at home after depression/TMS care. This is a **general wellbeing interaction prototype**, not maintenance TMS, a device delivering medical care, therapy, relapse prediction, emergency monitoring or a clinically validated recommendation engine. It does not use the separate Aalto Humanoid M320 dataset, or the publicly discussed OpenNeuro EEG sample as supposed treatment evidence.

## Actual runnable user journey

1. User selects a self-described energy preference and voluntarily chooses one of four low-risk, generic support actions (short pause, light movement, connecting with a chosen person, daylight).
2. No diagnosis, symptom score, mood surveillance or risk inference is calculated; the suggestion is exactly the user's own selected action.
3. User explicitly decides to choose the action. No sensor, smartphone function, clinician notification or external service activates.
4. Optional **preview** shows precisely the small whitelist of fields that *could* go in a wellbeing discussion; the interface requires a separate positive opt-in to create a **local unsent draft**. It never sends anything or persists the draft.
5. **Revoke** discards the local draft. **Erase session & capsule** clears memory and attempts local ciphertext deletion, reporting storage failures separately. A crisis guidance disclosure is visible and includes the Finnish 112 emergency number for immediate danger; the app does not triage emergencies.

## Run and checks

```bash
npm test
npm run demo
npm start
# http://127.0.0.1:4180
```

Dependency-free Node and browser ES modules, read-only loopback static serving, `connect-src 'none'`, no localStorage/analytics, no network calls, no login or permissions. The M1 check-in and sharing draft use **in-memory, disposable synthetic state**; only the separately opted-in M2 capsule persists as ciphertext in IndexedDB. users must not enter personal clinical information. The flow is not appropriate for real vulnerable patients before qualified clinical and privacy review, ethical oversight, accessible usability validation and regulatory classification.

## Boundaries and honest acceptance

- 0 clinical-treatment and diagnosis claims; no PHQ-9, EEG classifier or TMS relapse model.
- All drafts require explicit user action, a scoped field whitelist and consent; revocation proves only that **our local draft** was cleared, not any remote copy. No connected clinician, authenticated actor, external delivery or medical-decision system exists. M2 adds bounded encrypted local storage, not a clinical security/deployment qualification.
- The clinician preview demonstrates an interaction pattern, not a legitimate medical record or sharing capability. This distinction must be visible in demo and feedback.
- Next: independent clinical/content review of a consented daily journey, screen-reader/keyboard test on actual browsers, participant-created persona validation, data privacy impact assessment and a properly controlled pilot. Outcomes such as prevention of depression relapse **cannot** be inferred from synthetic usability.

**Ownership:** 1 Aalto company writer for the 2 M343 slice; M320 Humanoid starts sequentially after claim release. The Portfolio PR Recovery owns integration; the Junction FINAL controller owns submissions. No new paid service or provider account authorized.

## M2 encrypted local capsule

Choose an action first, separately check the local-save opt-in, optionally include the coarse energy preference, enter a user-kept passphrase, and press **Save / replace capsule**. Reopen the same browser profile and exact origin (including port), enter the passphrase, and press **Explicitly unlock saved capsule**. No automatic restore occurs. A saved view is separate from today's session: it cannot authorize a share draft. **Lock saved view** and `pagehide` clear its display; **Delete saved capsule**, **Revoke & clear draft**, and **Erase session & capsule** delete ciphertext. Erase clears memory even if the browser denies deletion; the status must report that failure. Retrying deletion remains available.

`src/vault.mjs` uses dependency-free WebCrypto AES-GCM-256 with a fresh secure 12-byte IV and 16-byte salt for each save, PBKDF2-SHA256 with 210,000 iterations, non-extractable derived keys and fixed purpose/version plus exact-origin authenticated context. Only an action ID, optional coarse preference and duplicated authenticated creation/expiry times are encrypted. The strict storage envelope has exactly version/context/iterations/times/salt/IV/ciphertext; no key, passphrase, session, draft, recipient or consent object is persisted. Unlock rebuilds a verified snapshot via `newSession` → `checkIn` → `chooseAction` and never assigns it to current sharing authorization. Adapter operations serialize save/delete to prevent a pending save from overtaking revocation.

TTL is fixed at seven days. Expired/malformed envelopes are purged on inspection/unlock; a running view schedules expiry. Closed browsers cannot run purge timers. Wrong passphrase or cryptographic damage returns no plaintext (a structurally valid locked record is retained because those cases cannot be distinguished). Unavailable WebCrypto/IndexedDB fails closed with an explanatory status. Deletion is local only, with no sent remote copy; it cannot guarantee erasure of backups, caches, forensic remnants or user-made copies. Exact-origin binding prevents cross-origin replay, but cannot distinguish a copied record returned to the same origin/profile context, same-origin tabs, browser compromise or clock rollback. Offline guessing remains possible with a weak passphrase. No clinical effectiveness, clinician sharing, real-patient suitability or GDPR clinical deployment is established.

### Targeted verification and handoff

Run `node --test solutions/aalto-recovery-compass/tests/*.test.mjs` from the repository root (or `npm test` here). Fixtures use Node WebCrypto, an injected memory storage backend and a minimal DOM harness; they do not qualify an actual browser's IndexedDB, accessibility, tab lifecycle or storage-denial behavior. KDF cost is fixed at one 210,000-iteration derivation per save/unlock, with no caller-controlled iteration escalation; slower/mobile-browser latency remains unmeasured. There are no dependencies or new network connections; the local server retains `connect-src 'none'`.

Source baseline: PR #114 HEAD `1a02a0bb650598571b63554312c7b5e82b323c7f`, supplied coordinator main `73669fee92f24fa2acf28d4b683b851e0fa39a1b` (local refs match; live remote refresh is separate). Work ID `J26-PF-AALTO-M343-PRIVATE-CAPSULE-M2-20261115`. Knowledge OS lifecycle tools were not exposed in this runtime (`registry_identity_unverifiable` / not routed); source files and the supplied claim govern this slice. Coordinator owns independent safety review, actual-browser save/close/reopen/unlock/expiry/delete and keyboard/screen-reader checks, source reconciliation, publication and integration. This writer leaves a local commit only; no PR #114 mutation, push, merge, FINAL update or ongoing worker.

Local closeout (15 November 2026): `node --test solutions/aalto-recovery-compass/tests/*.test.mjs` passed **28/28**, including the 15 unchanged M1 checks; `node --check` on `web/app.mjs` and `web/serve.mjs` and `git diff --check` passed. No actual-browser test or independent safety review was executed. Local Git staging/commit was blocked by sandbox denial creating `/Users/mikaelervamaa/Developer/junction-pets-20261111/.git/worktrees/j26-pf-aalto-m343-vault-m2-20261115/index.lock`; no commit, push or PR was created. Next action: coordinator reviews these eight product-scoped files, commits them on the owned branch using authorized Git metadata access, then performs independent safety/browser acceptance before publication. Preserve the current dirty source; do not reset this worktree.
