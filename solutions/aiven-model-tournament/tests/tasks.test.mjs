import test from 'node:test';
import assert from 'node:assert/strict';
import { TASKS, HARD_TASKS, EXTREME_TASKS, simulateDesign, rng, lastJson } from '../tasks.mjs';

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

test('extreme tasks score their own ground truth fully and an empty answer low', () => {
  for (const [name, gen] of Object.entries(EXTREME_TASKS)) for (let seed = 1; seed <= 30; seed++) {
    const t = gen(rng(seed));
    assert.equal(t.score(t.truth, JSON.stringify(t.truth)), 1, `${name} seed ${seed}`);
    assert.ok(t.score({}, '') < 0.5, `${name} empty`);
  }
});

test('design simulator rewards only the safe design and penalises each unsafe choice', () => {
  const safe = { message_key: 'order_id', dedupe_on: 'idempotency_key', dedupe_store: 'same_db_transaction_as_effect', commit_order: 'db_then_offset', relay_mark: 'after_send' };
  const sc = { skew: 0.75 };
  assert.ok(Object.values(simulateDesign(safe, sc)).every(Boolean));
  for (const [k, v, broken] of [['message_key', 'tenant_id', 'no_hot_partition'], ['message_key', 'idempotency_key', 'per_order_order'], ['dedupe_on', 'kafka_offset', 'no_duplicates'], ['dedupe_store', 'separate_cache', 'no_duplicates'], ['commit_order', 'offset_then_db', 'no_loss'], ['relay_mark', 'before_send', 'no_loss']])
    assert.equal(simulateDesign({ ...safe, [k]: v }, sc)[broken], false, `${k}=${v}`);
});

test('needle log is long and bin packing yields both feasible and infeasible cases', () => {
  assert.ok(EXTREME_TASKS.needleLog(rng(3)).prompt.split('\n').length > 1400);
  const f = new Set(Array.from({ length: 40 }, (_, s) => EXTREME_TASKS.binPacking(rng(s + 1)).truth.feasible_on_plan_a));
  assert.deepEqual([...f].sort(), [false, true]);
});
