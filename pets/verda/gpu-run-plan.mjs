// Invented, bounded declarations only. No provider access, verified credit or execution authority.
const ID = /^fictional-[a-z0-9]+(?:-[a-z0-9]+)*$/;
const RESOURCE_MAX = {gpuCount: 64, cpuCount: 256, memoryGiB: 4096};
function requireValue(ok, message) { if (!ok) throw new TypeError(message); }
function fields(value, keys, name) {
  requireValue(value !== null && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key)),
  `${name} fields must be exactly ${keys.join(', ')}`);
}
function integer(value, min, max, name) {
  requireValue(value === null || Number.isSafeInteger(value) && !Object.is(value, -0) && value >= min && value <= max,
    `invalid ${name}`);
}
function id(value, name, nullable = false) {
  requireValue(nullable && value === null || typeof value === 'string' && value.length <= 64 && ID.test(value),
    `invalid fictional ${name}`);
}

export function reviewGpuRunPlan(jsonText) {
  requireValue(typeof jsonText === 'string' && jsonText.length <= 12288 && new TextEncoder().encode(jsonText).length <= 12288,
    'expected primitive JSON text of at most 12288 UTF-8 bytes');
  let input;
  try { input = JSON.parse(jsonText); } catch { throw new TypeError('invalid JSON text'); }
  fields(input, ['schemaVersion', 'kind', 'runId', 'mode', 'resources', 'limits', 'execution', 'credits'], 'input');
  requireValue(input.schemaVersion === 1 && input.kind === 'fictional-gpu-run-plan', 'unsupported schemaVersion or kind');
  requireValue(input.mode === 'plan-only', 'only plan-only mode is supported; execution is refused');
  id(input.runId, 'runId');
  const {resources, limits, execution, credits} = input;
  fields(resources, Object.keys(RESOURCE_MAX), 'resources');
  fields(limits, [...Object.keys(RESOURCE_MAX), 'wallTimeSeconds'], 'limits');
  for (const [key, max] of Object.entries(RESOURCE_MAX)) {
    integer(resources[key], 1, max, `resources.${key}`);
    integer(limits[key], 0, max, `limits.${key}`);
  }
  integer(limits.wallTimeSeconds, 0, 604800, 'limits.wallTimeSeconds');
  fields(execution, ['timeoutSeconds', 'maxRetries', 'retryBackoffSeconds', 'shutdownOwnerId', 'stopCondition'], 'execution');
  integer(execution.timeoutSeconds, 1, 86400, 'timeoutSeconds');
  integer(execution.maxRetries, 0, 8, 'maxRetries');
  integer(execution.retryBackoffSeconds, 0, 3600, 'retryBackoffSeconds');
  id(execution.shutdownOwnerId, 'shutdownOwnerId', true);
  requireValue(execution.stopCondition === null || execution.stopCondition === 'timeout-or-complete', 'invalid stopCondition');
  fields(credits, ['unit', 'perAttemptCeiling', 'available'], 'credits');
  requireValue(credits.unit === 'fictional-credit', 'only fictional-credit is supported');
  integer(credits.perAttemptCeiling, 0, 1000000, 'perAttemptCeiling');
  integer(credits.available, 0, 100000000, 'available');

  const findings = [], flag = (code, field) => findings.push({code, field});
  for (const key of Object.keys(RESOURCE_MAX)) {
    if (resources[key] === null) flag(`unknown-${key}`, `resources.${key}`);
    if (limits[key] === null) flag(`unknown-${key}-limit`, `limits.${key}`);
    if (resources[key] !== null && limits[key] !== null && resources[key] > limits[key]) {
      flag(`${key}-exceeds-limit`, `resources.${key}`);
    }
  }
  for (const key of ['timeoutSeconds', 'maxRetries', 'retryBackoffSeconds']) {
    if (execution[key] === null) flag(`unknown-${key}`, `execution.${key}`);
  }
  if (execution.shutdownOwnerId === null) flag('unknown-shutdown-owner', 'execution.shutdownOwnerId');
  if (execution.stopCondition === null) flag('unknown-stop-condition', 'execution.stopCondition');
  const attempts = execution.maxRetries === null ? null : execution.maxRetries + 1;
  const computeSeconds = attempts === null || execution.timeoutSeconds === null ? null : attempts * execution.timeoutSeconds;
  const wallTimeSeconds = computeSeconds === null || execution.retryBackoffSeconds === null ? null :
    computeSeconds + execution.maxRetries * execution.retryBackoffSeconds;
  const gpuSeconds = computeSeconds === null || resources.gpuCount === null ? null : computeSeconds * resources.gpuCount;
  if (limits.wallTimeSeconds === null) flag('unknown-wall-time-limit', 'limits.wallTimeSeconds');
  else if (wallTimeSeconds !== null && wallTimeSeconds > limits.wallTimeSeconds) flag('wall-time-exceeds-limit', 'limits.wallTimeSeconds');
  if (credits.perAttemptCeiling === null) flag('unknown-attempt-credit-ceiling', 'credits.perAttemptCeiling');
  if (credits.available === null) flag('unknown-available-credits', 'credits.available');
  const worstCaseFictionalCredits = attempts === null || credits.perAttemptCeiling === null ? null : attempts * credits.perAttemptCeiling;
  const remainingFictionalCredits = worstCaseFictionalCredits === null || credits.available === null ? null : credits.available - worstCaseFictionalCredits;
  if (remainingFictionalCredits !== null && remainingFictionalCredits < 0) flag('fictional-credits-exceed-available', 'credits.available');

  return {
    schemaVersion: 1, kind: 'fictional-gpu-plan-card', status: findings.length ? 'needs-review' : 'consistent-declarations', findings,
    summary: {runId: input.runId, attempts, computeSeconds, wallTimeSeconds, gpuSeconds, worstCaseFictionalCredits, remainingFictionalCredits},
    boundary: {synthetic: true, capacityVerified: false, creditsVerified: false,
      executionAuthorized: false, executionStarted: false, spendIncurred: false},
  };
}
