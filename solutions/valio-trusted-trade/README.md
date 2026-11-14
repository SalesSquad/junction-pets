# Trusted Trade · an auditable buying agent

> **Independent Junction 2026 proof of concept, not a Valio Aimo product.** The entire buyer, product catalog, stock, prices, approvals, orders and audit events are invented local fixtures. **No supplier is contacted. No financial commitment occurs.** The browser and API use a *working local control plane*, not a sponsor connection.

![status](https://img.shields.io/badge/provider-INVENTED%20FIXTURE-orange) ![execution](https://img.shields.io/badge/fulfillment-SIMULATED-orange)

## Quick start

Requires Node.js 22+; zero package dependencies and zero credentials.

```sh
cd solutions/valio-trusted-trade
npm test
npm start
```

Open **http://127.0.0.1:4177** on the same computer. For a phone, use a tunnel or an explicitly configured HTTPS demo proxy; the Node server intentionally binds to localhost only. The responsive UI works in a narrow mobile browser, but no iOS app or native integration is claimed.

## Why this product

The sponsor asks how independent purchasing assistants can *discover catalog items and prices, check availability, and place a compliant order* through a structured open interface. A new marketplace or natural-language chatbot alone would miss the fundamental opportunity: **safe agent interoperability with supplier commerce and buyer authority**.

Trusted Trade composes a constrained buyer request, explicit product facts, immutable quote evidence, server-enforced spending policy and a one-time order receipt. Start with the preset *1,000 litres of lactose-free milk by Monday* scenario; it uses two source-versioned SKUs (€1,773.00 total), breaches the €750 fictional auto-commit threshold, and requires an explicit unauthenticated demo decision. Select €1,500 to see the budget refusal; simulate a price change to see the stale-quote refusal; commit twice with the same key to prove one deduction; cancel to restore simulated stock.

### Demo routes

| Method | Endpoint | Guarantee in this prototype |
|---|---|---|
| GET | `/api/health` | Clearly states `SIMULATED` |
| GET | `/api/catalog?q=milk` | Typed products, stock counts, price cents and version |
| GET | `/api/policy` | Synthetic buyer scope and spending ceiling; `approverAuthentication: NOT_IMPLEMENTED` |
| POST | `/api/quotes` | Rejects unavailable stock, unsuitable substitutions or budget overflow |
| GET | `/api/quotes/:id` | Original fixed-price basket and expiry |
| POST | `/api/quotes/:id/approval` | Fictional human approve/reject decision receipt |
| POST | `/api/orders` | Atomic in-memory stock recheck, quote validity and idempotency |
| GET | `/api/orders/:id` | Provider-neutral order receipt, explicitly simulated |
| POST | `/api/orders/:id/cancel` | Idempotent cancellation and synthetic restock |
| GET | `/api/audit` | Event trail across quotes, decisions, commits and cancels |
| POST | `/api/demo/reprice` | Demo-only catalog source mutation to test stale quotes |

See [supplier OpenAPI proposal](./openapi.yaml) and `src/supplier-port.mjs` for the **future external provider** boundary. The standalone HTTP port implements read-only JSON catalog interoperability and enforces HTTPS for non-local sources, but is intentionally **not wired to the purchasing simulator** and forbids all external order writes. The current API is a local buyer-controlled simulation. It does not accept Valio credentials or attempt undocumented sponsor endpoints.

## Explicit limits and next integrations

- **No live supplier API.** Sponsor endpoint details, scope, procurement sandbox and order authorization have not been confirmed. Inventing these would risk fake procurement claims.
- **No real login or legally binding approval.** Browser reviewer button is clearly unauthenticated; real OAuth 2.1, roles, scoped delegation and buyer proofs are release prerequisites.
- **No durable order store.** In-memory state resets on restart; production requires transactional stock reservation, persisted idempotency, immutable signed receipts, cancel/reconcile jobs, human escalation and provenance.
- **No tax, freight, real delivery calendar or substitutions.** The demo explicitly quotes item net amounts only and one fixture delivery date (Monday 16 November 2026). Real freight/tax must be source-backed.
- **No autonomous intent guessing.** The bounded parser supports whole-litre lactose-free dairy milk requests. Other intents are refused; this prevents prompt injection from silently changing purchasing authority.
- **No live demo publishing or external writes.** `npm start` is local only. A deployed public service would need authentication and removal or isolation of the demo reprice mutation.

Existing Valio recipe arithmetic in merged PR #49 is complementary exploratory work, not the procurement provider; no recipe logic has been copied or altered. The challenge companion's `pets/valio-aimo/CHALLENGE_RESEARCH.md` and official brief are source references, not edited by this feature.

## Judging walkthrough (90 seconds)

1. Open the product and start the 1,000-L preset purchase. Show two fixed-price availability lines, per-SKU source version and quote ID.
2. Point at the €750 auto-commit threshold. Attempt a direct POST order without approval: it returns `APPROVAL_REQUIRED`. Approve as fictional buyer.
3. Commit and inspect a synthetic order receipt; retry the same idempotency key and observe the same order ID. Show cancellation and audit events.
4. Create a fresh quote, hit **Simulate stale price** and show placement refused. Select €1,500 to demonstrate budget refusal. Stress all products and approvals are fictional and no external order is sent.
5. Explain the open provider interface and the remaining sponsor mock credential / real approval / reconciliation work.

## Evaluating the solution against sponsor priorities

| Sponsor focus | Demonstration evidence | Honest gap |
|---|---|---|
| End-to-end trade loop (30%) | Request → split fixed-price basket → approval → simulated commit → receipt | Sponsor-backed quote/order not yet connected |
| Professional buyer need (20%) | Realistic kitchen volume, delivery constraint, budget ceiling, multi-SKU stock | Placeholder buyer and delivery calendar |
| Agent autonomy and controls (20%) | Structured selection; explicit per-order approval; authority enforced by server | Delegated signed scoped approvals needed |
| Exceptions (15%) | Stock exhaustion, budget, stale price, expired offer, double submit, rejected order, cancellation | Production refunds and substitutions needed |
| Open interoperability (15%) | HTTP JSON contract, OpenAPI supplier boundary, source version fields | Source schema negotiation and live sandbox qualification |

This is an operational vertical slice suitable for sponsor feedback, **not a finished commercial procurement system**.
