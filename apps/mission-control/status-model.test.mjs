import test from 'node:test';
import assert from 'node:assert/strict';
import {
  cloudAssessment, filterPets, formatDate, normalizeRegistry,
  petSourceUrl, pluginAssessment, safePluginPageUrl, safeCount, snapshotAge, sourceCommit,
} from './status-model.mjs';

function fixture() {
  return {
    schemaVersion: 1,
    generatedAt: '2026-11-12T18:00:00.000Z',
    source: {repository: 'SalesSquad/junction-pets', commit: null, verification: 'local-git-only'},
    pets: Array.from({length: 34}, (_, i) => ({
      slug: `junction-company-${i}`,
      company: {name: `Company ${i}`, slug: `company-${i}`, role: i < 20 ? 'challenge' : 'technology'},
      agent: {id: `junction-dev-company-${i}`},
      cloud: {provider: 'codex-cloud', desiredName: `junction-company-${i}`, environmentId: null, state: 'unprovisioned', verifiedAt: null},
      development: {state: 'content-ready'},
      evaluation: {defined: 6, executed: 0, passed: 0, failed: 0},
      runtime: {state: 'unverified'},
      nextAction: 'Provision verified environment',
    })),
  };
}

test('requires exact source-backed roster length and unique safe company slugs', () => {
  assert.equal(normalizeRegistry(fixture()).pets.length, 34);
  const missing = fixture();
  missing.pets.pop();
  assert.throws(() => normalizeRegistry(missing), /Expected 34/);
  const duplicate = fixture();
  duplicate.pets[1].slug = duplicate.pets[0].slug;
  assert.throws(() => normalizeRegistry(duplicate), /duplicate/);
  const invalid = fixture();
  invalid.pets[1].slug = '../private-code';
  assert.throws(() => normalizeRegistry(invalid), /Invalid/);
});

test('provider readiness without an environment ID or verified date fails closed', () => {
  assert.equal(cloudAssessment({state: 'ready', environmentId: null, verifiedAt: null}).effectiveState, 'unverified');
  assert.equal(cloudAssessment({state: 'running', environmentId: 'id', verifiedAt: null}).tone, 'critical');
  assert.equal(cloudAssessment({state: 'ready', environmentId: 'id', verifiedAt: '2026-11-12T18:00:00Z'}).effectiveState, 'unverified');
  assert.equal(cloudAssessment({state: 'reported-ready', environmentId: 'id', verifiedAt: '2026-11-12T18:00:00Z'}).effectiveState, 'unverified');
  assert.equal(cloudAssessment({state: 'ready', environmentId: 'id', verifiedAt: '2026-11-12T18:00:00Z', verification: 'provider-attested'}).effectiveState, 'unverified');
  assert.equal(cloudAssessment({state: 'unprovisioned'}).effectiveState, 'unprovisioned');
});

test('a forged provider-attested marker with plausible source receipt cannot turn a cell green', () => {
  const forged = {
    state: 'running', provider: 'codex-cloud', desiredName: 'junction-mariadb',
    environmentId: 'env_aaaaaaaaaaaaaaaa', verifiedAt: new Date().toISOString(),
    verification: 'provider-attested',
    evidenceUrl: 'https://chatgpt.com/codex/cloud/environments/env_aaaaaaaaaaaaaaaa',
    attestation: {
      schemaVersion: 1, issuer: 'openai', sourceCommit: 'a'.repeat(40),
      environmentId: 'env_aaaaaaaaaaaaaaaa', signature: 'this-is-not-a-signed-proof',
    },
  };
  assert.equal(cloudAssessment(forged).effectiveState, 'unverified');
  assert.equal(cloudAssessment(forged).tone, 'critical');
  assert.equal(filterPets([{company: {role: 'challenge'}, cloud: forged}], {mode: 'ready'}).length, 0);
  assert.equal(filterPets([{company: {role: 'challenge'}, cloud: forged}], {mode: 'issues'}).length, 1);
});

test('filters by state, role and full-text case insensitively', () => {
  const pets = normalizeRegistry(fixture()).pets;
  pets[0].cloud = {state: 'provisioning', environmentId: null, verifiedAt: null};
  pets[1].cloud = {state: 'blocked'};
  assert.equal(filterPets(pets, {mode: 'active'}).length, 1);
  assert.equal(filterPets(pets, {mode: 'issues'}).length, 1);
  assert.equal(filterPets(pets, {mode: 'needs-setup'}).length, 32);
  assert.equal(filterPets(pets, {role: 'technology'}).length, 14);
  assert.equal(filterPets(pets, {query: 'COMPANY 19'}).length, 1);
});

test('does not synthesize a source SHA from the branch name or local reconstruction', () => {
  const pets = normalizeRegistry(fixture()).pets;
  assert.equal(sourceCommit({commit: 'main'}), null);
  assert.equal(petSourceUrl(pets[0], {commit: null}), 'https://github.com/SalesSquad/junction-pets/tree/main/pets/company-0');
  const hash = 'a'.repeat(40);
  assert.equal(petSourceUrl(pets[0], {commit: hash}), `https://github.com/SalesSquad/junction-pets/tree/${hash}/pets/company-0`);
  assert.equal(petSourceUrl(pets[0], {commit: hash, verification: 'local-git-only'}), 'https://github.com/SalesSquad/junction-pets/tree/main/pets/company-0');
});

test('timestamp age and counts never fabricate provider evidence', () => {
  assert.equal(snapshotAge('2026-11-12T18:00:00Z', Date.parse('2026-11-12T18:04:00Z')).stale, false);
  assert.equal(snapshotAge('2026-11-12T18:00:00Z', Date.parse('2026-11-12T20:00:00Z')).stale, true);
  assert.equal(snapshotAge(null).stale, true);
  assert.match(formatDate(null), /No verified timestamp/);
  assert.equal(safeCount(-5), 0);
  assert.equal(safeCount('204'), 0);
});

test('plugin source presence is not equivalent to private registration or installed host', () => {
  const plugin = {
    desiredName: 'junction-aiven', sourcePath: 'plugins/junction-aiven/plugin.json',
    presence: 'source-present', installationState: 'not-registered',
    pluginId: null, registrationBinding: 'missing', verification: 'source-file-only-no-install-proof',
  };
  const state = pluginAssessment(plugin, 'junction-aiven');
  assert.equal(state.source.label, 'Source manifest reported present');
  assert.equal(state.registration.label, 'No registration recorded');
  assert.equal(state.host.label, 'Host installation not independently verified');
  assert.notEqual(state.host.tone, 'good');
});

test('source-matched private plugin registration remains reported, not host-verified', () => {
  const plugin = {
    desiredName: 'junction-aiven', sourcePath: 'plugins/junction-aiven/plugin.json',
    presence: 'source-present', installationState: 'registered-source-matched-reported',
    pluginId: 'plugins_aiven_12345', releaseId: 'release-42', visibility: 'USER_PRIVATE',
    registrationBinding: 'source-matched-reported', verification: 'provider-readback-recorded-not-rechecked',
    sourceBundleSha256: 'a'.repeat(64), observedAt: new Date().toISOString(),
    pluginUrl: 'https://chatgpt.com/plugins/plugins_aiven_12345',
  };
  const state = pluginAssessment(plugin, 'junction-aiven');
  assert.equal(state.registration.tone, 'warning');
  assert.equal(state.registration.label, 'Private registration reported');
  assert.equal(state.host.tone, 'neutral');
  assert.equal(safePluginPageUrl(plugin), 'https://chatgpt.com/plugins/plugins_aiven_12345');
});

test('malformed or cross-pet plugin data and unsafe links never produce a trusted claim or URL', () => {
  const forged = {
    desiredName: 'junction-meta', sourcePath: 'plugins/junction-meta/plugin.json',
    presence: 'source-present', installationState: 'registered-source-matched-reported',
    registrationBinding: 'source-matched-reported', pluginId: 'plugins_aiven_12345',
    sourceBundleSha256: 'a'.repeat(64), visibility: 'USER_PRIVATE',
    pluginUrl: 'https://chatgpt.com/plugins/plugins_aiven_12345?token=secret',
    verification: 'provider-verified',
  };
  const state = pluginAssessment(forged, 'junction-aiven');
  assert.equal(state.source.tone, 'critical');
  assert.equal(state.registration.tone, 'critical');
  assert.equal(state.host.tone, 'neutral');
  assert.equal(safePluginPageUrl(forged), null);
  assert.equal(safePluginPageUrl({...forged, pluginUrl: 'https://evil.invalid/plugins/plugins_aiven_12345'}), null);
  assert.equal(safePluginPageUrl({...forged, pluginUrl: 'javascript:alert(1)'}), null);
  assert.equal(safePluginPageUrl({...forged, pluginId: '../plugins_different'}), null);
  assert.equal(safePluginPageUrl({...forged, pluginUrl: 'https://chatgpt.com@evil.invalid/plugins/plugins_aiven_12345'}), null);
  assert.equal(pluginAssessment({presence: 'source-drift', installationState: 'stale-registration'}, 'junction-aiven').source.tone, 'warning');
});
