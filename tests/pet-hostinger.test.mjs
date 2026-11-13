import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {reviewDnsSnapshot} from '../pets/hostinger/dns-review.mjs';

const a = (value = '192.0.2.10', ttlSeconds = 300) => ({type: 'A', value, ttlSeconds});
const cname = (value = 'origin.launch.example', ttlSeconds = 300) => ({type: 'CNAME', value, ttlSeconds});
const input = (authoritative = [a()], recursive = [a()]) => ({schemaVersion: 1, scenario: 'fictional', owner: 'www.launch.example', authoritative, recursive});
const review = value => reviewDnsSnapshot(JSON.stringify(value));

test('matching identities ignore order and cross-view TTL differences without claiming health', () => {
  const result = review(input([a(), a('198.51.100.9')], [a('198.51.100.9', 0), a('192.0.2.10', 0)]));
  assert.equal(result.comparison, 'matching-supplied-records');
  assert.deepEqual(result.hypotheses, []);
  assert.equal(result.liveDnsVerified, false);
  assert.equal(result.accountAccessed, false);
  assert.equal(result.networkAccessed, false);
  assert.equal(result.diagnosis, 'not-established');
  assert.deepEqual(result.observations.recursive.knownTtlSeconds, [0]);
});

test('different supplied views produce only an unconfirmed hypothesis and read-only next checks', () => {
  const result = review(input([a()], [a('203.0.113.40')]));
  assert.equal(result.comparison, 'different-supplied-records');
  assert.deepEqual(result.hypotheses.map(x => [x.id, x.status]), [['view-or-time-difference', 'unconfirmed']]);
  assert.equal(result.nextChecks.every(x => x.executed === false && x.effect === 'read-only'), true);
  assert.match(result.limitations.join(' '), /not prove cache/);
});

test('null views, empty views and supplied records remain distinct', () => {
  assert.equal(review(input(null, [a()])).observations.authoritative.state, 'not-supplied');
  const empty = review(input([], []));
  assert.equal(empty.observations.authoritative.state, 'supplied-empty');
  assert.equal(empty.comparison, 'unknown');
  assert.equal(review(input([], [a()])).comparison, 'different-supplied-records');
  assert.equal(review(input(null, [])).comparison, 'unknown');
  assert.match(empty.limitations.join(' '), /NXDOMAIN/);
});

test('CNAME and address co-occurrence blocks a clean comparison', () => {
  const result = review(input([cname(), a()], [cname(), a()]));
  assert.equal(result.comparison, 'input-conflict');
  assert.deepEqual(result.findings.map(x => [x.view, x.code]), [['authoritative', 'cname-with-address'], ['recursive', 'cname-with-address']]);
  assert.equal(result.hypotheses[0].status, 'unconfirmed');
});

test('multiple canonical targets conflict; identical repeated records are preserved as duplicates', () => {
  const result = review(input([cname(), cname('other.launch.example')], null));
  assert.equal(result.comparison, 'input-conflict');
  assert.equal(result.findings[0].code, 'multiple-cname-targets');
  const duplicates = review(input([cname(), cname()], [cname()]));
  assert.equal(duplicates.comparison, 'matching-supplied-records');
  assert.equal(duplicates.observations.authoritative.recordCount, 2);
  assert.equal(duplicates.observations.authoritative.duplicateRecordCount, 1);
  assert.deepEqual(duplicates.findings, []);
});

test('TTL disagreement inside a supplied RRset is a conflict, not a cache countdown diagnosis', () => {
  const result = review(input([a('192.0.2.10', 0), a('192.0.2.11', 300)], [a()]));
  assert.equal(result.findings[0].code, 'mixed-ttl-within-rrset');
  assert.equal(result.comparison, 'input-conflict');
  assert.deepEqual(result.observations.authoritative.knownTtlSeconds, [0, 300]);
});

test('unknown TTL is not zero, and numeric TTL boundaries are enforced', () => {
  const result = review(input([a('192.0.2.10', null)], [a('192.0.2.10', 0)]));
  assert.equal(result.comparison, 'matching-supplied-records');
  assert.equal(result.observations.authoritative.unknownTtlCount, 1);
  assert.deepEqual(result.observations.authoritative.knownTtlSeconds, []);
  assert.equal(review(input([a('192.0.2.10', 2147483647)])).observations.authoritative.unknownTtlCount, 0);
  for (const ttl of [-1, 0.5, 2147483648, '300', false]) assert.throws(() => review(input([a('192.0.2.10', ttl)])), /ttlSeconds/);
  const missing = a(); delete missing.ttlSeconds;
  assert.throws(() => review(input([missing])), /record fields/);
});

test('self-referencing CNAME is detected without resolving any remote chain', () => {
  const result = review(input([cname('www.launch.example')], null));
  assert.equal(result.comparison, 'input-conflict');
  assert.equal(result.findings[0].code, 'self-cname');
  assert.equal(result.networkAccessed, false);
});

test('strict input shape rejects unsupported claims, extra keys and missing view evidence', () => {
  for (const extra of ['apiSuccess', 'deployed', '__proto__', 'accountId']) {
    const value = input(); Object.defineProperty(value, extra, {value: true, enumerable: true});
    assert.throws(() => review(value), /snapshot fields/);
  }
  const missing = input(); delete missing.recursive;
  assert.throws(() => review(missing), /snapshot fields/);
  assert.throws(() => review({...input(), scenario: 'production'}), /fictional/);
  assert.throws(() => review({...input(), schemaVersion: 2}), /schemaVersion/);
  assert.throws(() => review(input([{...a(), owner: 'elsewhere.example'}])), /record fields/);
});

test('only canonical fictional names and documentation IPv4 addresses are accepted', () => {
  for (const owner of ['example', 'hostinger.com', 'www.launch.example\n', 'WWW.launch.example', 'www.launch.example.', 'https://launch.example', '-bad.example', 'x'.repeat(64) + '.example']) {
    assert.throws(() => review({...input(), owner}), /fictional name/);
  }
  for (const ip of ['8.8.8.8', '192.0.2.256', '192.0.2.01', '192.0.2.1\n', '192.0.2.1;run', null]) assert.throws(() => review(input([a(ip)])), /documentation IPv4/);
  assert.throws(() => review(input([cname('origin.real.com')])), /fictional name/);
  assert.throws(() => review(input([{...a(), type: 'AAAA'}])), /record type/);
});

test('text, array and byte bounds reject malformed or oversized data without invoking object hooks', () => {
  let called = false;
  assert.throws(() => reviewDnsSnapshot({toString() { called = true; return '{}'; }}), /JSON text/);
  assert.equal(called, false);
  for (const text of ['', '{', 'null', '[]', '1']) assert.throws(() => reviewDnsSnapshot(text));
  assert.throws(() => reviewDnsSnapshot(' '.repeat(32769)), /32768/);
  assert.throws(() => review(input(Array.from({length: 17}, () => a()))), /16 records/);
  assert.doesNotThrow(() => review(input(Array.from({length: 16}, () => a()))));
  assert.throws(() => review(input({records: []})), /16 records/);
});

test('the fictional example deterministically reports the provided mismatch only', async () => {
  const text = await readFile(new URL('../pets/hostinger/example.json', import.meta.url), 'utf8');
  const result = reviewDnsSnapshot(text);
  assert.deepEqual(reviewDnsSnapshot(text), result);
  assert.equal(result.comparison, 'different-supplied-records');
  assert.equal(result.owner, 'www.launch.example');
  assert.equal(result.diagnosis, 'not-established');
});
