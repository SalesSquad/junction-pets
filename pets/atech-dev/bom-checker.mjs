/** Offline fictional BOM review. No hardware, provider or authorization effects. */
const fail = message => { throw new TypeError(message); };

// Snapshot descriptors before reading values. Never use input iteration methods,
// getters, coercion or serialization hooks. Proxies are outside this data contract.
function snapshot(input) {
  const ancestors = new Set();
  let nodes = 0;
  function visit(value, depth) {
    if (++nodes > 20000 || depth > 20) fail('input exceeds bounded data limits');
    if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
    if (typeof value === 'number') {
      if (!Number.isFinite(value)) fail('nonfinite number');
      return value;
    }
    if (typeof value !== 'object') fail('unsupported data value');
    if (ancestors.has(value)) fail('cyclic data');
    const array = Array.isArray(value);
    const proto = Object.getPrototypeOf(value);
    if (array ? proto !== Array.prototype : proto !== Object.prototype && proto !== null) fail('unsupported prototype');
    ancestors.add(value);
    const descriptors = Object.getOwnPropertyDescriptors(value);
    const keys = Reflect.ownKeys(descriptors);
    const out = array ? [] : Object.create(null);
    let length;
    if (array) {
      length = descriptors.length.value;
      if (length > 1000 || keys.length !== length + 1) fail('invalid array size or properties');
      for (let i = 0; i < length; i++) if (!Object.hasOwn(descriptors, String(i))) fail('sparse array');
    }
    for (const key of keys) {
      const d = descriptors[key];
      if (array && key === 'length') continue;
      if (typeof key !== 'string' || !d.enumerable || !Object.hasOwn(d, 'value')) fail('only enumerable data properties allowed');
      if (array && (!/^(0|[1-9][0-9]*)$/.test(key) || Number(key) >= length)) fail('extra array property');
      out[key] = visit(d.value, depth + 1);
    }
    ancestors.delete(value);
    return out;
  }
  return visit(input, 0);
}

function record(value, allowed, required = allowed) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) fail('expected record');
  for (const key of Object.keys(value)) if (!allowed.includes(key)) fail(`unknown key: ${key}`);
  for (const key of required) if (!Object.hasOwn(value, key)) fail(`required key: ${key}`);
}
function list(value) { if (!Array.isArray(value)) fail('expected array'); return value; }
function integer(value, minimum = 0) {
  if (!Number.isSafeInteger(value) || value < minimum) fail('expected bounded nonnegative integer');
  return value;
}
function safe(value) { if (!Number.isSafeInteger(value)) fail('unsafe arithmetic'); return value; }
function name(value) {
  if (typeof value !== 'string' || !/^[a-z][a-z0-9-]{0,63}$/.test(value)) fail('invalid identifier');
  return value;
}
function unique(values) {
  if (new Set(values).size !== values.length) fail('duplicate identifier');
}
function voltage(v) {
  record(v, ['min', 'max', 'unit']);
  const scale = v.unit === 'V' ? 1000 : v.unit === 'mV' ? 1 : fail('invalid voltage unit');
  const min = safe(integer(v.min) * scale), max = safe(integer(v.max) * scale);
  if (min > max) fail('reversed voltage range');
  return {min, max};
}
function current(v) {
  record(v, ['value', 'unit']);
  const scale = v.unit === 'A' ? 1000 : v.unit === 'mA' ? 1 : fail('invalid current unit');
  return safe(integer(v.value) * scale);
}
function interfaces(values, requirement = false) {
  const key = requirement ? 'interface' : 'name';
  const out = list(values).map(v => {
    record(v, [key, 'pins']);
    return {name: name(v[key]), pins: integer(v.pins)};
  });
  unique(out.map(v => v.name));
  return out;
}
function specification(owner, key, parse, issues, label = key) {
  if (!Object.hasOwn(owner, key)) { issues.push(`missing:${label}`); return null; }
  if (owner[key] === null) { issues.push(`null:${label}`); return null; }
  return parse(owner[key]);
}

export function checkBom(input) {
  const data = snapshot(input);
  record(data, ['board', 'parts']);
  record(data.board, ['voltage', 'current', 'interfaces'], []);
  const issues = [];
  const boardVoltage = specification(data.board, 'voltage', voltage, issues, 'board.voltage');
  const boardCurrent = specification(data.board, 'current', current, issues, 'board.current');
  const boardInterfaces = specification(data.board, 'interfaces', interfaces, issues, 'board.interfaces');
  const parts = list(data.parts).map(p => {
    record(p, ['id', 'quantity', 'rating', 'voltage', 'current', 'requirements'], ['id', 'quantity', 'rating']);
    name(p.id); integer(p.quantity, 1);
    if (p.rating !== 'known' && p.rating !== 'unknown') fail('invalid rating');
    const missing = p.rating === 'unknown' ? ['unknown:rating'] : [];
    const volts = specification(p, 'voltage', voltage, missing);
    const amps = specification(p, 'current', current, missing);
    const needs = specification(p, 'requirements', v => interfaces(v, true), missing);
    return {id: p.id, quantity: p.quantity, rating: p.rating, volts, amps, needs, issues: missing};
  });
  unique(parts.map(p => p.id));
  if (!parts.length) issues.push('missing:parts');
  const conflicts = [];
  const affected = new Set();
  function conflict(code, ids, detail) {
    conflicts.push({code, parts: ids, ...detail});
    for (const id of ids) affected.add(id);
  }
  let total = 0;
  const pins = new Map();
  for (const p of parts) {
    if (p.volts && boardVoltage && (boardVoltage.min < p.volts.min || boardVoltage.max > p.volts.max)) {
      conflict('voltage-range', [p.id], {});
    }
    if (p.amps !== null) total = safe(total + safe(p.amps * p.quantity));
    if (p.needs) for (const need of p.needs) {
      const used = pins.get(need.name) ?? {count: 0, ids: []};
      used.count = safe(used.count + safe(need.pins * p.quantity));
      used.ids.push(p.id);
      pins.set(need.name, used);
    }
  }
  if (boardCurrent !== null && total > boardCurrent) conflict('current-capacity', parts.filter(p => p.amps !== null).map(p => p.id), {requiredMA: total, availableMA: boardCurrent});
  if (boardInterfaces) for (const [key, used] of pins) {
    const available = boardInterfaces.find(v => v.name === key);
    if (!available) conflict('interface-missing', used.ids, {interface: key});
    else if (used.count > available.pins) conflict('pin-capacity', used.ids, {interface: key, requiredPins: used.count, availablePins: available.pins});
  }
  const incomplete = issues.length > 0 || parts.some(p => p.issues.length > 0);
  return {
    status: incomplete ? 'incomplete' : conflicts.length ? 'incompatible' : 'internally-consistent',
    issues, conflicts, totalCurrentMA: incomplete ? null : total,
    parts: parts.map(p => ({id: p.id, rating: p.rating, status: p.issues.length || issues.length ? 'incomplete' : affected.has(p.id) ? 'incompatible' : 'internally-consistent', issues: p.issues}))
  };
}
