// Local-only three-channel energy evidence review. Input metadata is self-reported,
// never a physical-meter attestation, an energy-saving claim or an actuation grant.
export const METER_SCHEMA = 'green-edge.meter-review.v1';
export const CHANNELS = Object.freeze(['baseline', 'scenario', 'device']);
export const MAX_INPUT_BYTES = 131072;
const MAX_INTERVALS = 96;
const MAX_MWH_PER_INTERVAL = 1000000000;
const MAX_INTERVAL_MS = 3600000;
const MAX_TOTAL_MS = 86400000;

function fail(message) { throw new Error(`Meter review refused: ${message}`); }
function plain(value) { return value !== null && typeof value === 'object' && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype; }
function exact(value, keys, where) {
  if (!plain(value) || Object.keys(value).sort().join('|') !== [...keys].sort().join('|')) fail(`invalid ${where} fields`);
}
function safeInt(value, min, max, name) {
  if (!Number.isSafeInteger(value) || value < min || value > max) fail(`invalid ${name}`);
}
function meterName(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$/.test(value)) fail('invalid pseudonymous meter id');
}

export function reviewMeterDocument(doc) {
  exact(doc, ['schema', 'evidence', 'unit', 'calibration', 'channels'], 'document');
  if (doc.schema !== METER_SCHEMA) fail('unsupported schema');
  if (!['SYNTHETIC', 'USER_SUPPLIED_UNVERIFIED'].includes(doc.evidence)) fail('unsupported evidence type');
  if (doc.unit !== 'mWh') fail('unit must be integer milli-watt-hours (mWh)');
  exact(doc.calibration, CHANNELS, 'calibration');
  exact(doc.channels, CHANNELS, 'channels');
  const totals = { baseline: 0, scenario: 0, device: 0 };
  const comparison = [];
  let firstStart = null;
  let previousEnd = null;
  const meterIds = new Set();
  for (const kind of CHANNELS) {
    const meta = doc.calibration[kind];
    exact(meta, ['meterId', 'checkedAtMs', 'validUntilMs'], `${kind} calibration`);
    meterName(meta.meterId);
    if (meterIds.has(meta.meterId)) fail('duplicate meter id across measurement channels');
    meterIds.add(meta.meterId);
    safeInt(meta.checkedAtMs, 0, Number.MAX_SAFE_INTEGER, `${kind} calibration check time`);
    safeInt(meta.validUntilMs, 0, Number.MAX_SAFE_INTEGER, `${kind} calibration expiry`);
    if (meta.validUntilMs <= meta.checkedAtMs) fail(`${kind} calibration is expired`);
    const intervals = doc.channels[kind];
    if (!Array.isArray(intervals) || intervals.length < 2 || intervals.length > MAX_INTERVALS) fail(`${kind} needs 2–96 intervals`);
    let lastEnd = null;
    for (let i = 0; i < intervals.length; i++) {
      const row = intervals[i];
      exact(row, ['startMs', 'endMs', 'mWh'], `${kind} interval ${i}`);
      safeInt(row.startMs, 0, Number.MAX_SAFE_INTEGER, `${kind} start`);
      safeInt(row.endMs, 1, Number.MAX_SAFE_INTEGER, `${kind} end`);
      safeInt(row.mWh, 0, MAX_MWH_PER_INTERVAL, `${kind} energy`);
      if (row.endMs <= row.startMs || row.endMs - row.startMs > MAX_INTERVAL_MS) fail(`${kind} invalid duration`);
      if (lastEnd !== null && row.startMs !== lastEnd) fail(`${kind} has gap, overlap or unsorted interval`);
      if (row.startMs < meta.checkedAtMs || row.endMs > meta.validUntilMs) fail(`${kind} outside self-reported calibration window`);
      if (kind === 'baseline') comparison.push([row.startMs, row.endMs]);
      else if (!comparison[i] || row.startMs !== comparison[i][0] || row.endMs !== comparison[i][1]) fail(`${kind} does not match baseline comparison window`);
      const next = totals[kind] + row.mWh;
      if (!Number.isSafeInteger(next)) fail(`${kind} energy overflow`);
      totals[kind] = next;
      lastEnd = row.endMs;
    }
    if (kind === 'baseline') {
      firstStart = intervals[0].startMs;
      previousEnd = lastEnd;
      if (previousEnd - firstStart > MAX_TOTAL_MS) fail('comparison window exceeds one day');
    } else if (intervals.length !== comparison.length || intervals[0].startMs !== firstStart || lastEnd !== previousEnd) {
      fail(`${kind} coverage does not match baseline`);
    }
  }
  const netMWh = totals.baseline - totals.scenario - totals.device;
  if (!Number.isSafeInteger(netMWh)) fail('net energy overflow');
  return {
    schema: METER_SCHEMA, evidence: doc.evidence, status: 'UNVERIFIED_COMPARISON',
    actuationAuthorized: false, measuredEnvironmentalBenefit: false,
    windowStartMs: firstStart, windowEndMs: previousEnd,
    intervalCount: comparison.length, coverage: 'COMPLETE_SELF_REPORTED',
    totalsMWh: totals, netDifferenceMWh: netMWh, netDifferenceKWh: netMWh / 1000000,
    caveat: doc.evidence === 'SYNTHETIC'
      ? 'Synthetic fixture only. No physical device or measured saving.'
      : 'User-supplied values and calibration declarations are unverified. Not a causal saving or certified measurement.'
  };
}

export function parseMeterDocument(text) {
  if (typeof text !== 'string' || new TextEncoder().encode(text).length > MAX_INPUT_BYTES) fail('input exceeds 128 KiB or is not text');
  let doc;
  try { doc = JSON.parse(text); } catch { fail('malformed JSON'); }
  return reviewMeterDocument(doc);
}

export function syntheticMeterDocument(variant = 'positive') {
  if (!['positive', 'negative'].includes(variant)) fail('unknown synthetic scenario');
  const times = [[0, 10000], [10000, 20000], [20000, 30000]];
  const values = variant === 'positive'
    ? { baseline: [170, 170, 170], scenario: [90, 90, 90], device: [10, 10, 10] }
    : { baseline: [100, 100, 100], scenario: [125, 125, 125], device: [20, 20, 20] };
  return {
    schema: METER_SCHEMA, evidence: 'SYNTHETIC', unit: 'mWh',
    calibration: Object.fromEntries(CHANNELS.map(kind => [kind, { meterId: `fixture-${kind}`, checkedAtMs: 0, validUntilMs: 30000 }])),
    channels: Object.fromEntries(CHANNELS.map(kind => [kind, times.map(([startMs, endMs], i) => ({ startMs, endMs, mWh: values[kind][i] }))]))
  };
}
