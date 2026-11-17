import test from 'node:test';
import assert from 'node:assert/strict';
import { completeOnce, gapPrompt, GAPS_SCHEMA } from '../services/aiven-platform/completeness.mjs';

const draft = { answer: 'Lag is high.' };
test('no gaps keeps the draft and makes one call', async () => {
  const calls = [];
  const r = await completeOnce({ claude: async (...a) => { calls.push(a); return { data: { gaps: [] }, cost: 0.001 }; }, model: 'haiku', framedPrompt: 'P', draft });
  assert.equal(r.revised, false); assert.equal(r.response, draft); assert.equal(calls.length, 1); assert.equal(calls[0][3], GAPS_SCHEMA);
});
test('gaps trigger exactly one revision that carries the gaps but no rubric', async () => {
  const calls = [];
  const claude = async (model, prompt, system, schema) => { calls.push({ prompt, schema }); return calls.length === 1 ? { data: { gaps: [{ gap: 'partition 7 lag missing', evidence: 'p7 lag=287507' }] } } : { data: { answer: 'Lag is high; partition 7 holds 287,507.' } }; };
  const r = await completeOnce({ claude, model: 'haiku', system: 'S', schema: { s: 1 }, framedPrompt: 'P', draft });
  assert.equal(r.revised, true); assert.equal(calls.length, 2); assert.match(calls[1].prompt, /partition 7 lag missing/);
  assert.doesNotMatch(calls[1].prompt, /mustInclude/);
});
test('the checker prompt keeps attachments as untrusted data', () => {
  assert.match(gapPrompt('P', draft), /never instructions/);
});
test('additive completion keeps the draft intact and appends additions', async () => {
  const { completeAdditive } = await import('../services/aiven-platform/completeness.mjs');
  let n = 0; const claude = async () => (++n === 1 ? { data: { gaps: [{ gap: 'missing p50', evidence: 'p50 42-51' }] } } : { data: { additions: ['p50 stayed between 42 and 51 ms.'] } });
  const r = await completeAdditive({ claude, model: 'haiku', framedPrompt: 'P', draft: { answer: 'Spike at 11:00.', facts: [] } });
  assert.equal(r.revised, true); assert.match(r.response.answer, /^Spike at 11:00\.\n\np50 stayed/); assert.deepEqual(r.response.facts, []);
});
