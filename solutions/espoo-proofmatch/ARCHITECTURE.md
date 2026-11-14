# ProofMatch boundaries

`data.mjs` → `matcher.mjs` → `app.mjs` → semantic static HTML/CSS.
`benchmark.mjs` reuses the same pure matcher, with independently declared fixture
labels. `matcher.test.mjs` is the sole focused Node test file. `serve.mjs` serves
only the seven shell files plus the root page on 127.0.0.1. No npm dependency,
root workspace integration, database, backend action API or external request.

## Determinism and audit

The scoring observation date is injected, never read from the wall clock. Every
skill result exposes status, eligible evidence IDs, quality, age, role weight and
score contribution. The UI links IDs to local fixture cards and their issuer,
reference, source type, observed date and explicit `externalVerification:false`.
These are synthetic descriptions of self-provided material. No third party has
checked them; an artifact-shaped claim can be fabricated. Outcome presence is a
simple heuristic, not semantic validation. No legal or hiring inference follows.
There is no model, embedding similarity, AI-authorship detector or rejection
threshold. Generic bio padding is used only by the labelled naive baseline.

Per-skill maximum support avoids duplicate-card inflation. Stable ASCII-ID tie
breaks and final one-decimal rounding make repeated results reproducible.
Validation rejects missing/duplicate IDs, unsupported source types, purported
external verification, invalid dates, nonfinite/nonpositive weights and malformed
UTC windows. Functions do not mutate their input. Unknown skills stay visible;
unknown capability is distinct from a known negative outcome. No personal or
protected characteristics are input to the scoring path.

## Scheduling and draft state

Intersections use explicit UTC half-open windows and canonical complete 20-minute
slots. Overlapping input windows deduplicate. A draft holds its candidate and
employer across roles within this tab, so overlapping pairs are unavailable;
touching boundaries are allowed. Duplicate role/candidate pairs are rejected
even at another slot. Both demo consent values must be boolean `true` at draft
creation. Validation is repeated at the function boundary, not just in the UI.

The ledger is caller-supplied memory. It is neither trusted consent nor durable
transactional storage. Two tabs do not coordinate; refresh loses drafts. There
is no authenticated party, actual mutual confirmation, message recipient,
email/calendar service or external booking. Availability is a fixed fictional
event snapshot, not checked against current time or calendars. A live system
would need participant identity, revocable consent, actual schedule freshness,
atomic duplicate/conflict controls and independent provenance evaluation. These
are future boundaries, not part of this demo or claims of authorization.

## Privacy, offline and accessible presentation

No real people, PII import fields, analytics, cookies, localStorage, credentials,
private repository material or external assets. UI dynamic strings are escaped
before rendering; source references are text, never arbitrary executable URLs.
The one external challenge link navigates only on user action. The local server
has a strict file allowlist, read-only methods, MIME headers and restrictive CSP.
The optional service worker caches only named shell assets at this origin and
uses network-first with offline fallback; no drafts are written to storage.
First load requires the local server. A stale cache is possible offline; clear
site data for a fresh version. Cache versions must be changed for future releases.

Native select/buttons/checkboxes/details, labelled fields, semantic landmarks,
skip link, selected-state buttons, live announcements, focus restoration and
visible focus support keyboard use. Consent resets on selection/role changes.
Layout collapses for narrow screens; system fonts and reduced-motion rules avoid
network and animation requirements. Automated/source checks do not establish
screen-reader, device or production accessibility qualification.
