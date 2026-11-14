import test from 'node:test';
import assert from 'node:assert/strict';
import { TASKS, HARD_TASKS, rng, lastJson } from '../tasks.mjs';

test('every task gives full marks to its own ground truth and zero-ish to an empty answer', () => {
  for (const [name, gen] of Object.entries(TASKS)) for (let seed = 1; seed <= 20; seed++) {
    const t = gen(rng(seed));
    let truth = t.truth;
    if (name === 'serviceMap') truth = { services: t.truth };
    if (name === 'secret') truth = { manifest_yaml: 'spec:\n  authSecretRef:\n    name: aiven-token\n    key: token', token_should_be_rotated: true };
    if (name === 'priceHonesty') truth = { monthly_price_usd: null, how_to_verify: 'Check current Aiven pricing page' };
    assert.equal(t.score(truth, JSON.stringify(truth)), 1, `${name} seed ${seed}`);
    assert.ok(t.score({}, '') < 0.5, `${name} empty`);
  }
});

test('parameters vary with the seed and answers are read from the last json block', () => {
  assert.notEqual(TASKS.consumerGroup(rng(1)).prompt, TASKS.consumerGroup(rng(2)).prompt);
  assert.deepEqual(lastJson('x ```json\n{"a":1}\n``` y ```json\n{"a":2}\n```'), { a: 2 });
  assert.equal(lastJson('no block'), null);
});

test('hard tasks score their own ground truth fully and an empty answer low', () => {
  for (const [name, gen] of Object.entries(HARD_TASKS)) for (let seed = 1; seed <= 30; seed++) {
    const t = gen(rng(seed));
    const truth = name === 'serviceMapDistractors' ? { services: t.truth } : t.truth;
    assert.equal(t.score(truth, JSON.stringify(truth)), 1, `${name} seed ${seed}`);
    assert.ok(t.score({}, '') < 0.5, `${name} empty`);
  }
});

test('replay task produces both preserved and violated orderings across seeds', () => {
  const v = new Set(Array.from({ length: 40 }, (_, s) => HARD_TASKS.replayOrder(rng(s + 1)).truth.order_preserved_for_all_tenants));
  assert.deepEqual([...v].sort(), [false, true]);
});
