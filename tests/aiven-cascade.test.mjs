import test from 'node:test';
import assert from 'node:assert/strict';
import { answerWithCascade, escalationReasons } from '../services/aiven-platform/cascade.mjs';

const resp = (over = {}) => ({ answer: 'ok', facts: [], assumptions: [], action_proposals: [], executed_actions: [], next_check: 'x', risks_and_side_effects: [], governance: { owner_role: 'platform owner', approvals_needed: [], data_classification: 'internal' }, peer_handoffs: [], untrusted_instructions: [], ...over });
const fake = script => { const calls = []; return { calls, claude: async (model, prompt) => { calls.push(model); return { data: script(model, calls.length, prompt), cost: model === 'haiku' ? 0.001 : 0.01 }; } }; };

test('plain request stays on haiku', async () => {
  const f = fake(() => resp());
  const r = await answerWithCascade({ request: 'Map my app to Aiven services', claude: f.claude });
  assert.equal(r.route, 'haiku'); assert.deepEqual(f.calls, ['haiku']);
});

test('lint issue is repaired on haiku without escalation', async () => {
  const prop = { operation: 'service_update_plan', target: 'pg', parameters: {}, reason: 'r', risk: 'medium', reversible: true, owner_role: 'o', rollback: 'down' };
  const f = fake((m, n) => n === 1 ? resp() : resp({ action_proposals: [prop], risks_and_side_effects: ['cost'] }));
  const r = await answerWithCascade({ request: 'Scale pg to business-8', claude: f.claude });
  assert.equal(r.route, 'haiku+repair'); assert.deepEqual(f.calls, ['haiku', 'haiku']);
});

test('sensitive data stays on haiku by default; opt-in and tool-heavy requests escalate with reasons', async () => {
  const sensitive = () => resp({ governance: { owner_role: 'dpo', approvals_needed: ['DPO'], data_classification: 'special_category' } });
  const req = 'Load patient registry rows into ClickHouse in an EU region';
  assert.equal((await answerWithCascade({ request: req, claude: fake(sensitive).claude })).route, 'haiku');
  const r = await answerWithCascade({ request: req, claude: fake(sensitive).claude, escalateSensitive: true });
  assert.equal(r.route, 'sonnet'); assert.ok(r.reasons.includes('personal or special-category data'));
  assert.deepEqual(escalationReasons(resp({ action_proposals: [{ risk: 'high' }] }), 'x', [], { escalateSensitive: true }), ['high-risk proposal']);
  assert.deepEqual(escalationReasons(resp(), 'x', [], { toolHeavy: true }), ['tool-heavy request']);
});
