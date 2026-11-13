import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {reviewStorageMatrix} from '../pets/ironshard/storage-matrix.mjs';

function fixture() {
  return {
    schemaVersion: 1, scenario: 'fictional', asOfMs: 1000,
    snapshot: {observedAtMs: 990, maxAgeMs: 10},
    tenants: ['tenant-a', 'tenant-b'],
    actors: [{id: 'agent-a', tenantId: 'tenant-a'}, {id: 'agent-b', tenantId: 'tenant-b'}],
    objects: [{id: 'object-a', tenantId: 'tenant-a'}, {id: 'object-b', tenantId: 'tenant-b'}, {id: 'object-a-copy', tenantId: 'tenant-a'}],
    grants: [{id: 'grant-a', tenantId: 'tenant-a', actorId: 'agent-a', objectIds: ['object-a'], operations: ['read'], startsAtMs: 0, expiresAtMs: 1001, revoked: false}],
    requests: [{id: 'read-a', tenantId: 'tenant-a', actorId: 'agent-a', objectId: 'object-a', grantId: 'grant-a', operation: 'read'}],
  };
}
const check = value => reviewStorageMatrix(JSON.stringify(value));
const row = result => result.requests[0];
const deny = value => assert.equal(row(check(value)).decision, 'denied');

test('exact declared actor/object/effect matches are not real authorization or verified provenance', () => {
  const result = check(fixture());
  assert.deepEqual(row(result), {id: 'read-a', decision: 'matches-declared-scope', reasons: []});
  assert.deepEqual(result.snapshot, {ageMs: 10, reasons: []});
  assert.deepEqual(result.grants, [{id: 'grant-a', reasons: []}]);
  assert.equal(result.kind, 'fictional-storage-matrix-review');
  assert.deepEqual(result.qualification, {authorizationGranted: false, storageAccessed: false, credentialsIssued: false, provenanceVerified: false});
});

test('object and operation scopes require exact membership, with no prefix or wildcard expansion', () => {
  for (const change of [
    r => { r.objectId = 'object-a-copy'; }, r => { r.operation = 'write'; }, r => { r.operation = 'delete'; },
  ]) {
    const value = fixture(); change(value.requests[0]); deny(value);
  }
  const wildcard = fixture(); wildcard.grants[0].objectIds = ['*'];
  assert.throws(() => check(wildcard), /Invalid storage matrix/);
  wildcard.grants[0].objectIds = ['object-a'];
  wildcard.requests[0].objectId = 'object-a/path';
  assert.throws(() => check(wildcard), /Invalid storage matrix/);
});

test('cross-tenant request, actor, object and grant declarations all fail closed', () => {
  for (const mutate of [
    x => { x.requests[0].tenantId = 'tenant-b'; },
    x => { x.requests[0].actorId = 'agent-b'; },
    x => { x.requests[0].objectId = 'object-b'; },
    x => { x.grants[0].tenantId = 'tenant-b'; },
    x => { x.grants[0].actorId = 'agent-b'; },
    x => { x.grants[0].objectIds.push('object-b'); },
  ]) {
    const value = fixture(); mutate(value); deny(value);
  }
  const value = fixture(); value.grants[0].objectIds.push('object-b');
  assert.ok(check(value).grants[0].reasons.includes('cross-tenant-object:object-b'));
});

test('unknown and explicitly null request identities or effects are denied, never borrowed from context', () => {
  for (const key of ['tenantId', 'actorId', 'objectId', 'grantId', 'operation']) {
    for (const unknown of ['not-declared', null]) {
      const value = fixture(); value.requests[0][key] = unknown; deny(value);
    }
  }
  for (const mutate of [
    x => { x.grants[0].objectIds.push('not-declared'); },
    x => { x.grants[0].actorId = null; },
    x => { x.objects[0].tenantId = null; },
    x => { x.actors[0].tenantId = null; },
  ]) {
    const value = fixture(); mutate(value); deny(value);
  }
});

test('revoked and unknown revocation declarations deny; a later supplied snapshot can remove a prior match', () => {
  const value = fixture();
  const before = check(value);
  for (const revoked of [true, null]) {
    value.grants[0].revoked = revoked;
    deny(value);
  }
  assert.equal(row(before).decision, 'matches-declared-scope');
  value.grants[0].revoked = false;
  assert.equal(row(check(value)).decision, 'matches-declared-scope');
  assert.equal(check(value).qualification.provenanceVerified, false);
});

test('grant time uses an inclusive start and exclusive expiry, with zero and null kept distinct', () => {
  const value = fixture();
  value.grants[0].startsAtMs = 1000;
  assert.equal(row(check(value)).decision, 'matches-declared-scope');
  for (const mutate of [
    x => { x.grants[0].startsAtMs = 1001; },
    x => { x.grants[0].expiresAtMs = 1000; },
    x => { x.grants[0].startsAtMs = null; },
    x => { x.grants[0].expiresAtMs = null; },
    x => { x.grants[0].expiresAtMs = x.grants[0].startsAtMs; },
    x => { x.asOfMs = null; },
  ]) {
    const changed = fixture(); mutate(changed); deny(changed);
  }
  value.asOfMs = 0; value.snapshot = {observedAtMs: 0, maxAgeMs: 0};
  value.grants[0].startsAtMs = 0; value.grants[0].expiresAtMs = 1;
  assert.equal(row(check(value)).decision, 'matches-declared-scope');
});

test('stale, future or unknown revocation snapshot timing denies every request', () => {
  for (const snapshot of [
    {observedAtMs: 989, maxAgeMs: 10}, {observedAtMs: 1001, maxAgeMs: 10},
    {observedAtMs: null, maxAgeMs: 10}, {observedAtMs: 990, maxAgeMs: null},
  ]) {
    const value = fixture(); value.snapshot = snapshot;
    const result = check(value);
    assert.equal(row(result).decision, 'denied');
    assert.ok(result.snapshot.reasons.length > 0);
  }
  const value = fixture(); value.snapshot = {observedAtMs: 1000, maxAgeMs: 0};
  assert.equal(row(check(value)).decision, 'matches-declared-scope');
});

test('the explicitly named grant alone is checked; rights from other grants never combine', () => {
  const value = fixture();
  value.grants.push({...value.grants[0], id: 'write-grant', operations: ['write']});
  value.requests[0].operation = 'write';
  deny(value);
  value.requests[0].grantId = 'write-grant';
  assert.equal(row(check(value)).decision, 'matches-declared-scope');
  value.grants[1].actorId = 'agent-b';
  deny(value);
});

test('closed schemas reject unsupported approval claims, missing fields and ambiguous duplicate declarations', () => {
  const mutations = [
    x => { x.authorizationGranted = true; },
    x => { x.snapshot.signatureVerified = true; },
    x => { x.grants[0].token = 'invented'; },
    x => { delete x.grants[0].revoked; },
    x => { x.requests[0].effect = 'read'; },
    x => { x.tenants.push('tenant-a'); },
    x => { x.actors.push({...x.actors[0]}); },
    x => { x.objects.push({...x.objects[0]}); },
    x => { x.grants.push({...x.grants[0]}); },
    x => { x.requests.push({...x.requests[0]}); },
    x => { x.grants[0].operations = ['read', 'read']; },
    x => { x.grants[0].operations = ['admin']; },
    x => { x.grants[0].objectIds = []; },
    x => { x.grants[0].objectIds.push('object-a'); },
  ];
  for (const mutate of mutations) {
    const value = fixture(); mutate(value);
    assert.throws(() => check(value), /Invalid storage matrix/);
  }
});

test('bounded JSON text and numeric/collection bounds reject malformed data without executing hooks', () => {
  let hooks = 0;
  for (const text of [null, {}, new String('{}'), {toJSON() { hooks++; }}, '', '{', 'null', '[]', ' '.repeat(65537)]) {
    assert.throws(() => reviewStorageMatrix(text), /Invalid storage matrix/);
  }
  assert.equal(hooks, 0);
  for (const n of [-1, 1.5, '1000', false, Number.MAX_SAFE_INTEGER + 1]) {
    const value = fixture(); value.asOfMs = n;
    assert.throws(() => check(value), /Invalid storage matrix/);
  }
  const value = fixture();
  value.requests = Array.from({length: 128}, (_, i) => ({...value.requests[0], id: 'request-' + i}));
  assert.equal(check(value).requests.length, 128);
  value.requests.push({...value.requests[0], id: 'request-overflow'});
  assert.throws(() => check(value), /Invalid storage matrix/);
  const malformed = fixture(); malformed.actors[0].id = 'agent-a\n';
  assert.throws(() => check(malformed), /Invalid storage matrix/);
});

test('output ordering is stable and returned values are isolated; ordinary JSON duplicate members use the last value', () => {
  const value = fixture();
  value.requests.push({...value.requests[0], id: 'denied-copy', objectId: 'object-a-copy'});
  const original = JSON.stringify(value), expected = check(value);
  value.tenants.reverse(); value.actors.reverse(); value.objects.reverse(); value.grants.reverse(); value.requests.reverse();
  assert.deepEqual(check(value), expected);
  expected.requests[0].decision = 'forged'; expected.grants[0].reasons.push('forged');
  assert.notDeepEqual(reviewStorageMatrix(original), expected);
  const duplicate = JSON.stringify(fixture()).replace('"revoked":false', '"revoked":true,"revoked":false');
  assert.deepEqual(reviewStorageMatrix(duplicate), check(fixture()));
});

test('invented example produces a scoped match and a denied wider request, with no storage operation', () => {
  const text = readFileSync(new URL('../pets/ironshard/example.json', import.meta.url), 'utf8');
  const result = reviewStorageMatrix(text);
  assert.deepEqual(result.requests.map(r => [r.id, r.decision]), [
    ['read-report', 'matches-declared-scope'], ['write-report', 'denied'],
  ]);
  assert.equal(result.qualification.storageAccessed, false);
});
