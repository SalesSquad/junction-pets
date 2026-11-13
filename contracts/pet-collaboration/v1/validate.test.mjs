import assert from 'node:assert/strict';
import test from 'node:test';
import { authorizeAndReserve, validateRequestShape } from './validate.mjs';

const NOW = Date.parse('2026-11-12T15:00:00Z');
const SOURCE = 'a'.repeat(40);
const request = () => ({
  schemaVersion: 'pet-collaboration.v1',
  kind: 'request',
  requestId: 'req.01',
  conversationId: 'turn.01',
  tenantId: 'tenant.alpha',
  actorPetId: 'junction.openai-codex',
  recipientPetId: 'junction.mariadb',
  capabilityId: 'query-review',
  sourceSha: SOURCE,
  authorityRef: 'host.grant.01',
  requestedEffect: 'read',
  createdAt: '2026-11-12T14:59:59Z',
  expiresAt: '2026-11-12T15:02:00Z',
  depth: 0,
  context: {
    ref: 'context.redacted.01',
    digest: 'sha256:' + 'a'.repeat(64),
    dataClass: 'synthetic',
  },
  budget: { maxTokens: 600, maxDepth: 2 },
});

const hostDecision = (r) => ({
  allowed: true,
  revoked: false,
  decisionRef: 'host.decision.01',
  authorityRef: r.authorityRef,
  tenantId: r.tenantId,
  actorPetId: r.actorPetId,
  recipientPetId: r.recipientPetId,
  capabilityId: r.capabilityId,
  sourceSha: r.sourceSha,
  requestId: r.requestId,
  conversationId: r.conversationId,
  parentRequestId: r.parentRequestId ?? null,
  depth: r.depth,
  contextRef: r.context.ref,
  requestedEffect: r.requestedEffect,
  contextDigest: r.context.digest,
  allowedDataClasses: ['synthetic'],
  expiresAt: '2026-11-12T15:03:00Z',
  maxTokens: 1_000,
  maxDepth: 4,
});

const host = (r, overrides = {}) => {
  const seen = new Set();
  return {
    authenticatedTenantId: r.tenantId,
    authenticatedActorPetId: r.actorPetId,
    nowMs: NOW,
    verifyHostGrant: async () => ({ ...hostDecision(r), ...overrides }),
    reserveReplay: async ({ tenantId, requestId }) => {
      const key = tenantId + '/' + requestId;
      if (seen.has(key)) return { reserved: false };
      seen.add(key);
      return { reserved: true };
    },
  };
};

test('valid contract succeeds with independently verified host decision and atomic reservation', async () => {
  const r = request();
  assert.equal(validateRequestShape(r), true);
  const verified = await authorizeAndReserve(r, host(r));
  assert.deepEqual(verified, {
    ok: true,
    code: 'AUTHORIZED_AND_RESERVED',
    requestId: r.requestId,
    decisionRef: 'host.decision.01',
  });
});

test('replay of same tenant/request is rejected after first admission', async () => {
  const r = request();
  const h = host(r);
  assert.equal((await authorizeAndReserve(r, h)).ok, true);
  assert.equal((await authorizeAndReserve(r, h)).code, 'REPLAY_OR_RESERVATION_FAILED');
});

test('unsigned self-reported authorityRef never substitutes for host adapter', async () => {
  const r = request();
  const result = await authorizeAndReserve(r, {
    authenticatedTenantId: r.tenantId, authenticatedActorPetId: r.actorPetId, nowMs: NOW,
  });
  assert.equal(result.code, 'HOST_INTEGRATION_UNAVAILABLE');
});

test('cross-tenant and cross-actor request cannot claim authenticated identity', async () => {
  const r = request();
  assert.equal((await authorizeAndReserve(r, { ...host(r), authenticatedTenantId: 'tenant.other' })).code, 'IDENTITY_MISMATCH');
  assert.equal((await authorizeAndReserve(r, { ...host(r), authenticatedActorPetId: 'junction.meta' })).code, 'IDENTITY_MISMATCH');
  assert.equal((await authorizeAndReserve(r, { ...host(r), authenticatedActorPetId: undefined })).code, 'NO_AUTHENTICATED_IDENTITY');
});

test('extra fields, embedded payload, malformed digest and cycle are rejected', async () => {
  for (const change of [
    (r) => { r.authorization = { allowed: true }; },
    (r) => { r.context.payload = 'should not cross the boundary'; },
    (r) => { r.context.digest = 'sha256:bad'; },
    (r) => { r.actorPetId = r.recipientPetId; },
    (r) => { r.depth = 3; r.parentRequestId = 'req.parent'; r.budget.maxDepth = 2; },
    (r) => { r.budget.maxTokens = -1; },
    (r) => { r.createdAt = '2026-02-30T14:59:59Z'; },
    (r) => { r.parentRequestId = 123; },
    (r) => { delete r.sourceSha; },
    (r) => { r.sourceSha = 'not-a-real-commit'; },
  ]) {
    const r = request(); change(r);
    assert.equal(validateRequestShape(r), false);
    assert.equal((await authorizeAndReserve(r, host(r))).code, 'INVALID_SHAPE');
  }
});

test('expired, future and overlong envelopes are rejected before host policy call', async () => {
  for (const change of [
    (r) => { r.expiresAt = '2026-11-12T14:59:00Z'; },
    (r) => { r.createdAt = '2026-11-12T16:00:00Z'; },
    (r) => { r.expiresAt = '2026-11-12T15:20:00Z'; },
  ]) {
    const r = request(); change(r);
    assert.equal((await authorizeAndReserve(r, host(r))).code, 'EXPIRED_OR_INVALID_TTL');
  }
});

test('host denies revoked, wrong recipient, wrong capability, effect and context', async () => {
  for (const override of [
    { revoked: true },
    { allowed: false },
    { recipientPetId: 'junction.nvidia' },
    { capabilityId: 'execute-sql' },
    { requestedEffect: 'write' },
    { contextDigest: 'sha256:' + 'b'.repeat(64) },
    { allowedDataClasses: ['public'] },
    { authorityRef: 'different' },
    { requestId: 'req.other' },
    { sourceSha: 'b'.repeat(40) },
    { contextRef: 'context.swapped' },
    { conversationId: 'turn.other' },
    { parentRequestId: 'req.swapped' },
    { depth: 1 },
    { decisionRef: 123 },
    { maxTokens: 500 },
    { maxDepth: 1 },
  ]) {
    const r = request();
    assert.equal((await authorizeAndReserve(r, host(r, override))).code, 'HOST_POLICY_DENIED');
  }
});

test('host policy or replay-store faults fail closed', async () => {
  const r = request();
  assert.equal((await authorizeAndReserve(r, {
    ...host(r), verifyHostGrant: async () => { throw new Error('offline'); },
  })).code, 'HOST_POLICY_UNAVAILABLE');
  assert.equal((await authorizeAndReserve(r, {
    ...host(r), reserveReplay: async () => { throw new Error('offline'); },
  })).code, 'REPLAY_OR_RESERVATION_FAILED');
});

test('child handoff binds parent, depth, source and context reference at host boundary', async () => {
  const r = request();
  r.parentRequestId = 'req.parent.01';
  r.depth = 1;
  let hostInput;
  const h = host(r);
  h.verifyHostGrant = async input => { hostInput = input; return hostDecision(r); };
  assert.equal((await authorizeAndReserve(r, h)).ok, true);
  assert.equal(hostInput.sourceSha, SOURCE);
  assert.equal(hostInput.conversationId, r.conversationId);
  assert.equal(hostInput.parentRequestId, r.parentRequestId);
  assert.equal(hostInput.depth, 1);
  assert.equal(hostInput.contextRef, r.context.ref);
  assert.equal(hostInput.contextDigest, r.context.digest);
});

test('replay reservation uses tenant scope, never global request ID alone', async () => {
  const r = request();
  const observed = [];
  const h = { ...host(r), reserveReplay: async (key) => { observed.push(key); return { reserved: true }; } };
  assert.equal((await authorizeAndReserve(r, h)).ok, true);
  assert.equal(observed[0].tenantId, 'tenant.alpha');
  assert.equal(observed[0].requestId, 'req.01');
  assert.equal(observed[0].decisionRef, 'host.decision.01');
  assert.equal(observed[0].sourceSha, SOURCE);
  assert.equal(observed[0].contextRef, r.context.ref);
  assert.equal(observed[0].conversationId, r.conversationId);
});
