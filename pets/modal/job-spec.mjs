// Pure fictional-plan consistency checks. No provider, clock, file or execution access.
const ID = /^[a-z0-9][a-z0-9._-]{0,63}$/;
const RESOURCES = {timeoutSeconds: [1, 86400], cpuUnits: [1, 256], memoryMiB: [1, 65536], gpuUnits: [0, 16], parallelism: [1, 64]};

function record(value, keys, field) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)
    || Object.keys(value).length !== keys.length || keys.some(key => !Object.hasOwn(value, key))) {
    throw new TypeError(`${field} must contain exactly: ${keys.join(', ')}`);
  }
}

function integer(value, min, max, field, nullable = false) {
  if (nullable && value === null) return;
  if (!Number.isSafeInteger(value) || Object.is(value, -0) || value < min || value > max) {
    throw new TypeError(`${field} must be an integer from ${min} to ${max}${nullable ? ' or null' : ''}`);
  }
}

export function reviewJobSpec(jsonText) {
  if (typeof jsonText !== 'string' || jsonText.length > 16384 || new TextEncoder().encode(jsonText).length > 16384) {
    throw new TypeError('job spec must be primitive JSON text, at most 16384 UTF-8 bytes');
  }
  let spec;
  try { spec = JSON.parse(jsonText); } catch { throw new TypeError('job spec must be valid JSON'); }
  record(spec, ['schemaVersion', 'scenario', 'jobId', 'items', 'retry', 'resources', 'ceilings', 'budget'], 'job spec');
  if (spec.schemaVersion !== 1 || spec.scenario !== 'fictional' || typeof spec.jobId !== 'string' || !ID.test(spec.jobId)) {
    throw new TypeError('schemaVersion=1, scenario=fictional and a bounded jobId are required');
  }
  if (!Array.isArray(spec.items) || spec.items.length < 1 || spec.items.length > 64) {
    throw new TypeError('items must contain 1–64 entries');
  }
  const seen = new Set();
  for (const item of spec.items) {
    record(item, ['id', 'inputSha256'], 'item');
    if (typeof item.id !== 'string' || !ID.test(item.id) || seen.has(item.id)) throw new TypeError('item IDs must be bounded and unique');
    if (typeof item.inputSha256 !== 'string' || !/^[a-f0-9]{64}$/.test(item.inputSha256)) throw new TypeError('inputSha256 must be 64 lowercase hex characters');
    seen.add(item.id);
  }
  record(spec.retry, ['maxRetries', 'maxAttempts', 'keyPolicy'], 'retry');
  integer(spec.retry.maxRetries, 0, 1000, 'retry.maxRetries');
  integer(spec.retry.maxAttempts, 1, 1001, 'retry.maxAttempts');
  if (![null, 'stable-per-item', 'per-attempt'].includes(spec.retry.keyPolicy)) throw new TypeError('invalid retry.keyPolicy');
  for (const group of ['resources', 'ceilings']) {
    record(spec[group], Object.keys(RESOURCES), group);
    for (const [name, [min, max]] of Object.entries(RESOURCES)) integer(spec[group][name], min, max, `${group}.${name}`, group === 'ceilings');
  }
  record(spec.budget, ['unit', 'creditsPerAttempt', 'maxCredits'], 'budget');
  if (spec.budget.unit !== 'fictional-credit') throw new TypeError('only fictional-credit accounting is supported');
  integer(spec.budget.creditsPerAttempt, 0, 1000000, 'budget.creditsPerAttempt', true);
  integer(spec.budget.maxCredits, 0, 1000000000, 'budget.maxCredits', true);

  const findings = [];
  const flag = (code, field) => findings.push({code, field});
  if (spec.retry.maxRetries > 8 || spec.retry.maxAttempts > 9) flag('retry-ceiling-exceeded', 'retry');
  if (spec.retry.maxAttempts !== spec.retry.maxRetries + 1) flag('attempt-count-mismatch', 'retry.maxAttempts');
  if (spec.retry.keyPolicy !== 'stable-per-item') flag(spec.retry.keyPolicy === null ? 'unknown-retry-key-policy' : 'unstable-retry-key', 'retry.keyPolicy');
  for (const name of Object.keys(RESOURCES)) {
    if (spec.ceilings[name] === null) flag('unknown-capacity', `ceilings.${name}`);
    else if (spec.resources[name] > spec.ceilings[name]) flag('resource-ceiling-exceeded', `resources.${name}`);
  }
  const attemptsPerItem = Math.max(spec.retry.maxRetries + 1, spec.retry.maxAttempts);
  const totalAttempts = spec.items.length * attemptsPerItem;
  const fictionalCredits = spec.budget.creditsPerAttempt === null ? null : totalAttempts * spec.budget.creditsPerAttempt;
  if (fictionalCredits === null) flag('unknown-attempt-cost', 'budget.creditsPerAttempt');
  if (spec.budget.maxCredits === null) flag('unknown-budget', 'budget.maxCredits');
  else if (fictionalCredits !== null && fictionalCredits > spec.budget.maxCredits) flag('fictional-budget-exceeded', 'budget.maxCredits');
  return {
    schemaVersion: 1, kind: 'fictional-job-spec-review', jobId: spec.jobId,
    verdict: findings.length ? 'needs-review' : 'within-declared-bounds', findings,
    bounds: {items: spec.items.length, attemptsPerItem, totalAttempts, aggregateAttemptSeconds: totalAttempts * spec.resources.timeoutSeconds, fictionalCredits},
    identities: spec.items.map(item => ({itemId: item.id, key: JSON.stringify(['junction.modal.job.v1', spec.jobId, item.id, item.inputSha256])}))
      .sort((a, b) => a.itemId < b.itemId ? -1 : a.itemId > b.itemId ? 1 : 0),
    executionVerified: false, providerConnected: false, spendAuthorized: false,
  };
}
