import {Buffer} from 'node:buffer';

// Pure synthetic comparison; this never fetches a catalog or executes a model.
const MAX_BYTES = 32768;
const PROTOCOL_KEYS = ['taskSet', 'runtime', 'precision', 'concurrency', 'sampleCount'];
const METRICS = [
  {key: 'qualityPercent', requirement: 'minQualityPercent', max: 100, minimum: true},
  {key: 'p95LatencyMs', requirement: 'maxP95LatencyMs', max: 1_000_000_000, minimum: false},
  {key: 'peakMemoryMiB', requirement: 'maxPeakMemoryMiB', max: 1_000_000_000, minimum: false},
];
const BOUNDARY = {
  rankingScope: 'eligible-supplied-protocol-only', factsVerified: false,
  providerRequestExecuted: false, liveApiSuccess: false, authorization: false,
  throughputTokensPerSecond: null,
};
const fail = () => {throw new Error('malformed-or-unsupported-comparison');};

function record(value, required, optional = []) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail();
  if (required.some(key => !Object.hasOwn(value, key))) fail();
  if (Object.keys(value).some(key => !required.includes(key) && !optional.includes(key))) fail();
}
function label(value) {
  if (typeof value !== 'string' || value.length > 80 || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value)) fail();
}
function number(value, max) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > max) fail();
}
function protocol(value) {
  record(value, PROTOCOL_KEYS);
  for (const key of ['taskSet', 'runtime', 'precision']) {
    label(value[key]);
    if (value[key] === 'unknown') fail();
  }
  for (const [key, max] of [['concurrency', 1000], ['sampleCount', 1_000_000]]) {
    number(value[key], max);
    if (!Number.isSafeInteger(value[key]) || value[key] < 1) fail();
  }
}

function parse(text) {
  if (typeof text !== 'string' || text.length === 0 || text.length > MAX_BYTES || Buffer.byteLength(text, 'utf8') > MAX_BYTES) fail();
  const value = JSON.parse(text);
  record(value, ['schemaVersion', 'kind', 'protocol', 'requirements', 'candidates']);
  if (value.schemaVersion !== 1 || value.kind !== 'fictional-open-weight-comparison') fail();
  protocol(value.protocol);
  record(value.requirements, METRICS.map(metric => metric.requirement));
  for (const metric of METRICS) number(value.requirements[metric.requirement], metric.max);
  if (!Array.isArray(value.candidates) || value.candidates.length < 1 || value.candidates.length > 20) fail();
  const ids = new Set();
  for (const candidate of value.candidates) {
    record(candidate, ['id', 'protocol', 'metrics']);
    label(candidate.id);
    if (!candidate.id.startsWith('fictional-') || candidate.id === 'fictional-' || ids.has(candidate.id)) fail();
    ids.add(candidate.id);
    protocol(candidate.protocol);
    record(candidate.metrics, [], METRICS.map(metric => metric.key));
    for (const metric of METRICS) {
      const supplied = candidate.metrics[metric.key];
      if (Object.hasOwn(candidate.metrics, metric.key) && supplied !== null && supplied !== 'unknown') number(supplied, metric.max);
    }
  }
  return value;
}

function metricCheck(metrics, spec, requirements) {
  if (!Object.hasOwn(metrics, spec.key)) return {status: 'unknown', value: null, reason: 'missing'};
  const value = metrics[spec.key];
  if (value === null || value === 'unknown') return {status: 'unknown', value: null, reason: value === null ? 'null' : 'declared-unknown'};
  const met = spec.minimum ? value >= requirements[spec.requirement] : value <= requirements[spec.requirement];
  return {status: met ? 'met' : 'not-met', value, reason: null};
}

function compareMetrics(a, b) {
  return b.checks.qualityPercent.value - a.checks.qualityPercent.value ||
    a.checks.p95LatencyMs.value - b.checks.p95LatencyMs.value ||
    a.checks.peakMemoryMiB.value - b.checks.peakMemoryMiB.value;
}

export function compareModelCandidates(text) {
  let input;
  try {input = parse(text);} catch {
    return {...BOUNDARY, status: 'invalid', candidates: [], ranking: [], issues: ['malformed-or-unsupported-comparison']};
  }
  const candidates = input.candidates.map(candidate => {
    const protocolDifferences = PROTOCOL_KEYS.filter(key => input.protocol[key] !== candidate.protocol[key]);
    if (protocolDifferences.length) return {id: candidate.id, status: 'incomparable', rank: null, protocolDifferences, checks: null};
    const checks = Object.fromEntries(METRICS.map(spec => [spec.key, metricCheck(candidate.metrics, spec, input.requirements)]));
    const states = Object.values(checks).map(check => check.status);
    const status = states.includes('not-met') ? 'ineligible' : states.includes('unknown') ? 'insufficient-evidence' : 'eligible';
    return {id: candidate.id, status, rank: null, protocolDifferences, checks};
  });
  const eligible = candidates.filter(candidate => candidate.status === 'eligible');
  eligible.sort((a, b) => compareMetrics(a, b) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  for (let index = 0; index < eligible.length; index++) {
    eligible[index].rank = index > 0 && compareMetrics(eligible[index - 1], eligible[index]) === 0 ? eligible[index - 1].rank : index + 1;
  }
  return {...BOUNDARY, status: 'compared', candidates, ranking: eligible.map(({id, rank}) => ({id, rank})), issues: []};
}
