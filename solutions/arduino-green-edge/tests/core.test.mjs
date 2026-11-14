import test from 'node:test';
import assert from 'node:assert/strict';
import { evaluate, initialState, synthetic, createLedger, account, digest, readBridge } from '../core.mjs';
const t = 1794650400000;
const run = (sample, state, options = {}) => evaluate(sample, state, { now: sample?.at ?? t, optIn: true, ...options });
function ready(scenario = 'warm') { return run(synthetic(t + 10000, scenario), run(synthetic(t, scenario)).state); }
test('two samples debounce before opted-in simulation', () => {
  assert.equal(run(synthetic(t)).decision, 'HOLD');
  assert.deepEqual(ready().action, { fan: true, light: true });
});
test('no opt-in means proposal only, including manual override', () => {
  const revoked = run(synthetic(t + 20000), ready().state, { optIn: false });
  assert.equal(revoked.decision, 'PROPOSE');
  assert.equal(revoked.action, null);
  assert.equal(revoked.state.fan, false);
  assert.equal(revoked.state.light, false);
  assert.equal(run(synthetic(t + 30000), revoked.state).decision, 'HOLD');
  assert.equal(run(synthetic(t + 40000), run(synthetic(t + 30000), revoked.state).state).decision, 'SIMULATE');
  assert.equal(run(synthetic(t), undefined, { optIn: false, override: 'off' }).action, null);
});
test('manual off beats warm demand and re-entry needs debounce', () => {
  const off = run(synthetic(t + 20000), ready().state, { override: 'off' });
  assert.deepEqual(off.action, { fan: false, light: false });
  assert.equal(run(synthetic(t + 30000), off.state).decision, 'HOLD');
});
test('temperature and light hysteresis do not chatter in deadbands', () => {
  const sample = { ...synthetic(t + 20000), temperature: 26, lux: 300 };
  assert.deepEqual(run(sample, ready().state).action, { fan: true, light: true });
  assert.deepEqual(ready('daylight').action, { fan: false, light: false });
});
test('humidity hysteresis and occupancy zero', () => {
  const on = ready('humid');
  assert.equal(on.action.fan, true);
  assert.equal(run({ ...synthetic(t + 20000), temperature: 24, humidity: 68 }, on.state).proposed, undefined);
  assert.deepEqual(ready('empty').action, { fan: false, light: false });
});
test('sensor dropout resets outputs and requires two recovery readings', () => {
  const bad = run({ ...synthetic(t + 20000), connected: false }, ready().state);
  assert.equal(bad.decision, 'HOLD'); assert.equal(bad.action, null);
  const recovery = run(synthetic(t + 30000), bad.state);
  assert.equal(recovery.decision, 'HOLD');
  assert.equal(run(synthetic(t + 40000), recovery.state).decision, 'SIMULATE');
});
test('stale, missing, future, invalid clocks fail closed even under override', () => {
  for (const sample of [null, {}, { ...synthetic(t), at: t - 30001 }, { ...synthetic(t), at: t + 1 }]) assert.equal(evaluate(sample, initialState(), { now: t, optIn: true, override: 'off' }).action, null);
  assert.equal(evaluate(synthetic(t), undefined, { now: NaN }).decision, 'HOLD');
});
test('malformed values, missing fields and invalid controls fail closed', () => {
  for (const [key, value] of [['temperature', '28'], ['temperature', NaN], ['humidity', Infinity], ['humidity', 101], ['lux', -1], ['occupancy', .5], ['occupancy', null], ['connected', undefined]]) {
    assert.equal(run({ ...synthetic(t), [key]: value }).decision, 'HOLD', key);
  }
  assert.equal(run(synthetic(t), undefined, { override: 'on' }).decision, 'HOLD');
  assert.equal(run(synthetic(t), undefined, { optIn: 'yes' }).decision, 'HOLD');
});
test('duplicates, out of order and watchdog gaps cannot actuate', () => {
  const state = ready().state;
  assert.equal(run(synthetic(t), state).decision, 'HOLD');
  assert.equal(run(synthetic(t + 10000), state).decision, 'HOLD');
  assert.match(run(synthetic(t + 60000), state).reason, /Watchdog/);
  assert.equal(evaluate(synthetic(t + 10000), state, { now: t + 60000, optIn: true }).decision, 'HOLD');
});
test('offline transport stub, deterministic fingerprints and policy', async () => {
  const sample = await readBridge({ call: async method => { assert.equal(method, 'green_edge.sample'); return synthetic(t); } });
  assert.deepEqual(run(sample), run(sample));
  assert.equal(run(sample).networkRequired, false);
  assert.equal(digest({ a: 1, b: 2 }), digest({ b: 2, a: 1 }));
  assert.notEqual(digest(sample), digest({ ...sample, lux: 0 }));
  await assert.rejects(readBridge(null), /Injected/);
});
test('kWh arithmetic, negative avoidance and independent unknown device ledger', () => {
  const a = account(createLedger(), { start: t, end: t + 60000, baselineWatts: 60, scenarioWatts: 20 });
  assert.ok(Math.abs(a.estimatedAvoidedKWh - 40 / 60000) < 1e-12);
  assert.equal(a.devicePower.measuredKWh, null);
  const b = account(a, { start: t + 60000, end: t + 120000, baselineWatts: 0, scenarioWatts: 100 });
  assert.ok(b.estimatedAvoidedKWh < 0);
});
test('duplicate and overlapping energy intervals rejected; adjacent allowed', () => {
  const interval = { start: t, end: t + 10000, baselineWatts: 60, scenarioWatts: 0 };
  const a = account(createLedger(), interval);
  assert.throws(() => account(a, interval), /double-counting/);
  assert.throws(() => account(a, { ...interval, start: t + 1 }), /double-counting/);
  assert.equal(account(a, { ...interval, start: t + 10000, end: t + 20000 }).intervals.length, 2);
});
test('malformed energy arithmetic rejected, never coerced', () => {
  for (const patch of [{ baselineWatts: '60' }, { scenarioWatts: NaN }, { end: t }, { end: t + 60001 }, { baselineWatts: -1 }]) assert.throws(() => account(createLedger(), { start: t, end: t + 10000, baselineWatts: 60, scenarioWatts: 0, ...patch }));
});
