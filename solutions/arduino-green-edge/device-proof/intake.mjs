import { CHANNELS, METER_SCHEMA, reviewMeterDocument } from '../measurement.mjs';

export const PACKET_SCHEMA = 'green-edge.bridge-energy.v1';
export const BRIDGE_METHOD = 'green_edge.energy_interval';
export const EVIDENCE = 'USER_SUPPLIED_UNVERIFIED';
// Admission bounds, not hardware specifications. The existing reviewer remains
// authoritative for comparison validation and ALL energy arithmetic.
export const LIMITS = Object.freeze({
  packetBytes: 8192, replayBytes: 1048576, packets: 96, freshMs: 30000,
  intervalMs: 3600000, totalMs: 86400000, intervalMWh: 1000000000,
});

export class IntakeError extends Error {
  constructor(code) { super(`Telemetry intake refused: ${code}`); this.name = 'IntakeError'; this.code = code; }
}
export function refuse(code) { throw new IntakeError(code); }

/** Small bounded JSON reader: no arrays, duplicate/escaped-duplicate keys,
 * prototype keys, arbitrary JS objects, getters, coercion or raw error echo.
 * The protocol contains only objects and primitives. Limits apply BEFORE parse.
 */
export function parseBoundedJSON(text, maxBytes = LIMITS.packetBytes) {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1 || maxBytes > LIMITS.replayBytes) refuse('INPUT_SIZE_OR_TYPE');
  if (typeof text !== 'string' || text.length > maxBytes
    || new TextEncoder().encode(text).length > maxBytes) refuse('INPUT_SIZE_OR_TYPE');
  let at = 0, nodes = 0;
  const ws = () => { while (/[\x20\t\r\n]/.test(text[at] ?? '\x00')) at++; };
  const string = () => {
    const token = /^"(?:[^"\\\u0000-\u001f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"/.exec(text.slice(at));
    if (!token) refuse('MALFORMED_JSON');
    at += token[0].length;
    return JSON.parse(token[0]);
  };
  function value(depth) {
    if (++nodes > 128 || depth > 6) refuse('JSON_COMPLEXITY');
    ws();
    if (text[at] === '{') {
      at++; ws();
      const result = {}, keys = new Set();
      if (text[at] === '}') { at++; return result; }
      while (true) {
        const key = string();
        if (keys.has(key)) refuse('DUPLICATE_JSON_KEY');
        if (['__proto__', 'constructor', 'prototype'].includes(key)) refuse('FORBIDDEN_JSON_KEY');
        keys.add(key); ws();
        if (text[at++] !== ':') refuse('MALFORMED_JSON');
        result[key] = value(depth + 1); ws();
        const delimiter = text[at++];
        if (delimiter === '}') return result;
        if (delimiter !== ',') refuse('MALFORMED_JSON');
        ws();
      }
    }
    if (text[at] === '"') return string();
    const token = /^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/.exec(text.slice(at));
    if (!token) refuse('MALFORMED_JSON');
    at += token[0].length;
    const parsed = JSON.parse(token[0]);
    // All protocol numbers are decimal integers. Reject fraction/exponent
    // spellings BEFORE IEEE-754 rounding can turn underflow/fractions into an
    // apparently valid integer (for example 1e-9999 -> 0).
    if (typeof parsed === 'number' && (/[.eE]/.test(token[0])
      || !Number.isSafeInteger(parsed) || Object.is(parsed, -0))) refuse('INTEGER_RANGE');
    return parsed;
  }
  const result = value(1); ws();
  if (at !== text.length) refuse('MALFORMED_JSON');
  return result;
}

export function exact(value, keys) {
  if (value === null || typeof value !== 'object' || Object.getPrototypeOf(value) !== Object.prototype) refuse('EXACT_FIELDS');
  const fields = Reflect.ownKeys(value);
  if (fields.length !== keys.length || fields.some(key => !keys.includes(key))) refuse('EXACT_FIELDS');
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !Object.hasOwn(descriptor, 'value') || !descriptor.enumerable) refuse('EXACT_FIELDS');
  }
}
function integer(value, min, max) {
  if (!Number.isSafeInteger(value) || Object.is(value, -0) || value < min || value > max) refuse('INTEGER_RANGE');
}
function pseudonym(value, prefix) {
  if (typeof value !== 'string' || value.length !== prefix.length + 17
    || !new RegExp(`^${prefix}-[a-f0-9]{16}$`).test(value)) refuse('PSEUDONYM');
}
function clock(value, id) {
  exact(value, ['kind', 'id', 'atMs']);
  if (value.kind !== 'monotonic-ms' || value.id !== id) refuse('TIME_BASE_MISMATCH');
  integer(value.atMs, 0, Number.MAX_SAFE_INTEGER);
}
function freeze(value) {
  if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); }
  return value;
}
const flags = () => ({
  evidence: EVIDENCE, actuationAuthorized: false, physicalExecution: false,
  measuredEnvironmentalBenefit: false, producerAuthenticated: false,
});

/** One trusted caller owns one in-memory stream. No transport or state hydration.
 * append accepts JSON TEXT, never invokes a supplied object's behavior.
 * Host receivedClock must already be mapped to the pinned device time domain.
 */
export function createTelemetryIntake(enrollment) {
  exact(enrollment, ['streamId', 'clockId']);
  pseudonym(enrollment.streamId, 'stream'); pseudonym(enrollment.clockId, 'clock');
  const { streamId, clockId } = enrollment;
  const entries = [];
  let calibration = null;
  function documentFor(packets) {
    return {
      schema: METER_SCHEMA, evidence: EVIDENCE, unit: 'mWh',
      calibration: Object.fromEntries(CHANNELS.map(kind => {
        const row = packets[0].channels[kind];
        return [kind, { meterId: row.meterId, ...row.calibration }];
      })),
      channels: Object.fromEntries(CHANNELS.map(kind => [kind, packets.map(packet => {
        const { startMs, endMs, mWh } = packet.channels[kind];
        return { startMs, endMs, mWh };
      })])),
    };
  }
  function checkedDocument() {
    if (entries.length < 2) refuse('NEED_TWO_INTERVALS');
    return documentFor(entries.map(entry => entry.packet));
  }
  return Object.freeze({
    append(text, receivedClock) {
      clock(receivedClock, clockId);
      const packet = parseBoundedJSON(text);
      exact(packet, ['schema', 'method', 'streamId', 'sequence', 'clock', 'unit', 'channels']);
      if (packet.schema !== PACKET_SCHEMA || packet.method !== BRIDGE_METHOD || packet.unit !== 'mWh') refuse('PROTOCOL');
      if (packet.streamId !== streamId) refuse('STREAM_MISMATCH');
      clock(packet.clock, clockId);
      integer(packet.sequence, 1, Number.MAX_SAFE_INTEGER);
      if (entries.length >= LIMITS.packets) refuse('CAPACITY');
      if (packet.sequence !== entries.length + 1) refuse('SEQUENCE');
      const previous = entries.at(-1);
      if (previous && (packet.clock.atMs <= previous.packet.clock.atMs
        || receivedClock.atMs < previous.receivedClock.atMs)) refuse('CLOCK_ORDER');
      if (packet.clock.atMs > receivedClock.atMs
        || receivedClock.atMs - packet.clock.atMs > LIMITS.freshMs) refuse('STALE_OR_FUTURE');
      exact(packet.channels, CHANNELS);
      const ids = new Set(), nextCalibration = {};
      let start, end;
      for (const kind of CHANNELS) {
        const row = packet.channels[kind];
        exact(row, ['meterId', 'clockId', 'startMs', 'endMs', 'mWh', 'calibration']);
        pseudonym(row.meterId, 'meter');
        if (ids.has(row.meterId)) refuse('METER_REUSE');
        ids.add(row.meterId);
        if (row.clockId !== clockId) refuse('TIME_BASE_MISMATCH');
        integer(row.startMs, 0, Number.MAX_SAFE_INTEGER);
        integer(row.endMs, 1, Number.MAX_SAFE_INTEGER);
        integer(row.mWh, 0, LIMITS.intervalMWh);
        if (row.endMs <= row.startMs || row.endMs - row.startMs > LIMITS.intervalMs) refuse('DURATION');
        if (kind === 'baseline') { start = row.startMs; end = row.endMs; }
        else if (row.startMs !== start || row.endMs !== end) refuse('CHANNEL_ALIGNMENT');
        exact(row.calibration, ['checkedAtMs', 'validUntilMs']);
        const { checkedAtMs, validUntilMs } = row.calibration;
        integer(checkedAtMs, 0, Number.MAX_SAFE_INTEGER);
        integer(validUntilMs, 1, Number.MAX_SAFE_INTEGER);
        if (checkedAtMs >= validUntilMs || row.startMs < checkedAtMs || row.endMs > validUntilMs) refuse('CALIBRATION_WINDOW');
        nextCalibration[kind] = { meterId: row.meterId, checkedAtMs, validUntilMs };
        const pinned = calibration?.[kind];
        if (pinned && (pinned.meterId !== row.meterId || pinned.checkedAtMs !== checkedAtMs
          || pinned.validUntilMs !== validUntilMs)) refuse('METER_OR_CALIBRATION_CHANGED');
      }
      if (end > packet.clock.atMs || receivedClock.atMs - end > LIMITS.freshMs) refuse('STALE_OR_FUTURE');
      if (previous && start !== previous.packet.channels.baseline.endMs) refuse('INTERVAL_GAP_OR_OVERLAP');
      const firstStart = entries[0]?.packet.channels.baseline.startMs ?? start;
      if (end - firstStart > LIMITS.totalMs) refuse('TOTAL_DURATION');
      // Validate the ENTIRE candidate comparison before mutating append-only state.
      // One interval is staged only; the reviewer intentionally requires >=2.
      if (entries.length) {
        try { reviewMeterDocument(documentFor([...entries.map(entry => entry.packet), packet])); }
        catch { refuse('METER_CONTRACT'); }
      }
      const entry = freeze({
        ...flags(), receivedClock: { ...receivedClock }, packet,
      });
      calibration ??= freeze(nextCalibration);
      entries.push(entry);
      return freeze({ ...flags(), sequence: packet.sequence, acceptedPackets: entries.length,
        status: entries.length < 2 ? 'COLLECTING' : 'READY_FOR_UNVERIFIED_REVIEW' });
    },
    snapshot() { return structuredClone(entries); },
    document() {
      const doc = checkedDocument();
      reviewMeterDocument(doc);
      return doc;
    },
    review() {
      return {
        ...reviewMeterDocument(checkedDocument()), ...flags(),
        intake: { schema: PACKET_SCHEMA, streamId, clockId, acceptedPackets: entries.length,
          storage: 'VOLATILE_APPEND_ONLY', calibration: 'DECLARED_NOT_VERIFIED' },
      };
    },
  });
}
