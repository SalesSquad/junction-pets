# Recovery Compass — voluntary wellbeing after treatment

**Junction 2026 M343 · Aalto `aalto` partner key · synthetic product milestone 1/6.** Beyond the Clinic is specifically about supporting people at home after depression/TMS care. This is a **general wellbeing interaction prototype**, not maintenance TMS, a device delivering medical care, therapy, relapse prediction, emergency monitoring or a clinically validated recommendation engine. It does not use the separate Aalto Humanoid M320 dataset, or the publicly discussed OpenNeuro EEG sample as supposed treatment evidence.

## Actual runnable user journey

1. User selects a self-described energy preference and voluntarily chooses one of four low-risk, generic support actions (short pause, light movement, connecting with a chosen person, daylight).
2. No diagnosis, symptom score, mood surveillance or risk inference is calculated; the suggestion is exactly the user's own selected action.
3. User explicitly decides to choose the action. No sensor, smartphone function, clinician notification or external service activates.
4. Optional **preview** shows precisely the small whitelist of fields that *could* go in a wellbeing discussion; the interface requires a separate positive opt-in to create a **local unsent draft**. It never sends or stores anything outside the tab.
5. **Revoke** discards the local draft. **Erase session** clears the state. A crisis guidance disclosure is visible and includes the Finnish 112 emergency number for immediate danger; the app does not triage emergencies.

## Run and checks

```bash
npm test
npm run demo
npm start
# http://127.0.0.1:4180
```

Dependency-free Node and browser ES modules, read-only loopback static serving, `connect-src 'none'`, no localStorage/analytics, no network calls, no login or permissions. The runtime uses **in-memory, disposable synthetic state**; users must not enter personal clinical information. The flow is not appropriate for real vulnerable patients before qualified clinical and privacy review, ethical oversight, accessible usability validation and regulatory classification.

## Boundaries and honest acceptance

- 0 clinical-treatment and diagnosis claims; no PHQ-9, EEG classifier or TMS relapse model.
- All drafts require explicit user action, a scoped field whitelist and consent; revocation proves only that **our local draft** was cleared, not any remote copy. No connected clinician, authenticated actor, external delivery, secure storage or medical-decision system exists.
- The clinician preview demonstrates an interaction pattern, not a legitimate medical record or sharing capability. This distinction must be visible in demo and feedback.
- Next: independent clinical/content review of a consented daily journey, screen-reader/keyboard test on actual browsers, participant-created persona validation, data privacy impact assessment and a properly controlled pilot. Outcomes such as prevention of depression relapse **cannot** be inferred from synthetic usability.

**Ownership:** 1 Aalto company writer for the 2 M343 slice; M320 Humanoid starts sequentially after claim release. The Portfolio PR Recovery owns integration; the Junction FINAL controller owns submissions. No new paid service or provider account authorized.
