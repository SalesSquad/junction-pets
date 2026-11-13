// Fictional offline declarations only. No I/O, DNS, crawler or permission authority.
const HOST = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+invalid$/;
const ID = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const statuses = ['candidate', 'needs-review', 'exclude'];
function requireValue(ok, message) { if (!ok) throw new TypeError(message); }
function record(value, keys, name) {
  requireValue(value !== null && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key)), `${name} has missing or unsupported fields`);
}
function text(value, max, pattern, name) {
  requireValue(typeof value === 'string' && value.length <= max && !/[\u0000-\u0020\u007f]/.test(value) && pattern.test(value), `invalid ${name}`);
}
function integer(value, min, max, name, nullable = true) {
  requireValue(nullable && value === null || Number.isSafeInteger(value) && !Object.is(value, -0) && value >= min && value <= max, `invalid ${name}`);
}
function list(value, min, max, name) { requireValue(Array.isArray(value) && value.length >= min && value.length <= max, `invalid ${name} count`); }

export function reviewCollectionPlan(jsonText) {
  requireValue(typeof jsonText === 'string' && jsonText.length <= 32768 && new TextEncoder().encode(jsonText).length <= 32768, 'expected at most 32768 UTF-8 bytes of JSON text');
  let plan;
  try { plan = JSON.parse(jsonText); } catch { throw new TypeError('invalid JSON text'); }
  record(plan, ['schemaVersion', 'scenario', 'allowedHosts', 'limits', 'fields', 'targets'], 'plan');
  requireValue(plan.schemaVersion === 1 && plan.scenario === 'fictional', 'only schemaVersion 1 fictional plans accepted');
  list(plan.allowedHosts, 1, 8, 'allowed hosts');
  for (const host of plan.allowedHosts) text(host, 253, HOST, 'fictional host');
  requireValue(new Set(plan.allowedHosts).size === plan.allowedHosts.length, 'duplicate allowed host');
  record(plan.limits, ['maxPages', 'maxRetries', 'timeoutSeconds', 'maxAgeHours'], 'limits');
  integer(plan.limits.maxPages, 1, 1000, 'page limit');
  integer(plan.limits.maxRetries, 0, 3, 'retry limit');
  integer(plan.limits.timeoutSeconds, 1, 3600, 'timeout');
  integer(plan.limits.maxAgeHours, 0, 8760, 'sample age limit');
  list(plan.fields, 1, 16, 'fields');
  const fieldNames = new Set();
  for (const field of plan.fields) {
    record(field, ['name', 'personal'], 'field'); text(field.name, 64, ID, 'field name');
    requireValue(!fieldNames.has(field.name) && [true, false, null].includes(field.personal), 'duplicate field or invalid sensitivity');
    fieldNames.add(field.name);
  }
  list(plan.targets, 1, 32, 'targets');
  const ids = new Set(), urls = new Set();
  for (const target of plan.targets) {
    record(target, ['id', 'url', 'visibility', 'permission', 'robots', 'sample'], 'target'); text(target.id, 64, ID, 'target id');
    text(target.url, 512, /^https:\/\/[^/]+(?:\/[A-Za-z0-9/_-]*)?$/, 'fictional URL');
    text(target.url.slice(8).split('/')[0], 253, HOST, 'fictional URL host');
    requireValue(!ids.has(target.id) && !urls.has(target.url), 'duplicate target id or URL'); ids.add(target.id); urls.add(target.url);
    requireValue(['public', 'private', 'authenticated', 'paywalled', null].includes(target.visibility), 'invalid visibility');
    for (const key of ['permission', 'robots']) requireValue(['allowed', 'denied', null].includes(target[key]), `invalid ${key}`);
    if (target.sample !== null) {
      record(target.sample, ['records', 'missingRequired', 'duplicates', 'ageHours'], 'quality sample');
      integer(target.sample.records, 0, 1000, 'sample records', false);
      integer(target.sample.missingRequired, 0, target.sample.records, 'missing count', false);
      integer(target.sample.duplicates, 0, target.sample.records, 'duplicate count', false);
      integer(target.sample.ageHours, 0, 8760, 'sample age');
    }
  }
  const findings = []; let globalRank = 0;
  const global = (code, subject, rank = 1) => { findings.push({code, subject}); globalRank = Math.max(globalRank, rank); };
  for (const [key, code] of [['maxPages', 'unknown-page-limit'], ['maxRetries', 'unknown-retry-limit'], ['timeoutSeconds', 'unknown-timeout'], ['maxAgeHours', 'unknown-age-limit']]) {
    if (plan.limits[key] === null) global(code, `limits.${key}`);
  }
  if (plan.limits.maxPages !== null && plan.targets.length > plan.limits.maxPages) global('page-limit-exceeded', 'targets', 2);
  for (const field of plan.fields) {
    if (field.personal === true) global('personal-field-excluded', field.name, 2);
    else if (field.personal === null) global('unknown-field-sensitivity', field.name);
  }
  const targets = plan.targets.map(target => {
    const findings = []; let rank = globalRank;
    const add = (code, severity = 1) => { findings.push({code, subject: target.id}); rank = Math.max(rank, severity); };
    if (!plan.allowedHosts.includes(target.url.slice(8).split('/')[0])) add('host-not-allowlisted', 2);
    if (target.visibility === null) add('unknown-visibility');
    else if (target.visibility !== 'public') add('non-public-target', 2);
    for (const key of ['permission', 'robots']) {
      if (target[key] === null) add(`unknown-${key}`);
      else if (target[key] === 'denied') add(`${key}-denied`, 2);
    }
    if (target.sample === null) add('missing-quality-sample');
    else {
      if (target.sample.records === 0) add('empty-quality-sample');
      if (target.sample.missingRequired > 0) add('missing-required-fields');
      if (target.sample.duplicates > 0) add('duplicate-records');
      if (target.sample.ageHours === null) add('unknown-sample-age');
      else if (plan.limits.maxAgeHours !== null && target.sample.ageHours > plan.limits.maxAgeHours) add('stale-sample');
    }
    return {id: target.id, status: statuses[rank], findings};
  });
  const attemptsPerPage = plan.limits.maxRetries === null ? null : plan.limits.maxRetries + 1;
  const maxAttempts = plan.limits.maxPages === null || attemptsPerPage === null ? null : plan.limits.maxPages * attemptsPerPage;
  return {schemaVersion: 1, kind: 'fictional-collection-plan-review', status: statuses[Math.max(globalRank, ...targets.map(t => statuses.indexOf(t.status)))], findings, targets,
    bounds: {maxPages: plan.limits.maxPages, attemptsPerPage, maxAttempts, aggregateAttemptSeconds: maxAttempts === null || plan.limits.timeoutSeconds === null ? null : maxAttempts * plan.limits.timeoutSeconds},
    boundary: {fictional: true, fetched: false, permissionVerified: false, collectionAuthorized: false, complianceVerified: false}};
}
