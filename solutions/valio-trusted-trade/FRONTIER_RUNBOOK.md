# Trusted Trade / Aimo — Frontier hackathon demonstration

**Work:** J26-VALIO-FRONTIER-20261114  
**Scope:** `solutions/valio-trusted-trade/**` only  
**Status:** event-born, synthetic, noncommercial research prototype  
**Sponsor:** Valio Aimo “Trusted Trade Agents” (Junction 2026)

## What is genuinely new here

**A self-healing procurement transaction that carries its own evidence.** The buyer can:

1. Request **two product families** together in whole litres, with exact dietary and date constraints.
2. Compare **cost / resilience / emissions** options using server-owned stock, prices and *invented* supplier metrics. The planner never silently substitutes an incompatible product or exceeds a budget.
3. Convert one option into a fixed-price quote with source versions, expiry and a human-decision gate.
4. Receive a **supplier-signed Ed25519 offer**, sign a **buyer mandate in an independent agent process or browser**, and exchange evidence bound to quote ID, buyer, audience, amount, expiry and a single-use nonce.
5. Refuse changed terms; on simulated source stock loss, **replan the same exact requirements**, reset authority and issue a new quote and new buyer decision. Previous approval and signatures cannot be carried over.
6. Commit one simulated order. An identical idempotency-key replay returns the original receipt, never a second stock deduction. Every local receipt also extends a verifiable SHA-256 hash chain.
7. Independently approve the **payment** for a portfolio order that **already passed signed Kättely verification**. The seller IDs are bound into the signed v2 quote body; the separate fictional payment click submits the digest of a complete order/supplier/EUR payout proposal. The local double-entry journal distributes invented EUR cents, records equal debit/credit amounts, blocks duplicate payments, and compensates cancellations with matching reversal entries. Legacy unsigned orders explicitly cannot pay. No financial institution is contacted.

No LLM, anonymous browser button, or agent can grant itself spending rights. Price, stock and agreement validity are rechecked by deterministic server code.

## Run

```bash
cd solutions/valio-trusted-trade
npm test
npm start
# Open http://127.0.0.1:4177/ — new responsive Mission Control
# Open http://127.0.0.1:4177/classic — preserved previous demonstration
```

Run the separate process in another terminal:

```bash
cd solutions/valio-trusted-trade
npm run demo:frontier -- happy --decision=approve
npm run demo:frontier -- replay --decision=approve
npm run demo:frontier -- shock --decision=approve
npm run demo:frontier -- refusal
npm run demo:frontier -- reject --decision=reject
# Optional fully synthetic trading + money movement (explicit fictional payment choice):
npm run demo:frontier -- happy --decision=approve --payment-decision=approve
# Optional compensating reversal and buyer wallet restoration:
npm run demo:frontier -- happy --decision=approve --payment-decision=approve --refund-demo
```

`--decision=approve` and `--payment-decision=approve` are **two separate scripted fictional human decisions**, not real authentication, funds or payment consent. The second flag is optional and must be supplied explicitly; the agent never self-authorizes payment. Without the first flag, the independent buyer agent prompts for an explicit purchase approval or rejection. Every scenario uses actual HTTP between an independent Node buyer process and the localhost supplier process; the buyer private key never leaves the agent process. The browser demonstration likewise creates a local WebCrypto key, publishes only the public JWK, signs locally and independently verifies signatures where supported.

## 110-second judge story — trade and fictional EUR included

| Seconds | Live action | Visible evidence |
|---|---|---|
| 0–15 | “Our kitchen needs 480 L lactose-free milk + 240 L oat drink within €1,750.” Click **Plan autonomous basket** | Three deterministic portfolios, full amount, source constraints, cost/risk/fictional footprint |
| 15–30 | Select **Resilient supply**, **Create fixed-price quote** | Inventory version, fixed cents, required approval |
| 30–42 | **Approve synthetic quote**, then **Verify Kättely handshake** | Separate buyer/private key, supplier/private key; quote digest and bounded mandate |
| 42–58 | **Simulate supplier outage** | Original terms refuse; agent generates a new viable basket without human prompting |
| 58–75 | **Create a fresh quote**, **Approve**, **Verify handshake**, **Commit** | Previous approval is not reused; one simulated order receipt |
| 75–90 | **Approve demo payment** and **Transfer fictional EUR** | Separate payment decision; one debit and one credit per supplier, fixed to the order amount |
| 90–110 | **Prove no duplicate transfer**, then **Cancel & reverse** | Idempotent replay; compensating double-entry refund; identical original buyer balance |

**Optional independent process proof:** Show `npm run demo:frontier -- shock --decision=approve --payment-decision=approve --refund-demo` in a separate terminal. The Node buyer agent discovers the OpenAPI, registers its own Ed25519 public key, validates the supplier signature, signs a buyer mandate, sees a disruption, replans, commits, and only then executes a separately permitted **fictional** payment and reversal without importing supplier state.

## Exact honesty boundary

**Real cryptography**: Ed25519 signatures are generated and checked in Node; browser WebCrypto signs the buyer mandate separately and can verify both signatures. Keys are ephemeral and not externally trusted. **Not real identity**: the demo session can register a self-attested public key without enterprise login. **Not a real sponsor integration**: supplier names, prices, inventory, reliability percentages, carbon factors, buyers, reviews and orders are invented. The EUR balances, transfer approvals, supplier credits and refunds are also invented; no Valio API, PSP, bank, payment rail or order placement is contacted. **Not AP2 / UCP / Kättely certification**: design inspiration comes from public specifications, but the wire protocol is explicitly `kattely.demo.procurement-envelope.v1` and does not make standards-conformance claims. **Not production durability**: all plans, audit receipts, fictional balances, double-entry journal and idempotency mappings are in memory and are reset on server restart.

The **cryptographically signed order mandate authorizes only one fictional ORDER**, never a payment. The additional fictional payment decision is **not** a signed payment mandate and does not prove the decision-maker's identity. The payment proposal is separately digest-bound to exact recipients, split amounts, order, EUR and the signed quote-body digest; source-derived terms cannot be changed by the client. A future real transfer requires a distinct signed payment mandate, real payer/beneficiary identities, expiry/nonce, authenticated human approval, regulated payment provider, durable journal and reconciled bank receipts.

The audit receipts form a SHA-256 hash chain, independently recomputed by the buyer agent. This is **not externally anchored or durable**: server restarts erase the local evidence.

## Open contracts and verifiers

- `GET /.well-known/trusted-trade`, `GET /openapi.json`: discovery and exact implemented API.
- `POST /api/plans`, `POST /api/plans/{id}/quotes`, `POST /api/plans/{id}/recover`: typed portfolio and recovery.
- `POST /api/trust/buyer-key`: session-bound buyer *public* JWK only.
- `POST /api/quotes/{id}/offer`: supplier-signed Ed25519 offer.
- `POST /api/quotes/{id}/handshake`: independently signed buyer mandate, verified and nonce-bound.
- `POST /api/demo/shock`: clearly labeled fictional inventory change.
- `POST /api/orders`: quote/approval/mandate/freshness/one-order validation.
- `POST /api/orders/{id}/payment-approval`: additional synthetic human payment decision, bound to the complete signed-trade-derived payout proposal digest; **legacy unsigned orders forbidden**.
- `POST /api/orders/{id}/settlement`: exact order amount, server-owned supplier split, bounded idempotency key, balanced fictional EUR entries.
- `GET /api/orders/{id}/payment`, `GET /api/demo/wallet`: owner-session fictional transfer and balances.
- `GET /api/demo/ledger`, `GET /api/demo/ledger/verify`: inspect in-memory double-entry postings and validate the hash-linked EUR journal.
- `POST /api/orders/{id}/cancel`: restock and issue compensating **fictional refund** journal entries if previously settled.
- `GET /api/audit`: in-memory evidence events.
- `GET /api/audit/verify`: local hash-chain verification; the buyer independently recomputes each receipt.

The independent buyer agent uses only HTTP plus the shared canonical wire encoder. Unit and integration tests target actual failure boundaries: wrong buyer/session/key, swapped amount, altered signature, replay, budget exceedance, expired quote, stale catalog and approval reset. No need for CI or external credentials to run locally.

## Integration constraints after hackathon

1. Replace self-attested identities with an authorized enterprise identity and actual buyer delegation service, including authenticated human approval.
2. Integrate a sponsor-verified catalog, live price/availability, reservations and external writes only **after separate explicit production authority**.
3. Persist mandates, nonce reuse protection, event/provenance evidence, idempotency and supplier reconciliation transactionally.
4. Harden API schema validation, authorization scopes and multi-tenant isolation, and provide signed deployment verification.
5. Use the existing **BankMatch `finance_core` / canonical `PaymentDraft`** for a future durable money/workspace/policy integration. This demo contains a disposable, order-scoped fictional-wallet projection for judging, **not** a second production ledger or a permission engine. Integrate an authorized PSP/PISP only after a separate mandate, regulatory review, real consent and explicit owner approval; never reinterpret demo session capability as banking authorization.

**Principle:** strong demo mechanics now, no invented production integration claims.
