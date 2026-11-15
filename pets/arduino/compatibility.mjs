// Offline synthetic declarations only. No hardware or provider operations.
import {types} from 'node:util';

const boardPin = {id: null, modes: [null]};
const sensorPin = {pin: null, mode: null, currentMa: null};
const boardFields = {powerLimitMa: null, pinLimitMa: null,
  totalPinLimitMa: null, pinCount: null, pins: [boardPin]};
const sensorFields = {id: null, currentMa: null, ground: null,
  pinCount: null, pins: [sensorPin]};
const legacyShape = {
  board: {voltageMv: null, ...boardFields},
  sensors: [{voltageMv: null, ...sensorFields}],
};
const splitShape = {
  schemaVersion: null,
  board: {supplyVoltageMv: null, logicVoltageMv: null, ...boardFields},
  sensors: [{supplyVoltageMv: null, logicVoltageMv: null, ...sensorFields}],
};

// Diagnostics never stringify, inspect or return caller-owned objects.
function safeActual(value) {
  if (value === null || typeof value === 'boolean') return value;
  if (typeof value === 'string') return value.length > 80 ? value.slice(0, 80) + '…' : value;
  if (typeof value === 'number') return Number.isFinite(value) ? value : '[nonfinite]';
  return '[unavailable]';
}
class InvalidDeclaration extends Error {
  constructor(code, path, actual, expected, correction) {
    super('invalid declaration');
    this.diagnostic = {code, path, actual: safeActual(actual), expected, correction};
  }
}
function invalid(code, path, actual, expected, correction) {
  throw new InvalidDeclaration(code, path, actual, expected, correction);
}
const childPath = (path, key, array = false) => array ? `${path}[${key}]` : path === '$' ? key : `${path}.${key}`;

function plainObject(value, path) {
  if (types.isProxy(value)) invalid('unsupported-proxy', path, '[unavailable]', 'plain data', 'Replace the proxy with plain JSON-like data.');
  if (value === null || typeof value !== 'object') invalid('unsupported-value', path, value, 'plain object or array', 'Supply the documented data structure.');
  const array = Array.isArray(value), proto = Object.getPrototypeOf(value);
  if (array ? proto !== Array.prototype : proto !== Object.prototype && proto !== null) {
    invalid('unsupported-prototype', path, '[unavailable]', 'ordinary array or plain record', 'Replace custom instances with plain JSON-like data.');
  }
  return array;
}
function recordKeys(keys, expected, path) {
  if (keys.some(k => typeof k !== 'string')) invalid('unknown-field', path, '[unavailable]', 'documented string keys only', 'Remove symbol and undocumented keys.');
  const names = Object.keys(expected);
  // Reject unknown keys before descriptors or child values are inspected.
  const unknown = keys.find(k => !Object.hasOwn(expected, k));
  if (unknown !== undefined) invalid('unknown-field', childPath(path, safeActual(unknown)), '[unavailable]', 'only documented keys', 'Remove undocumented fields; do not mix voltage schemas.');
  for (const key of names) if (!keys.includes(key)) {
    invalid('missing-field', childPath(path, key), '[missing]', 'required field', 'Supply this documented field explicitly.');
  }
}
function selectShape(input) {
  if (plainObject(input, '$')) invalid('unsupported-value', '$', '[unavailable]', 'plain root record', 'Supply a board and sensor record.');
  const keys = Reflect.ownKeys(input);
  // Bound the root before considering the schema marker or other descriptors.
  if (keys.length > 3 || keys.some(k => typeof k !== 'string')) {
    invalid('unknown-field', '$', '[unavailable]', 'board, sensors, optional schemaVersion', 'Remove undocumented root fields.');
  }
  const split = keys.includes('schemaVersion');
  const expected = split ? splitShape : legacyShape;
  recordKeys(keys, expected, '$');
  if (split) {
    const descriptor = Object.getOwnPropertyDescriptor(input, 'schemaVersion');
    if (!Object.hasOwn(descriptor, 'value') || !descriptor.enumerable) {
      invalid('unsupported-value', 'schemaVersion', '[unavailable]', 'enumerable data value 2', 'Supply schemaVersion as a plain data property.');
    }
    if (descriptor.value !== 2) invalid('unsupported-schema', 'schemaVersion', descriptor.value, 2, 'Use schemaVersion 2 for split supply and logic voltages.');
  }
  return expected;
}

// Copy only descriptor values. Never invoke input accessors, proxy traps,
// iterators, conversion hooks or overridden collection methods. Logical
// occurrences, including repeated references, share one request budget.
function snapshot(value, expected, path = '$', budget = {values: 4096, properties: 8192}, depth = 0, seen = new Set()) {
  if (--budget.values < 0 || depth > 10) invalid('validation-budget-exceeded', path, '[unavailable]', 'bounded declaration', 'Reduce the number or nesting of declared items.');
  if (types.isProxy(value)) invalid('unsupported-proxy', path, '[unavailable]', 'plain data', 'Replace the proxy with plain JSON-like data.');
  if (expected !== null && (value === null || typeof value !== 'object')) {
    invalid('unsupported-value', path, value, 'documented record or array', 'Supply this field in its documented structural form.');
  }
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) invalid('invalid-number', path, value, 'finite integer', 'Use an integer in the documented units.');
    return value;
  }
  if (typeof value !== 'object' || expected === null || seen.has(value)) {
    invalid('unsupported-value', path, '[unavailable]', 'acyclic plain JSON-like data', 'Replace functions, cycles and object-valued scalars with documented data.');
  }
  const array = plainObject(value, path);
  if (array !== Array.isArray(expected)) invalid('unsupported-value', path, '[unavailable]', Array.isArray(expected) ? 'array' : 'record', 'Use the documented structure for this field.');
  const keys = Reflect.ownKeys(value);
  if ((budget.properties -= keys.length) < 0) invalid('validation-budget-exceeded', path, '[unavailable]', 'at most 8192 property visits', 'Reduce the number of declared items.');
  if (array) {
    const length = Object.getOwnPropertyDescriptor(value, 'length').value;
    if (!Number.isInteger(length) || length > 100 || keys.length !== length + 1 || keys.some(k => typeof k !== 'string')) {
      invalid('invalid-array', path, '[unavailable]', 'dense ordinary array of at most 100 items', 'Remove holes, extra properties and unsupported items.');
    }
    for (let i = 0; i < length; i++) if (!Object.hasOwn(value, String(i))) {
      invalid('invalid-array', childPath(path, i, true), '[missing]', 'dense array entry', 'Supply every indexed entry without extra properties.');
    }
  } else recordKeys(keys, expected, path);
  seen.add(value);
  const result = array ? [] : Object.create(null);
  for (const key of keys) {
    if (array && key === 'length') continue;
    const nextPath = childPath(path, key, array);
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!Object.hasOwn(descriptor, 'value') || !descriptor.enumerable) {
      invalid('unsupported-value', nextPath, '[unavailable]', 'enumerable data property', 'Replace accessors and hidden properties with plain data.');
    }
    result[key] = snapshot(descriptor.value, array ? expected[0] : expected[key], nextPath, budget, depth + 1, seen);
  }
  seen.delete(value);
  return result;
}
function number(value, path, min = 0) {
  if (!Number.isSafeInteger(value) || value < min || value > 1_000_000_000) {
    invalid('invalid-number', path, value, `integer ${min}..1000000000 in declared units`, 'Supply a finite integer in millivolts or milliamps as documented.');
  }
}
function id(value, path) {
  if (typeof value !== 'string' || !/^[a-zA-Z0-9-]{1,40}$/.test(value)) invalid('invalid-id', path, value, '1–40 ASCII letters, digits or hyphens', 'Supply a bounded identifier using the allowed characters.');
}
function list(value, path) {
  if (!Array.isArray(value) || value.length < 1 || value.length > 100) invalid('invalid-array', path, '[unavailable]', '1–100 entries', 'Supply a nonempty array within the declared item limit.');
}
function counted(value, path) {
  list(value.pins, `${path}.pins`);
  number(value.pinCount, `${path}.pinCount`, 1);
  if (value.pinCount !== value.pins.length) invalid('invalid-count', `${path}.pinCount`, value.pinCount, value.pins.length, 'Make pinCount equal the supplied pin array length.');
}
const modes = new Set(['input', 'output', 'analog-input']);
function mode(value, path) {
  if (!modes.has(value)) invalid('invalid-mode', path, value, 'input, output or analog-input', 'Declare one supported board-perspective pin mode.');
}
const budgetEntry = (demandMa, limitMa) => ({demandMa, limitMa, headroomMa: limitMa === null ? null : limitMa - demandMa});

export function reviewCompatibility(input) {
  const boundary = {
    authorization: false, safetyCertification: false,
    unknowns: ['Declarations are synthetic and unauthenticated.',
      'Actual board revision, component ratings and wiring are unverified.',
      'Transient loads, tolerances, thermal behavior and real device behavior are outside this model.'],
  };
  try {
    const selected = selectShape(input);
    const x = snapshot(input, selected);
    const split = selected === splitShape;
    const inputSchema = split ? 'split-voltage-v2' : 'legacy-single-voltage';
    const voltageKeys = split ? ['supplyVoltageMv', 'logicVoltageMv'] : ['voltageMv'];
    const supplyKey = voltageKeys[0];
    const b = x.board;
    for (const key of voltageKeys) number(b[key], `board.${key}`, 1);
    counted(b, 'board');
    const issues = [], diagnostics = [];
    const issue = (code, path, actual, expected, correction) => {
      issues.push(code);
      diagnostics.push({code, path, actual: safeActual(actual), expected, correction});
    };
    for (const key of ['powerLimitMa', 'pinLimitMa', 'totalPinLimitMa']) {
      if (b[key] === null) issue(`unknown-${key}`, `board.${key}`, null, 'known current limit in mA', 'Supply a known declared limit; unknown is not zero.');
      else number(b[key], `board.${key}`);
    }
    const pins = new Map();
    for (let i = 0; i < b.pins.length; i++) {
      const p = b.pins[i], path = `board.pins[${i}]`;
      id(p.id, `${path}.id`); list(p.modes, `${path}.modes`);
      if (pins.has(p.id)) invalid('duplicate-id', `${path}.id`, p.id, 'unique board pin ID', 'Give every declared board pin a unique ID.');
      if (new Set(p.modes).size !== p.modes.length) invalid('invalid-mode', `${path}.modes`, '[unavailable]', 'distinct modes', 'Remove repeated modes.');
      for (let j = 0; j < p.modes.length; j++) mode(p.modes[j], `${path}.modes[${j}]`);
      pins.set(p.id, p.modes);
    }
    list(x.sensors, 'sensors');
    const allocated = new Set(), sensors = new Set(), pinDemand = new Map();
    let supplyMa = 0, signalMa = 0;
    for (let i = 0; i < x.sensors.length; i++) {
      const s = x.sensors[i], path = `sensors[${i}]`;
      id(s.id, `${path}.id`);
      for (const key of voltageKeys) number(s[key], `${path}.${key}`, 1);
      number(s.currentMa, `${path}.currentMa`); counted(s, path);
      if (sensors.has(s.id)) invalid('duplicate-id', `${path}.id`, s.id, 'unique sensor ID', 'Give every sensor a unique ID.');
      if (typeof s.ground !== 'boolean') invalid('invalid-boolean', `${path}.ground`, s.ground, 'boolean', 'Declare common ground as true or false.');
      sensors.add(s.id);
      if (!s.ground) issue(`missing-ground:${s.id}`, `${path}.ground`, false, true, 'Review the missing declared common ground against the fictional design constraints.');
      if (s[supplyKey] !== b[supplyKey]) issue(`voltage-mismatch:${s.id}`, `${path}.${supplyKey}`, s[supplyKey], b[supplyKey], 'Review the declared supply-voltage mismatch against the fictional design constraints.');
      if (split && s.logicVoltageMv !== b.logicVoltageMv) issue(`logic-voltage-mismatch:${s.id}`, `${path}.logicVoltageMv`, s.logicVoltageMv, b.logicVoltageMv, 'Review the declared signal-voltage mismatch separately from supply voltage.');
      supplyMa += s.currentMa;
      for (let j = 0; j < s.pins.length; j++) {
        const p = s.pins[j], pinPath = `${path}.pins[${j}]`;
        id(p.pin, `${pinPath}.pin`); number(p.currentMa, `${pinPath}.currentMa`); mode(p.mode, `${pinPath}.mode`);
        if (allocated.has(p.pin)) issue(`duplicate-pin:${p.pin}`, `${pinPath}.pin`, p.pin, 'one allocation per board pin', 'Review the repeated allocation; shared buses are outside this fictional model.');
        allocated.add(p.pin);
        if (!pins.has(p.pin)) issue(`unknown-pin:${p.pin}`, `${pinPath}.pin`, p.pin, 'a declared board pin ID', 'Review this reference against the declared board pin list; do not invent a real pinout.');
        else if (!pins.get(p.pin).includes(p.mode)) issue(`mode-mismatch:${p.pin}`, `${pinPath}.mode`, p.mode, pins.get(p.pin).join(', '), 'Review the requested mode against those declared for this fictional board pin.');
        if (b.pinLimitMa !== null && p.currentMa > b.pinLimitMa) issue(`pin-oversubscribed:${p.pin}`, `${pinPath}.currentMa`, p.currentMa, b.pinLimitMa, 'Review the declared signal demand and limit against the fictional design constraints.');
        signalMa += p.currentMa;
        pinDemand.set(p.pin, (pinDemand.get(p.pin) ?? 0) + p.currentMa);
      }
    }
    if (b.powerLimitMa !== null && supplyMa + signalMa > b.powerLimitMa) issue('power-oversubscribed', 'board.powerLimitMa', b.powerLimitMa, `at least ${supplyMa + signalMa} mA for declared demand`, 'Review total declared current demand and its limit against the fictional design constraints.');
    if (b.totalPinLimitMa !== null && signalMa > b.totalPinLimitMa) issue('signal-oversubscribed', 'board.totalPinLimitMa', b.totalPinLimitMa, `at least ${signalMa} mA for declared demand`, 'Review aggregate declared signal demand and its limit against the fictional design constraints.');
    const budgets = {
      total: budgetEntry(supplyMa + signalMa, b.powerLimitMa),
      signal: budgetEntry(signalMa, b.totalPinLimitMa),
      pins: [...pinDemand].map(([pin, demandMa]) => ({pin, ...budgetEntry(demandMa, b.pinLimitMa)})),
    };
    return {...boundary, inputSchema, status: issues.length ? 'needs-review' : 'consistent', issues,
      diagnostics, totals: {supplyMa, signalMa}, budgets};
  } catch (error) {
    const diagnostic = error instanceof InvalidDeclaration ? error.diagnostic : {
      code: 'malformed-or-unsupported-input', path: '$', actual: '[unavailable]',
      expected: 'documented plain JSON-like declaration', correction: 'Supply data matching one supported input schema.',
    };
    return {...boundary, inputSchema: null, status: 'invalid', issues: ['malformed-or-unsupported-input'],
      diagnostics: [diagnostic], totals: null, budgets: null};
  }
}
