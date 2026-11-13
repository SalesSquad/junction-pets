import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {reviewFictionalSms} from '../pets/s-pankki/sms-guidance.mjs';

const fixture = () => ({
  schemaVersion: 1, kind: 'fictional-sms-safety-scenario', scenarioId: 'fictional-message-a',
  cues: {urgentDeadline: false, messageLink: false, credentialRequest: false, paymentRequest: false, attachment: false, displayNameMatch: false},
  outsideCheck: 'reported-match', requestedAction: 'guidance',
});
const run = input => reviewFictionalSms(JSON.stringify(input));

test('fictional positive cues produce an exact bounded guidance report, never a fraud verdict', () => {
  const input = fixture();
  input.cues.urgentDeadline = true;
  input.cues.credentialRequest = true;
  input.cues.messageLink = true;
  input.outsideCheck = 'unknown';
  const result = run(input);
  assert.equal(result.classification, 'declared-warning-signs');
  assert.deepEqual(result.warningSigns, [
    {code: 'declared-urgent-deadline', field: 'cues.urgentDeadline'},
    {code: 'declared-message-link', field: 'cues.messageLink'},
    {code: 'declared-credential-request', field: 'cues.credentialRequest'},
  ]);
  assert.deepEqual(result.unknownFields, ['outsideCheck']);
  assert.deepEqual(result.boundary, {synthetic: true, senderAuthenticated: false, fraudDetermined: false, accountAccessed: false, financialActionExecuted: false});
  assert.equal(result.action, 'guidance-only');
  assert.equal(result.deniedAction, null);
});

test('no listed warnings, branding and a reported match cannot authenticate or declare a message safe', () => {
  const input = fixture();
  input.cues.displayNameMatch = true;
  const result = run(input);
  assert.equal(result.classification, 'no-listed-warning-declared');
  assert.deepEqual(result.warningSigns, []);
  assert.deepEqual(result.unknownFields, []);
  assert.deepEqual(result.notes, ['branding-is-not-authentication', 'outside-check-is-an-unverified-declaration']);
  assert.equal(result.boundary.senderAuthenticated, false);
  assert.equal(result.boundary.fraudDetermined, false);
  assert.deepEqual(result.guidance, ['do-not-follow-message-links-or-attachments', 'do-not-share-credentials-or-codes', 'verify-through-independently-reached-official-channel']);
});

test('explicit unknown cues and null check are preserved, not treated as false or verified', () => {
  const input = fixture();
  input.cues.messageLink = null;
  input.cues.paymentRequest = null;
  input.outsideCheck = null;
  const result = run(input);
  assert.equal(result.classification, 'incomplete-declarations');
  assert.deepEqual(result.unknownFields, ['cues.messageLink', 'cues.paymentRequest', 'outsideCheck']);
  input.cues.urgentDeadline = true;
  assert.equal(run(input).classification, 'declared-warning-signs');
  assert.deepEqual(run(input).unknownFields, result.unknownFields);
  delete input.cues.messageLink;
  assert.throws(() => run(input), /cues fields/);
});

test('each listed risk cue and a reported outside mismatch stays an explicit unverified warning', () => {
  for (const [field, code] of [
    ['urgentDeadline', 'declared-urgent-deadline'], ['messageLink', 'declared-message-link'],
    ['credentialRequest', 'declared-credential-request'], ['paymentRequest', 'declared-payment-request'],
    ['attachment', 'declared-attachment'],
  ]) {
    const input = fixture(); input.cues[field] = true;
    assert.deepEqual(run(input).warningSigns, [{code, field: `cues.${field}`}]);
  }
  const input = fixture(); input.outsideCheck = 'reported-mismatch';
  assert.deepEqual(run(input).warningSigns, [{code: 'reported-outside-mismatch', field: 'outsideCheck'}]);
  assert.equal(run(input).boundary.fraudDetermined, false);
});

test('link opening, account login, payments and authenticity confirmation are refused even with benign declarations', () => {
  for (const requestedAction of ['open-link', 'account-login', 'make-payment', 'confirm-authenticity']) {
    const input = fixture(); input.requestedAction = requestedAction;
    const result = run(input);
    assert.equal(result.action, 'guidance-only');
    assert.equal(result.deniedAction, requestedAction);
    assert.equal(result.boundary.senderAuthenticated, false);
    assert.equal(result.boundary.accountAccessed, false);
    assert.equal(result.boundary.financialActionExecuted, false);
  }
});

test('closed scenario input refuses real message text, credentials, URLs and fabricated authority fields', () => {
  const mutations = [
    x => {x.messageText = 'not accepted';}, x => {x.credentials = 'not accepted';},
    x => {x.url = 'https://example.invalid';}, x => {x.senderAuthenticated = true;},
    x => {x.cues.authenticated = true;}, x => {x.kind = 'production-message';},
    x => {x.outsideCheck = 'verified';}, x => {x.requestedAction = 'execute';},
    x => {x.scenarioId = 'actual-account';}, x => {x.scenarioId += '\n';},
  ];
  for (const change of mutations) { const input = fixture(); change(input); assert.throws(() => run(input), TypeError); }
});

test('bounded primitive JSON and exact boolean-or-null cues reject malformed or coerced input', () => {
  for (const text of [null, {}, [], new String('{}'), '{', ' '.repeat(8193), 'é'.repeat(4097)]) {
    assert.throws(() => reviewFictionalSms(text), TypeError);
  }
  for (const value of [0, 1, 'false', [], {}]) {
    const input = fixture(); input.cues.messageLink = value;
    assert.throws(() => run(input), TypeError);
  }
  const input = fixture(); input.schemaVersion = 1.5;
  assert.throws(() => run(input), TypeError);
  delete input.schemaVersion;
  assert.throws(() => run(input), TypeError);
});

test('ordinary JSON last-member semantics are explicit and prototype-shaped data cannot expand the contract', () => {
  const raw = JSON.stringify(fixture());
  const duplicate = raw.replace('"messageLink":false', '"messageLink":true,"messageLink":false');
  assert.equal(reviewFictionalSms(duplicate).classification, 'no-listed-warning-declared');
  assert.throws(() => reviewFictionalSms(raw.replace('"schemaVersion":1', '"schemaVersion":1,"__proto__":{"polluted":true}')), TypeError);
  assert.equal({}.polluted, undefined);
});

test('output and guidance are deterministic, order-independent and isolated between calls', () => {
  const input = fixture();
  const before = JSON.stringify(input), result = run(input);
  input.cues = Object.fromEntries(Object.entries(input.cues).reverse());
  assert.deepEqual(run(input), result);
  result.guidance.push('tamper'); result.warningSigns.push({code: 'tamper', field: 'tamper'});
  assert.deepEqual(reviewFictionalSms(before), run(input));
  assert.equal(JSON.stringify(fixture()), before);
});

test('checked-in invented example uses the exact public contract without real SMS or account data', () => {
  const text = readFileSync(new URL('../pets/s-pankki/example-sms.json', import.meta.url), 'utf8');
  const result = reviewFictionalSms(text);
  assert.equal(result.classification, 'declared-warning-signs');
  assert.equal(result.deniedAction, 'confirm-authenticity');
  assert.match(result.scenarioId, /^fictional-/);
  assert.equal(result.boundary.senderAuthenticated, false);
});
