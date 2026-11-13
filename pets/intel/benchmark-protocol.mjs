/** Offline arithmetic over fictional declarations, never a hardware benchmark. */
const protocolKeys = ['workloadId', 'inputId', 'outputSpecId', 'runtimeId', 'configId',
  'batchSize', 'warmupIterations', 'repetitions', 'metric', 'unit'];
const identityKeys = protocolKeys.slice(0, 5);
const shape = (value, keys) => value !== null && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const id = value => typeof value === 'string' && value !== 'unknown'
  && value === value.trim() && /^[a-z][a-z0-9-]{0,63}$/.test(value);
const integer = (value, min, max) => Number.isSafeInteger(value) && value >= min && value <= max;

function validRun(run) {
  if (!shape(run, ['id', 'device', 'protocol', 'outputCheck', 'samples']) || !id(run.id)
    || !['cpu', 'gpu'].includes(run.device) || !shape(run.protocol, protocolKeys)
    || !['match', 'mismatch', null].includes(run.outputCheck)) return false;
  const p = run.protocol;
  if (!identityKeys.every(key => p[key] === null || id(p[key]))
    || !(p.batchSize === null || integer(p.batchSize, 1, 1024))
    || !(p.warmupIterations === null || integer(p.warmupIterations, 0, 100000))
    || !(p.repetitions === null || integer(p.repetitions, 1, 64))
    || !['latency', 'throughput', null].includes(p.metric)
    || !['ms', 's', 'items/s', null].includes(p.unit)) return false;
  if (p.metric !== null && p.unit !== null && (p.metric === 'latency'
    ? !['ms', 's'].includes(p.unit) : p.unit !== 'items/s')) return false;
  return run.samples === null || (Array.isArray(run.samples) && run.samples.length <= 64
    && run.samples.every(value => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1e9));
}

export function compareBenchmarkProtocols(jsonText) {
  const boundary = {basis: 'supplied-fictional-declarations', benchmarkExecuted: false,
    hardwareVerified: false, performanceVerified: false, provenanceAuthenticated: false, authorization: false};
  const invalid = () => ({...boundary, status: 'invalid', issues: ['malformed-or-unsupported-plan'], declaredComparison: null});
  if (typeof jsonText !== 'string' || Buffer.byteLength(jsonText, 'utf8') > 65536) return invalid();
  let plan;
  try { plan = JSON.parse(jsonText); } catch { return invalid(); }
  if (!shape(plan, ['schemaVersion', 'kind', 'baseline', 'candidate']) || plan.schemaVersion !== 1
    || plan.kind !== 'fictional-benchmark-plan' || !validRun(plan.baseline) || !validRun(plan.candidate)
    || plan.baseline.id === plan.candidate.id) return invalid();

  const issues = [];
  let incomparable = false;
  for (const name of ['baseline', 'candidate']) {
    const run = plan[name];
    for (const key of protocolKeys) if (run.protocol[key] === null) issues.push(`unknown:${name}.protocol.${key}`);
    if (run.outputCheck === null) issues.push(`unknown:${name}.outputCheck`);
    else if (run.outputCheck === 'mismatch') { issues.push(`output-mismatch:${name}`); incomparable = true; }
    if (run.samples === null) issues.push(`unknown:${name}.samples`);
    else if (run.protocol.repetitions !== null && run.samples.length !== run.protocol.repetitions) issues.push(`sample-count:${name}`);
  }
  for (const key of protocolKeys.filter(key => key !== 'unit')) {
    const a = plan.baseline.protocol[key], b = plan.candidate.protocol[key];
    if (a !== null && b !== null && a !== b) { issues.push(`protocol-mismatch:${key}`); incomparable = true; }
  }
  issues.sort();
  const status = incomparable ? 'incomparable' : issues.length ? 'insufficient-evidence' : 'comparable-declarations';
  let declaredComparison = null;
  if (status === 'comparable-declarations') {
    const mean = run => run.samples.reduce((sum, value) => sum + value, 0) / run.samples.length
      * (run.protocol.unit === 's' ? 1000 : 1);
    const baselineMean = mean(plan.baseline), candidateMean = mean(plan.candidate);
    declaredComparison = {metric: plan.baseline.protocol.metric,
      unit: plan.baseline.protocol.metric === 'latency' ? 'ms' : 'items/s',
      baselineMean, candidateMean, candidateMinusBaseline: candidateMean - baselineMean};
  }
  return {...boundary, status, issues, declaredComparison};
}
