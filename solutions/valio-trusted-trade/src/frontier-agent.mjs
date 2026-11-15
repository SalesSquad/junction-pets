/**
 * Independent buyer agent, separate Node process and separate Ed25519 key.
 * It uses only the discovered localhost HTTP contract and shared wire codec.
 * No import of the supplier service, catalog fixtures or business state.
 * All scenarios are SYNTHETIC and make NO commercial purchases.
 */
import { createInterface } from 'node:readline/promises';
import { stdin, stdout } from 'node:process';
import { createPublicKey, generateKeyPairSync, randomUUID, verify } from 'node:crypto';
import assert from 'node:assert/strict';
import { verifyBuyerTerms, verifyBuyerBody } from './buyer-terms.mjs';
import { canonical, digest, makeDemoMandatePayload, signDemoEnvelope } from './trust-envelope.mjs';

const scenario = process.argv.find((x) => ['happy', 'shock', 'reject', 'replay', 'refusal'].includes(x)) ?? 'happy';
const base = new URL(process.env.SUPPLIER_URL ?? 'http://127.0.0.1:4177');
if (base.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname) || base.username || base.password) {
  throw new Error('Synthetic supplier must be localhost HTTP with no URL credentials.');
}
let token;
let paymentOutcome = null;
const requests = [];
const call = async (path, payload, errorCode) => {
  const url = new URL(path, base);
  if (url.origin !== base.origin) throw Error('Refusing cross-origin synthetic discovery.');
  const started = performance.now();
  const response = await fetch(url, { method: payload === undefined ? 'GET' : 'POST', redirect: 'error', signal: AbortSignal.timeout(6000),
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: payload === undefined ? undefined : JSON.stringify(payload) });
  const body = await response.json();
  requests.push({ method: payload === undefined ? 'GET' : 'POST', path, status: response.status, elapsedMs: +(performance.now() - started).toFixed(2) });
  if (errorCode) {
    assert.equal(body.error?.code, errorCode, JSON.stringify(body));
    assert.ok(!response.ok);
  } else if (!response.ok) throw Error(`${body.error?.code}: ${body.error?.message}`);
  return body;
};

const started = performance.now();
const discovery = await call('/.well-known/trusted-trade');
assert.equal(discovery.mode, 'SYNTHETIC_NONCOMMERCIAL');
const openapi = await call(discovery.openapi);
for (const endpoint of Object.values(discovery.endpoints)) assert.ok(openapi.paths[endpoint], `Undocumented ${endpoint}`);
const policy = await call(discovery.endpoints.policy);
({ token } = await call(discovery.endpoints.session, { buyerId: policy.buyerId }));

// This private key exists only in the independent BUYER agent process.
const { publicKey, privateKey } = generateKeyPairSync('ed25519');
const publicJwk = publicKey.export({ format: 'jwk' });
const registration = await call(discovery.endpoints.buyerKey,
  { buyerId: policy.buyerId, publicJwk: { kty: publicJwk.kty, crv: publicJwk.crv, x: publicJwk.x } });
assert.ok(registration.kid.startsWith('demo-buyer-'));

const intention = { buyerId: policy.buyerId, budgetCents: scenario === 'refusal' ? 1 : 175000,
  requirements: [
    { family: 'dairy-milk', lactoseFree: true, quantityLitres: 480, deliverBy: discovery.fixtureDeliveryDate },
    { family: 'oat-drink', lactoseFree: true, quantityLitres: 240, deliverBy: discovery.fixtureDeliveryDate },
  ] };
if (scenario === 'refusal') {
  await call(discovery.endpoints.plans, intention, 'BUDGET_EXCEEDED');
} else {
  let { plan } = await call(discovery.endpoints.plans, intention);
  assert.equal(plan.options.length, 3);
  assert.ok(plan.options.some((candidate) => candidate.withinBudget));
  const fixedQuote = async (chosenPlan) => {
    const optionId = chosenPlan.recommendedOptionId;
    const { quote } = await call(`/api/plans/${chosenPlan.id}/quotes`, { buyerId: policy.buyerId, optionId });
    verifyBuyerTerms(quote, policy, { requirements: intention.requirements, budgetCents: intention.budgetCents });
    if (quote.approvalRequired) {
      let decision = process.argv.find((x) => x.startsWith('--decision='))?.split('=')[1];
      if (!decision) {
        const rl = createInterface({ input: stdin, output: stdout });
        try { decision = (await rl.question('SYNTHETIC HUMAN DECISION only: approve or reject? ')).trim(); }
        finally { rl.close(); }
      }
      assert.ok(['approve', 'reject'].includes(decision), 'No autonomous approval escalation permitted.');
      const reviewed = await call(`/api/quotes/${quote.id}/approval`, { buyerId: policy.buyerId, decision, approver: 'Separate process scripted DEMO reviewer · UNAUTHENTICATED' });
      quote.status = reviewed.quote.status;
      quote.approval = reviewed.quote.approval;
    }
    return quote;
  };
  let quote = await fixedQuote(plan);
  if (scenario === 'reject') {
    await call(`/api/quotes/${quote.id}/offer`, { buyerId: policy.buyerId }, 'APPROVAL_REQUIRED');
    stdout.write(`SYNTHETIC buyer veto preserved; ${quote.id} will never be committed.\n`);
  } else {
    if (scenario === 'shock') {
      await call(discovery.endpoints.shock, { sku: 'DEMO-LF-1', unitsAvailable: 0 });
      await call(`/api/quotes/${quote.id}/offer`, { buyerId: policy.buyerId }, 'QUOTE_STALE');
      const recovered = await call(`/api/plans/${plan.id}/recover`, { buyerId: policy.buyerId });
      plan = recovered.plan;
      assert.equal(plan.humanApprovalCarriedOver, false);
      quote = await fixedQuote(plan); // Fresh quote ID and fresh decision; no implicit reused mandate.
    }
    const { signedOffer } = await call(`/api/quotes/${quote.id}/offer`, { buyerId: policy.buyerId });
    const keys = await call(discovery.endpoints.jwks);
    const supplierJwk = keys.keys.find((key) => key.kid === signedOffer.protected.kid);
    assert.ok(supplierJwk, 'Supplier public key must be discoverable.');
    const supplierKey = createPublicKey({ key: supplierJwk, format: 'jwk' });
    const proofBytes = Buffer.from(`${canonical(signedOffer.protected)}.${canonical(signedOffer.payload)}`);
    assert.ok(verify(null, proofBytes, supplierKey, Buffer.from(signedOffer.signature, 'base64url')));
    assert.equal(signedOffer.payload.quoteId, quote.id);
    assert.equal(signedOffer.payload.totalCents, quote.totalCents);
    const exported = await call(`/api/quotes/${quote.id}/body`);
    verifyBuyerBody(exported.body, quote);
    assert.equal(signedOffer.payload.quoteBodyDigest, digest(exported.body));
    const signedMandate = signDemoEnvelope(privateKey, registration.kid,
      makeDemoMandatePayload({ quote, signedOffer, now: Date.now(), nonce: randomUUID() }));
    assert.equal(signedMandate.payload.signedOfferDigest, digest(signedOffer));
    const { proof } = await call(`/api/quotes/${quote.id}/handshake`, { buyerId: policy.buyerId, signedMandate });
    assert.equal(proof.verification.valid, true);
    assert.equal(proof.verification.signedMandateDigest, digest(signedMandate));
    await call(`/api/quotes/${quote.id}/handshake`, { buyerId: policy.buyerId, signedMandate }, 'MANDATE_REPLAY');
    const request = { quoteId: quote.id, buyerId: policy.buyerId, idempotencyKey: randomUUID() };
    const { order } = await call(discovery.endpoints.orders, request);
    assert.equal(order.status, 'SIMULATED_COMMITTED');
    if (scenario === 'replay' || scenario === 'shock') {
      const repeated = await call(discovery.endpoints.orders, request);
      assert.equal(repeated.order.id, order.id);
      assert.equal(repeated.order.idempotentReplay, true);
    }
    // Optional explicit fictional-human approval; agent cannot silently grant
    // itself payment authority. Even a scripted approval is NOT real consent.
    const paymentDecision = process.argv.find((x) => x.startsWith('--payment-decision='))?.split('=')[1];
    if (paymentDecision) {
      assert.ok(['approve', 'reject'].includes(paymentDecision), 'Only an explicit fictional payment choice is supported.');
      const proposal = await call(`/api/orders/${order.id}/payment`);
      assert.equal(proposal.proposal.amountCents, order.totalCents);
      assert.equal(proposal.proposal.allocations.reduce((sum, x) => sum + x.amountCents, 0), order.totalCents);
      await call(`/api/orders/${order.id}/payment-approval`, { buyerId: policy.buyerId, decision: paymentDecision,
        proposalDigest: proposal.proposal.digest });
      if (paymentDecision === 'approve') {
        const instruction = { buyerId: policy.buyerId, idempotencyKey: randomUUID() };
        const paid = await call(`/api/orders/${order.id}/settlement`, instruction);
        assert.equal(paid.transfer.amountCents, order.totalCents);
        assert.equal(paid.transfer.rail, 'IN_MEMORY_NO_BANK_OR_PSP');
        const repeated = await call(`/api/orders/${order.id}/settlement`, instruction);
        assert.equal(repeated.idempotentReplay, true);
        assert.equal(repeated.transfer.id, paid.transfer.id);
        const ledger = await call(discovery.endpoints.ledgerVerify);
        assert.equal(ledger.valid, true, 'Fictional double-entry posting must balance.');
        paymentOutcome = { transferId: paid.transfer.id, amountCents: paid.transfer.amountCents,
          supplierCount: paid.transfer.allocations.length, ledgerEntries: ledger.journalEntries,
          rail: paid.transfer.rail };
        if (process.argv.includes('--refund-demo')) {
          const reversed = await call(`/api/orders/${order.id}/cancel`, { buyerId: policy.buyerId });
          assert.equal(reversed.order.status, 'SIMULATED_CANCELLED');
          const verification = await call(discovery.endpoints.ledgerVerify);
          assert.equal(verification.valid, true);
          assert.equal((await call(discovery.endpoints.wallet)).wallet.buyerBalanceCents, 250000);
          paymentOutcome.refunded = true;
        }
      } else {
        await call(`/api/orders/${order.id}/settlement`, { buyerId: policy.buyerId, idempotencyKey: randomUUID() }, 'PAYMENT_APPROVAL_REQUIRED');
        paymentOutcome = { decision: 'reject', transferId: null };
      }
    }
    stdout.write(`SIMULATED ${scenario}: independently signed offer + buyer mandate → one ${order.id} (${order.totalCents} cents); no commercial purchase.\n`);
  }
}
const audit = await call(discovery.endpoints.audit);
let previous = 'GENESIS';
for (const receipt of audit.receipts) {
  assert.equal(receipt.prevHash, previous, 'Receipt must link to previous SHA-256 digest');
  assert.equal(receipt.hash, digest({ id: receipt.id, time: receipt.time, event: receipt.event,
    detail: receipt.detail, prevHash: receipt.prevHash }), 'Buyer independently verifies hash chain');
  previous = receipt.hash;
}
assert.equal((await call(discovery.endpoints.auditVerify)).headDigest, previous);
stdout.write(JSON.stringify({ mode: 'SYNTHETIC', actor: 'INDEPENDENT_BUYER_PROCESS',
  scenario, payment: paymentOutcome, signed_buyer_private_key_location: 'THIS_PROCESS_ONLY',
  durationMs: +(performance.now() - started).toFixed(2), HTTP_requests: requests, auditReceipts: audit.receipts.length }) + '\n');
