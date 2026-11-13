/** Synthetic supplied declarations only. This is not an authorization engine. */
const effects = new Set(['read', 'write', 'delete']);
const id = value => typeof value === 'string' && value === value.trim() && /^[a-z][a-z0-9-]{0,47}$/.test(value);
const ref = value => value === null || id(value);
const time = value => value === null || (Number.isSafeInteger(value) && value >= 0);
const shape = (value, keys) => value !== null && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const list = (value, predicate, max, min = 0) => Array.isArray(value) && value.length >= min
  && value.length <= max && value.every(predicate) && new Set(value).size === value.length;
const records = (value, predicate, max) => Array.isArray(value) && value.length <= max
  && value.every(predicate) && new Set(value.map(record => record.id)).size === value.length;
const byId = (a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
const unique = values => [...new Set(values)].sort();

function valid(data) {
  return shape(data, ['schemaVersion', 'scenario', 'asOfMs', 'snapshot', 'tenants', 'actors', 'objects', 'grants', 'requests'])
    && data.schemaVersion === 1 && data.scenario === 'fictional' && time(data.asOfMs)
    && shape(data.snapshot, ['observedAtMs', 'maxAgeMs']) && time(data.snapshot.observedAtMs) && time(data.snapshot.maxAgeMs)
    && list(data.tenants, id, 16)
    && records(data.actors, actor => shape(actor, ['id', 'tenantId']) && id(actor.id) && ref(actor.tenantId), 32)
    && records(data.objects, object => shape(object, ['id', 'tenantId']) && id(object.id) && ref(object.tenantId), 64)
    && records(data.grants, grant => shape(grant, ['id', 'tenantId', 'actorId', 'objectIds', 'operations', 'startsAtMs', 'expiresAtMs', 'revoked'])
      && id(grant.id) && ref(grant.tenantId) && ref(grant.actorId) && list(grant.objectIds, id, 16, 1)
      && list(grant.operations, operation => effects.has(operation), 3, 1)
      && time(grant.startsAtMs) && time(grant.expiresAtMs) && [true, false, null].includes(grant.revoked), 64)
    && records(data.requests, request => shape(request, ['id', 'tenantId', 'actorId', 'objectId', 'grantId', 'operation'])
      && id(request.id) && ['tenantId', 'actorId', 'objectId', 'grantId', 'operation'].every(key => ref(request[key])), 128);
}

export function reviewStorageMatrix(jsonText) {
  const invalid = () => { throw new TypeError('Invalid storage matrix: bounded fictional JSON declarations required'); };
  if (typeof jsonText !== 'string' || Buffer.byteLength(jsonText, 'utf8') > 65536) return invalid();
  let data;
  try { data = JSON.parse(jsonText); } catch { return invalid(); }
  if (!valid(data)) return invalid();

  const tenants = new Set(data.tenants), actors = new Map(data.actors.map(value => [value.id, value]));
  const objects = new Map(data.objects.map(value => [value.id, value])), grants = new Map(data.grants.map(value => [value.id, value]));
  const {observedAtMs, maxAgeMs} = data.snapshot, now = data.asOfMs;
  const ageMs = now === null || observedAtMs === null ? null : now - observedAtMs;
  const snapshotReasons = [];
  if (ageMs === null || maxAgeMs === null) snapshotReasons.push('snapshot-time-unknown');
  else if (ageMs < 0) snapshotReasons.push('snapshot-from-future');
  else if (ageMs > maxAgeMs) snapshotReasons.push('snapshot-stale');

  const grantRows = data.grants.map(grant => {
    const reasons = [], actor = actors.get(grant.actorId);
    if (!tenants.has(grant.tenantId)) reasons.push('unknown-tenant');
    if (!actor) reasons.push('unknown-actor');
    else if (actor.tenantId !== grant.tenantId) reasons.push('cross-tenant-actor');
    for (const objectId of grant.objectIds) {
      const object = objects.get(objectId);
      if (!object) reasons.push('unknown-object:' + objectId);
      else if (object.tenantId !== grant.tenantId) reasons.push('cross-tenant-object:' + objectId);
    }
    if (grant.revoked === true) reasons.push('grant-revoked');
    if (grant.revoked === null) reasons.push('revocation-unknown');
    if (now === null || grant.startsAtMs === null || grant.expiresAtMs === null) reasons.push('grant-time-unknown');
    else {
      if (grant.expiresAtMs <= grant.startsAtMs) reasons.push('invalid-grant-window');
      if (now < grant.startsAtMs) reasons.push('grant-not-started');
      if (now >= grant.expiresAtMs) reasons.push('grant-expired');
    }
    return {id: grant.id, reasons: unique(reasons)};
  }).sort(byId);
  const grantIssues = new Map(grantRows.map(row => [row.id, row.reasons]));
  const requests = data.requests.map(request => {
    const reasons = [...snapshotReasons], actor = actors.get(request.actorId);
    const object = objects.get(request.objectId), grant = grants.get(request.grantId);
    if (!tenants.has(request.tenantId)) reasons.push('unknown-tenant');
    if (!actor) reasons.push('unknown-actor');
    else if (actor.tenantId !== request.tenantId) reasons.push('cross-tenant-actor');
    if (!object) reasons.push('unknown-object');
    else if (object.tenantId !== request.tenantId) reasons.push('cross-tenant-object');
    if (!effects.has(request.operation)) reasons.push('unknown-effect');
    if (!grant) reasons.push('unknown-grant');
    else {
      reasons.push(...grantIssues.get(grant.id));
      if (grant.tenantId !== request.tenantId) reasons.push('grant-tenant-mismatch');
      if (grant.actorId !== request.actorId) reasons.push('grant-actor-mismatch');
      if (!grant.objectIds.includes(request.objectId)) reasons.push('object-outside-grant');
      if (!grant.operations.includes(request.operation)) reasons.push('operation-outside-grant');
    }
    return {id: request.id, decision: reasons.length ? 'denied' : 'matches-declared-scope', reasons: unique(reasons)};
  }).sort(byId);
  return {
    kind: 'fictional-storage-matrix-review', snapshot: {ageMs, reasons: snapshotReasons},
    grants: grantRows, requests,
    qualification: {authorizationGranted: false, storageAccessed: false, credentialsIssued: false, provenanceVerified: false},
  };
}
