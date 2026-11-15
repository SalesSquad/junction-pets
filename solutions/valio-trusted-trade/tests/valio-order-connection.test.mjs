import test from 'node:test';
import assert from 'node:assert/strict';
import { createTradeService, unsignedQuoteBody, FIXTURE_CATALOG, FIXTURE_POLICY, TradeError } from '../src/core.mjs';
import { digest } from '../src/trust-envelope.mjs';
import { valioOrderConnectionStatus, createValioOrderHandoff } from '../src/valio-order-connection.mjs';

const buyerId = 'helsinki-hotel-demo';
const fixture = ({ packs = false, fees = false } = {}) => {
  const service = createTradeService({
    ...(packs ? { initialCatalog: FIXTURE_CATALOG.map(line => ({ ...line, packLitres: 6, minOrderPacks: 2 })) } : {}),
    ...(fees ? { policy: { ...FIXTURE_POLICY, deliveryFeeCents: 500, taxBps: 1400 } } : {}),
  });
  const quoted = service.requestQuote({ buyerId, need: { family: 'dairy-milk', lactoseFree: true,
    quantityLitres: packs ? 120 : 100, deliverBy: '2026-11-16' }, budgetCents: 250000 });
  const order = service.commitOrder({ quoteId: quoted.id, buyerId, idempotencyKey: 'supplier-handoff-test-01' });
  const quote = service.quote(quoted.id);
  return { service, quote, order, body: unsignedQuoteBody(quote) };
};
const refused = input => assert.throws(() => createValioOrderHandoff(input),
  error => error instanceof TradeError && error.code === 'INVALID_SUPPLIER_HANDOFF' && error.httpStatus === 409);

test('connection status states scoped observations, no transport, no authority and fresh returned data', () => {
  const status = valioOrderConnectionStatus();
  assert.equal(status.sendAllowed, false);
  assert.equal(status.endpoint, null);
  assert.equal(status.authentication, 'NOT_CONFIGURED');
  assert.equal(status.productionContract, 'UNVERIFIED');
  assert.equal(status.procurementAuthority, 'NOT_CONFIGURED');
  assert.equal(status.blocker, 'NO_VERIFIED_ORDER_CONTRACT');
  assert.deepEqual(status.challengeMock.observedOperations, ['GET /api/ping', 'POST /api/availability', 'POST /api/price', 'GET /api/products/download', 'GET /api/delivery-reliability/download', 'GET /api/carbon-footprint/download']);
  assert.equal(status.challengeMock.orderEndpointInObservedSchema, false);
  assert.ok(status.nextRequirements.includes('IDEMPOTENCY_STATUS_LOOKUP_AND_RECONCILIATION'));
  status.nextRequirements.pop();
  status.challengeMock.observedOperations.push('POST /invented/order');
  assert.equal(valioOrderConnectionStatus().nextRequirements.length, 7);
  assert.equal(valioOrderConnectionStatus().challengeMock.observedOperations.length, 6);
});

test('handoff is deterministic, non-sendable, source-bound and omits arbitrary metadata and buyer identifiers', () => {
  const { quote, order, body } = fixture();
  const before = structuredClone({ quote, order, body });
  quote.customerId = 'PRIVATE_CUSTOMER_DO_NOT_COPY';
  order.secret = 'PRIVATE_CUSTOMER_DO_NOT_COPY';
  const result = createValioOrderHandoff({ quote, order, body });
  assert.equal(result.sendAllowed, false);
  assert.equal(result.vendorRequest, false);
  assert.equal(result.source, 'INVENTED_FIXTURE');
  assert.equal(result.blocker, 'NO_VERIFIED_ORDER_CONTRACT');
  assert.deepEqual(result.references, { quoteId: quote.id, orderId: order.id,
    sourceSnapshotId: quote.snapshotId, quoteBodyDigest: digest(body) });
  assert.equal(result.terms.currency, 'EUR');
  assert.equal(result.terms.totalCents, order.totalCents);
  assert.equal(result.evidence.quoteBody, 'UNSIGNED_SYNTHETIC_QUOTE');
  assert.equal(result.evidence.supplierAcceptance, 'NOT_OBTAINED');
  assert.equal(result.evidence.buyerAuthority, 'REQUIRES_SEPARATE_HOST_VERIFICATION');
  assert.match(result.idempotencyReference, /^internal-handoff-[A-Za-z0-9_-]{43}$/);
  const { payloadDigest, ...unsigned } = result;
  assert.equal(payloadDigest, digest(unsigned));
  assert.equal(JSON.stringify(result).includes('PRIVATE_CUSTOMER_DO_NOT_COPY'), false);
  assert.equal(JSON.stringify(result).includes(buyerId), false);
  assert.deepEqual(result, createValioOrderHandoff({ quote, order: { ...order, idempotentReplay: true }, body }));
  delete quote.customerId; delete order.secret;
  assert.deepEqual({ quote, order, body }, before, 'preparation never mutates quote or receipt');
  result.terms.lines[0].packs = 999;
  assert.notEqual(createValioOrderHandoff({ quote, order, body }).terms.lines[0].packs, 999);
});

test('whole packs and fixed synthetic fee/tax arithmetic are carried exactly', () => {
  const { quote, order, body } = fixture({ packs: true, fees: true });
  const result = createValioOrderHandoff({ quote, order, body });
  assert.deepEqual(result.terms.costBreakdown, quote.costBreakdown);
  assert.equal(result.terms.lines[0].packLitres, 6);
  assert.equal(result.terms.lines[0].packs, 20);
  assert.equal(result.terms.lines[0].quantityLitres, 120);
  assert.equal(result.terms.costBreakdown.deliveryFeeCents, 500);
  assert.equal(result.terms.costBreakdown.taxBps, 1400);
});

test('uncommitted, canceled, unrelated and malformed receipts cannot become a supplier handoff', () => {
  const base = fixture();
  for (const mutation of [
    value => { value.quote.orderId = 'different-order'; },
    value => { value.order.quoteId = 'different-quote'; },
    value => { value.order.buyerId = 'other-buyer'; },
    value => { value.order.snapshotId = 'different-source'; },
    value => { value.quote.sourceSnapshot.id = 'different-source'; },
    value => { value.quote.status = 'APPROVED'; },
    value => { value.order.status = 'SIMULATED_CANCELLED'; },
    value => { value.order.commitment = 'REAL_ORDER'; },
    value => { value.quote.provider = 'VALIO'; },
    value => { value.order.lines = []; },
    value => { value.quote.lines = []; },
    value => { value.quote.costBreakdown = null; },
  ]) { const value = structuredClone({ quote: base.quote, order: base.order, body: base.body }); mutation(value); refused(value); }
  for (const value of [undefined, null, [], {}, { quote: null, order: null, body: {} }]) refused(value);
  const canceled = base.service.cancelOrder({ orderId: base.order.id, buyerId });
  refused({ ...base, order: canceled });
});

test('mismatched quantity, packs, source price, costs and body digest fail closed', () => {
  const { quote, order, body } = fixture();
  for (const mutation of [
    value => { value.order.totalCents++; },
    value => { value.order.lines[0].quantityLitres++; },
    value => { value.quote.lines[0].quantityLitres++; },
    value => { value.quote.lines[0].packs = 0; },
    value => { value.quote.lines[0].unitPriceCents++; },
    value => { value.quote.lines[0].stockVersion = 0; },
    value => { value.order.costBreakdown.taxCents++; },
    value => { value.quote.costBreakdown.subtotalCents++; },
    value => { value.body.total_cents++; },
    value => { value.body.currency = 'USD'; },
    value => { value.body.lines[0].quantity++; },
    value => { value.body.lines[0].unit_price_cents++; },
    value => { value.order.verifiedQuoteBodyDigest = 'a'.repeat(64); },
    value => { value.quote.verifiedHandshake = { quoteBodyDigest: 'a'.repeat(64) }; },
  ]) { const value = structuredClone({ quote, order, body }); mutation(value); refused(value); }
});

test('coherently modified quote/order arithmetic cannot conceal mismatched pricing', () => {
  const value = fixture();
  value.quote.totalCents++; value.order.totalCents++; value.body.total_cents++;
  refused(value);
});


test('two-family portfolio quote remains an internal non-sendable handoff', () => {
  const service = createTradeService();
  const requirements = ['dairy-milk', 'oat-drink'].map(family => ({
    family, lactoseFree: true, quantityLitres: 100, deliverBy: '2026-11-16',
  }));
  const plan = service.planBasket({ buyerId, requirements, budgetCents: 250000 });
  const quoted = service.quoteBasketPlan({ buyerId, planId: plan.id, optionId: plan.recommendedOptionId });
  const order = service.commitOrder({ quoteId: quoted.id, buyerId, idempotencyKey: 'portfolio-handoff-0001' });
  const quote = service.quote(quoted.id);
  const result = createValioOrderHandoff({ quote, order, body: unsignedQuoteBody(quote) });
  assert.equal(result.sendAllowed, false);
  assert.equal(result.terms.lines.length, 2);
  assert.equal(result.terms.lines.reduce((sum, line) => sum + line.quantityLitres, 0), 200);
});

test('matching modified records and body cannot substitute another price for the original snapshot', () => {
  const { quote, order } = fixture();
  for (const value of [quote, order]) {
    value.lines[0].unitPriceCents++;
    value.lines[0].totalCents += value.lines[0].quantityLitres;
    value.totalCents += value.lines[0].quantityLitres;
    value.costBreakdown.subtotalCents += value.lines[0].quantityLitres;
  }
  refused({ quote, order, body: unsignedQuoteBody(quote) });
});
