# Agent development instructions — portable Chibi × eve starter

This directory is an independent, public-safe example. It is **not** the
authenticated Chibi runtime or a company-sponsored pet. The parent repository's
contributor contract still applies when editing it inside Junction Pets.

- Keep the example runnable with Node 24+ and the pinned Eve dependencies.
- Keep `defaultTools: false`; any new tool must declare its effect, validate
  input, and remain proposal-only until a host-issued permission boundary exists.
- Never add credentials, private user data, cross-tenant memory, marketplace
  entitlements, real payment operations, or implicit adoption to the starter.
- Observability must stay disabled by default, apply the span-attribute
  allowlist, strip input/output content and identity span attributes at source,
  and configure only a trusted loopback collector. Before any real data,
  enforce redirects/egress and resource-data checks at the host or collector.
  Direct external export needs separate review. Never add keys to templates.
- `maker-draft.json` is an editable **local authoring example**. Do not present
  it as a saved/published Chibi listing or a supported server import endpoint.
- Chibi's private Rust/Cedar host remains the authority for authenticated
  actions, consent, revocation, budgets, idempotency and signed receipts.
- Run focused checks before a PR; never claim a live model, browser, host,
  marketplace installation or deployment succeeded without separate evidence.
