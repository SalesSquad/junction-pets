import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, readdirSync} from 'node:fs';
import {discoverCapabilities, getCapability, executeCapability} from './registry.mjs';

const fixtures = {
  afterquery: 'synthetic-failure-trace.json', arduino: 'example.json',
  astrazeneca: 'fictional-evidence-card.json', 'bahn-express': 'examples/custody-timeline.json',
  cala: 'examples/field-provenance.json', 'city-of-espoo': 'example.json',
  cloudinary: 'examples/responsive-media.json', 'context-dev': 'example.json',
  craci: 'example-sbom.json', exa: 'search-example.json', featherless: 'example.json',
  'google-deepmind': 'example.json', hostinger: 'example.json', 'ignite-next': 'example.json',
  intel: 'example.json', ironshard: 'example.json', modal: 'examples/fictional-job.json',
  'openai-codex': 'example-handoff.json', oxylabs: 'examples/fictional-collection.json',
  qualia: 'examples/fictional-episode.json', 's-pankki': 'example-sms.json',
  scailab: 'examples/fictional-coverage.json', stoa: 'examples/fictional-handoff.json',
  tieto: 'examples/workflow.json', 'valio-aimo': 'examples/fictional-recipe.json',
  verda: 'examples/fictional-gpu-run.json', wendy: 'examples/fictional-sensor-log.json',
};
const row = () => ({workload: 'synthetic-room-v1', kind: 'gaussian-splat', sceneCount: 1,
  objectCount: 1000, inputDigest: 'a'.repeat(64), width: 640, height: 480, precision: 'fp32',
  quality: 'exact-reference-v1', hardware: 'fictional-gpu-A', software: 'fictional-renderer-v1',
  timingScope: 'render-only-synchronized', warmup: 0, repeats: 3, unit: 'ms',
  timings: [10, 12, 14], evidence: 'authored-estimate', provenance: 'worksheet author'});
const inline = {
  'aalto-university': () => ({claimType: 'designed-experiment', hypothesis: 'A blue label reduces fictional sorting time.',
    outcome: {metric: 'sorting time', unit: 'seconds', window: 'one synthetic puzzle'},
    control: {comparison: 'grey label', allocation: 'randomized'}, confounds: ['Practice changes timing.'],
    decision: {preregistered: true, minimumDifference: 0, direction: 'decrease', rule: 'Compare fixed group means.'},
    uncertainty: ['No observations collected.'], sample: {treatment: 20, control: 20}}),
  'atech-dev': () => ({board: {voltage: {min: 3, max: 3, unit: 'V'}, current: {value: 100, unit: 'mA'},
    interfaces: [{name: 'fictional-digital', pins: 4}]}, parts: [{id: 'invented-sensor', quantity: 2,
    rating: 'known', voltage: {min: 3000, max: 5000, unit: 'mV'}, current: {value: 20, unit: 'mA'},
    requirements: [{interface: 'fictional-digital', pins: 2}]}]}),
  mariadb: () => ({provenance: 'offline-synthetic-authored', format: 'EXPLAIN EXTENDED',
    query: 'SELECT sku FROM inventory WHERE quantity < 5', row: {table: 'inventory', type: 'ALL',
      possible_keys: ['idx_quantity'], key: null, rows: 10000, filtered: 2, Extra: 'Using where'}}),
  meta: () => ({scope: 'synthetic-reminder-preview', now: 10, events: []}),
  nvidia: () => {const baseline = row(), candidate = row(); candidate.timings = [5, 6, 7]; return {baseline, candidate};},
  rokoko: () => ({source: {bones: ['hip', 'foot'], handedness: 'right', upAxis: 'Y', units: 'cm', formats: ['fictional-motion']},
    target: {bones: ['root', 'toe'], handedness: 'right', upAxis: 'Y', units: 'm', formats: ['fictional-motion']},
    mapping: [{source: 'hip', target: 'root'}, {source: 'foot', target: 'toe'}], exportFormat: 'fictional-motion', sourceDistance: 125}),
};
function validInput(company) {
  if (company === 'aiven') return {query: 'Kafka consumer group lag'};
  const value = inline[company]?.() ?? JSON.parse(readFileSync(new URL(`../../pets/${company}/${fixtures[company]}`, import.meta.url), 'utf8'));
  return {jsonText: JSON.stringify(value)};
}

const capabilities = discoverCapabilities();
test('discovery covers the actual 34 package identities with one explicit offline binding each', () => {
  const packageSlugs = readdirSync(new URL('../../pets/', import.meta.url), {withFileTypes: true})
    .filter(entry => entry.isDirectory()).map(entry => `junction-${entry.name}`).sort();
  assert.equal(capabilities.length, 34);
  assert.deepEqual(capabilities.map(capability => capability.petSlug).sort(), packageSlugs);
  assert.equal(new Set(capabilities.map(capability => capability.id)).size, 34);
  for (const capability of capabilities) {
    assert.equal(capability.available, true);
    assert.equal(capability.effect, 'none');
    assert.equal(capability.network, 'none');
    assert.equal(capability.evidenceTier, 'deterministic-analysis');
    assert.equal(capability.networkAccess, false);
    assert.equal(capability.providerConnected, false);
    assert.equal(capability.chibiHostVerified, false);
    assert.equal(capability.execution, 'offline-deterministic');
    assert.equal(capability.inputSchema.additionalProperties, false);
    assert.deepEqual(discoverCapabilities({petSlug: capability.petSlug}), [capability]);
  }
});

for (const capability of capabilities) test(`${capability.id} completes its declared fixture without mutating it`, async () => {
  const input = validInput(capability.companySlug), frozen = Object.freeze({...input});
  const before = structuredClone(input);
  const response = await executeCapability(capability.id, frozen);
  assert.equal(response.ok, true, JSON.stringify(response));
  assert.equal(response.capabilityId, capability.id);
  assert.equal(response.petSlug, capability.petSlug);
  assert.equal(response.execution, 'offline-deterministic');
  assert.equal(response.providerConnected, false);
  assert.equal(response.chibiHostVerified, false);
  assert.equal(typeof response.result, 'object');
  assert.notEqual(response.result.status, 'invalid');
  assert.notEqual(response.result.status, 'malformed');
  assert.notEqual(response.result.status, 'rejected');
  assert.notEqual(response.result.structuralStatus, 'rejected');
  assert.notEqual(response.result.verdict, 'INVALID');
  assert.deepEqual(input, before);
  assert.deepEqual(await executeCapability(capability.id, input), response);
});

test('Aiven performs an offline shortlist, abstains on nonsense, and refuses destructive intent', async () => {
  const kafka = await executeCapability('aiven.docs-shortlist', {query: 'Kafka consumer group lag'});
  assert.equal(kafka.result.code, 'MATCHES_UNVERIFIED');
  assert.equal(kafka.result.matches[0].id, 'kafka-consumer-groups');
  const nonsense = await executeCapability('aiven.docs-shortlist', {query: 'purple sandwich unicorn'});
  assert.equal(nonsense.result.code, 'NO_RELEVANT_DOCUMENTS');
  assert.deepEqual(nonsense.result.matches, []);
  const destructive = await executeCapability('aiven.docs-shortlist', {query: 'delete Kafka consumer groups'});
  assert.equal(destructive.result.code, 'ACTION_INTENT_OUT_OF_SCOPE');
});

test('completed MariaDB classification retains estimates and unknown runtime counters', async () => {
  const {result} = await executeCapability('mariadb.explain-evidence', validInput('mariadb'));
  assert.deepEqual(result.facts.rows, {kind: 'estimate', value: 10000});
  assert.deepEqual(result.facts.r_rows, {kind: 'unknown', value: null});
  assert.equal(result.executionVerified, false);
});

test('completed AfterQuery review returns FAIL for unsupported success claims', async () => {
  const response = await executeCapability('afterquery.failure-rubric', validInput('afterquery'));
  assert.equal(response.ok, true);
  assert.deepEqual(response.result, {verdict: 'FAIL', execution: 'unknown', reporting: 'unsupported-success'});
});

test('NVIDIA returns useful declared arithmetic without upgrading measurement confidence', async () => {
  const response = await executeCapability('nvidia.benchmark-comparability', validInput('nvidia'));
  assert.equal(response.result.comparable, true);
  assert.equal(response.result.ratio, 2);
  assert.equal(response.result.measuredPerformanceVerified, false);
});

test('registry never invokes fetch or arbitrary module/path commands', async () => {
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = () => {calls++; throw Error('network must not run');};
  try {
    for (const capability of capabilities) assert.equal((await executeCapability(capability.id, validInput(capability.companySlug))).ok, true);
    for (const id of ['../../node:child_process', 'node:fs', 'aiven.searchAivenPublicDocs', 'delete-project', '', null, {}]) {
      assert.deepEqual(await executeCapability(id, {command: 'secret-value'}), {ok: false, code: 'UNKNOWN_CAPABILITY'});
    }
    assert.equal(calls, 0);
  } finally {globalThis.fetch = original;}
});

test('strict envelopes reject extra keys, symbols, hooks and accessors without evaluating them', async () => {
  let calls = 0;
  const getter = Object.defineProperty({}, 'query', {enumerable: true, get() {calls++; throw Error('getter');}});
  const hook = {query: 'Kafka consumer lag', toJSON() {calls++; return {};}};
  const symbol = {query: 'Kafka consumer lag', [Symbol('secret')]: true};
  for (const input of [getter, hook, symbol, {query: 'Kafka consumer lag', credentials: 'secret-value'},
    Object.create({query: 'Kafka consumer lag'}), null, [], 'Kafka consumer lag']) {
    const response = await executeCapability('aiven.docs-shortlist', input);
    assert.equal(response.ok, false);
    assert.equal(response.code, 'INVALID_INPUT');
    assert.equal(JSON.stringify(response).includes('secret-value'), false);
  }
  assert.equal(calls, 0);
});

test('JSON input bounds, duplicate escaped keys, prototype keys and nonfinite numbers fail closed', async () => {
  const cases = ['not json', 'null', '[]', '{}'.repeat(32769), '{"a":1,"\\u0061":2}',
    '{"__proto__":{"polluted":true}}', '{"x":{"constructor":{}}}', '{"value":1e400}',
    '{"x":' + '['.repeat(14) + '0' + ']'.repeat(14) + '}',
    JSON.stringify({events: Array(1001).fill(0)}), JSON.stringify({message: 'ä'.repeat(32768)}),
    '{"broken":"\ud800"}', '{"broken":"\\ud800"}'];
  for (const jsonText of cases) {
    const response = await executeCapability('mariadb.explain-evidence', {jsonText});
    assert.equal(response.ok, false, jsonText.slice(0, 80));
    assert.equal(response.code, 'INVALID_INPUT');
  }
  assert.equal({}.polluted, undefined);
});

test('AfterQuery inner trace schema rejects unknown event or root fields', async () => {
  const data = JSON.parse(validInput('afterquery').jsonText);
  for (const mutate of [x => {x.authority = true;}, x => {x.events[0].credentials = 'secret-value';}, x => {x.events[1].type = 'execute-code';}]) {
    const value = structuredClone(data); mutate(value);
    const result = await executeCapability('afterquery.failure-rubric', {jsonText: JSON.stringify(value)});
    assert.equal(result.ok, false);
    assert.equal(result.code, 'INVALID_INPUT');
    assert.equal(JSON.stringify(result).includes('secret-value'), false);
  }
});

test('discovery/schema copies cannot mutate future validation or reroute capabilities', async () => {
  const selected = getCapability('aiven.docs-shortlist');
  selected.inputSchema.additionalProperties = true;
  selected.petSlug = 'junction-other';
  const discovery = discoverCapabilities(); discovery[0].id = 'tampered'; discovery.pop();
  assert.equal(getCapability('aiven.docs-shortlist').inputSchema.additionalProperties, false);
  assert.equal(getCapability('aiven.docs-shortlist').petSlug, 'junction-aiven');
  assert.equal(discoverCapabilities().length, 34);
  assert.equal(getCapability('unknown'), null);
  assert.equal(getCapability({toString() {throw Error('coercion');}}), null);
  assert.equal((await executeCapability('aiven.docs-shortlist', {query: 'Kafka consumer lag', extra: true})).ok, false);
});

test('discovery rejects invalid filters and does not turn an unknown company into a capability', () => {
  for (const input of [null, [], 'aiven', {petSlug: 'aiven'}, {petSlug: 'junction-aiven', extra: true}]) {
    assert.throws(() => discoverCapabilities(input), TypeError);
  }
  assert.deepEqual(discoverCapabilities({petSlug: 'junction-no-such-company'}), []);
});
