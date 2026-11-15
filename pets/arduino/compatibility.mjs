// Offline synthetic declarations only. No hardware or provider operations.
import {types} from 'node:util';

const invalid = () => { throw new Error('invalid declaration'); };

const boardPin = {id: null, modes: [null]};
const sensorPin = {pin: null, mode: null, currentMa: null};
const shape = {
  board: {voltageMv: null, powerLimitMa: null, pinLimitMa: null,
    totalPinLimitMa: null, pinCount: null, pins: [boardPin]},
  sensors: [{id: null, voltageMv: null, currentMa: null, ground: null,
    pinCount: null, pins: [sensorPin]}],
};

// Copy descriptor values before calculation. Never invoke input accessors,
// proxy traps, iterators, conversion hooks or overridden collection methods.
// Budget logical occurrences, including repeated references, across the request.
function snapshot(value, expected, budget = {values: 4096, properties: 8192}, depth = 0, seen = new Set()) {
  if (--budget.values < 0 || depth > 10 || types.isProxy(value)) invalid();
  if (expected !== null && (value === null || typeof value !== 'object')) invalid();
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') { if (!Number.isFinite(value)) invalid(); return value; }
  if (typeof value !== 'object' || expected === null || seen.has(value)) invalid();
  const array = Array.isArray(value), proto = Object.getPrototypeOf(value);
  if (array !== Array.isArray(expected)) invalid();
  if (array ? proto !== Array.prototype : proto !== Object.prototype && proto !== null) invalid();
  const keys = Reflect.ownKeys(value);
  if ((budget.properties -= keys.length) < 0 || keys.some(k => typeof k !== 'string')) invalid();
  // Check shape before reading any property descriptor or descending into data.
  if (array) {
    const length = Object.getOwnPropertyDescriptor(value, 'length').value;
    if (!Number.isInteger(length) || length > 100 || keys.length !== length + 1) invalid();
    for (let i = 0; i < length; i++) if (!Object.hasOwn(value, String(i))) invalid();
  } else if (keys.length !== Object.keys(expected).length || keys.some(k => !Object.hasOwn(expected, k))) invalid();
  seen.add(value);
  const result = array ? [] : Object.create(null);
  for (const k of keys) {
    if (array && k === 'length') continue;
    const descriptor = Object.getOwnPropertyDescriptor(value, k);
    if (!Object.hasOwn(descriptor, 'value') || !descriptor.enumerable) invalid();
    result[k] = snapshot(descriptor.value, array ? expected[0] : expected[k], budget, depth + 1, seen);
  }
  seen.delete(value);
  return result;
}
function record(x, keys) {
  if (!x || Array.isArray(x) || typeof x !== 'object') invalid();
  if (Object.keys(x).length !== keys.length || keys.some(k => !Object.hasOwn(x, k))) invalid();
}
function number(x, min = 0) {
  if (!Number.isSafeInteger(x) || x < min || x > 1_000_000_000) invalid();
}
function id(x) { if (typeof x !== 'string' || !/^[a-zA-Z0-9-]{1,40}$/.test(x)) invalid(); }
function list(x) { if (!Array.isArray(x) || x.length < 1 || x.length > 100) invalid(); }
function counted(x) { list(x.pins); number(x.pinCount, 1); if (x.pinCount !== x.pins.length) invalid(); }
const modes = new Set(['input', 'output', 'analog-input']);

export function reviewCompatibility(input) {
  const boundary = {
    authorization: false, safetyCertification: false,
    unknowns: ['Declarations are synthetic and unauthenticated.',
      'Actual board revision, component ratings and wiring are unverified.',
      'Transient loads, tolerances, thermal behavior and real device behavior are outside this model.'],
  };
  try {
    const x = snapshot(input, shape);
    record(x, ['board', 'sensors']);
    const b = x.board;
    record(b, ['voltageMv', 'powerLimitMa', 'pinLimitMa', 'totalPinLimitMa', 'pinCount', 'pins']);
    number(b.voltageMv, 1); counted(b);
    const issues = [];
    for (const key of ['powerLimitMa', 'pinLimitMa', 'totalPinLimitMa']) {
      if (b[key] === null) issues.push(`unknown-${key}`); else number(b[key]);
    }
    const pins = new Map();
    for (const p of b.pins) {
      record(p, ['id', 'modes']); id(p.id); list(p.modes);
      if (pins.has(p.id) || new Set(p.modes).size !== p.modes.length) invalid();
      for (const mode of p.modes) if (!modes.has(mode)) invalid();
      pins.set(p.id, p.modes);
    }
    list(x.sensors);
    const allocated = new Set(), sensors = new Set();
    let supplyMa = 0, signalMa = 0;
    for (const s of x.sensors) {
      record(s, ['id', 'voltageMv', 'currentMa', 'ground', 'pinCount', 'pins']);
      id(s.id); number(s.voltageMv, 1); number(s.currentMa); counted(s);
      if (sensors.has(s.id) || typeof s.ground !== 'boolean') invalid();
      sensors.add(s.id);
      if (!s.ground) issues.push(`missing-ground:${s.id}`);
      if (s.voltageMv !== b.voltageMv) issues.push(`voltage-mismatch:${s.id}`);
      supplyMa += s.currentMa;
      for (const p of s.pins) {
        record(p, ['pin', 'mode', 'currentMa']); id(p.pin); number(p.currentMa);
        if (!modes.has(p.mode)) invalid();
        if (allocated.has(p.pin)) issues.push(`duplicate-pin:${p.pin}`);
        allocated.add(p.pin);
        if (!pins.has(p.pin)) issues.push(`unknown-pin:${p.pin}`);
        else if (!pins.get(p.pin).includes(p.mode)) issues.push(`mode-mismatch:${p.pin}`);
        if (b.pinLimitMa !== null && p.currentMa > b.pinLimitMa) issues.push(`pin-oversubscribed:${p.pin}`);
        signalMa += p.currentMa;
      }
    }
    if (b.powerLimitMa !== null && supplyMa + signalMa > b.powerLimitMa) issues.push('power-oversubscribed');
    if (b.totalPinLimitMa !== null && signalMa > b.totalPinLimitMa) issues.push('signal-oversubscribed');
    return {...boundary, status: issues.length ? 'needs-review' : 'consistent', issues, totals: {supplyMa, signalMa}};
  } catch {
    return {...boundary, status: 'invalid', issues: ['malformed-or-unsupported-input'], totals: null};
  }
}
