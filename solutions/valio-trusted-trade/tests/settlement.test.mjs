import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { createTradeService, FIXTURE_POLICY } from '../src/core.mjs';
import { createTradeHttpServer } from '../src/server.mjs';

const buyerId = 'helsinki-hotel-demo';
const orderFor = (service, quantityLitres, key) => {
  const q = service.requestQuote({ buyerId, requestText: `${quantityLitres} L lactose-free milk`, budgetCents: service.policy().perOrderBudgetCents });
  if (q.approvalRequired) service.approve({ quoteId: q.id, buyerId, decision: 'approve' });
  return service.commitOrder({ buyerId, quoteId: q.id, idempotencyKey: key });
};

test('multi-supplier trade settles one exact server-owned amount with balanced debit/credit and an idempotent refund', () => {
  const service = createTradeService();
  const order = orderFor(service, 1000, 'settlement-order-001');
  const allocations = new Set(order.lines.map((line) => line.supplierId));
  assert.ok(allocations.size > 1, 'the settlement must actually split a multi-supplier basket');
  const before = service.demoWallet();
  assert.equal(before.buyerBalanceCents, 250000);
  assert.throws(() => service.settlePayment({ buyerId, orderId: order.id, idempotencyKey: 'transfer-test-001' }), { code: 'PAYMENT_APPROVAL_REQUIRED' });
  assert.equal(service.paymentJournal().length, 0);
  service.approvePayment({ orderId: order.id, buyerId, decision: 'approve' });
  const paid = service.settlePayment({ orderId: order.id, buyerId, idempotencyKey: 'transfer-test-001' });
  assert.equal(paid.transfer.status, 'SIMULATED_SETTLED');
  assert.equal(paid.transfer.amountCents, order.totalCents);
  assert.equal(paid.transfer.allocations.length, allocations.size);
  assert.equal(paid.transfer.allocations.reduce((sum, x) => sum + x.amountCents, 0), order.totalCents);
  assert.equal(paid.wallet.buyerBalanceCents, 250000 - order.totalCents);
  assert.equal(paid.wallet.suppliers.reduce((sum, x) => sum + x.balanceCents, 0), order.totalCents);
  assert.equal(service.paymentJournalVerify().valid, true);
  assert.equal(service.paymentJournalVerify().totalDebitCents, order.totalCents);
  const count = service.paymentJournal().length;
  const replay = service.settlePayment({ orderId: order.id, buyerId, idempotencyKey: 'transfer-test-001' });
  assert.equal(replay.idempotentReplay, true);
  assert.equal(replay.transfer.id, paid.transfer.id);
  assert.equal(service.paymentJournal().length, count);
  assert.throws(() => service.settlePayment({ orderId: order.id, buyerId, idempotencyKey: 'different-payment-key-001' }), { code: 'PAYMENT_ALREADY_SETTLED' });
  const cancelled = service.cancelOrder({ orderId: order.id, buyerId });
  assert.equal(cancelled.status, 'SIMULATED_CANCELLED');
  const refunded = service.payment(order.id, buyerId);
  assert.equal(refunded.transfer.status, 'SIMULATED_REFUNDED');
  assert.equal(refunded.wallet.buyerBalanceCents, 250000);
  assert.equal(refunded.wallet.suppliers.reduce((sum, x) => sum + x.balanceCents, 0), 0);
  assert.equal(service.paymentJournal().length, count * 2);
  service.cancelOrder({ orderId: order.id, buyerId });
  assert.equal(service.paymentJournal().length, count * 2);
  assert.equal(service.paymentJournalVerify().valid, true);
  assert.ok(service.audit().some((event) => event.event === 'DEMO_MONEY_TRANSFER_SETTLED'));
  assert.ok(service.audit().some((event) => event.event === 'DEMO_PAYMENT_REVERSED'));
  assert.equal(service.auditVerify().valid, true);
});

test('payment decisions are separate, terminal and reject injected amount and beneficiary fields', () => {
  const service = createTradeService();
  const first = orderFor(service, 100, 'settlement-first-001');
  assert.throws(() => service.approvePayment({ orderId: first.id, buyerId, decision: 'approve', recipient: 'attacker' }), { code: 'PAYMENT_TERMS_FORBIDDEN' });
  assert.throws(() => service.approvePayment({ orderId: first.id, buyerId: 'attacker', decision: 'approve' }), { code: 'BUYER_MISMATCH' });
  service.approvePayment({ orderId: first.id, buyerId, decision: 'reject' });
  assert.throws(() => service.approvePayment({ orderId: first.id, buyerId, decision: 'approve' }), { code: 'PAYMENT_DECISION_FINAL' });
  assert.throws(() => service.settlePayment({ orderId: first.id, buyerId, idempotencyKey: 'reject-transfer-001' }), { code: 'PAYMENT_APPROVAL_REQUIRED' });
  const second = orderFor(service, 100, 'settlement-second-002');
  service.approvePayment({ orderId: second.id, buyerId, decision: 'approve' });
  assert.throws(() => service.settlePayment({ orderId: second.id, buyerId, idempotencyKey: 'second-transfer-001', amountCents: 1 }), { code: 'PAYMENT_TERMS_FORBIDDEN' });
  assert.throws(() => service.settlePayment({ orderId: second.id, buyerId, idempotencyKey: 'second-transfer-001', supplierId: 'attacker' }), { code: 'PAYMENT_TERMS_FORBIDDEN' });
  service.settlePayment({ orderId: second.id, buyerId, idempotencyKey: 'second-transfer-001' });
  assert.throws(() => service.settlePayment({ orderId: first.id, buyerId, idempotencyKey: 'second-transfer-001' }), { code: 'IDEMPOTENCY_CONFLICT' });
  assert.equal(service.paymentJournalVerify().valid, true);
});

test('insufficient synthetic EUR blocks atomic postings without touching wallet or audit transfer', () => {
  const service = createTradeService({ policy: { ...FIXTURE_POLICY, perOrderBudgetCents: 350000 } });
  const order = orderFor(service, 1500, 'insufficient-order-001');
  assert.ok(order.totalCents > 250000);
  service.approvePayment({ orderId: order.id, buyerId, decision: 'approve' });
  assert.throws(() => service.settlePayment({ orderId: order.id, buyerId, idempotencyKey: 'insufficient-transfer-001' }), { code: 'INSUFFICIENT_DEMO_FUNDS' });
  assert.equal(service.demoWallet().buyerBalanceCents, 250000);
  assert.equal(service.paymentJournal().length, 0);
  assert.equal(service.paymentJournalVerify().valid, true);
});

test('HTTP payment APIs bind synthetic session ownership, block tampering and verify refund', async () => {
  const service = createTradeService();
  const server = createTradeHttpServer(service);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const call = async (path, payload, token) => {
    const response = await fetch(base + path, { method: payload === undefined ? 'GET' : 'POST',
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: payload === undefined ? undefined : JSON.stringify(payload) });
    return { status: response.status, ...await response.json() };
  };
  try {
    const session = await call('/api/demo/session', { buyerId });
    const other = await call('/api/demo/session', { buyerId });
    const token = session.token;
    const quoted = (await call('/api/quotes', { buyerId, requestText: '100 L lactose-free milk' }, token)).quote;
    const order = (await call('/api/orders', { buyerId, quoteId: quoted.id, idempotencyKey: 'http-money-order-001' }, token)).order;
    const approvalPath = `/api/orders/${order.id}/payment-approval`;
    const settlePath = `/api/orders/${order.id}/settlement`;
    assert.equal((await call('/api/demo/wallet')).status, 403);
    assert.equal((await call('/api/demo/ledger/verify')).status, 403);
    assert.equal((await call(`/api/orders/${order.id}/payment`)).status, 403);
    assert.equal((await call(`/api/orders/${order.id}/payment`, undefined, other.token)).status, 403);
    assert.equal((await call(approvalPath, { buyerId, decision: 'approve' }, other.token)).error.code, 'BUYER_MISMATCH');
    assert.equal((await call(settlePath, { buyerId, idempotencyKey: 'http-money-payment-001' }, token)).error.code, 'PAYMENT_APPROVAL_REQUIRED');
    assert.equal((await call(approvalPath, { buyerId, decision: 'approve', amountCents: 1 }, token)).error.code, 'PAYMENT_TERMS_FORBIDDEN');
    assert.equal((await call(approvalPath, { buyerId, decision: 'approve' }, token)).status, 200);
    assert.equal((await call(settlePath, { buyerId, idempotencyKey: 'http-money-payment-001', recipient: 'evil' }, token)).error.code, 'PAYMENT_TERMS_FORBIDDEN');
    const paid = await call(settlePath, { buyerId, idempotencyKey: 'http-money-payment-001' }, token);
    assert.equal(paid.status, 201);
    assert.equal(paid.transfer.amountCents, order.totalCents);
    assert.equal((await call('/api/demo/ledger/verify', undefined, token)).valid, true);
    assert.equal((await call('/api/demo/ledger', undefined, token)).entries.length, paid.transfer.allocations.length);
    assert.equal((await call(settlePath, { buyerId, idempotencyKey: 'http-money-payment-001' }, token)).idempotentReplay, true);
    assert.equal((await call(`/api/orders/${order.id}/cancel`, { buyerId }, token)).status, 200);
    assert.equal((await call(`/api/orders/${order.id}/payment`, undefined, token)).transfer.status, 'SIMULATED_REFUNDED');
    assert.equal((await call('/api/demo/wallet', undefined, token)).wallet.buyerBalanceCents, 250000);
    assert.equal((await call('/api/demo/ledger/verify', undefined, token)).valid, true);
    assert.ok((await call('/openapi.json')).paths[settlePath.replace(order.id, '{id}')]);
  } finally { await new Promise((done) => server.close(done)); }
});
