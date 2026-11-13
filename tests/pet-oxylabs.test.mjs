import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {reviewCollectionPlan} from '../pets/oxylabs/collection-plan.mjs';

const fixture = () => ({
  schemaVersion: 1, scenario: 'fictional', allowedHosts: ['docs.example.invalid'],
  limits: {maxPages: 2, maxRetries: 1, timeoutSeconds: 30, maxAgeHours: 24},
  fields: [{name: 'title', personal: false}],
  targets: [{id: 'page-a', url: 'https://docs.example.invalid/guide', visibility: 'public', permission: 'allowed', robots: 'allowed',
    sample: {records: 2, missingRequired: 0, duplicates: 0, ageHours: 1}}],
});
const review = value => reviewCollectionPlan(JSON.stringify(value));
const codes = result => [...result.findings, ...result.targets.flatMap(t => t.findings)].map(f => f.code);

test('bounded invented public plan is only a candidate, never access or compliance approval', () => {
  const result = review(fixture());
  assert.equal(result.status, 'candidate');
  assert.deepEqual(result.findings, []);
  assert.deepEqual(result.targets[0].findings, []);
  assert.deepEqual(result.bounds, {maxPages: 2, attemptsPerPage: 2, maxAttempts: 4, aggregateAttemptSeconds: 120});
  assert.deepEqual(result.boundary, {fictional: true, fetched: false, permissionVerified: false, collectionAuthorized: false, complianceVerified: false});
});

test('private, authenticated and paywalled targets are excluded even with declared permission', () => {
  for (const visibility of ['private', 'authenticated', 'paywalled']) {
    const data = fixture(); data.targets[0].visibility = visibility;
    const result = review(data);
    assert.equal(result.status, 'exclude');
    assert.equal(result.targets[0].status, 'exclude');
    assert.ok(codes(result).includes('non-public-target'));
  }
});

test('denied permission or robots policy excludes; unknown remains review, not allowed', () => {
  for (const field of ['permission', 'robots']) {
    const data = fixture(); data.targets[0][field] = 'denied';
    assert.equal(review(data).targets[0].status, 'exclude');
    data.targets[0][field] = null;
    assert.equal(review(data).targets[0].status, 'needs-review');
    assert.ok(codes(review(data)).includes(`unknown-${field}`));
  }
  const data = fixture(); data.targets[0].visibility = null;
  assert.deepEqual(codes(review(data)), ['unknown-visibility']);
});

test('unbounded or over-capacity plan never produces candidate targets or complete arithmetic', () => {
  const data = fixture(); data.limits.maxPages = null; data.limits.maxRetries = null; data.limits.timeoutSeconds = null;
  const result = review(data);
  assert.equal(result.status, 'needs-review');
  assert.equal(result.targets[0].status, 'needs-review');
  assert.deepEqual(result.bounds, {maxPages: null, attemptsPerPage: null, maxAttempts: null, aggregateAttemptSeconds: null});
  assert.deepEqual(codes(result), ['unknown-page-limit', 'unknown-retry-limit', 'unknown-timeout']);
  data.limits = {maxPages: 1, maxRetries: 0, timeoutSeconds: 1, maxAgeHours: 0};
  data.targets.push({...data.targets[0], id: 'page-b', url: 'https://docs.example.invalid/other'});
  assert.equal(review(data).status, 'exclude');
  assert.ok(codes(review(data)).includes('page-limit-exceeded'));
});

test('allowlist matches the exact invented host, not suffixes or wildcard permission', () => {
  const data = fixture(); data.targets[0].url = 'https://sub.docs.example.invalid/guide';
  assert.deepEqual(codes(review(data)), ['host-not-allowlisted']);
  assert.equal(review(data).status, 'exclude');
  data.targets[0].url = 'https://docs.example.invalid.attacker.invalid/guide';
  assert.equal(review(data).status, 'exclude');
  data.allowedHosts = ['*.example.invalid'];
  assert.throws(() => review(data), /host/);
});

test('personal fields exclude; unknown sensitivity cannot become nonpersonal', () => {
  const data = fixture(); data.fields[0].personal = true;
  assert.equal(review(data).status, 'exclude');
  assert.equal(review(data).targets[0].status, 'exclude');
  assert.deepEqual(codes(review(data)), ['personal-field-excluded']);
  data.fields[0].personal = null;
  assert.equal(review(data).status, 'needs-review');
  assert.deepEqual(codes(review(data)), ['unknown-field-sensitivity']);
});

test('sample quality differentiates missing evidence, empty samples, stale and defective observations', () => {
  const data = fixture(); data.targets[0].sample = null;
  assert.deepEqual(codes(review(data)), ['missing-quality-sample']);
  data.targets[0].sample = {records: 0, missingRequired: 0, duplicates: 0, ageHours: null};
  assert.deepEqual(codes(review(data)), ['empty-quality-sample', 'unknown-sample-age']);
  data.targets[0].sample = {records: 2, missingRequired: 1, duplicates: 1, ageHours: 25};
  assert.deepEqual(codes(review(data)), ['missing-required-fields', 'duplicate-records', 'stale-sample']);
  assert.equal(review(data).status, 'needs-review');
  data.targets[0].sample.ageHours = 24;
  assert.ok(!codes(review(data)).includes('stale-sample'));
});

test('zero retries and age are meaningful; missing fields and impossible counts are malformed', () => {
  const data = fixture(); data.limits.maxRetries = 0; data.limits.maxAgeHours = 0; data.targets[0].sample.ageHours = 0;
  assert.equal(review(data).status, 'candidate');
  assert.equal(review(data).bounds.maxAttempts, 2);
  data.limits.maxAgeHours = null;
  assert.equal(review(data).status, 'needs-review');
  delete data.limits.maxAgeHours;
  assert.throws(() => review(data), TypeError);
  const impossible = fixture(); impossible.targets[0].sample.duplicates = 3;
  assert.throws(() => review(impossible), TypeError);
});

test('closed finite JSON refuses secrets, real hosts, URL ambiguity and malformed values without network calls', () => {
  for (const value of [null, {}, '{', ' '.repeat(32769)]) assert.throws(() => reviewCollectionPlan(value), TypeError);
  for (const mutate of [
    d => {d.apiKey = 'not-accepted';}, d => {d.targets[0].token = 'not-accepted';},
    d => {d.targets[0].url = 'https://docs.example.invalid/guide?token=example';},
    d => {d.targets[0].url = 'https://user:pass@docs.example.invalid/guide';},
    d => {d.targets[0].url = 'https://docs.example.invalid/guide#secret';},
    d => {d.targets[0].url = 'http://docs.example.invalid/guide';},
    d => {d.targets[0].url = 'https://example.com/guide';},
    d => {d.allowedHosts = [];}, d => {d.limits.maxRetries = 4;},
    d => {d.limits.maxPages = 0;}, d => {d.limits.timeoutSeconds = 1.5;},
    d => {d.fields.push({...d.fields[0]});}, d => {d.targets.push({...d.targets[0]});},
  ]) { const data = fixture(); mutate(data); assert.throws(() => review(data), TypeError); }
  assert.throws(() => reviewCollectionPlan('é'.repeat(17000)), TypeError);
});

test('ordinary JSON last-member semantics and deterministic invented example never elevate claims', () => {
  const raw = JSON.stringify(fixture()).replace('"maxPages":2', '"maxPages":null,"maxPages":2');
  assert.equal(reviewCollectionPlan(raw).status, 'candidate');
  assert.deepEqual(reviewCollectionPlan(raw), reviewCollectionPlan(raw));
  const example = readFileSync(new URL('../pets/oxylabs/examples/fictional-collection.json', import.meta.url), 'utf8');
  assert.equal(reviewCollectionPlan(example).status, 'candidate');
  assert.equal(reviewCollectionPlan(example).boundary.collectionAuthorized, false);
});
