/** Fictional, supplied-data consistency checks; never authenticated Cala facts. */
import {createHash} from 'node:crypto';
import {isDeepStrictEqual, types} from 'node:util';

const FIELD = /^[A-Za-z][A-Za-z0-9_.-]{0,127}$/;
const ARTIFACT = /^fictional:[a-z0-9][a-z0-9-]{0,63}$/;
const DIGEST = /^sha256:[a-f0-9]{64}$/;
const TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const VALUE_TYPES = new Set(['string', 'number', 'boolean', 'object', 'array']);

class InputError extends TypeError {
  constructor(code, path) {
    super(`${code} at ${path}`);
    this.code = code;
    this.path = path;
  }
}

const invalid = (code, path) => { throw new InputError(code, path); };
const issue = (code, path, severity = 'fail') => ({code, path, severity});
const childPath = (path, key) => `${path}[${JSON.stringify(key)}]`;
const statusOf = issues => issues.some(x => x.severity === 'fail') ? 'fail'
  : issues.some(x => x.severity === 'inconclusive') ? 'inconclusive' : 'consistent';

// Copy only own data descriptors. Never serialize/coerce the caller's objects.
// Proxies are not JSON data and are outside the contract; detect them before
// reflective operations so ordinary Proxy traps do not run in this Node helper.
function snapshotJson(input) {
  const ancestors = new Set();
  let nodes = 0;
  let characters = 0;
  const countString = (value, path) => {
    characters += value.length;
    if (characters > 131072) invalid('input-limit', path);
  };
  function visit(value, path, depth) {
    if (++nodes > 8192 || depth > 16) invalid('input-limit', path);
    if (value === null || typeof value === 'boolean') return value;
    if (typeof value === 'number') {
      if (!Number.isFinite(value)) invalid('non-json-value', path);
      return value;
    }
    if (typeof value === 'string') { countString(value, path); return value; }
    if (typeof value !== 'object') invalid('non-json-value', path);
    if (types.isProxy(value)) invalid('unsupported-proxy', path);
    const array = Array.isArray(value);
    const prototype = Object.getPrototypeOf(value);
    if (array ? prototype !== Array.prototype : prototype !== Object.prototype && prototype !== null) {
      invalid('unsupported-prototype', path);
    }
    if (ancestors.has(value)) invalid('cyclic-value', path);
    const descriptors = Object.getOwnPropertyDescriptors(value);
    const keys = Reflect.ownKeys(descriptors);
    if (keys.some(key => typeof key === 'symbol')) invalid('symbol-property', path);
    const copy = array ? [] : Object.create(null);
    const length = array ? descriptors.length.value : keys.length;
    if (length > 256) invalid('input-limit', path);
    if (array) {
      for (const key of keys) {
        if (key !== 'length' && (!/^(0|[1-9]\d*)$/.test(key) || Number(key) >= length)) {
          invalid('array-extra-property', childPath(path, key));
        }
      }
      for (let i = 0; i < length; i++) {
        if (!Object.hasOwn(descriptors, String(i))) invalid('sparse-array', `${path}[${i}]`);
      }
    }
    ancestors.add(value);
    for (const key of keys) {
      if (array && key === 'length') continue;
      const propertyPath = childPath(path, key);
      countString(key, propertyPath);
      const descriptor = descriptors[key];
      if (!Object.hasOwn(descriptor, 'value')) invalid('accessor-property', propertyPath);
      if (!descriptor.enumerable) invalid('non-enumerable-property', propertyPath);
      copy[key] = visit(descriptor.value, propertyPath, depth + 1);
    }
    ancestors.delete(value);
    return copy;
  }
  return visit(input, '$', 0);
}

function record(value, path) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) invalid('expected-record', path);
}

function keys(value, required, optional, path) {
  record(value, path);
  const allowed = new Set([...required, ...optional]);
  for (const key of Object.keys(value)) if (!allowed.has(key)) invalid('unknown-key', childPath(path, key));
  for (const key of required) if (!Object.hasOwn(value, key)) invalid('missing-key', childPath(path, key));
}

function pattern(value, expression, code, path) {
  if (typeof value !== 'string' || !expression.test(value)) invalid(code, path);
}

function fieldMap(value, path) {
  record(value, path);
  for (const key of Object.keys(value)) pattern(key, FIELD, 'invalid-field-name', childPath(path, key));
}

function canonicalJson(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
}

function payloadDigest(sourceTime, fields) {
  return `sha256:${createHash('sha256').update(canonicalJson({sourceTime, fields})).digest('hex')}`;
}

/** Hash only the supplied fictional payload, not its truth or provenance. */
export function digestFictionalPayload(input) {
  const value = snapshotJson(input);
  keys(value, ['sourceTime', 'fields'], [], '$');
  if (value.sourceTime !== null && typeof value.sourceTime !== 'string') invalid('invalid-time', '$["sourceTime"]');
  fieldMap(value.fields, '$["fields"]');
  return payloadDigest(value.sourceTime, value.fields);
}

function validateShape(value) {
  keys(value, ['schemaVersion', 'mode', 'asOf', 'maxAgeSeconds', 'artifacts', 'claims'], [], '$');
  if (value.schemaVersion !== 1) invalid('unsupported-schema', '$["schemaVersion"]');
  if (value.mode !== 'fictional-offline') invalid('unsupported-mode', '$["mode"]');
  if (!Number.isSafeInteger(value.maxAgeSeconds) || value.maxAgeSeconds < 0
    || value.maxAgeSeconds > Math.floor(Number.MAX_SAFE_INTEGER / 1000)) {
    invalid('invalid-max-age', '$["maxAgeSeconds"]');
  }
  if (!Array.isArray(value.artifacts) || value.artifacts.length > 32) invalid('invalid-artifact-count', '$["artifacts"]');
  if (!Array.isArray(value.claims) || value.claims.length < 1 || value.claims.length > 64) invalid('invalid-claim-count', '$["claims"]');
  const artifactIds = new Set();
  for (const [index, artifact] of value.artifacts.entries()) {
    const path = `$["artifacts"][${index}]`;
    keys(artifact, ['id', 'sha256', 'sourceTime', 'observedTime', 'fields'], [], path);
    pattern(artifact.id, ARTIFACT, 'invalid-artifact-id', `${path}["id"]`);
    if (artifactIds.has(artifact.id)) invalid('duplicate-artifact', `${path}["id"]`);
    artifactIds.add(artifact.id);
    pattern(artifact.sha256, DIGEST, 'invalid-digest', `${path}["sha256"]`);
    fieldMap(artifact.fields, `${path}["fields"]`);
  }
  const fieldNames = new Set();
  for (const [index, claim] of value.claims.entries()) {
    const path = `$["claims"][${index}]`;
    keys(claim, ['field', 'type', 'value'], ['source'], path);
    pattern(claim.field, FIELD, 'invalid-field-name', `${path}["field"]`);
    if (fieldNames.has(claim.field)) invalid('duplicate-field', `${path}["field"]`);
    fieldNames.add(claim.field);
    if (!VALUE_TYPES.has(claim.type)) invalid('invalid-field-type', `${path}["type"]`);
    if (!Object.hasOwn(claim, 'source') || claim.source === null) continue;
    keys(claim.source, ['artifactId', 'field', 'sha256', 'sourceTime', 'observedTime'], [], `${path}["source"]`);
    pattern(claim.source.artifactId, ARTIFACT, 'invalid-artifact-id', `${path}["source"]["artifactId"]`);
    pattern(claim.source.field, FIELD, 'invalid-field-name', `${path}["source"]["field"]`);
    pattern(claim.source.sha256, DIGEST, 'invalid-digest', `${path}["source"]["sha256"]`);
  }
}

function timestamp(value, path, issues, allowNull = true) {
  if (value === null && allowNull) {
    issues.push(issue('unknown-time', path, 'inconclusive'));
    return null;
  }
  if (typeof value !== 'string' || !TIMESTAMP.test(value)) {
    issues.push(issue('invalid-time', path));
    return null;
  }
  const result = Date.parse(value);
  if (!Number.isFinite(result) || new Date(result).toISOString() !== value) {
    issues.push(issue('invalid-time', path));
    return null;
  }
  return result;
}

function checkTimes(value, path, asOf, maxAge, issues) {
  const source = timestamp(value.sourceTime, `${path}["sourceTime"]`, issues);
  const observed = timestamp(value.observedTime, `${path}["observedTime"]`, issues);
  if (source !== null && observed !== null && source > observed) issues.push(issue('source-after-observation', path));
  for (const [time, key, staleCode] of [[source, 'sourceTime', 'stale-source'], [observed, 'observedTime', 'stale-observation']]) {
    if (time === null) continue;
    if (time > asOf) issues.push(issue('future-time', `${path}["${key}"]`));
    else if (asOf - time > maxAge) issues.push(issue(staleCode, `${path}["${key}"]`));
  }
}

function report(issues = [], artifacts = [], fields = []) {
  const states = [...issues, ...artifacts.map(x => ({severity: x.status})), ...fields.map(x => ({severity: x.status}))];
  return {
    schemaVersion: 1, mode: 'fictional-offline', status: statusOf(states),
    sourceAuthenticated: false, truthVerified: false, connectorExecuted: false,
    issues, artifacts, fields,
  };
}

/** Validate exact supplied field bindings and freshness, not external facts. */
export function checkFieldProvenance(input) {
  let value;
  try {
    value = snapshotJson(input);
    validateShape(value);
  } catch (error) {
    if (!(error instanceof InputError)) throw error;
    return report([issue(error.code, error.path)]);
  }
  const issues = [];
  const asOf = timestamp(value.asOf, '$["asOf"]', issues, false);
  if (asOf === null) return report(issues);
  const maxAge = value.maxAgeSeconds * 1000;
  const artifacts = [];
  const byId = new Map();
  for (const [index, artifact] of value.artifacts.entries()) {
    const path = `$["artifacts"][${index}]`;
    const artifactIssues = [];
    if (payloadDigest(artifact.sourceTime, artifact.fields) !== artifact.sha256) {
      artifactIssues.push(issue('artifact-digest-mismatch', `${path}["sha256"]`));
    }
    checkTimes(artifact, path, asOf, maxAge, artifactIssues);
    const result = {id: artifact.id, status: statusOf(artifactIssues), issues: artifactIssues};
    artifacts.push(result);
    byId.set(artifact.id, {artifact, result});
  }
  const fields = value.claims.map((claim, index) => {
    const path = `$["claims"][${index}]`;
    const fieldIssues = [];
    const source = claim.source ?? null;
    if (claim.value === null) fieldIssues.push(issue('null-value', `${path}["value"]`, 'inconclusive'));
    else {
      const type = Array.isArray(claim.value) ? 'array' : typeof claim.value;
      if (type !== claim.type) fieldIssues.push(issue('type-mismatch', `${path}["value"]`));
    }
    if (source === null) fieldIssues.push(issue('uncited-field', `${path}["source"]`, 'inconclusive'));
    else {
      checkTimes(source, `${path}["source"]`, asOf, maxAge, fieldIssues);
      if (source.field !== claim.field) fieldIssues.push(issue('source-field-mismatch', `${path}["source"]["field"]`));
      const selected = byId.get(source.artifactId);
      if (!selected) fieldIssues.push(issue('missing-artifact', `${path}["source"]["artifactId"]`, 'inconclusive'));
      else {
        const {artifact, result} = selected;
        if (result.status !== 'consistent') fieldIssues.push(issue('source-artifact-not-consistent', `${path}["source"]`, result.status));
        for (const [key, code] of [['sha256', 'source-digest-mismatch'], ['sourceTime', 'source-time-mismatch'], ['observedTime', 'observed-time-mismatch']]) {
          if (source[key] !== artifact[key]) fieldIssues.push(issue(code, `${path}["source"]["${key}"]`));
        }
        if (!Object.hasOwn(artifact.fields, source.field)) {
          fieldIssues.push(issue('missing-source-field', `${path}["source"]["field"]`, 'inconclusive'));
        } else if (!isDeepStrictEqual(claim.value, artifact.fields[source.field])) {
          fieldIssues.push(issue('value-mismatch', `${path}["value"]`));
        }
      }
    }
    return {
      field: claim.field, type: claim.type, valueState: claim.value === null ? 'null' : 'present',
      source, status: statusOf(fieldIssues), issues: fieldIssues,
    };
  });
  return report(issues, artifacts, fields);
}
