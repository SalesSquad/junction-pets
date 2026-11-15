# Trusted Trade Agents: Valio Aimo submission guide

**Everything here is synthetic. All suppliers, buyers, catalog items, prices, stock, approvals, orders and EUR balances are invented. No real Valio Aimo system, API, payment rail or customer data is connected.** This is an independent Junction 2026 prototype, not a Valio product.

## Problem

A food-service wholesaler such as Valio Aimo will soon face autonomous purchasing agents that want to find products, compare offers, order and get the right approval. The wholesaler cannot hand those agents its real systems, confidential pricing or marketplace roadmap, and a buyer cannot let an agent spend money without bounded, provable authority. The answer has to rest on open, verifiable standards rather than a private integration.

## What we built

A localhost supplier service plus an independent buyer agent that talk only over HTTP. The agent reads an OpenAPI contract, plans a two-family basket (lactose-free milk and oat drink) against stock, price, budget and date constraints, and gets a fixed-price quote. The supplier signs the offer. A human decision gates the purchase, and the buyer signs a bounded mandate with its own private key, which never leaves the agent process. The server rechecks approval, expiry, stock and price, then issues one order and one receipt. If stock disappears mid-flow, the agent re-plans the same requirements and old approvals are discarded. Every step lands in a hash-linked audit. An optional MCP bridge exposes the same buyer to LLM hosts as typed tools.

## 3-minute demo path

Requires Node 22.16+ and no installs. Run from `solutions/valio-trusted-trade`.

1. Start the server (default state is private local SQLite; add `VALIO_EPHEMERAL=1` for a resettable run):
   ```sh
   npm start
   ```
2. Check it is up: `curl http://127.0.0.1:4177/api/health` returns `"mode":"SIMULATED"` and `"provider":"invented-local-catalog"`.
3. Open http://127.0.0.1:4177/mission. Click **Plan autonomous basket**, pick **Resilient supply**, create a quote, approve, verify the handshake, **Simulate supplier outage**, create a fresh quote, approve, verify, commit. The 110-second table is in [FRONTIER_RUNBOOK.md](FRONTIER_RUNBOOK.md).
4. In a second terminal, run the independent buyer process:
   ```sh
   npm run demo:frontier -- happy --decision=approve
   npm run demo:frontier -- shock --decision=approve
   ```
   `shock` approves a quote, simulates supplier stock loss, sees the old offer refused (HTTP 409), recovers with a new plan and quote, re-approves, signs, and commits one order. `refusal` and `reject` show the failure paths.
5. Optional agent-tool view: `cd mcp && npm ci --ignore-scripts && npm start`, then point an MCP host at `mcp/server.mjs` with `SUPPLIER_URL=http://127.0.0.1:4177` (see [mcp/README.md](mcp/README.md)).
6. Verify the suite: `npm test` (146 tests).

### Observed on 15 Nov 2026 (Node 22.23.4, commit 320b8cf)

- `/api/health` returned `status: ok`, `mode: SIMULATED`, storage `LOCAL_SQLITE_WAL_FULL_SYNCHRONOUS_SYNTHETIC`. `/` and `/mission` both returned HTTP 200.
- `happy --decision=approve`: 16 HTTP requests in about 115 ms, one order for 126,720 cents, 6 audit receipts. A repeated handshake was refused with 409 (single-use nonce).
- `shock --decision=approve`: the offer on the original quote was refused with 409 after the stock shock, `/recover` produced a new plan, and one order was committed for 129,600 cents. 19 audit receipts, and the audit verify call returned 200.

## Open standards used

Each item below was checked in the source.

- **MCP**: official `@modelcontextprotocol/server` 2.4.0 over stdio, tools registered in `mcp/server.mjs`.
- **OpenAPI 3.1**: served at `/openapi.json`, with discovery at `/.well-known/trusted-trade`. `openapi.yaml` is generated from `src/contract.mjs`.
- **Ed25519 signatures**: Node `crypto` keys in `src/trust-envelope.mjs`, public keys published as OKP/Ed25519 JWKs. The buyer signs in a separate process, and the browser signs with WebCrypto.
- **SHA-256**: canonical digests bind quotes and mandates (`src/trust-envelope.mjs`), and audit receipts form a hash chain from a `GENESIS` link (`src/core.mjs`), recomputed independently by the buyer.
- **Idempotent orders**: `Idempotency-Key` replay returns the original receipt and never deducts stock twice. A reused key with changed input conflicts.
- **SQLite durability**: `node:sqlite` with WAL and `synchronous=FULL`, 0700 directory and 0600 files. Orders, keys and idempotency records survive restart.

## What this is not

Identities are self-attested demo keys, not enterprise authentication. The wire envelope is `kattely.demo.procurement-envelope.v1` and makes no AP2 or Kättely conformance claim. The sponsor mock adapter is read-only and optional, and no order endpoint exists upstream.

## What's next

1. Confirm the sponsor sandbox contract and connect read-only catalog and price lookups.
2. Replace demo sessions with authenticated buyers and scoped delegated approval.
3. Move idempotency and audit into a transactional store with supplier-side reconciliation.
4. Add a separately signed payment mandate before any money movement.

Further reading: [AGENT_USAGE_AUDIT.md](AGENT_USAGE_AUDIT.md), [ARCHITECTURE.md](ARCHITECTURE.md), [README.md](README.md).
