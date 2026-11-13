import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {reviewHandoff} from '../pets/stoa/handoff-proof.mjs';

const fixture = () => ({
  schemaVersion: 1, kind: 'fictional-document-handoff',
  document: {documentId: 'fictional-model-a', currentRevision: 4, owners: ['fictional-design-owner']},
  handoff: {documentId: 'fictional-model-a', revision: 4, fromOwnerId: 'fictional-design-owner', recipientId: 'fictional-reviewer'},
  acceptance: {documentId: 'fictional-model-a', revision: 4, recipientId: 'fictional-reviewer', state: 'accepted'},
});
const run = value => reviewHandoff(JSON.stringify(value));
const codes = value => run(value).findings.map(f => f.code);

test('matching invented declarations produce a deterministic proof card, never project approval', () => {
  const value = fixture(), before = JSON.stringify(value), result = run(value);
  assert.equal(result.status, 'consistent-declarations');
  assert.deepEqual(result.findings, []);
  assert.deepEqual(result.summary, {documentId: 'fictional-model-a', currentRevision: 4, submittedRevision: 4, ownerDeclarations: 1, acceptanceDeclaration: 'accepted'});
  assert.deepEqual(result.boundary, {synthetic: true, documentInspected: false, ownershipVerified: false, acceptanceVerified: false, siteActionAuthorized: false});
  assert.equal(JSON.stringify(value), before);
  assert.deepEqual(result, run(value));
});

test('both stale and unrecognized newer revisions require review, even when acceptance repeats them', () => {
  for (const [revision, code] of [[3, 'stale-revision'], [5, 'unrecognized-revision']]) {
    const value = fixture(); value.handoff.revision = revision; value.acceptance.revision = revision;
    assert.deepEqual(codes(value), [code]);
    assert.equal(run(value).status, 'needs-review');
  }
});

test('missing, unknown, duplicate and conflicting owner declarations cannot supply a sole owner', () => {
  for (const [owners, expected] of [[[], ['missing-owner']], [null, ['unknown-owners']],
    [['fictional-owner-a', 'fictional-owner-b'], ['conflicting-owners']],
    [['fictional-design-owner', 'fictional-design-owner'], ['duplicate-owner']]]) {
    const value = fixture(); value.document.owners = owners;
    assert.deepEqual(codes(value), expected);
    assert.equal(run(value).status, 'needs-review');
    assert.equal(run(value).boundary.ownershipVerified, false);
  }
});

test('the declared sender must be the sole owner and the recipient cannot be the sender', () => {
  const value = fixture(); value.handoff.fromOwnerId = 'fictional-other-owner';
  assert.deepEqual(codes(value), ['sender-owner-mismatch']);
  value.handoff.fromOwnerId = null;
  assert.deepEqual(codes(value), ['unknown-sender']);
  value.handoff.fromOwnerId = 'fictional-design-owner';
  value.handoff.recipientId = value.handoff.fromOwnerId; value.acceptance.recipientId = value.handoff.recipientId;
  assert.deepEqual(codes(value), ['self-handoff']);
});

test('handoff and acceptance bind to the exact declared document, not merely a matching revision', () => {
  const value = fixture(); value.handoff.documentId = 'fictional-other-model'; value.acceptance.documentId = 'fictional-other-model';
  assert.deepEqual(codes(value), ['handoff-document-mismatch', 'acceptance-document-mismatch']);
  value.handoff.documentId = null; value.acceptance.documentId = null;
  assert.deepEqual(codes(value), ['unknown-handoff-document', 'unknown-acceptance-document']);
});

test('unknown, pending, rejected and absent acceptance never become consistent declarations', () => {
  const value = fixture(); value.acceptance = null;
  assert.deepEqual(codes(value), ['missing-acceptance']);
  for (const [state, code] of [[null, 'unknown-acceptance'], ['unknown', 'unknown-acceptance'], ['pending', 'pending-acceptance'], ['rejected', 'rejected-acceptance']]) {
    value.acceptance = {...fixture().acceptance, state};
    assert.deepEqual(codes(value), [code]);
    assert.equal(run(value).status, 'needs-review');
    assert.equal(run(value).boundary.acceptanceVerified, false);
  }
});

test('an accepted declaration cannot be replayed across revisions or recipients', () => {
  const value = fixture(); value.acceptance.revision = 3; value.acceptance.recipientId = 'fictional-other-reviewer';
  assert.deepEqual(codes(value), ['acceptance-revision-mismatch', 'acceptance-recipient-mismatch']);
  value.acceptance.revision = null; value.acceptance.recipientId = null;
  assert.deepEqual(codes(value), ['unknown-acceptance-revision', 'unknown-acceptance-recipient']);
  value.acceptance = {...fixture().acceptance}; value.handoff.recipientId = null;
  assert.deepEqual(codes(value), ['unknown-recipient']);
});

test('revision zero is valid, explicit null stays unknown, and omitted revision is malformed', () => {
  const value = fixture(); value.document.currentRevision = 0; value.handoff.revision = 0; value.acceptance.revision = 0;
  assert.equal(run(value).status, 'consistent-declarations');
  value.document.currentRevision = null; value.handoff.revision = null;
  assert.deepEqual(codes(value), ['unknown-current-revision', 'unknown-handoff-revision']);
  assert.equal(run(value).summary.submittedRevision, null);
  delete value.handoff.revision;
  assert.throws(() => run(value), /handoff fields/);
});

test('missing handoff cannot be rescued by an accepted declaration and absent keys are not defaulted', () => {
  const value = fixture(); value.handoff = null;
  assert.deepEqual(codes(value), ['missing-handoff']);
  assert.equal(run(value).summary.submittedRevision, null);
  assert.equal(run(value).status, 'needs-review');
  delete value.handoff;
  assert.throws(() => run(value), /input fields/);
});

test('closed bounded JSON refuses malformed records, real identifiers, extra authority and numeric coercion', () => {
  for (const text of [null, {}, new String('{}'), '{', ' '.repeat(12289), 'é'.repeat(7000)]) assert.throws(() => reviewHandoff(text), TypeError);
  for (const mutate of [
    x => {x.siteActionAuthorized = true;}, x => {x.document.url = 'https://example.invalid/model';},
    x => {x.kind = 'real-document-handoff';}, x => {x.schemaVersion = 2;}, x => {x.document.documentId = 'customer-123';},
    x => {x.document.currentRevision = '4';}, x => {x.handoff.revision = -1;}, x => {x.acceptance.revision = 4.5;},
    x => {x.document.owners = ['fictional-a', null];}, x => {x.acceptance.state = 'approved';},
    x => {x.handoff.fromOwnerId = 'fictional-' + 'a'.repeat(60);},
  ]) {const value = fixture(); mutate(value); assert.throws(() => run(value), TypeError);}
  const text = JSON.stringify(fixture());
  assert.throws(() => reviewHandoff(text.replace('"currentRevision":4', '"currentRevision":1e999')), TypeError);
  assert.throws(() => reviewHandoff(text.replace('"revision":4', '"revision":-0')), TypeError);
});

test('owner and revision bounds are finite and JSON duplicate members use the last parsed value', () => {
  const value = fixture(); value.document.owners = Array.from({length: 8}, (_, i) => `fictional-owner-${i}`);
  assert.deepEqual(codes(value), ['conflicting-owners']);
  value.document.owners.push('fictional-overflow'); assert.throws(() => run(value), /owners/);
  value.document.owners = ['fictional-design-owner'];
  value.document.currentRevision = 999999; value.handoff.revision = 999999; value.acceptance.revision = 999999;
  assert.equal(run(value).status, 'consistent-declarations');
  value.document.currentRevision++; assert.throws(() => run(value), /currentRevision/);
  const text = JSON.stringify(fixture()).replace('"currentRevision":4', '"currentRevision":2,"currentRevision":4');
  assert.equal(reviewHandoff(text).status, 'consistent-declarations');
  assert.throws(() => reviewHandoff(text.replace('"schemaVersion":1', '"schemaVersion":1,"__proto__":{"polluted":true}')), TypeError);
  assert.equal({}.polluted, undefined);
});

test('the checked-in fictional BIM handoff example only establishes declaration consistency', () => {
  const text = readFileSync(new URL('../pets/stoa/examples/fictional-handoff.json', import.meta.url), 'utf8');
  const result = reviewHandoff(text);
  assert.equal(result.status, 'consistent-declarations');
  assert.equal(result.summary.documentId, 'fictional-coordination-model');
  assert.equal(result.boundary.documentInspected, false);
  assert.equal(result.boundary.siteActionAuthorized, false);
});
