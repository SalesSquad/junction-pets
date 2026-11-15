# Trusted Trade · external buyer agent ↔ synthetic wholesaler

**Independent Junction 2026 prototype. Not a Valio Aimo product or endorsement.** Every supplier, buyer, catalog fact, price, stock count, approval and order is **SYNTHETIC / NONCOMMERCIAL**. Localhost HTTP is real; supplier commerce is simulated. Zero dependencies, credentials, payments or external provider writes.

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

**Restart the server between the following independent demonstrations** to reset in-memory stock and prices:

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
- `GET /api/quotes/:id/body`: `{mode:"SYNTHETIC",signature:"UNSIGNED",body:{...}}`. Body uses stable `kattely.procurement.quote.v1` fields, Unix-second issue/expiry, supplier `supplier-demo`, audience `https://supplier-demo.invalid`, EUR and quantity × cents recomputed per line. **No signer, signature, delegation proof or cryptographic verification.** Separate Kättely work may consume this body later; there is no repository dependency.

[src/supplier-port.mjs](src/supplier-port.mjs) remains an optional read-only future-provider adapter with external order writes disabled. The runnable supplier is the local synthetic HTTP service above; no live-provider wiring is implied.

## Verification and boundaries

```sh
npm test
```

The original 22 tests retain their assertions (HTTP helpers now obtain the required synthetic capability). Seven additional focused tests cover forged/mismatched capabilities, altered order terms, replay conflicts, rejected/unapproved orders, competing stock, stale prices, injected-clock expiry, typed needs and cent-exact interoperability. One launches separate buyer Node processes against actual localhost HTTP servers for six scenarios; no sleeps or printed fake results. No monorepo suite or Actions changes.

Not commercially qualified: real buyer authentication/approver separation, durable transactional stock and idempotency, signed evidence, revocation, taxes/freight and real delivery calendars. Capabilities and all state reset on restart; reads are intentionally public synthetic data. Any local user can request a demo identity; this is **not production access control**. No browser/device usability claim follows from Node tests. Mobile/keyboard behavior needs browser review.

Source: [official challenge brief #327](https://hackjunction.app/participate/45/challenges/327), mirrored in the repository's `docs/challenge-research/official-briefs.md`; external-agent lookup → fixed-price inquiry/order → buyer permissions and approvals. **Sponsor integration remains unverified and disconnected.** Next priorities: sponsor-confirmed sandbox schema, authenticated scoped authority and durable reconciliation, under separate authorization. No deployment, commercial order or spending is authorized here.
