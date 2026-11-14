# Trusted Trade — architecture and trust boundary

**Repository source baseline:** `SalesSquad/junction-pets` `main` at `bb1f50908e05ada32e947abff86ac5e31e82e22d` (verified 14 November 2026). All owned implementation files stay inside `solutions/valio-trusted-trade/`.

## Current runtime

```text
Independent buyer Node process + Browser (synthetic demo identities only)
    ↕ Same-origin JSON HTTP (localhost)
src/server.mjs       route contract, payload limits, origin-bound CSS/JS
    ↕
src/core.mjs         deterministic intent parser → catalog selection → quote
                     server policy → explicit demo approval → one-time commit
                     versioned stock recheck → cancel/restock → audit events
    ↕
IN-MEMORY SYNTHETIC FIXTURE CATALOG / AUDIT / ORDERS
```

All fixture data and policy live server-side, not in the browser. Requests cannot override the URL-bound quote or order ID. There are no provider side effects. No external assets, network calls or dependencies are required.

Typed needs validate exact dairy-milk/oat-drink family, whole litres, dietary boolean and the fixed demo date, rejecting unknown fields. The preserved legacy intent boundary uses an **anchored, single-product whole-litre grammar**. Unsupported or mixed text results in `UNSUPPORTED_REQUEST`, including comma/point decimals, negative quantities, two products, unsupported delivery deadlines and instruction suffixes. The purchase layer must never extract a numeric fragment from an ambiguous natural-language message.

## Requested future sponsor/provider boundary

```text
Buyer agent / assistant (Taimi, Chibi or any other consumer)
    → typed intent + human principal + budgets
Buyer control plane (identity, policy, risk, approval, durable audit)
    → vendor-neutral provider adapter, per-provider scope
Supplier API (signed catalog, quote/availability, reservation, order, status)
    → immutable supplier receipt and reconciliation
```

`src/contract.mjs` is the implemented synthetic HTTP interface, served at `/openapi.json` and exported to `openapi.yaml`. `/.well-known/trusted-trade` advertises its endpoints. `buyer-agent.mjs` runs in a separate process and uses only real localhost HTTP, checks catalog/quote facts and never imports core functions. All writes require an ephemeral server-issued synthetic session capability; quotes/orders bind to that session. This prevents token forgery and cross-session commitment, but the open demo session issuer is **not real buyer authentication**. Approval labels are explicitly unauthenticated and share that session; real approver separation is absent.

`GET /api/quotes/:id/body` exports an **UNSIGNED synthetic** Kättely-compatible body. No signature or cross-repository trust is implemented. Reads are public synthetic data. HTTP refusals and idempotent replays append audit events. Monotonic client processing measurements exclude human input in the cumulative HTTP field; no manual baseline is measured.

`src/supplier-port.mjs` remains an isolated optional read-only external adapter with no order capability; it is not connected to the purchasing simulator. The implemented local supplier supports the whole simulated order flow independently of that future-provider adapter. Sponsor-specific mapping requires verified schema and separately authorized sandbox access.

## State transitions

```text
request → rejected (no stock / budget) or QUOTE
QUOTE → AUTO_COMMIT_ELIGIBLE or AWAITING_HUMAN_APPROVAL
AWAITING_HUMAN_APPROVAL → APPROVED / REJECTED
APPROVED or AUTO_COMMIT_ELIGIBLE → SIMULATED_COMMITTED
SIMULATED_COMMITTED → SIMULATED_CANCELLED
```

Expired terms and versioned price/stock changes prevent placement, even after an earlier approval. The in-memory idempotency registry maps each key to exactly one buyer+quote fingerprint and stored order; the same key returns the original result, while a key reused for another quote fails. Re-running cancellation never restocks twice. No values are sourced from a natural-language instruction for authority, price or stock.

## Production acceptance gate

1. Sponsor confirms product lookup, price validity, delivery windows, quote reservation, order status and cancellation schema.
2. Buyer identity and human approvals bound to authenticated principals and **limited scopes**, with expiry and revocation.
3. Durable database transaction and provider idempotency receipt, crash/retry recovery and explicit reserved-stock lifecycle.
4. Complete cost model (VAT, freight, deposit, exceptions); buyer approval covers the full amount and actual supplier identity.
5. Audit with immutable source hashes/provenance; policy on external prompt/tool output; reconciliation and operator escalation.
6. Explicit non-spend sandbox qualification before enabling even a trial external order.
