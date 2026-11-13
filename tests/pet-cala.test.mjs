import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {checkFieldProvenance, digestFictionalPayload} from '../pets/cala/provenance.mjs';

const fixtureText = readFileSync(new URL('../pets/cala/examples/field-provenance.json', import.meta.url), 'utf8');
const sample = () => JSON.parse(fixtureText);
const allIssues = report => [...report.issues, ...report.artifacts.flatMap(x => x.issues), ...report.fields.flatMap(x => x.issues)];
const hasCode = (report, code) => allIssues(report).some(x => x.code === code);
const reject = (input, code) => {
  const report = checkFieldProvenance(input);
  assert.equal(report.status, 'fail');
  if (code) assert.ok(hasCode(report, code), `missing issue ${code}: ${JSON.stringify(report)}`);
  return report;
};
function rebind(input) {
  const artifact = input.artifacts[0];
  artifact.sha256 = digestFictionalPayload({sourceTime: artifact.sourceTime, fields: artifact.fields});
  for (const claim of input.claims) {
    if (claim.source?.artifactId === artifact.id) Object.assign(claim.source, {
      sha256: artifact.sha256, sourceTime: artifact.sourceTime, observedTime: artifact.observedTime,
    });
  }
  return input;
}
function withValue(value, type) {
  const input = sample();
  input.claims = [input.claims[0]];
  input.claims[0].value = value;
  input.claims[0].type = type;
  input.artifacts[0].fields[input.claims[0].field] = value;
  return rebind(input);
}

test('fictional fixture binds three exact values to a digest and distinct source/observation times', () => {
  const input = sample();
  const report = checkFieldProvenance(input);
  assert.equal(report.status, 'consistent');
  assert.equal(report.fields.length, 3);
  assert.equal(report.artifacts.length, 1);
  assert.equal(allIssues(report).length, 0);
  for (const [i, field] of report.fields.entries()) {
    assert.equal(field.status, 'consistent');
    assert.equal(field.valueState, 'present');
    assert.deepEqual({...field.source}, input.claims[i].source);
  }
  assert.equal(report.sourceAuthenticated, false);
  assert.equal(report.truthVerified, false);
  assert.equal(report.connectorExecuted, false);
});

test('digest has an independently pinned byte encoding and ignores record key insertion order', () => {
  const canonical = '{"fields":{"prototype.active":false,"prototype.sensorCount":0,"prototype.status":"draft"},"sourceTime":"2026-11-01T09:00:00.000Z"}';
  const expected = `sha256:${createHash('sha256').update(canonical).digest('hex')}`;
  assert.equal(expected, 'sha256:bda9768de3f17957e14338d644fe0121e790254d5e9edf3212adddd48c1ade90');
  const artifact = sample().artifacts[0];
  assert.equal(digestFictionalPayload({fields: artifact.fields, sourceTime: artifact.sourceTime}), expected);
});

for (const [value, type] of [[0, 'number'], [false, 'boolean'], ['', 'string']]) {
  test(`present ${JSON.stringify(value)} is not confused with missing or null`, () => {
    const report = checkFieldProvenance(withValue(value, type));
    assert.equal(report.status, 'consistent');
    assert.equal(report.fields[0].valueState, 'present');
  });
}

test('explicit null is unknown; missing value is invalid, not implicitly null', () => {
  const input = withValue(null, 'number');
  const report = checkFieldProvenance(input);
  assert.equal(report.status, 'inconclusive');
  assert.equal(report.fields[0].valueState, 'null');
  assert.ok(hasCode(report, 'null-value'));
  delete input.claims[0].value;
  reject(input, 'missing-key');
});

for (const citation of ['omitted', null]) {
  test(`an ${citation === null ? 'explicit null' : 'omitted'} citation cannot establish a structured claim`, () => {
    const input = sample();
    if (citation === null) input.claims[0].source = null;
    else delete input.claims[0].source;
    const report = checkFieldProvenance(input);
    assert.equal(report.status, 'inconclusive');
    assert.ok(hasCode(report, 'uncited-field'));
  });
}

test('unknown artifact and absent exact field are inconclusive', () => {
  const input = sample();
  input.claims[0].source.artifactId = 'fictional:missing';
  assert.ok(hasCode(checkFieldProvenance(input), 'missing-artifact'));
  input.claims[0].source.artifactId = input.artifacts[0].id;
  delete input.artifacts[0].fields[input.claims[0].field];
  rebind(input);
  const report = checkFieldProvenance(input);
  assert.equal(report.status, 'inconclusive');
  assert.ok(hasCode(report, 'missing-source-field'));
});

test('a different field with the same value cannot substitute for the exact cited field', () => {
  const input = sample();
  input.artifacts[0].fields.otherCount = 0;
  input.claims[0].source.field = 'otherCount';
  reject(rebind(input), 'source-field-mismatch');
});

test('changed value or type fails even when a citation is present', () => {
  const input = sample();
  input.claims[0].value = 1;
  reject(input, 'value-mismatch');
  reject(withValue('0', 'number'), 'type-mismatch');
  reject(withValue([], 'object'), 'type-mismatch');
  reject(withValue({}, 'array'), 'type-mismatch');
});

test('objects compare by data while array order and negative zero remain distinct', () => {
  const input = withValue({width: 3, height: 2, labels: ['a', null]}, 'object');
  input.claims[0].value = {labels: ['a', null], height: 2, width: 3};
  assert.equal(checkFieldProvenance(input).status, 'consistent');
  const array = withValue(['a', 'b'], 'array');
  array.claims[0].value = ['b', 'a'];
  reject(array, 'value-mismatch');
  const zero = withValue(0, 'number');
  zero.claims[0].value = -0;
  reject(zero, 'value-mismatch');
});

for (const key of ['sourceTime', 'observedTime']) {
  test(`citation ${key} must exactly equal the selected artifact metadata`, () => {
    const input = sample();
    input.claims[0].source[key] = '2026-11-01T09:30:00.000Z';
    reject(input, key === 'sourceTime' ? 'source-time-mismatch' : 'observed-time-mismatch');
  });
  test(`null ${key} remains unknown`, () => {
    const input = sample();
    input.artifacts[0][key] = null;
    const report = checkFieldProvenance(rebind(input));
    assert.equal(report.status, 'inconclusive');
    assert.ok(hasCode(report, 'unknown-time'));
  });
}

test('fresh observation does not refresh an old source', () => {
  const input = sample();
  input.artifacts[0].sourceTime = '2026-10-31T09:00:00.000Z';
  input.artifacts[0].observedTime = input.asOf;
  reject(rebind(input), 'stale-source');
});

test('stale observation and chronology reversal fail', () => {
  const input = sample();
  input.artifacts[0].sourceTime = '2026-10-31T08:00:00.000Z';
  input.artifacts[0].observedTime = '2026-10-31T09:00:00.000Z';
  reject(rebind(input), 'stale-observation');
  input.artifacts[0].sourceTime = '2026-11-01T11:00:00.000Z';
  input.artifacts[0].observedTime = '2026-11-01T10:00:00.000Z';
  reject(rebind(input), 'source-after-observation');
});

for (const key of ['sourceTime', 'observedTime']) {
  test(`future ${key} fails relative to the explicit as-of time`, () => {
    const input = sample();
    input.artifacts[0][key] = '2026-11-01T13:00:00.000Z';
    reject(rebind(input), 'future-time');
  });
}

for (const invalid of ['2026-02-30T09:00:00.000Z', '2026-11-01', '2026-11-01T09:00:00Z',
  '2026-11-01T10:00:00.000+01:00', '2026-11-01T24:00:00.000Z', '', 0]) {
  test(`invalid time ${JSON.stringify(invalid)} is not coerced or normalized`, () => {
    const input = sample();
    input.artifacts[0].observedTime = invalid;
    input.claims[0].source.observedTime = invalid;
    reject(input, 'invalid-time');
  });
}

test('invalid as-of and fractional/unsafe/negative age limits are rejected', () => {
  for (const value of [null, '2026-02-30T00:00:00.000Z', 0]) {
    const input = sample(); input.asOf = value; reject(input, 'invalid-time');
  }
  for (const value of [-1, 0.5, Number.MAX_SAFE_INTEGER, '60']) {
    const input = sample(); input.maxAgeSeconds = value; reject(input, 'invalid-max-age');
  }
});

test('freshness boundaries are inclusive and zero means exact time, not default age', () => {
  const input = sample();
  input.maxAgeSeconds = 10800;
  assert.equal(checkFieldProvenance(input).status, 'consistent');
  input.maxAgeSeconds = 10799;
  reject(input, 'stale-source');
  input.maxAgeSeconds = 0;
  input.artifacts[0].sourceTime = input.asOf;
  input.artifacts[0].observedTime = input.asOf;
  assert.equal(checkFieldProvenance(rebind(input)).status, 'consistent');
});

test('the ISO epoch is a valid instant, not an absent or numeric timestamp', () => {
  const input = sample();
  input.asOf = '1970-01-01T00:00:00.000Z';
  input.artifacts[0].sourceTime = input.asOf;
  input.artifacts[0].observedTime = input.asOf;
  input.maxAgeSeconds = 0;
  assert.equal(checkFieldProvenance(rebind(input)).status, 'consistent');
});

test('artifact digest is recomputed, not accepted merely because both metadata strings agree', () => {
  const input = sample();
  input.artifacts[0].fields['prototype.sensorCount'] = 1;
  input.claims[0].value = 1;
  reject(input, 'artifact-digest-mismatch');
  assert.equal(checkFieldProvenance(rebind(input)).status, 'consistent');
  assert.equal(checkFieldProvenance(input).sourceAuthenticated, false);
  input.claims[0].source.sha256 = `sha256:${'0'.repeat(64)}`;
  reject(input, 'source-digest-mismatch');
});

test('duplicates, empty claims, unknown metadata and unsupported schema mode fail closed', () => {
  const duplicate = sample(); duplicate.artifacts.push(structuredClone(duplicate.artifacts[0]));
  reject(duplicate, 'duplicate-artifact');
  const repeated = sample(); repeated.claims.push(structuredClone(repeated.claims[0]));
  reject(repeated, 'duplicate-field');
  const empty = sample(); empty.claims = []; reject(empty, 'invalid-claim-count');
  for (const select of [x => x, x => x.artifacts[0], x => x.claims[0], x => x.claims[0].source]) {
    const input = sample(); select(input).unexpected = true; reject(input, 'unknown-key');
  }
  const live = sample(); live.mode = 'live'; reject(live, 'unsupported-mode');
  const version = sample(); version.schemaVersion = 2; reject(version, 'unsupported-schema');
});

test('literal field names, identifiers and digest format are validated without normalization', () => {
  for (const name of ['', ' prototype.sensorCount', '1count', '../count', 'a'.repeat(129)]) {
    const input = sample(); input.claims[0].field = name; reject(input, 'invalid-field-name');
  }
  const id = sample(); id.artifacts[0].id = 'real-account'; reject(id, 'invalid-artifact-id');
  const digest = sample(); digest.artifacts[0].sha256 = digest.artifacts[0].sha256.toUpperCase();
  reject(digest, 'invalid-digest');
  const required = sample(); delete required.artifacts[0].observedTime; reject(required, 'missing-key');
  const authority = sample(); authority.sourceAuthenticated = true;
  assert.equal(reject(authority, 'unknown-key').sourceAuthenticated, false);
});

test('an unused malformed artifact cannot be hidden behind a valid claim', () => {
  const input = sample();
  const unused = structuredClone(input.artifacts[0]);
  unused.id = 'fictional:unused'; unused.sha256 = `sha256:${'0'.repeat(64)}`;
  input.artifacts.push(unused);
  reject(input, 'artifact-digest-mismatch');
});

test('plain null-prototype records and frozen input are supported without mutation', () => {
  const input = sample();
  input.artifacts[0].fields = Object.assign(Object.create(null), input.artifacts[0].fields);
  const before = JSON.stringify(input);
  function freeze(value) { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); } }
  freeze(input);
  assert.deepEqual(checkFieldProvenance(input), checkFieldProvenance(input));
  assert.equal(checkFieldProvenance(input).status, 'consistent');
  assert.equal(JSON.stringify(input), before);
});

test('JSON keys resembling prototype or serialization hooks remain inert data', () => {
  const value = JSON.parse('{"__proto__":{"polluted":true},"constructor":"literal","toJSON":"literal"}');
  assert.equal(checkFieldProvenance(withValue(value, 'object')).status, 'consistent');
  assert.equal(Object.prototype.polluted, undefined);
});

for (const [name, value] of [['undefined', undefined], ['NaN', NaN], ['Infinity', Infinity],
  ['-Infinity', -Infinity], ['bigint', 1n], ['symbol', Symbol('value')], ['function', () => 1]]) {
  test(`non-JSON ${name} is rejected without coercion`, () => {
    const input = sample(); input.claims[0].value = value; reject(input, 'non-json-value');
  });
}

test('unsupported object and array prototypes are rejected', () => {
  for (const value of [new Date(), new Map(), new Set(), new Number(0), Object.create({inherited: 1})]) {
    const input = sample(); input.claims[0].value = value; reject(input, 'unsupported-prototype');
  }
  const input = sample(); Object.setPrototypeOf(input.claims, null); reject(input, 'unsupported-prototype');
});

test('accessors, toJSON and coercion hooks are never called', () => {
  let calls = 0;
  for (const place of ['root', 'value', 'array', 'unused']) {
    const input = sample();
    const getter = {enumerable: true, get() { calls++; throw Error('must not execute'); }};
    if (place === 'root') Object.defineProperty(input, 'claims', getter);
    if (place === 'value') Object.defineProperty(input.claims[0], 'value', getter);
    if (place === 'array') Object.defineProperty(input.claims, '0', getter);
    if (place === 'unused') Object.defineProperty(input.artifacts[0].fields, 'unused', getter);
    reject(input, 'accessor-property');
  }
  for (const key of ['toJSON', 'valueOf', 'toString']) {
    const input = sample(); input.claims[0].value = {[key]() { calls++; return 0; }};
    reject(input, 'non-json-value');
  }
  const hooked = sample();
  hooked.claims[0].value = {[Symbol.toPrimitive]() { calls++; return 0; }};
  reject(hooked, 'symbol-property');
  assert.equal(calls, 0);
});

test('hidden keys, symbols, sparse arrays and array extras cannot evade validation', () => {
  const hidden = sample(); Object.defineProperty(hidden.claims[0], 'hidden', {value: true});
  reject(hidden, 'non-enumerable-property');
  const symbol = sample(); symbol.claims[0][Symbol('hidden')] = 1; reject(symbol, 'symbol-property');
  const sparse = sample(); delete sparse.claims[1]; reject(sparse, 'sparse-array');
  const extra = sample(); extra.claims.toJSON = () => []; reject(extra, 'array-extra-property');
});

test('cycles, oversized data and unsupported roots fail without executing anything', () => {
  const cycle = sample(); cycle.claims[0].value = cycle; reject(cycle, 'cyclic-value');
  let nested = {}; for (let i = 0; i < 20; i++) nested = {nested};
  const deep = sample(); deep.claims[0].value = nested; reject(deep, 'input-limit');
  const long = sample(); long.claims[0].value = 'a'.repeat(131073); reject(long, 'input-limit');
  const wide = sample(); wide.claims = Array(257).fill(null); reject(wide, 'input-limit');
  for (const root of [null, 0, 'text', []]) reject(root, 'expected-record');
});

test('artifact, claim, nested-entry and total-node limits are enforced independently', () => {
  const artifacts = sample(); artifacts.artifacts = Array(33).fill(artifacts.artifacts[0]);
  reject(artifacts, 'invalid-artifact-count');
  const claims = sample(); claims.claims = Array(65).fill(claims.claims[0]);
  reject(claims, 'invalid-claim-count');
  const record = sample(); record.claims[0].value = Object.fromEntries(Array.from({length: 257}, (_, i) => [`k${i}`, i]));
  reject(record, 'input-limit');
  const nodes = sample(); nodes.claims[0].value = Array.from({length: 64}, () => Array(128).fill(0));
  reject(nodes, 'input-limit');
});

test('Proxy inputs are outside the data contract and detected Proxies are rejected before traps', () => {
  let calls = 0;
  const input = new Proxy(sample(), {
    getPrototypeOf() { calls++; throw Error('must not execute'); },
    ownKeys() { calls++; throw Error('must not execute'); },
    get() { calls++; throw Error('must not execute'); },
  });
  reject(input, 'unsupported-proxy');
  assert.equal(calls, 0);
});

test('digest helper rejects unsupported/unknown data instead of invoking serialization hooks', () => {
  let calls = 0;
  assert.throws(() => digestFictionalPayload({sourceTime: null, fields: {}, unexpected: 1}), /unknown-key/);
  assert.throws(() => digestFictionalPayload({sourceTime: null, fields: {toJSON() { calls++; return {}; }}}), /non-json-value/);
  assert.equal(calls, 0);
});

test('all six authored Cala behavioral evals remain byte-exact, not reported as model executions', () => {
  const bytes = readFileSync(new URL('../pets/cala/evals.json', import.meta.url));
  assert.equal(createHash('sha256').update(bytes).digest('hex'), '7057faf20b21ad8a1a2fcbae0bf4fd2e8518317687b4d8b82eb477ae3508b47b');
  assert.equal(JSON.parse(bytes).cases.length, 6);
});
