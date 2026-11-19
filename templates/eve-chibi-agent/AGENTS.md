# Agent development instructions — portable Chibi × eve starter

This directory is an independent, public-safe example. It is **not** the
authenticated Chibi runtime or a company-sponsored pet. The parent repository's
contributor contract still applies when editing it inside Junction Pets.

- Keep the example runnable with Node 24+ and the pinned Eve dependencies.
- Keep `defaultTools: false`; any new tool must declare its effect, validate
  input, and remain proposal-only until a host-issued permission boundary exists.
- Never add credentials, private user data, cross-tenant memory, marketplace
  entitlements, real payment operations, or implicit adoption to the starter.
- Observability stays off by default. Eve export policy and the final OTLP
  wrapper must allow only finite numeric usage metrics, fixed resource/name,
  and safe timing/context IDs: no content, free strings, events or links.
  Keep synthetic Eve-filter and protobuf tests. Configure only trusted loopback
  receivers. Before any real data, enforce redirects/egress at the host and
  review collector privacy/retention. Never add keys to templates.
- `maker-draft.json` is an editable **local authoring example**. Do not present
  it as a saved/published Chibi listing or a supported server import endpoint.
- Chibi's private Rust/Cedar host remains the authority for authenticated
  actions, consent, revocation, budgets, idempotency and signed receipts.
- Run focused checks before a PR; never claim a live model, browser, host,
  marketplace installation or deployment succeeded without separate evidence.
