import test from 'node:test';
import assert from 'node:assert/strict';
import { createTradeService, FIXTURE_POLICY } from '../src/core.mjs';

const buyerId = FIXTURE_POLICY.buyerId;
const need = { family: 'dairy-milk', quantityLitres: 1, lactoseFree: true, deliverBy: '2026-11-16' };

test('stock shock preserves headroom for cancellation without losing original inventory', () => {
  const service = createTradeService();
  const quote = service.requestQuote({ buyerId, need, budgetCents: 10000 });
  const sku = quote.lines[0].sku;
  const original = service.catalog().find((item) => item.sku === sku).unitsAvailable;
  const order = service.commitOrder({ buyerId, quoteId: quote.id, idempotencyKey: 'audit-stock-bound-001' });
  assert.throws(() => service.simulateStockShock({ sku, unitsAvailable: 1_000_000 }));
  assert.equal(service.catalog().find((item) => item.sku === sku).unitsAvailable, original - 1);
  service.cancelOrder({ buyerId, orderId: order.id });
  assert.equal(service.catalog().find((item) => item.sku === sku).unitsAvailable, original);
  assert.ok(service.requestQuote({ buyerId, need, budgetCents: 10000 }).id);
});

test('recorded scan retry survives cancellation while new observations remain forbidden', () => {
  const service = createTradeService();
  const plan = service.planBasket({ buyerId, requirements: [need, { ...need, family: 'oat-drink' }], budgetCents: 10000 });
  const quote = service.quoteBasketPlan({ buyerId, planId: plan.id, optionId: plan.recommendedOptionId });
  // Internal verifier handoff fixture; HTTP verifies real signatures before this hook.
  service.recordVerifiedHandshake({ quoteId: quote.id, verification: {
    valid: true, quoteId: quote.id, buyerId, signedBy: ['fixture-supplier', 'fixture-buyer'],
    signedOfferDigest: 'fixture-offer', signedMandateDigest: 'fixture-mandate', quoteBodyDigest: 'fixture-body',
  } });
  const order = service.commitOrder({ buyerId, quoteId: quote.id, idempotencyKey: 'audit-scan-order-001' });
  const gtin = service.catalog().find((item) => item.sku === order.lines[0].sku).gtin;
  const args = { buyerId, orderId: order.id, gtin, idempotencyKey: 'audit-scan-lost-ack' };
  const original = service.scanDelivery(args);
  service.cancelOrder({ buyerId, orderId: order.id });
  assert.deepEqual(service.scanDelivery(args), { ...original, idempotentReplay: true });
  assert.throws(() => service.scanDelivery({ ...args, idempotencyKey: 'audit-scan-new-after-cancel' }), { code: 'ORDER_NOT_ACTIVE' });
});
