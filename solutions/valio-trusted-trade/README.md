# Trusted Trade · autonomous procurement with proof-carrying Kättely

## Frontier v3 — Mission Control (14 November 2026)

The new **[Frontier runbook](./FRONTIER_RUNBOOK.md)** is the main competition demo guide. Run `npm start` and open **http://127.0.0.1:4177/mission** for the responsive procurement command center; snapshot-bound review stays at **/** (also **/classic**). All actors, catalog items, prices, risk/emission figures, approvals, signatures' identities and simulated orders are synthetic.

The new independent buyer is `npm run demo:frontier -- shock --decision=approve` (or `happy`, `replay`, `refusal`, `reject`). It compares a two-family portfolio, applies real policy/stock constraints, proves the supplier offer and the browser/agent-held buyer mandate with **independent Ed25519 private keys**, recovers after fictional stock disruption, and independently verifies a SHA-256 hash-linked in-memory audit. This is not production Kättely, AP2, Valio Aimo API integration or identity authentication. **the original targeted tests** passed on the Mac, and the new desktop + mobile Chromium workflow was exercised end-to-end. The legacy single-family agent remains available below.

---

**Independent Junction 2026 prototype. Not a Valio Aimo product or endorsement.** Every supplier, buyer, catalog fact, price, stock count, approval and order is **SYNTHETIC / NONCOMMERCIAL**. Localhost HTTP is real; supplier commerce is simulated. The HTTP demo needs no npm runtime dependencies or credentials. Payments use fictional cents; no external provider writes occur. Optional PostgreSQL labs and OCR have separate local prerequisites.

## Agent workflow and recovery (15 November 2026)

Use the [optional official MCP v2 bridge](mcp/README.md) for typed agent tools,
compact results, host-mediated synthetic confirmation and resumable buying.
The [full audit](AGENT_USAGE_AUDIT.md) records the tested scope, source semantics
and production boundaries. Model tool arguments never include a vendor key.

`npm start` requires Node22.16+ and now defaults to SQLite at
`.runtime/state.sqlite`: private directory0700, database/WAL/SHM0600,
WAL/FULL synchronization and commit-before-response. The source namespace,
synthetic signing keys, capability hashes, ownership, approval, stock, payment,
refund and command replay records survive restart. `VALIO_STATE_FILE` selects
another private LOCAL path. Do not place active databases in iCloud/network
storage. `VALIO_EPHEMERAL=1` explicitly selects the old resettable memory demo.
The program never silently falls back or reseeds incompatible/corrupt state.

Create a new backup, without overwriting any existing file:

```sh
npm run state:backup -- --state /private/owner/state.sqlite --output /private/owner/new-backup.sqlite
```

Reopen a verified backup by selecting that new path; do not overwrite the active
store. Backups contain private synthetic keys and capability context and stay
local. These safeguards are local demo durability, not multi-host warehousing,
real buyer identity or independently anchored audit evidence.

The browser uses origin-local IndexedDB, including nonextractable buyer keys,
and rechecks server state/freshness before restoring controls. Reload never
creates approval or payment. Denied local storage explicitly selects ephemeral
use; inconsistent state or temporary server failures preserve recovery records
and block buying rather than silently switching buyer sessions.

Agent HTTP flow: `POST /api/agent/prepare` with a stable `Idempotency-Key`,
then owner-scoped `GET /api/agent/runs/:id`. Compact replies list allowed next
actions; `?detail=full` supplies source facts for independent verification.
A decision binds quote+snapshot; commitment requires a verified mandate and
the original owner. Changed command input conflicts; lost acknowledgements
reuse the original key. Catalog/search/audit have typed bounded queries and
opaque source-bound cursors. Refusals include explicit recovery guidance.

For authorized SPONSOR MOCK reads only, inject `VALIO_MOCK_API_KEY` into the
server through the operator's existing secret store, never tool arguments,
URLs, source or chat. `GET /api/integrations/status` reports configuration
without making a probe. `POST /api/suppliers/valio-mock/observe` accepts only
1–20 narrowed product IDs and a date; it caches bounded read observations.
It never promotes source prices/units into fixture purchasing authority.
No production endpoint, order capability, trusted human identity or hosted
deployment is implied by configuration or SDK confirmation.

## Integrated prototype

The portfolio, independently signed demo mandates, separate payment approval,
refundable balanced ledger, OCR/barcode observations, read-only pgvector adapter
and PostgreSQL recovery labs now share this source tree. The executable HTTP demo now persists private local SQLite state; the PostgreSQL lab remains a separate qualification executor.
The wallet and journal are deliberately shared public single-buyer fixtures.
Order/payment writes remain bound to the creating demo session.

Both single-family review and portfolio planning enforce explicit whole-pack
sizes and minimum order packs. Unknown pack facts fail closed; the invented
catalog explicitly uses 1 L packs/minimum 1. Inexact quantities require a revised
request, never silent overdelivery. Delivery scans count ordered packs and show
litres separately. Policy delivery fees and synthetic tax basis points enter the
full total once per basket, the approval delta and the signed v3 financial body.
Default fee/tax are zero; these are not actual supplier freight or VAT tariffs.

For browser qualification, run `node tests/approval-card.browser.mjs` and
`node tests/mission.browser.mjs` with an available Playwright installation.
The second script uses local Tesseract on a generated recipe; it requires no
camera, customer photo, provider account or commerce permission.

The sponsor portal and official schema were reached through the normal authorized Safari login on 15 November. Ping, one narrowed availability read and one price read returned HTTP200. The sponsor exposes no order endpoint. The optional read-only adapter accepts an operator-managed server credential; default purchasing remains the explicitly invented fixture.

## Snapshot-bound review and budget exceptions

The existing browser workflow now obtains diagnosis, relevant product facts,
policy and fixed-price proposal from one coherent server source snapshot.
Select the EUR 1400 budget to review the exact EUR 373 exception for the
unchanged 1000 L milk fixture. The card retains the original quantity, family,
diet and date, confirms the exact quote/source identifiers, and grants no
general budget increase. Changed facts or expired terms require a new offer
and new decision; missing stock and the policy ceiling cannot be approved away.
Stock is checked, not reserved. Everything remains synthetic and unauthenticated.

See [procurement diagnostics and review contracts](PROCUREMENT_DIAGNOSTICS.md).
The original independent buyer CLI and strict over-budget refusal remain
available unchanged; the browser opts into the explicit quote-only review flow.

## Run the independent agent

Node 22+. Terminal 1:

```sh
cd solutions/valio-trusted-trade
npm start
```

Terminal 2, same directory:

```sh
npm run demo:agent -- success
# Read the fixed-price basket; type approve or reject at the SYNTHETIC human prompt.
```

Open `http://127.0.0.1:4177` for the existing browser workspace and activity timeline. The CLI is a **separate Node process**, imports no server/core functions, and makes actual HTTP requests. No LLM interpretation is used.

**For an isolated resettable demonstration, start with `VALIO_EPHEMERAL=1 npm start` and restart between scenarios.** The default `npm start` preserves stock, receipts, approvals and keys.

```sh
npm run demo:agent -- refusal
npm run demo:agent -- replay --decision=approve
npm run demo:agent -- stale --decision=approve
npm run demo:agent -- success --oat --decision=approve
npm run demo:agent -- success --decision=reject
```

`--decision=approve|reject` is explicitly a **scripted synthetic human decision**, never authenticated human approval. Without it, the agent pauses for terminal input when policy requires approval. `SUPPLIER_URL=http://127.0.0.1:PORT` selects another local demo instance; external origins and redirects are refused.

```text
Independent buyer-agent.mjs (Node process A)       Browser workspace
          │ real localhost HTTP                       │
          ├─ /.well-known/trusted-trade + /openapi.json ┤
          ├─ current catalog + server-owned policy     ┤
          ├─ ephemeral SYNTHETIC buyer capability      ┤
          ├─ typed need → fixed quote                  ┤
          ├─ explicit SYNTHETIC human approve/reject   ┤
          └─ order → receipt / refusal / same-key replay
                              │
                    server.mjs (Node process B)
                    core.mjs → invented in-memory stock / audit
```

## Ninety-second judging walkthrough

1. Run `success`. Discovery reads the implemented OpenAPI and current synthetic catalog. The exact dairy need returns 780 L at 174 cents plus 220 L at 189 cents: **177,300 cents**, with no oat substitution. Lowest price wins within exact family, dietary, date and stock constraints. Stock is checked, **not reserved**.
2. The agent first attempts commitment without approval and observes server refusal. The €750 synthetic auto-commit threshold requires an explicit decision. Type `approve`; one simulated receipt is issued. Quote terms, source versions and IDs remain fixed; approval/order state transitions are separate.
3. Restart and run `replay`: one commitment, same-key replay returns the same receipt without reducing stock twice; a new key for the used quote and a reused key for another quote are refused.
4. Restart and run `stale`: after synthetic approval, a source-price change invalidates the old terms. `refusal` independently demonstrates the budget boundary. `--oat` proves typed second-family buying without freeform interpretation.
5. In the browser, choose typed milk/oat or the preserved safe legacy sentence, set whole litres, quote, approve/reject, commit, verify replay, simulate stale price, cancel, and export the **UNSIGNED** body. Activity explains provenance, selection, refusals, IDs and measured local processing time. Manual baseline is **UNMEASURED**.

The CLI's final JSON records actual monotonic per-request durations, cumulative HTTP processing and elapsed time including human input. These are local measurements, not a claimed speed-up versus manual buying. A rejection also emits its measured request list.

## Implemented open interface

Discover `GET /.well-known/trusted-trade`; follow `openapi` to `/openapi.json` and `endpoints` to the actual routes. [openapi.yaml](openapi.yaml) is the generated snapshot of [src/contract.mjs](src/contract.mjs), a proposed synthetic interchange contract, **not a sponsor API specification**. Regenerate with `npm run contract:export`.

- Public synthetic reads: catalog, policy, original quote, order receipt and audit.
- `POST /api/demo/session` with `{"buyerId":"helsinki-hotel-demo"}` issues an ephemeral demo capability. Send `Authorization: Bearer <token>` for writes. This endpoint is deliberately unauthenticated; it does **not** verify a real buyer. A session owns its quotes and orders; another session cannot approve or commit them.
- `POST /api/quotes`: `buyerId`, optional smaller `budgetCents`, and **either** legacy `requestText` **or** typed `need`: `{"family":"oat-drink","quantityLitres":1000,"lactoseFree":true,"deliverBy":"2026-11-16"}`. Extra need/quote fields, decimals, unknown families/dates, and mixed text/typed requests fail closed.
- `POST /api/quotes/:id/approval`: `buyerId`, `decision: approve|reject`, optional synthetic `approver` label. URL ID is authoritative. Decision is single-use and expiry/source versions are checked.
- `POST /api/orders`: **only** `buyerId`, `quoteId`, `idempotencyKey`. Client quantities, price or authority are rejected, including on replay. The server rechecks approval, expiry, stock, price and versions; one quote produces at most one simulated order. Key conflicts refuse.
- `POST /api/orders/:id/cancel`: owning session + buyer; restocks once. `POST /api/demo/reprice`: capability + `sku`, `priceCents`; deliberately synthetic source mutation.
- `GET /api/quotes/:id/body`: `{mode:"SYNTHETIC",signature:"UNSIGNED",body:{...}}`. Body uses stable `kattely.procurement.quote.v3` fields, Unix-second issue/expiry, supplier `supplier-demo`, audience `https://supplier-demo.invalid`, EUR and quantity × cents recomputed per line. This endpoint exports an unsigned body; the portfolio offer/mandate exchange signs its digest with independent, self-attested Ed25519 demo keys. This is not a production Kättely/AP2 identity or receipt.

[src/supplier-port.mjs](src/supplier-port.mjs) remains an optional read-only future-provider adapter with external order writes disabled. The runnable supplier is the local synthetic HTTP service above; no live-provider wiring is implied.

## Verification and boundaries

```sh
npm test
```

The original 22 tests retain their assertions (HTTP helpers now obtain the required synthetic capability). Seven additional focused tests cover forged/mismatched capabilities, altered order terms, replay conflicts, rejected/unapproved orders, competing stock, stale prices, injected-clock expiry, typed needs and cent-exact interoperability. One launches separate buyer Node processes against actual localhost HTTP servers for six scenarios; no sleeps or printed fake results. No monorepo suite or Actions changes.

Not commercially qualified: real buyer authentication/approver separation, production identity/authorization, external supplier order integration, revocation, real taxes/freight and delivery calendars. The HTTP executable now uses local SQLite; the separate PostgreSQL lab remains independent. The default executable persists local synthetic state; the explicit memory test factory resets on restart; reads are intentionally public synthetic data. Any local user can request a demo identity; this is **not production access control**. No browser/device usability claim follows from Node tests. Mobile/keyboard behavior needs browser review.

Source: [official challenge brief #327](https://hackjunction.app/participate/45/challenges/327), mirrored in the repository's `docs/challenge-research/official-briefs.md`; external-agent lookup → fixed-price inquiry/order → buyer permissions and approvals. **Sponsor integration remains unverified and disconnected.** Next priorities: sponsor-confirmed sandbox schema, authenticated scoped authority and durable reconciliation, under separate authorization. No deployment, commercial order or spending is authorized here.

Sponsor lookup accepts only numeric catalog IDs (1–12 digits); never submit personal identifiers. Browser recovery omits free-text form inputs. Local bearer/key storage and host-mediated approval are suitable only for this synthetic prototype, not production identity or trusted human-presence evidence.
