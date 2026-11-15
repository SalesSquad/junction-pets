import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { generateKeyPairSync, randomUUID } from 'node:crypto';
import { createTradeService, FIXTURE_POLICY, unsignedQuoteBody } from '../src/core.mjs';
import { createTradeHttpServer } from '../src/server.mjs';
import { digest, makeDemoMandatePayload, signDemoEnvelope } from '../src/trust-envelope.mjs';

const buyerId = 'helsinki-hotel-demo';
const orderFor = (service, quantityLitres, key) => {
  const plan = service.planBasket({ buyerId, budgetCents: service.policy().perOrderBudgetCents,
    requirements: [
      { family: 'dairy-milk', lactoseFree: true, quantityLitres, deliverBy: '2026-11-16' },
      { family: 'oat-drink', lactoseFree: true, quantityLitres: 1, deliverBy: '2026-11-16' },
    ] });
  const q = service.quoteBasketPlan({ buyerId, planId: plan.id, optionId: 'cost' });
  if (q.approvalRequired) service.approve({ quoteId: q.id, buyerId, decision: 'approve' });
  // Ledger unit fixture: service records a verified handshake; the separate
  // HTTP end-to-end test below performs ACTUAL Ed25519 signing/verification.
  service.recordVerifiedHandshake({ quoteId: q.id, verification: { valid: true,
    quoteId: q.id, buyerId, signedBy: ['synthetic-buyer-unit-key', 'synthetic-supplier-unit-key'],
    signedOfferDigest: 'unit-fixture-offer', signedMandateDigest: 'unit-fixture-mandate',
    quoteBodyDigest: digest(unsignedQuoteBody(q)) } });
  return service.commitOrder({ buyerId, quoteId: q.id, idempotencyKey: key });
};
const approveDemo = (service, orderId, decision = 'approve') => service.approvePayment({
  orderId, buyerId, decision, proposalDigest: service.payment(orderId, buyerId).proposal.digest });

test('multi-supplier trade settles one exact server-owned amount with balanced debit/credit and an idempotent refund', () => {
  const service = createTradeService();
  const order = orderFor(service, 1000, 'settlement-order-001');
  const allocations = new Set(order.lines.map((line) => line.supplierId));
  assert.ok(allocations.size > 1, 'the settlement must actually split a multi-supplier basket');
  const before = service.demoWallet();
  assert.equal(before.buyerBalanceCents, 250000);
  assert.throws(() => service.settlePayment({ buyerId, orderId: order.id, idempotencyKey: 'transfer-test-001' }), { code: 'PAYMENT_APPROVAL_REQUIRED' });
  assert.equal(service.paymentJournal().length, 0);
  approveDemo(service, order.id);
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
  const firstDigest = service.payment(first.id, buyerId).proposal.digest;
  assert.throws(() => service.approvePayment({ orderId: first.id, buyerId, decision: 'approve', proposalDigest: firstDigest, recipient: 'attacker' }), { code: 'PAYMENT_TERMS_FORBIDDEN' });
  assert.throws(() => service.approvePayment({ orderId: first.id, buyerId: 'attacker', decision: 'approve', proposalDigest: firstDigest }), { code: 'BUYER_MISMATCH' });
  assert.throws(() => service.approvePayment({ orderId: first.id, buyerId, decision: 'approve', proposalDigest: 'forged' }), { code: 'PAYMENT_TERMS_STALE' });
  approveDemo(service, first.id, 'reject');
  assert.throws(() => approveDemo(service, first.id, 'approve'), { code: 'PAYMENT_DECISION_FINAL' });
  assert.throws(() => service.settlePayment({ orderId: first.id, buyerId, idempotencyKey: 'reject-transfer-001' }), { code: 'PAYMENT_APPROVAL_REQUIRED' });
  const second = orderFor(service, 100, 'settlement-second-002');
  approveDemo(service, second.id);
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
  approveDemo(service, order.id);
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
    const { publicKey, privateKey } = generateKeyPairSync('ed25519');
    const jwk = publicKey.export({ format: 'jwk' });
    const registered = await call('/api/trust/buyer-key', { buyerId,
      publicJwk: { kty: jwk.kty, crv: jwk.crv, x: jwk.x } }, token);
    const plan = (await call('/api/plans', { buyerId, budgetCents: 250000, requirements: [
      { family: 'dairy-milk', lactoseFree: true, quantityLitres: 100, deliverBy: '2026-11-16' },
      { family: 'oat-drink', lactoseFree: true, quantityLitres: 20, deliverBy: '2026-11-16' },
    ] }, token)).plan;
    const quoted = (await call(`/api/plans/${plan.id}/quotes`, { buyerId, optionId: 'cost' }, token)).quote;
    if (quoted.approvalRequired) await call(`/api/quotes/${quoted.id}/approval`, { buyerId, decision: 'approve' }, token);
    const signedOffer = (await call(`/api/quotes/${quoted.id}/offer`, { buyerId }, token)).signedOffer;
    const signedMandate = signDemoEnvelope(privateKey, registered.kid,
      makeDemoMandatePayload({ quote: quoted, signedOffer, now: Date.now(), nonce: randomUUID() }));
    assert.equal((await call(`/api/quotes/${quoted.id}/handshake`, { buyerId, signedMandate }, token)).proof.verification.valid, true);
    const order = (await call('/api/orders', { buyerId, quoteId: quoted.id, idempotencyKey: 'http-money-order-001' }, token)).order;
    assert.equal(order.paymentEligible, true);
    const approvalPath = `/api/orders/${order.id}/payment-approval`;
    const settlePath = `/api/orders/${order.id}/settlement`;
    assert.equal((await call('/api/demo/wallet')).status, 403);
    assert.equal((await call('/api/demo/ledger/verify')).status, 403);
    assert.equal((await call(`/api/orders/${order.id}/payment`)).status, 403);
    assert.equal((await call(`/api/orders/${order.id}/payment`, undefined, other.token)).status, 403);
    assert.equal((await call(approvalPath, { buyerId, decision: 'approve' }, other.token)).error.code, 'BUYER_MISMATCH');
    assert.equal((await call(settlePath, { buyerId, idempotencyKey: 'http-money-payment-001' }, token)).error.code, 'PAYMENT_APPROVAL_REQUIRED');
    assert.equal((await call(approvalPath, { buyerId, decision: 'approve', amountCents: 1 }, token)).error.code, 'PAYMENT_TERMS_FORBIDDEN');
    const proposal = (await call(`/api/orders/${order.id}/payment`, undefined, token)).proposal;
    assert.equal(proposal.allocations.reduce((sum, x) => sum + x.amountCents, 0), order.totalCents);
    assert.equal(proposal.signedQuoteBodyDigest, order.verifiedQuoteBodyDigest);
    assert.equal((await call(approvalPath, { buyerId, decision: 'approve', proposalDigest: 'tampered' }, token)).error.code, 'PAYMENT_TERMS_STALE');
    assert.equal((await call(approvalPath, { buyerId, decision: 'approve', proposalDigest: proposal.digest }, token)).status, 200);
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
    const unsigned = (await call('/api/quotes', { buyerId, requestText: '10 L lactose-free milk' }, token)).quote;
    const unsignedOrder = (await call('/api/orders', { buyerId, quoteId: unsigned.id, idempotencyKey: 'unsigned-legacy-order-001' }, token)).order;
    assert.equal(unsignedOrder.paymentEligible, false);
    assert.equal((await call(`/api/orders/${unsignedOrder.id}/payment-approval`, { buyerId, decision: 'approve', proposalDigest: proposal.digest }, token)).error.code, 'SIGNED_TRADE_REQUIRED');
    assert.equal((await call(`/api/orders/${unsignedOrder.id}/settlement`, { buyerId, idempotencyKey: 'unsigned-legacy-transfer-001' }, token)).error.code, 'SIGNED_TRADE_REQUIRED');
  } finally { await new Promise((done) => server.close(done)); }
});
