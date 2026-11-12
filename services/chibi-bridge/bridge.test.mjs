import test from 'node:test';
import assert from 'node:assert/strict';
import {dispatchPetRequest, receiptSha256, validateReceiptShape} from './bridge.mjs';

const SOURCE = '4'.repeat(40);
const NOW = Date.parse('2026-11-12T15:00:00Z');

function request() {
  return {
    schemaVersion: 'pet-collaboration.v1', kind: 'request',
    requestId: 'req.01', conversationId: 'turn.01',
    tenantId: 'tenant.alpha', actorPetId: 'junction.openai-codex',
    recipientPetId: 'junction.mariadb', capabilityId: 'query-review',
    authorityRef: 'host.grant.01', sourceSha: SOURCE, requestedEffect: 'read',
    createdAt: '2026-11-12T14:59:59Z', expiresAt: '2026-11-12T15:02:00Z',
    depth: 0, context: {ref: 'context.synthetic.1', digest: 'sha256:' + 'a'.repeat(64), dataClass: 'synthetic'},
    budget: {maxTokens: 600, maxDepth: 2},
  };
}

function grant(r, overrides = {}) {
  return {
    allowed: true, revoked: false, decisionRef: 'host.decision.01',
    authorityRef: r.authorityRef, tenantId: r.tenantId,
    actorPetId: r.actorPetId, recipientPetId: r.recipientPetId,
    capabilityId: r.capabilityId, sourceSha: r.sourceSha,
    requestId: r.requestId, conversationId: r.conversationId,
    parentRequestId: r.parentRequestId ?? null, depth: r.depth,
    requestedEffect: r.requestedEffect, contextRef: r.context.ref,
    contextDigest: r.context.digest,
    allowedDataClasses: [r.context.dataClass],
    expiresAt: '2026-11-12T15:03:00Z', maxTokens: 1000, maxDepth: 4,
    ...overrides,
  };
}

function receipt(r, overrides = {}) {
  return {
    schemaVersion: 'pet-collaboration.v1', kind: 'receipt',
    requestId: r.requestId, tenantId: r.tenantId,
    actorPetId: r.actorPetId, recipientPetId: r.recipientPetId,
    decisionRef: 'host.decision.01', status: 'completed',
    sourceSha: SOURCE, completedAt: '2026-11-12T15:00:10Z',
    outputDigest: 'sha256:' + 'b'.repeat(64),
    providerReceiptRef: 'provider.req.01',
    hostAuthorization: true, externalEffects: false,
    ...overrides,
  };
}

function host(r) {
  const used = new Set();
  const counters = {calls: 0, dispatches: 0, attestations: 0};
  const adapters = {
    authenticatedTenantId: r.tenantId,
    authenticatedActorPetId: r.actorPetId,
    sourceSha: SOURCE, nowMs: () => NOW, timeoutMs: 500,
    verifyHostGrant: async () => {counters.calls++; return grant(r);},
    reserveReplay: async ({tenantId, requestId}) => {
      const key = tenantId + '/' + requestId;
      if (used.has(key)) return {reserved: false};
      used.add(key);
      return {reserved: true};
    },
    transport: async ({idempotencyKey}) => {
      counters.dispatches++;
      assert.equal(idempotencyKey, 'tenant.alpha/req.01');
      return receipt(r);
    },
    verifyHostReceipt: async ({receipt: row, receiptSha256: digest, sourceSha, requestId}) => {
      counters.attestations++;
      return {verified: true, issuer: 'chibi-host', receiptSha256: digest, sourceSha, requestId,
        verificationRef: 'host.proof.01'};
    },
  };
  return {adapters, counters};
}

test('valid host-injected read-only receipt can be admitted and attested by injected verifier', async () => {
  const r = request(), h = host(r);
  const result = await dispatchPetRequest(r, h.adapters);
  assert.equal(result.ok, true);
  assert.equal(result.code, 'HOST_RECEIPT_ATTESTED');
  assert.equal(result.receipt.sourceSha, SOURCE);
  assert.equal(h.counters.dispatches, 1);
  assert.equal(h.counters.attestations, 1);
  assert.ok(h.counters.calls >= 3);
  assert.equal(validateReceiptShape(result.receipt), true);
  assert.match(receiptSha256(result.receipt), /^sha256:[a-f0-9]{64}$/);
});

test('host-dependent paths deny by default with missing credential/verifier/endpoint', async () => {
  const r = request(), h = host(r);
  for (const key of ['verifyHostGrant', 'reserveReplay', 'transport', 'verifyHostReceipt']) {
    const partial = {...h.adapters};
    delete partial[key];
    const outcome = await dispatchPetRequest(r, partial);
    assert.deepEqual(outcome, {ok: false, code: 'HOST_INTEGRATION_UNAVAILABLE'});
  }
  assert.equal((await dispatchPetRequest(r, {...h.adapters, sourceSha: 'not-a-commit'})).code, 'UNBOUND_SOURCE');
  assert.equal(h.counters.dispatches, 0);
});

test('tenant and actor identities are host-controlled, never taken from pet request', async () => {
  const r = request(), h = host(r);
  assert.equal((await dispatchPetRequest(r, {...h.adapters, authenticatedTenantId: 'tenant.other'})).code, 'IDENTITY_MISMATCH');
  assert.equal((await dispatchPetRequest(r, {...h.adapters, authenticatedActorPetId: 'junction.nvidia'})).code, 'IDENTITY_MISMATCH');
  assert.equal((await dispatchPetRequest(r, {...h.adapters, authenticatedActorPetId: null})).code, 'NO_HOST_IDENTITY');
  assert.equal(h.counters.dispatches, 0);
});

test('read-only bridge requires human approval for proposals or writes', async () => {
  const r = request(), h = host(r);
  for (const effect of ['proposal', 'write']) {
    assert.equal((await dispatchPetRequest({...r, requestedEffect: effect}, h.adapters)).code, 'HUMAN_APPROVAL_REQUIRED');
  }
  assert.equal(h.counters.dispatches, 0);
});

test('replay reservation preserves tenant/request idempotency', async () => {
  const r = request(), h = host(r);
  assert.equal((await dispatchPetRequest(r, h.adapters)).ok, true);
  assert.equal((await dispatchPetRequest(r, h.adapters)).code, 'REPLAY_OR_RESERVATION_FAILED');
  assert.equal(h.counters.dispatches, 1);
});

test('grant revocation before transport aborts dispatch', async () => {
  const r = request(), h = host(r);
  h.adapters.verifyHostGrant = async () => {
    h.counters.calls++;
    return grant(r, h.counters.calls >= 2 ? {revoked: true} : {});
  };
  const result = await dispatchPetRequest(r, h.adapters);
  assert.equal(result.code, 'REVOKED_BEFORE_DISPATCH');
  assert.equal(h.counters.dispatches, 0);
});

test('grant revocation after transport prevents any output receipt leakage', async () => {
  const r = request(), h = host(r);
  h.adapters.verifyHostGrant = async () => {
    h.counters.calls++;
    return grant(r, h.counters.calls >= 3 ? {revoked: true} : {});
  };
  const result = await dispatchPetRequest(r, h.adapters);
  assert.deepEqual(result, {ok: false, code: 'REVOKED_AFTER_DISPATCH'});
  assert.equal(h.counters.dispatches, 1);
  assert.equal(h.counters.attestations, 0);
});

test('tampered host receipt and fake attestation fail closed', async () => {
  const r = request(), h1 = host(r);
  h1.adapters.transport = async () => receipt(r, {recipientPetId: 'junction.nvidia'});
  assert.equal((await dispatchPetRequest(r, h1.adapters)).code, 'HOST_RECEIPT_INVALID');

  const h2 = host(r);
  h2.adapters.verifyHostReceipt = async () =>
    ({verified: true, issuer: 'chibi-host', receiptSha256: 'sha256:' + '0'.repeat(64),
      sourceSha: SOURCE, requestId: r.requestId, verificationRef: 'host.fake'});
  assert.equal((await dispatchPetRequest(r, h2.adapters)).code, 'HOST_ATTESTATION_INVALID');
});

test('no raw tokens, extra context or self-awarded grants can enter wire shape', async () => {
  const r = request(), h = host(r);
  r.context.payload = 'SECRET-PRIVATE-CONTENT';
  assert.equal((await dispatchPetRequest(r, h.adapters)).code, 'INVALID_REQUEST');
  delete r.context.payload;
  r.token = 'PRIVATE-TOKEN';
  assert.equal((await dispatchPetRequest(r, h.adapters)).code, 'INVALID_REQUEST');
  assert.equal(h.counters.dispatches, 0);
});

test('cancellation before dispatch fails without reserving replay', async () => {
  const r = request(), h = host(r), controller = new AbortController();
  controller.abort();
  assert.equal((await dispatchPetRequest(r, {...h.adapters, signal: controller.signal})).code, 'CANCELLED');
  assert.equal(h.counters.dispatches, 0);
});

test('timeout bounds an unresponsive host transport', async () => {
  const r = request(), h = host(r);
  h.adapters.transport = async () => new Promise(() => {});
  const result = await dispatchPetRequest(r, {...h.adapters, timeoutMs: 15});
  assert.equal(result.code, 'TIMEOUT');
  assert.equal(h.counters.attestations, 0);
});

test('in-flight cancellation never reports an authorized response', async () => {
  const r = request(), h = host(r), controller = new AbortController();
  h.adapters.transport = async (_payload, {signal}) => new Promise(resolve => {
    signal.addEventListener('abort', () => resolve(receipt(r)), {once: true});
  });
  const work = dispatchPetRequest(r, {...h.adapters, signal: controller.signal, timeoutMs: 200});
  await new Promise(resolve => setTimeout(resolve, 5));
  controller.abort();
  const result = await work;
  assert.equal(result.code, 'CANCELLED');
  assert.equal(h.counters.attestations, 0);
});

test('host transport and attestation failures redact diagnostic exceptions', async () => {
  const r = request(), h1 = host(r);
  h1.adapters.transport = async () => {throw new Error('PRIVATE-BEARER-TOKEN');};
  const failed = await dispatchPetRequest(r, h1.adapters);
  assert.deepEqual(failed, {ok: false, code: 'HOST_TRANSPORT_FAILED'});
  assert.ok(!JSON.stringify(failed).includes('PRIVATE-BEARER-TOKEN'));
  const h2 = host(r);
  h2.adapters.verifyHostReceipt = async () => {throw new Error('PRIVATE-SIGNATURE');};
  const attestation = await dispatchPetRequest(r, h2.adapters);
  assert.deepEqual(attestation, {ok: false, code: 'HOST_ATTESTATION_UNAVAILABLE'});
});

test('receipt validation rejects impossible dates and unauthorized external effects', async () => {
  const r = request(), h1 = host(r);
  h1.adapters.transport = async () => receipt(r, {completedAt: '2026-02-30T15:00:10Z'});
  assert.equal((await dispatchPetRequest(r, h1.adapters)).code, 'HOST_RECEIPT_INVALID');
  const h2 = host(r);
  h2.adapters.transport = async () => receipt(r, {externalEffects: true});
  assert.equal((await dispatchPetRequest(r, h2.adapters)).code, 'HOST_RECEIPT_INVALID');
});

test('cancellation during delayed host attestation withholds an otherwise valid receipt', async () => {
  const r = request(), h = host(r), controller = new AbortController();
  const originalVerifier = h.adapters.verifyHostReceipt;
  h.adapters.verifyHostReceipt = async args => {
    await new Promise(resolve => setTimeout(resolve, 25));
    return originalVerifier(args);
  };
  const pending = dispatchPetRequest(r, {...h.adapters, signal: controller.signal});
  await new Promise(resolve => setTimeout(resolve, 5));
  controller.abort();
  const result = await pending;
  assert.deepEqual(result, {ok: false, code: 'CANCELLED'});
});

test('source SHA must match the request, host grant and durable reservation', async () => {
  const r = request(), h1 = host(r);
  assert.equal((await dispatchPetRequest({...r, sourceSha: '5'.repeat(40)}, h1.adapters)).code, 'SOURCE_MISMATCH');
  assert.equal(h1.counters.dispatches, 0);

  const h2 = host(r);
  h2.adapters.verifyHostGrant = async () => grant(r, {sourceSha: '5'.repeat(40)});
  assert.equal((await dispatchPetRequest(r, h2.adapters)).code, 'HOST_POLICY_DENIED');
  assert.equal(h2.counters.dispatches, 0);

  const h3 = host(r);
  const originalReserve = h3.adapters.reserveReplay;
  let reservation;
  h3.adapters.reserveReplay = async query => {
    reservation = query;
    return originalReserve(query);
  };
  assert.equal((await dispatchPetRequest(r, h3.adapters)).ok, true);
  assert.equal(reservation.sourceSha, SOURCE);
  assert.equal(reservation.tenantId, r.tenantId);
  assert.equal(reservation.requestId, r.requestId);
});

test('recheck rejects source-scoped grant swapping before provider dispatch', async () => {
  const r = request(), h = host(r);
  h.adapters.verifyHostGrant = async () => {
    h.counters.calls++;
    return grant(r, h.counters.calls >= 2 ? {sourceSha: '5'.repeat(40)} : {});
  };
  assert.equal((await dispatchPetRequest(r, h.adapters)).code, 'REVOKED_BEFORE_DISPATCH');
  assert.equal(h.counters.dispatches, 0);
});
