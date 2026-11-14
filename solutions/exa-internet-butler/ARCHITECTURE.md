# Architecture

Everything here is new event-born source. Node standard library serves a static
page and two task-shaped APIs. There is no package install, model, private host,
identity integration, persistence service, scheduler or external-action executor.

`public/` → same-origin `/api/packet` → `core.mjs` → pinned official fixtures.
`public/` → per-request consent `/api/live` → `exa-adapter.mjs` → fixed Exa Search
then Contents. External page URLs are validated data sent to Exa; the server never
fetches those URLs directly. Host/origin validation restricts localhost cross-site
requests and DNS rebinding. CSP rejects inline scripts, frames and external resources.
No goal/key/body is logged. API keys never reach the client.

## Domain and evidence

`fixtures/official.json` selects M298 and latest clarification, with root catalog
provenance, observation times, snapshot and content hashes. `anchors.json` is the
reviewed source registry. The guard checks IDs, canonical URLs, content hashes,
observation and snapshot anchors, duplicate URLs and exact claim excerpts. A code
writer can deliberately change both registry and fixture; hashes are integrity
checks against accidental/adversarial input, not signatures or independent attestation.
Claims and paraphrase labels are curated implementation, not an LLM extraction.

The deadline/eligibility/balance unknowns and narrative-vs-Prizes discrepancy are
explicit; source text is never executed or used as authorization. Replayed source
observations age at request time; a newly generated packet does not refresh them.
Source publication timestamps are unknown in replay, never fabricated.

## State and local review

Goal → EVIDENCE_READY → checklist/user actions → editable draft → local acknowledgment
→ local approval → copy/export. Unknown goal → CONNECTION_NEEDED. Live lookup returns
LIVE_EVIDENCE_ONLY; turning arbitrary live content into a grounded plan remains a
next milestone. Changing goals clears the previous workspace; editing checklist or
draft clears approval. No real-world task executor exists.

Browser memory holds progress and draft. Export is the only persistent user-controlled
artifact. There is no automatic localStorage, analytics, user identifier or hidden PII
collection. Optional typed text and exports may contain user input; avoid PII. A
server reload/tab reload loses the session. Browser copy/download policies can fail;
clipboard failure directs the user to export.

## Live transport and limits

Fixed HTTPS host `api.exa.ai`, fixed `search`/`contents` paths; exact public domain
allowlist; no credential/port URLs, arbitrary endpoint, redirect, retry or polling.
Timeout covers both fetches and body reads through AbortSignal. At most five sources,
256 KB/response and 4,000 displayed text characters/source. Missing/invalid publication
time, duplicate or unmatched contents URL fail closed. Live mode means actual
retrieval, never independent truth, source freshness or external task completion.
The API exposes only configuration presence, not key contents. This loopback prototype
has no multi-tenant authentication and must not be bound to a public interface.

## Workspace compatibility

`solution.json` follows PR #82's exact allowed fields, `stage=building`, scoped
ownership, known `junction.exa` ID and no implied capability execution references.
Schema read at PR #82 HEAD `45f7755a2f8e88e40f14588d0505f2e1aff9f799`.
Shared tooling is not yet on main; nothing from it is copied or modified.
The older companion proof branch remains separate and untouched. Existing other
product PRs were inspected for ownership, not imported. Chibi owns any future
production identity/consent/memory/tool dispatch; this source grants none of it.
