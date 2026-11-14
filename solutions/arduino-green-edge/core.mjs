// Browser + Node, deterministic, transport-free. No physical actions.
export const POLICY = Object.freeze({ maxAgeMs: 30000, debounce: 2, maxGapMs: 15000 });
export function canonical(value) {
  if (value === undefined) return 'undefined';
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
}
// Portable diagnostic fingerprint, deliberately NOT a cryptographic attestation.
export function digest(value) {
  let h = 2166136261;
  for (const c of canonical(value)) h = Math.imul(h ^ c.charCodeAt(0), 16777619) >>> 0;
  return `fnv1a32:${h.toString(16).padStart(8, '0')}`;
}
export function initialState() {
  return { fan: false, light: false, pending: '', count: 0, lastAt: null, lastDigest: null };
}
export function evaluate(sample, state = initialState(), options = {}) {
  const { now = sample?.at, optIn = false, override = 'auto' } = options;
  const inputDigest = digest(sample);
  const base = { at: now, inputDigest, policyDigest: digest(POLICY), mode: 'OFFLINE_DETERMINISTIC', networkRequired: false };
  function hold(reason) {
    return { ...base, decision: 'HOLD', reason, action: null, state: { ...initialState(), lastAt: state.lastAt, lastDigest: state.lastDigest } };
  }
  if (!Number.isSafeInteger(now) || now < 0) return hold('Invalid evaluation clock');
  if (!sample || !Number.isSafeInteger(sample.at) || sample.at < 0 || sample.at > now || now - sample.at > POLICY.maxAgeMs) return hold('Missing, future or stale measurement');
  const ranges = { temperature: [-20, 60], humidity: [0, 100], occupancy: [0, 100], lux: [0, 200000] };
  for (const [key, [min, max]] of Object.entries(ranges)) {
    if (typeof sample[key] !== 'number' || !Number.isFinite(sample[key]) || sample[key] < min || sample[key] > max || (key === 'occupancy' && !Number.isInteger(sample[key]))) return hold(`Malformed or missing ${key}`);
  }
  if (sample.connected !== true) return hold('Sensor disconnected');
  if (!['auto', 'off'].includes(override) || typeof optIn !== 'boolean') return hold('Invalid control input');
  if (state.lastAt !== null && sample.at <= state.lastAt) return hold('Duplicate or out-of-order sample');
  const gap = state.lastAt !== null && sample.at - state.lastAt > POLICY.maxGapMs;
  const prior = gap ? initialState() : state;
  const fan = sample.occupancy > 0 && (prior.fan ? (sample.temperature > 25 || sample.humidity > 65) : sample.temperature >= 27 || sample.humidity >= 70);
  const light = sample.occupancy > 0 && (prior.light ? sample.lux < 400 : sample.lux < 250);
  const target = `${fan}:${light}`;
  const count = prior.pending === target ? prior.count + 1 : 1;
  const next = { ...prior, pending: target, count: Math.min(count, POLICY.debounce), lastAt: sample.at, lastDigest: inputDigest };
  if (override === 'off') return { ...base, decision: 'OVERRIDE', reason: 'Manual off: simulated outputs off', action: optIn ? { fan: false, light: false } : null, state: { ...next, fan: false, light: false, count: 0, pending: '' } };
  if (count < POLICY.debounce) return { ...base, decision: 'HOLD', reason: gap ? 'Watchdog gap: collecting two fresh samples' : 'Debounce: need two consecutive samples', action: null, state: next };
  if (!optIn) return { ...base, decision: 'PROPOSE', reason: 'Consent absent or revoked: outputs OFF; two fresh samples required after opt-in', action: null, proposed: { fan, light }, state: { ...next, fan: false, light: false, pending: '', count: 0 } };
  return { ...base, decision: 'SIMULATE', reason: 'Opted-in local simulation only', action: { fan, light }, state: { ...next, fan, light } };
}
export function createLedger() { return { intervals: [], estimatedBaselineKWh: 0, estimatedScenarioKWh: 0, estimatedAvoidedKWh: 0, devicePower: { measuredKWh: null, watts: null, status: 'UNO Q power unknown; not measured' } }; }
// Account only explicit, non-overlapping simulated intervals. No extrapolation through HOLD.
export function account(ledger, { start, end, baselineWatts, scenarioWatts }) {
  if (![start, end].every(Number.isSafeInteger) || start < 0 || end <= start || end - start > 60000 || ![baselineWatts, scenarioWatts].every(v => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 10000)) throw new Error('Invalid energy interval or watt assumption');
  if (ledger.intervals.some(([a, b]) => start < b && end > a)) throw new Error('Overlapping interval: double-counting refused');
  const hours = (end - start) / 3600000;
  const baseline = baselineWatts * hours / 1000;
  const scenario = scenarioWatts * hours / 1000;
  const estimatedBaselineKWh = ledger.estimatedBaselineKWh + baseline;
  const estimatedScenarioKWh = ledger.estimatedScenarioKWh + scenario;
  return { ...ledger, intervals: [...ledger.intervals, [start, end]], estimatedBaselineKWh, estimatedScenarioKWh, estimatedAvoidedKWh: estimatedBaselineKWh - estimatedScenarioKWh };
}
export function synthetic(at, scenario = 'warm') {
  const presets = { warm: [28, 48, 4, 180], daylight: [24, 45, 4, 650], empty: [23, 42, 0, 600], humid: [24, 75, 3, 320] };
  if (!presets[scenario]) throw new Error('Unknown synthetic scenario');
  const [temperature, humidity, occupancy, lux] = presets[scenario];
  return { at, temperature, humidity, occupancy, lux, connected: true };
}
// Injection seam only: a caller supplies a local transport. No built-in network or firmware.
export async function readBridge(transport) {
  if (!transport || typeof transport.call !== 'function') throw new Error('Injected Bridge-shaped transport required');
  return transport.call('green_edge.sample');
}
