import test from 'node:test';
import assert from 'node:assert/strict';
import { validateResponse, toPendingActions, decisionFor, canonical } from '../bridge.mjs';

const ctx = { adoptionId: '11111111-1111-4111-8111-111111111111', agentVersionId: '22222222-2222-4222-8222-222222222222', authorityRevision: '7', conversationId: 'conv-1', chibi: 'junction.aiven' };
const base = { answer: 'ok', facts: [], assumptions: [], action_proposals: [], executed_actions: [], next_check: 'check lag' };
const scale = { operation: 'service_update_plan', target: 'orders-kafka', parameters: { plan: 'business-8' }, reason: 'lag', risk: 'medium', reversible: true, owner_role: 'platform owner', rollback: 'revert to business-4' };

test('a write request becomes a pending human decision with stable hashes', () => {
  const [p] = toPendingActions({ ...base, action_proposals: [scale] }, ctx);
  assert.equal(p.state, 'pending');
  assert.equal(p.decision_available, true);
  assert.match(p.proposal_hash, /^[0-9a-f]{64}$/);
  const [again] = toPendingActions({ ...base, action_proposals: [{ ...scale, parameters: { plan: 'business-8' } }] }, ctx);
  assert.equal(again.proposal_hash, p.proposal_hash);
  assert.deepEqual(decisionFor(p, 'approve').binding, { proposal_hash: p.proposal_hash, version: '1', authority_revision: '7' });
});

test('changing any reviewed byte changes the binding', () => {
  const [a] = toPendingActions({ ...base, action_proposals: [scale] }, ctx);
  const [b] = toPendingActions({ ...base, action_proposals: [{ ...scale, parameters: { plan: 'business-16' } }] }, ctx);
  assert.notEqual(a.proposal_hash, b.proposal_hash);
  assert.notEqual(a.payload_hash, b.payload_hash);
});

test('invalid schema data and missing host authority cannot become pending actions', () => {
  const missingParameters = { ...base, action_proposals: [{ ...scale, parameters: null }] };
  assert.ok(validateResponse(missingParameters).some(e => /parameters/.test(e)));
  assert.throws(() => toPendingActions(missingParameters, ctx), /invalid companion response/);
  assert.ok(validateResponse({ ...base, facts: 'not-an-array' }).length > 0);
  assert.throws(() => toPendingActions({ ...base, action_proposals: [scale] }, {}), /missing host context/);
  assert.throws(() => toPendingActions({ ...base, action_proposals: [scale] }, { ...ctx, authorityRevision: ' ' }), /missing host context/);
  assert.throws(() => toPendingActions({ ...base, action_proposals: [{ ...scale, parameters: { plan: NaN } }] }, ctx), /bounded JSON/);
  const parameters = {}; Object.defineProperty(parameters, 'plan', { enumerable: true, get() { throw new Error('getter executed'); } });
  assert.throws(() => toPendingActions({ ...base, action_proposals: [{ ...scale, parameters }] }, ctx), /bounded JSON/);
});

test('the bridge refuses executed actions, unknown operations, low-risk deletes and unofficial sources', () => {
  assert.ok(validateResponse({ ...base, executed_actions: ['aiven_service_update'] }).some(e => /empty/.test(e)));
  assert.ok(validateResponse({ ...base, action_proposals: [{ ...scale, operation: 'drop_everything' }] }).some(e => /unknown operation/.test(e)));
  assert.ok(validateResponse({ ...base, action_proposals: [{ ...scale, operation: 'service_delete', risk: 'low' }] }).some(e => /high risk/.test(e)));
  assert.ok(validateResponse({ ...base, facts: [{ claim: 'x', source_url: 'https://blog.example.com' }] }).some(e => /non-official/.test(e)));
  assert.ok(validateResponse({ ...base, action_proposals: [{ ...scale, rollback: '' }] }).some(e => /rollback/.test(e)));
  assert.throws(() => toPendingActions({ ...base, executed_actions: ['x'] }, ctx), /invalid companion response/);
  assert.equal(canonical({ b: 1, a: [2, { d: 1, c: 2 }] }), '{"a":[2,{"c":2,"d":1}],"b":1}');
});

test('v2 responses validate with governance and refuse a LIVE handoff label', () => {
  const v2 = { ...base, risks_and_side_effects: ['rebalance'], governance: { owner_role: 'platform owner', approvals_needed: ['DPO'], data_classification: 'special_category' }, peer_handoffs: [] };
  assert.deepEqual(validateResponse(v2), []);
  const live = { ...v2, peer_handoffs: [{ actor: 'a', recipient: 'b', capability: 'c', approved_context: 'd', expiry: 'e', budget: 'f', receipt_label: 'LIVE' }] };
  assert.ok(validateResponse(live).some(e => /LIVE/.test(e)));
  assert.ok(validateResponse({ ...v2, extra: 1 }).some(e => /unknown field/.test(e)));
});
