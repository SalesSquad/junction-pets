import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {reviewCompatibility} from '../pets/arduino/compatibility.mjs';

const fixture = () => JSON.parse(readFileSync(new URL('../pets/arduino/example.json', import.meta.url), 'utf8'));
const rejected = x => {
  const r = reviewCompatibility(x);
  assert.equal(r.status, 'invalid');
  assert.deepEqual(r.issues, ['malformed-or-unsupported-input']);
  assert.equal(r.totals, null);
  assert.equal(r.authorization, false);
  assert.equal(r.safetyCertification, false);
};
const needsReview = (x, issues, totals = {supplyMa: 14, signalMa: 3}) => {
  const r = reviewCompatibility(x);
  assert.equal(r.status, 'needs-review');
  assert.deepEqual(r.issues, issues);
  assert.deepEqual(r.totals, totals);
  assert.equal(r.authorization, false);
  assert.equal(r.safetyCertification, false);
};

test('fictional worked arithmetic and review boundary', () => {
  const x = fixture(), before = structuredClone(x), r = reviewCompatibility(x);
  assert.equal(r.status, 'consistent');
  assert.deepEqual(r.totals, {supplyMa: 14, signalMa: 3});
  assert.equal(r.authorization, false);
  assert.equal(r.safetyCertification, false);
  assert.ok(r.unknowns.length >= 3);
  assert.deepEqual(x, before);
  assert.deepEqual(reviewCompatibility(x), r);
});

test('power and pin limits: exact boundary, zero, unknown and missing differ', () => {
  const x = fixture(); x.board.powerLimitMa = 17; x.board.totalPinLimitMa = 3;
  assert.equal(reviewCompatibility(x).status, 'consistent');
  x.board.powerLimitMa = 16; needsReview(x, ['power-oversubscribed']);
  x.board.powerLimitMa = 0; assert.ok(reviewCompatibility(x).issues.includes('power-oversubscribed'));
  x.board.powerLimitMa = null; assert.ok(reviewCompatibility(x).issues.includes('unknown-powerLimitMa'));
  delete x.board.powerLimitMa; assert.equal(reviewCompatibility(x).status, 'invalid');
});

test('each mismatch and oversubscription fails closed independently', () => {
  for (const [change, issues, totals] of [
    [x => x.sensors[0].voltageMv++, ['voltage-mismatch:sensor-a']],
    [x => x.sensors[0].ground = false, ['missing-ground:sensor-a']],
    [x => x.sensors[0].pins[0].mode = 'output', ['mode-mismatch:P0']],
    [x => x.sensors[0].pins[0].pin = 'absent', ['unknown-pin:absent']],
    [x => {x.sensors[1].pins[0].pin = 'P0'; x.sensors[1].pins[0].mode = 'input';}, ['duplicate-pin:P0']],
    [x => x.board.pinLimitMa = 0, ['pin-oversubscribed:P0', 'pin-oversubscribed:P1']],
    [x => x.board.totalPinLimitMa = 2, ['signal-oversubscribed']],
    [x => x.sensors[0].currentMa = 100, ['power-oversubscribed'], {supplyMa: 106, signalMa: 3}],
  ]) { const x = fixture(); change(x); needsReview(x, issues, totals); }
  for (const change of [x => x.board.pins[1].id = 'P0', x => x.sensors[1].id = 'sensor-a']) {
    const x = fixture(); change(x); rejected(x);
  }
});

test('all limit fields distinguish missing, null, zero, boundary and excess', () => {
  for (const [key, boundary, excessIssues, zeroIssues] of [
    ['powerLimitMa', 17, ['power-oversubscribed'], ['power-oversubscribed']],
    ['pinLimitMa', 2, ['pin-oversubscribed:P1'], ['pin-oversubscribed:P0', 'pin-oversubscribed:P1']],
    ['totalPinLimitMa', 3, ['signal-oversubscribed'], ['signal-oversubscribed']],
  ]) {
    const x = fixture(); x.board[key] = boundary;
    assert.equal(reviewCompatibility(x).status, 'consistent');
    x.board[key]--; needsReview(x, excessIssues);
    x.board[key] = 0; needsReview(x, zeroIssues);
    x.board[key] = null; needsReview(x, [`unknown-${key}`]);
    delete x.board[key]; rejected(x);
  }
});

test('proxy inputs at every structural position are rejected without executing traps', () => {
  let calls = 0;
  const handler = Object.fromEntries(['get', 'getPrototypeOf', 'ownKeys', 'getOwnPropertyDescriptor'].map(k =>
    [k, () => {calls++; throw Error('input trap');}]));
  for (const replace of [
    (x, wrap) => wrap(x),
    (x, wrap) => {x.board = wrap(x.board); return x;},
    (x, wrap) => {x.sensors = wrap(x.sensors); return x;},
    (x, wrap) => {x.board.pins[0] = wrap(x.board.pins[0]); return x;},
    (x, wrap) => {x.board.pins[0].modes = wrap(x.board.pins[0].modes); return x;},
    (x, wrap) => {x.sensors[0].pins[0] = wrap(x.sensors[0].pins[0]); return x;},
  ]) rejected(replace(fixture(), value => new Proxy(value, handler)));
  const revoked = Proxy.revocable({}, handler); revoked.revoke();
  rejected(revoked.proxy);
  // A transparent proxy must not be accepted either.
  const x = fixture(); x.board = new Proxy(x.board, {}); rejected(x);
  assert.equal(calls, 0);
});

test('unknown keys rejected before inspecting child descriptors or values', () => {
  let calls = 0;
  const x = fixture();
  x.extra = new Proxy({}, {getPrototypeOf() {calls++; throw Error('must not traverse');}});
  rejected(x);
  assert.equal(calls, 0);
});

test('shared work budget bounds repeated schema-shaped input; ordinary aliases work', () => {
  const x = fixture();
  // Only a few allocated objects but 10,000 logical pin occurrences.
  x.sensors[0].pins = Array(100).fill(x.sensors[0].pins[0]);
  x.sensors[0].pinCount = 100;
  x.sensors = Array.from({length: 100}, (_, i) => ({...x.sensors[0], id: `sensor-${i}`}));
  rejected(x);
  const y = fixture(); y.board.pins[0].modes = y.board.pins[1].modes = ['input'];
  y.sensors[1].pins[0].mode = 'input';
  assert.equal(reviewCompatibility(y).status, 'consistent');
});

test('strict scalar/count/unit validation at nested levels', () => {
  for (const value of [undefined, null, NaN, Infinity, -1, 0.5, '14', true, {}, 1e20]) {
    const x = fixture(); x.sensors[0].currentMa = value; rejected(x);
  }
  for (const count of [0, -1, 1.5, 3, null, '2']) {const x = fixture(); x.board.pinCount = count; rejected(x);}
  for (const mutate of [x => x.units = 'A', x => x.sensors[0].unit = 'A',
    x => x.board.pins[0].extra = true, x => x.sensors[0].pins[0].mode = 'analog-ish',
    x => x.board.pins[0].modes.push('input'), x => x.sensors = []]) {
    const x = fixture(); mutate(x); rejected(x);
  }
});

test('zero demand is known and acceptable under zero current limits', () => {
  const x = fixture();
  for (const s of x.sensors) {s.currentMa = 0; for (const p of s.pins) p.currentMa = 0;}
  x.board.powerLimitMa = x.board.pinLimitMa = x.board.totalPinLimitMa = 0;
  assert.equal(reviewCompatibility(x).status, 'consistent');
});

test('getters, hooks and caller methods are never invoked', () => {
  let calls = 0;
  for (const mutate of [
    x => Object.defineProperty(x.board, 'voltageMv', {get() {calls++; throw Error('getter');}}),
    x => Object.defineProperty(x.sensors, '0', {get() {calls++; throw Error('array getter');}}),
    x => x.toJSON = () => {calls++; throw Error('hook');},
    x => x.sensors.map = () => {calls++; throw Error('method');},
    x => Object.defineProperty(x.board, 'hidden', {get() {calls++; throw Error('hidden');}}),
  ]) { const x = fixture(); mutate(x); rejected(x); }
  assert.equal(calls, 0);
});

test('sparse, extended and foreign-prototype data rejected', () => {
  for (const mutate of [
    x => delete x.sensors[0], x => x.sensors.extra = 1,
    x => x.sensors[Symbol('extra')] = 1,
    x => Object.setPrototypeOf(x.board, {inherited: 1}),
    x => Object.setPrototypeOf(x.sensors, null),
    x => x.board.pins = new Uint8Array([1, 2]),
    x => x.sensors[0].pins[0] = new Date(),
    x => x.board.self = x.board,
  ]) { const x = fixture(); mutate(x); rejected(x); }
  rejected(null); rejected([]); rejected(new Map());
});
