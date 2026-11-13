import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {reviewCompatibility} from '../pets/arduino/compatibility.mjs';

const fixture = () => JSON.parse(readFileSync(new URL('../pets/arduino/example.json', import.meta.url), 'utf8'));
const rejected = x => assert.notEqual(reviewCompatibility(x).status, 'consistent');

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
  x.board.powerLimitMa = 16; rejected(x);
  x.board.powerLimitMa = 0; assert.ok(reviewCompatibility(x).issues.includes('power-oversubscribed'));
  x.board.powerLimitMa = null; assert.ok(reviewCompatibility(x).issues.includes('unknown-powerLimitMa'));
  delete x.board.powerLimitMa; assert.equal(reviewCompatibility(x).status, 'invalid');
});

test('each mismatch and oversubscription fails closed independently', () => {
  for (const change of [
    x => x.sensors[0].voltageMv++, x => x.sensors[0].ground = false,
    x => x.sensors[0].pins[0].mode = 'output', x => x.sensors[0].pins[0].pin = 'absent',
    x => x.sensors[1].pins[0].pin = 'P0', x => x.board.pinLimitMa = 0,
    x => x.board.totalPinLimitMa = 2, x => x.sensors[0].currentMa = 100,
    x => x.board.pins[1].id = 'P0', x => x.sensors[1].id = 'sensor-a',
  ]) { const x = fixture(); change(x); rejected(x); }
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
