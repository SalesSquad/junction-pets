# Valio order connection: implemented preparation, unverified provider contract

Observed 15 November 2026. This is an implementation-side integration boundary,
not Valio's order schema or an endorsement. The current purchasing domain,
catalog, prices and receipts remain **INVENTED FIXTURE / SIMULATED**.

## What is known

The challenge OpenAPI observed through the authorized Safari session contains
`GET /api/ping`, `POST /api/availability` and `POST /api/price`.
The POST operations read narrowly requested product facts. The observed schema
does not contain an order/checkout/write operation. This is evidence about that
dated challenge schema, not proof that Valio has no private production API.

- [Challenge OpenAPI](https://junction26.valioaimo.fi/openapi.json)
- [Challenge interactive docs](https://junction26.valioaimo.fi/docs)

The official commercial pages describe distinct customer channels:

- [Become a customer](https://www.valioaimo.fi/asiakkaaksi/): Aimo wholesale
  delivery customer and direct Valio customer are distinct arrangements.
- [Digital-service login](https://www.valioaimo.fi/asiakkaaksi/digipalveluihin-kirjautuminen/):
  access to a service follows the customer's rights. A website login is not a
  machine API credential, procurement mandate or permission to automate checkout.
- [VALO order service](https://www.valioaimo.fi/asiakkaaksi/valo-tilauspalvelu/):
  a direct-customer ordering channel; it does not by itself document a public
  machine order contract.
- [Official contacts](https://www.valioaimo.fi/yritys/yhteystiedot/):
  the channel for obtaining the appropriate technical/customer handoff.

The current research did not establish a public machine-order or EDI schema.
EDI availability, authentication, endpoints and accepted payloads must not be
inferred from the existence of a webshop or from generic commerce standards.
No supplier messages were sent, new account rights obtained or orders placed.

## Implemented boundary

`src/valio-order-connection.mjs` has no HTTP transport, configurable endpoint,
credential argument or send operation.

`valioOrderConnectionStatus()` returns fresh JSON with:

- `sendAllowed: false`, no endpoint, no configured procurement authority;
- a dated, explicitly non-live description of the challenge schema;
- the missing provider-contract requirements.

`createValioOrderHandoff({ quote, order, body })` accepts only matching,
server-held committed synthetic records. It verifies quote/order/buyer/snapshot
links, canonical quote body, source prices/stock versions, whole packs, line
totals and the existing deterministic fee/tax calculation. Canceled and
uncommitted receipts are refused with `INVALID_SUPPLIER_HANDOFF` (409).
A present synthetic handshake digest must match the body and receipt;
an unsigned classic quote stays explicitly unsigned.

The returned object is **our internal non-sendable envelope**, not a payload
for a guessed Valio endpoint. It contains only selected source references and
synthetic terms, no raw buyer/customer identifier, credentials or arbitrary
record metadata. Both `sendAllowed: false` and `vendorRequest: false` remain
hard-coded. A local simulated receipt is not supplier acceptance.

The stable `idempotencyReference` derives from order ID, quote ID and quote-body
digest. Repeated preparation creates identical bytes and payload digest. The
SHA256 digests use the existing canonical/base64url helper. These references are
internal; the real supplier contract must determine how idempotency is carried
and reconciled. Preparation grants no buying or payment authority.

Integration call after authenticating ownership:

```js
const order = service.order(orderId);
const quote = service.quote(order.quoteId);
const handoff = createValioOrderHandoff({
  quote, order, body: unsignedQuoteBody(quote),
});
// Read-only output. Never send this envelope to a supplier.
```

## Exact material needed before an order adapter can be implemented

Obtain these from the appropriate Valio channel for the actual customer model;
the owner must separately authorize any sandbox order-side effect:

1. Versioned approved request/response schema and sandbox endpoints, with a
   clearly identified Aimo wholesale or VALO/direct-customer contract.
2. Authorized customer, delivery branch/address references, buyer/delegation
   scope and who may approve an agent's request.
3. Host-managed authentication, operation scopes, rotation and revocation.
4. Fixed-price quotation/reservation identity, expiry and what must be rechecked
   before the order is committed.
5. Product mapping, sales units, whole packs, substitutions, tax/freight,
   delivery dates and cutoff semantics. The mock's `SK` and sentinel `999999`
   do not establish these meanings.
6. Idempotency-key scope and retention, order-status lookup after a timeout,
   retry rules and reconciliation when a supplier accepted but the ACK was lost.
7. Acceptance/rejection ACKs, partial availability, split orders, cancellation,
   amendments, refunds and the boundary after which changes are prohibited.

Only then can a provider-shaped request, lookup/recovery logic and authenticated
sandbox acceptance test be written. Host identity verification does not supply
missing customer procurement authority or turn fixture SKUs into provider SKUs.

## Focused check

```sh
node --test tests/valio-order-connection.test.mjs
```

The check uses the existing deterministic domain only. It covers coherent
preparation, retry identity, metadata omission, exact packs/fee/tax and negative
record/source/price/body bindings. It does not contact Valio or qualify live
orders, supplier idempotency, commercial identity or legal procurement authority.

## Fresh schema observation, 15 November 2026

Normal signed-in Safari fetched the official OpenAPI once (HTTP 200, 3.1.0, service 0.1.0). Its six operations are GET /api/ping, POST /api/availability, POST /api/price, GET /api/products/download, GET /api/delivery-reliability/download and GET /api/carbon-footprint/download. The earlier three-operation business-call summary omitted download routes; this current observation includes them. None is an order/write operation. This establishes the challenge schema only, not the absence of a private production integration. No dataset, account price, order, credential or provider permission was changed in this check.
