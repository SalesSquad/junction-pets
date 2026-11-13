import assert from 'node:assert/strict';
import {mkdtemp, rename, rm} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import test from 'node:test';

// Exercise the actual TS module on every supported Node 22+ runner, including
// versions predating Node's built-in TypeScript stripping. The test owns its
// temporary compilation root; no generated output enters the source checkout.
const compiledRoot = await mkdtemp(join(tmpdir(), 'junction-webmcp-test-'));
let registerCatalogTools;
try {
  const compiler = fileURLToPath(new URL('./bin/tsc', import.meta.resolve('typescript/package.json')));
  execFileSync(process.execPath, [compiler, fileURLToPath(new URL('./webmcp.ts', import.meta.url)), '--target', 'ES2022', '--module', 'ESNext', '--moduleResolution', 'Bundler', '--skipLibCheck', '--outDir', compiledRoot], {stdio: 'pipe'});
  await rename(join(compiledRoot, 'webmcp.js'), join(compiledRoot, 'webmcp.mjs'));
  ({registerCatalogTools} = await import(pathToFileURL(join(compiledRoot, 'webmcp.mjs')).href));
} finally { await rm(compiledRoot, {recursive: true, force: true}); }

const pet = (slug, company, role) => ({
  slug, displayName: `${company} companion`, version: '1.0.0', tagline: `Explore ${company}`,
  introduction: `Independent ${company} companion`, company: {name: company, role},
  capabilities: [{id: 'analyze', title: 'Analyze public inputs', description: 'A declared capability.', requiresConnection: false}],
  sources: [{title: `${company} documentation`, url: `https://example.com/${slug}`, checkedAt: '2026-11-13'}],
});
function harness(options = {}) {
  const tools = new Map();
  const signals = [];
  let selected = 'junction-aiven';
  const catalogue = {pets: [pet('junction-aiven', 'Aiven', 'technology'), pet('junction-mariadb', 'MariaDB', 'challenge')]};
  const context = {registerTool(tool, {signal}) {tools.set(tool.name, tool); signals.push(signal);}};
  const config = {
    document: {modelContext: context}, catalogue, getSelectedSlug: () => selected,
    selectCompanion: async slug => {selected = slug;}, ...options,
  };
  const registration = registerCatalogTools(config);
  return {tools, signals, context, config, registration, call: (name, input) => tools.get(name).execute(input)};
}

test('unsupported document and server render do not register or fail', () => {
  for (const document of [undefined, {}, {modelContext: {}}]) {
    const registration = registerCatalogTools({document, catalogue: {pets: []}, getSelectedSlug: () => null, selectCompanion: async () => {}});
    assert.equal(registration.supported, false);
    registration.dispose();
  }
});

test('three public tools register once, cleanup aborts all, next lifecycle can register', () => {
  const h = harness();
  assert.deepEqual([...h.tools.keys()], ['list_junction_companions', 'read_junction_companion', 'select_junction_companion']);
  registerCatalogTools(h.config).dispose();
  assert.equal(h.signals.length, 3);
  assert.ok(h.signals.every(signal => !signal.aborted));
  h.registration.dispose();
  assert.ok(h.signals.every(signal => signal.aborted));
  assert.throws(() => h.call('list_junction_companions', {}), /catalog_tools_inactive/);
  const next = registerCatalogTools(h.config);
  assert.equal(h.signals.length, 6);
  next.dispose();
});

test('listing filters, limits results and contains no private operational fields', () => {
  const h = harness();
  const result = h.call('list_junction_companions', {query: '  AÍVEN ', role: 'technology', limit: 1});
  assert.equal(result.total, 1);
  assert.equal(result.companions[0].slug, 'junction-aiven');
  assert.equal(result.companions[0].taskExecution, 'unavailable_in_catalog');
  assert.deepEqual(Object.keys(result.companions[0]).sort(), ['slug', 'name', 'company', 'role', 'version', 'declaredCapabilityCount', 'taskExecution'].sort());
  assert.equal(h.call('list_junction_companions', {role: 'challenge'}).companions[0].slug, 'junction-mariadb');
  h.registration.dispose();
});

test('all list input fields are validated, including unknown and symbolic fields', () => {
  const h = harness();
  const invalid = [null, [], 'Aiven', {query: 3}, {query: 'x'.repeat(121)}, {role: 'admin'}, {limit: 0}, {limit: 35}, {limit: 1.5}, {limit: NaN}, {limit: '1'}, {private: true}, {[Symbol('x')]: 1}];
  for (const input of invalid) assert.throws(() => h.call('list_junction_companions', input), /invalid_input/);
  h.registration.dispose();
});

test('read returns authored capabilities and citations with explicit execution limit', () => {
  const h = harness();
  const result = h.call('read_junction_companion', {slug: 'junction-aiven'});
  assert.equal(result.companyEndorsed, false);
  assert.equal(result.capabilities[0].execution, 'unavailable_in_catalog');
  assert.equal(result.sources[0].url, 'https://example.com/junction-aiven');
  assert.throws(() => h.call('read_junction_companion', {slug: 'junction-missing'}), /companion_not_found/);
  for (const input of [{}, {slug: '../ops'}, {slug: ['junction-aiven']}, {slug: 'junction-aiven', execute: true}]) assert.throws(() => h.call('read_junction_companion', input), /invalid_input/);
  h.registration.dispose();
});

test('selection waits for visible UI completion before returning success', async () => {
  let resolveNavigation;
  let selected = 'junction-aiven';
  const h = harness({getSelectedSlug: () => selected, selectCompanion: slug => new Promise(resolve => {resolveNavigation = () => {selected = slug; resolve();};})});
  let completed = false;
  const pending = h.call('select_junction_companion', {slug: 'junction-mariadb'}).then(result => {completed = true; return result;});
  await Promise.resolve();
  assert.equal(completed, false);
  resolveNavigation();
  assert.deepEqual(await pending, {slug: 'junction-mariadb', selected: true, profileVisible: true, taskExecution: 'unavailable_in_catalog'});
  assert.equal(h.tools.get('select_junction_companion').annotations.readOnlyHint, false);
  h.registration.dispose();
});

test('selection fails closed when navigation did not complete or lifecycle ended', async () => {
  const h = harness({selectCompanion: async () => {}});
  await assert.rejects(h.call('select_junction_companion', {slug: 'junction-mariadb'}), /selection_not_completed/);
  await assert.rejects(h.call('select_junction_companion', {slug: 'junction-aiven', extra: true}), /invalid_input/);
  h.registration.dispose();
  await assert.rejects(h.call('select_junction_companion', {slug: 'junction-aiven'}), /catalog_tools_inactive/);
});

test('sync and async registration failures abort previously registered tools', async () => {
  for (const asyncFailure of [false, true]) {
    const signals = [];
    const errors = [];
    const context = {registerTool(tool, {signal}) {
      signals.push(signal);
      if (tool.name === 'read_junction_companion') {
        if (asyncFailure) return Promise.reject(new Error('provider detail must not leak'));
        throw new Error('provider detail must not leak');
      }
    }};
    const h = harness({document: {modelContext: context}, onError: code => errors.push(code)});
    await new Promise(resolve => setImmediate(resolve));
    assert.ok(signals.every(signal => signal.aborted));
    assert.deepEqual(errors, ['catalog_tool_registration_failed']);
    h.registration.dispose();
  }
});
