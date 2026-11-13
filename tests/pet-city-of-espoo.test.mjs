import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {checkServiceRouting} from '../pets/city-of-espoo/service-routing.mjs';

const raw = readFileSync(new URL('../pets/city-of-espoo/example.json', import.meta.url), 'utf8');
const fixture = () => JSON.parse(raw);
const runMutation = mutate => {const input = fixture(); mutate(input); return checkServiceRouting(input);};
function boundaries(result) {
  assert.equal(result.synthetic, true);
  for (const key of ['realServiceAvailabilityVerified', 'accessibilityCertified', 'sourceFetched', 'authorization', 'companyEndorsed']) assert.equal(result[key], false, key);
}
function invalid(input) {
  const result = checkServiceRouting(input);
  assert.equal(result.status, 'invalid');
  assert.equal(result.serviceId, null);
  assert.equal(result.card, null);
  assert.equal(result.fallback, null);
  boundaries(result);
}

test('FI fixture routes an exact invented identifier with accessible text and explicit unknowns', () => {
  const input = fixture(), result = checkServiceRouting(input);
  assert.equal(result.status, 'routed-fictional');
  assert.equal(result.language, 'fi');
  assert.equal(result.serviceId, 'fictional-reading-room');
  assert.equal(result.card.title, input.services[0].localizations.fi.title);
  assert.equal(result.card.accessibleText, input.services[0].channels[0].accessibleText.fi);
  assert.equal(result.card.channelId, 'plain-text');
  assert.equal(result.sourceAgeHours, 24);
  assert.deepEqual(result.card.unknowns, input.services[0].localizations.fi.unknowns);
  assert.deepEqual(result.issues, []);
  assert.equal(result.fallback, null);
  boundaries(result);
});

test('EN uses the same identifier, matching language and localized text', () => {
  const input = fixture(); input.request.language = 'en';
  const result = checkServiceRouting(input);
  assert.equal(result.status, 'routed-fictional');
  assert.equal(result.language, 'en');
  assert.equal(result.card.title, input.services[0].localizations.en.title);
  assert.equal(result.card.accessibleText, input.services[0].channels[0].accessibleText.en);
  assert.equal(result.card.source.url, input.services[0].source.url);
  boundaries(result);
});

test('unknown exact identifier never guesses a service and retains FI/EN plain-text fallback', () => {
  for (const language of ['fi', 'en']) {
    const input = fixture(); input.request = {language, serviceId: 'fictional-unknown'};
    const result = checkServiceRouting(input);
    assert.equal(result.status, 'unknown-service');
    assert.equal(result.serviceId, null);
    assert.equal(result.card, null);
    assert.equal(result.sourceAgeHours, null);
    assert.equal(result.fallback.action, 'ask-for-service-detail');
    assert.equal(result.fallback.serviceId, null);
    assert.equal(result.fallback.message, input.unknownFallback.localizations[language].message);
    boundaries(result);
  }
});

test('unknown fallback cannot silently route, change action or substitute a localized service ID', () => {
  for (const mutate of [
    x => x.unknownFallback.serviceId = x.services[0].id,
    x => x.unknownFallback.action = 'route-to-nearest-service',
    x => x.unknownFallback.localizations.fi.serviceId = x.services[0].id,
    x => x.unknownFallback.localizations.en.language = 'fi',
    x => x.unknownFallback.localizations.en.nextStep = ' ',
  ]) {const input = fixture(); input.request.serviceId = 'fictional-unknown'; mutate(input); invalid(input);}
});

test('all required root, request, service, source and fallback fields are required even when null is allowed', () => {
  const selectors = [x => x, x => x.request, x => x.services[0], x => x.services[0].source, x => x.unknownFallback];
  for (const select of selectors) for (const key of Object.keys(select(fixture()))) {
    const input = fixture(); delete select(input)[key]; invalid(input);
  }
});

test('both localizations require all parity keys including every unknown and accessible-text language', () => {
  for (const language of ['fi', 'en']) {
    const selectors = [x => x.services[0].localizations[language], x => x.services[0].localizations[language].unknowns, x => x.unknownFallback.localizations[language]];
    for (const select of selectors) for (const key of Object.keys(select(fixture()))) {
      const input = fixture(); delete select(input)[key]; invalid(input);
    }
    for (const select of [x => x.services[0].localizations, x => x.unknownFallback.localizations, x => x.services[0].channels[0].accessibleText]) {
      const input = fixture(); delete select(input)[language]; invalid(input);
    }
  }
});

test('localized IDs and language declarations must match, and no implicit language fallback exists', () => {
  for (const language of ['fi', 'en']) for (const key of ['language', 'serviceId']) {
    const input = fixture(); input.services[0].localizations[language][key] = key === 'language' ? 'sv' : 'fictional-other'; invalid(input);
  }
  for (const value of ['FI', 'sv', '', 0, null, undefined]) {const input = fixture(); input.request.language = value; invalid(input);}
});

test('timestamps require exact real UTC instants, not parseable-but-normalized dates or types', () => {
  for (const field of ['asOf', 'checkedAt']) for (const value of [null, 0, undefined, '', '2026-11-13', '2026-02-30T12:00:00.000Z', '2026-11-13T25:00:00.000Z', '2026-11-13T12:00:00Z', '2026-11-13T12:00:00.000+00:00', 'not-a-date']) {
    if (field === 'checkedAt' && value === null) continue;
    const input = fixture(); (field === 'asOf' ? input : input.services[0].source)[field] = value; invalid(input);
  }
  const future = fixture(); future.services[0].source.checkedAt = '2026-11-13T12:00:00.001Z'; invalid(future);
});

test('freshness boundary is inclusive; zero, null, missing and stale are distinct', () => {
  assert.equal(runMutation(x => x.maxSourceAgeHours = 24).status, 'routed-fictional');
  const stale = runMutation(x => x.maxSourceAgeHours = 23);
  assert.equal(stale.status, 'needs-review'); assert.deepEqual(stale.issues, ['stale-source']); assert.equal(stale.card, null);
  assert.equal(runMutation(x => {x.maxSourceAgeHours = 0; x.services[0].source.checkedAt = x.asOf;}).status, 'routed-fictional');
  assert.equal(runMutation(x => x.maxSourceAgeHours = 0).status, 'needs-review');
  const unknown = runMutation(x => x.services[0].source.checkedAt = null);
  assert.equal(unknown.status, 'needs-review'); assert.deepEqual(unknown.issues, ['unknown-source-time']); assert.equal(unknown.sourceAgeHours, null);
  assert.equal(unknown.fallback.action, 'verify-official-guidance'); assert.equal(unknown.fallback.serviceId, null);
  for (const value of [null, undefined, -1, 0.5, 721, '24', NaN, Infinity]) {const input = fixture(); input.maxSourceAgeHours = value; invalid(input);}
});

test('source URLs are canonical credential-free synthetic HTTPS references, never live or unsafe links', () => {
  for (const url of ['', 'not-a-url', '/relative', 'http://fixtures.example.invalid/a', 'javascript:alert(1)', 'https://www.espoo.fi/en', 'https://fixtures.example.invalid.evil.test/a', 'https://user:pass@fixtures.example.invalid/a', 'https://fixtures.example.invalid/a?resident=1', 'https://fixtures.example.invalid/a#token', ' https://fixtures.example.invalid/a', 'https://fixtures.example.invalid:8443/a', 'https://fixtures.example.invalid/a/../b', 0, false]) {
    const input = fixture(); input.services[0].source.url = url; invalid(input);
  }
  const unknown = runMutation(x => x.services[0].source.url = null);
  assert.equal(unknown.status, 'needs-review'); assert.deepEqual(unknown.issues, ['unknown-source-url']); assert.equal(unknown.card, null);
  const sourceClaim = fixture(); sourceClaim.services[0].source.kind = 'verified-official'; invalid(sourceClaim);
});

test('inaccessible-only media and incomplete bilingual text cannot yield a route', () => {
  for (const kind of ['text', 'image', 'audio', 'video']) {
    const input = fixture(); input.services[0].channels = [{id: 'media-only', kind, accessibleText: {fi: null, en: null}}];
    const result = checkServiceRouting(input);
    assert.equal(result.status, 'needs-review'); assert.deepEqual(result.issues, ['no-accessible-text-channel']); assert.equal(result.card, null);
    boundaries(result);
  }
  for (const language of ['fi', 'en']) {
    const result = runMutation(x => x.services[0].channels[0].accessibleText[language] = null);
    assert.equal(result.status, 'needs-review');
  }
});

test('equivalent FI/EN text on a media channel is a structural alternative, never accessibility certification', () => {
  const result = runMutation(x => x.services[0].channels[0].kind = 'video');
  assert.equal(result.status, 'routed-fictional'); boundaries(result);
  const input = fixture(); input.services[0].channels.unshift({id: 'image-only', kind: 'image', accessibleText: {fi: null, en: null}});
  assert.equal(checkServiceRouting(input).card.channelId, 'plain-text');
});

test('duplicate IDs, empty collections, unsupported channel kinds and blank guidance fail closed', () => {
  for (const mutate of [
    x => x.services.push(structuredClone(x.services[0])),
    x => x.services[0].channels.push(structuredClone(x.services[0].channels[0])),
    x => x.services = [], x => x.services[0].channels = [],
    x => x.services[0].channels[0].kind = 'phone-only',
    x => x.services[0].localizations.fi.nextSteps = [],
    x => x.services[0].localizations.en.unknowns.eligibility = '',
    x => x.services[0].channels[0].accessibleText.en = ' ',
    x => x.services[0].id = 'real-service',
  ]) {const input = fixture(); mutate(input); invalid(input);}
});

test('malformed types, unsupported prototypes, extra verdicts and nonfinite values are invalid', () => {
  for (const input of [null, undefined, 0, false, 'card', [], {}, new Date(), () => {}]) invalid(input);
  for (const mutate of [
    x => x.schemaVersion = '1', x => x.dataKind = 'real-resident-data',
    x => x.authorization = true, x => x.services[0].source.verified = true,
    x => x.services[0].localizations.fi.unknowns.available = true,
    x => x.request.serviceId = 0, x => x.services[0].source = null,
    x => x.services[0].localizations.en.nextSteps = ['okay', null],
    x => Object.setPrototypeOf(x.request, {language: 'fi'}),
    x => Object.setPrototypeOf(x.services, Object.create(Array.prototype)),
  ]) {const input = fixture(); mutate(input); invalid(input);}
});

test('getters, hooks, array index accessors and caller collection methods are never invoked', () => {
  let calls = 0;
  const trap = () => {calls++; throw Error('must not run');};
  for (const mutate of [
    x => Object.defineProperty(x, 'request', {get: trap, enumerable: true}),
    x => Object.defineProperty(x.services[0].source, 'checkedAt', {get: trap, enumerable: true}),
    x => Object.defineProperty(x.services, '0', {get: trap, enumerable: true}),
    x => Object.defineProperty(x.services, 'some', {get: trap}),
    x => x.services.find = trap, x => x.services[0].channels.map = trap,
    x => x.toJSON = trap, x => x.request.valueOf = trap,
  ]) {const input = fixture(); mutate(input); invalid(input);}
  assert.equal(calls, 0);
});

test('sparse arrays, symbols, hidden fields, cycles and bounded resource excesses fail closed', () => {
  for (const mutate of [
    x => delete x.services[0], x => x.services.extra = 1,
    x => x.request[Symbol('extra')] = true,
    x => Object.defineProperty(x.request, 'hidden', {value: true}),
    x => x.services[0].channels.push(x),
    x => x.services[0].localizations.fi.title = 'a'.repeat(2001),
    x => x.services = Array.from({length: 31}, () => structuredClone(x.services[0])),
    x => x.services[0].localizations.fi.nextSteps = new Array(2),
  ]) {const input = fixture(); mutate(input); invalid(input);}
});

test('deterministic result neither mutates frozen input nor retains output aliases to it', () => {
  function freeze(value) {if (value && typeof value === 'object') {Object.values(value).forEach(freeze); Object.freeze(value);} return value;}
  const input = freeze(fixture()), before = JSON.stringify(input);
  const first = checkServiceRouting(input), second = checkServiceRouting(input);
  assert.deepEqual(first, second);
  first.card.nextSteps[0] = 'changed'; first.card.unknowns.availability = 'changed'; first.issues.push('changed');
  assert.deepEqual(checkServiceRouting(input), second);
  assert.equal(JSON.stringify(input), before);
});

test('all six authored model eval definitions remain byte-exact and are not executed here', () => {
  const bytes = readFileSync(new URL('../pets/city-of-espoo/evals.json', import.meta.url));
  assert.equal(createHash('sha256').update(bytes).digest('hex'), '8edecc83253041eef8c1605d749b053289242d518aec904bb87f11259ea28a74');
  assert.equal(JSON.parse(bytes).cases.length, 6);
});
