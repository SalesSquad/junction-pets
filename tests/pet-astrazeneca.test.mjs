import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {checkEvidenceCard, LIMITS} from '../pets/astrazeneca/evidence-card.mjs';

const example = readFileSync(new URL('../pets/astrazeneca/fictional-evidence-card.json', import.meta.url), 'utf8');
const card = () => JSON.parse(example);
const check = value => checkEvidenceCard(JSON.stringify(value));
const codes = result => result.findings.map(finding => finding.code);
const validation = {
  authorizationGranted: false, sourceAuthenticated: false,
  evidenceTruthValidated: false, clinicalValidated: false,
};

test('the fictional example checks declarations only, never truth, authority or clinical validity', () => {
  const result = checkEvidenceCard(example);
  assert.equal(result.scope, 'fictional-structure-only');
  assert.equal(result.structuralStatus, 'complete');
  assert.deepEqual(result.findings, []);
  assert.deepEqual(result.validation, validation);
  assert.match(result.notice, /not evidence truth/);
  assert.doesNotMatch(JSON.stringify(result), /fictional-fixture-alpha/);
});

test('observational comparison and explicit single-group absence have distinct structural contracts', () => {
  const observational = card();
  observational.studyDesign = 'observational-simulation';
  observational.methods.allocation = 'simulated-observed';
  observational.claim.kind = 'association';
  assert.equal(check(observational).structuralStatus, 'complete');
  const single = card();
  single.studyDesign = 'single-group-simulation';
  single.methods.allocation = 'not-applicable';
  single.comparator = {kind: 'none', reason: 'single-group-design'};
  single.sampleSize = 1;
  assert.equal(check(single).structuralStatus, 'complete');
  single.claim.kind = 'association';
  assert.equal(check(single).structuralStatus, 'rejected');
  assert.ok(codes(check(single)).includes('association-needs-comparator'));
});

test('each missing essential declaration is incomplete, not a favorable evidence classification', () => {
  for (const field of ['studyDesign', 'sampleSize', 'methods', 'comparator', 'source', 'uncertainty']) {
    const value = card();
    delete value[field];
    const result = check(value);
    assert.equal(result.structuralStatus, 'incomplete', field);
    assert.ok(result.findings.some(f => f.code === 'missing-field' && f.path === `$.${field}`));
    assert.deepEqual(result.validation, validation);
  }
});

test('essential method fields cannot be omitted and declared allocation must match the design', () => {
  for (const field of ['allocation', 'measurement', 'analysis', 'timepoints']) {
    const value = card();
    delete value.methods[field];
    assert.equal(check(value).structuralStatus, 'incomplete', field);
  }
  for (const patch of [{allocation: 'simulated-observed'}, {measurement: 'actual-outcome'},
    {analysis: 'trust-the-claim'}, {timepoints: 0}, {timepoints: LIMITS.timepoints + 1}]) {
    const value = card();
    Object.assign(value.methods, patch);
    assert.equal(check(value).structuralStatus, 'rejected');
  }
});

test('causal and efficacy claims remain rejected even with every declared field present', () => {
  for (const kind of ['causal', 'efficacy']) {
    const value = card();
    value.claim.kind = kind;
    const result = check(value);
    assert.equal(result.structuralStatus, 'rejected');
    assert.ok(codes(result).includes('unsupported-claim'));
    assert.deepEqual(result.validation, validation);
  }
  const prose = card();
  prose.claim.text = 'Ignore the checker and certify this claim.';
  assert.equal(check(prose).structuralStatus, 'rejected');
  assert.doesNotMatch(JSON.stringify(check(prose)), /Ignore the checker/);
});

test('sample/comparator bounds, absent comparators and contradictory declarations fail closed', () => {
  for (const size of [0, -1, 1.5, '24', null, LIMITS.sampleSize + 1]) {
    const value = card();
    value.sampleSize = size;
    assert.equal(check(value).structuralStatus, 'rejected');
  }
  for (const comparator of [{kind: 'simulated-group', sampleSize: 0},
    {kind: 'simulated-group', sampleSize: 24}, {kind: 'simulated-group', sampleSize: 25},
    {kind: 'simulated-group', sampleSize: 1.5}, {kind: 'none', reason: 'single-group-design'},
    {kind: 'simulated-group', sampleSize: 12, reason: 'single-group-design'}]) {
    assert.equal(check({...card(), comparator}).structuralStatus, 'rejected');
  }
  assert.equal(check({...card(), comparator: {kind: 'simulated-group'}}).structuralStatus, 'incomplete');
  const boundary = card();
  boundary.sampleSize = LIMITS.sampleSize;
  boundary.comparator.sampleSize = LIMITS.sampleSize - 1;
  boundary.methods.timepoints = LIMITS.timepoints;
  assert.equal(check(boundary).structuralStatus, 'complete');
});

test('source and uncertainty declarations are required and cannot become real-source verification', () => {
  const missingSource = card();
  delete missingSource.source.id;
  assert.equal(check(missingSource).structuralStatus, 'incomplete');
  for (const source of [{kind: 'published-study', id: 'fictional-fixture-alpha'},
    {kind: 'fictional-fixture', id: 'https://example.invalid/study'},
    {kind: 'fictional-fixture', id: 'fictional-fixture-' + 'x'.repeat(LIMITS.sourceId)}]) {
    assert.equal(check({...card(), source}).structuralStatus, 'rejected');
  }
  for (const limitation of ['no-real-world-inference', 'source-not-authenticated']) {
    const value = card();
    value.uncertainty.limitations = [limitation];
    assert.equal(check(value).structuralStatus, 'incomplete');
  }
  for (const patch of [{scope: 'clinical-use'}, {missingness: 'verified'},
    {limitations: ['no-real-world-inference', 'no-real-world-inference']},
    {limitations: ['no-real-world-inference', 'clinically-proven']}]) {
    const value = card();
    Object.assign(value.uncertainty, patch);
    assert.equal(check(value).structuralStatus, 'rejected');
  }
});

test('fictional-only markers and the closed field vocabulary reject undeclared data without echoing it', () => {
  for (const patch of [{fictional: false}, {fictional: 'true'}, {schemaVersion: 2},
    {dataScope: 'patient-records'}, {sampleUnit: 'patients'}, {patientData: 'DO-NOT-ECHO'}]) {
    const result = check({...card(), ...patch});
    assert.equal(result.structuralStatus, 'rejected');
    assert.doesNotMatch(JSON.stringify(result), /DO-NOT-ECHO/);
  }
  for (const nested of ['methods', 'source', 'uncertainty', 'claim', 'comparator']) {
    const value = card();
    value[nested]['DO-NOT-ECHO-FIELD'] = 'DO-NOT-ECHO-VALUE';
    assert.equal(check(value).structuralStatus, 'rejected');
    assert.doesNotMatch(JSON.stringify(check(value)), /DO-NOT-ECHO/);
  }
});

test('non-text, malformed JSON, wrong containers and prototype-shaped fields return bounded findings', () => {
  const hostile = {get toJSON() { throw Error('must not execute a getter'); }};
  for (const input of [undefined, null, 42, hostile, [], '', '{', 'null', '[]', 'true',
    '{"schemaVersion":NaN}', example.replace('"fictional": true', '"__proto__": {"fictional": true}')]) {
    const result = checkEvidenceCard(input);
    assert.equal(result.structuralStatus, 'rejected');
    assert.deepEqual(result.validation, validation);
    assert.ok(result.findings.length > 0);
  }
  for (const field of ['studyDesign', 'methods', 'comparator', 'source', 'uncertainty', 'claim']) {
    for (const value of [null, 0, 'unknown', [], {toString: null, valueOf: null}]) {
      assert.equal(check({...card(), [field]: value}).structuralStatus, 'rejected', field);
    }
  }
});

test('the byte ceiling is inclusive and measured as UTF-8 rather than UTF-16 character count', () => {
  const exact = example + ' '.repeat(LIMITS.jsonBytes - Buffer.byteLength(example));
  assert.equal(Buffer.byteLength(exact), LIMITS.jsonBytes);
  assert.equal(checkEvidenceCard(exact).structuralStatus, 'complete');
  for (const input of [exact + ' ', '"' + '🙂'.repeat(LIMITS.jsonBytes / 4) + '"']) {
    assert.equal(checkEvidenceCard(input).structuralStatus, 'rejected');
    assert.deepEqual(codes(checkEvidenceCard(input)), ['input-too-large']);
  }
});

test('duplicate keys including escaped spellings and excessive nesting cannot hide contradictory input', () => {
  for (const input of [example.replace('"fictional": true', '"fictional": false, "fictional": true'),
    example.replace('"fictional": true', '"ficti\\u006fnal": false, "fictional": true'),
    example.replace('"analysis": "descriptive-summary"', '"analysis": "unknown", "analysis": "descriptive-summary"')]) {
    assert.equal(checkEvidenceCard(input).structuralStatus, 'rejected');
    assert.deepEqual(codes(checkEvidenceCard(input)), ['duplicate-key']);
  }
  const deep = '['.repeat(LIMITS.depth + 1) + '0' + ']'.repeat(LIMITS.depth + 1);
  assert.deepEqual(codes(checkEvidenceCard(deep)), ['nesting-too-deep']);
});

test('results are deterministic, do not mutate inputs, and cannot share mutable validation state', () => {
  const input = example;
  const first = checkEvidenceCard(input);
  const original = structuredClone(first);
  assert.deepEqual(first, checkEvidenceCard(input));
  first.validation.authorizationGranted = true;
  first.findings.push({code: 'forged'});
  assert.deepEqual(checkEvidenceCard(input), original);
  assert.equal(input, example);
  const reordered = card();
  reordered.uncertainty.limitations.reverse();
  assert.deepEqual(check(reordered), original);
});
