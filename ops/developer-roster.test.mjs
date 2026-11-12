import test from 'node:test';
import assert from 'node:assert/strict';
import {buildDeveloperRoster,inspectDeveloperPreflight} from './developer-roster.mjs';

const COMPANIES = Object.freeze([
  'hostinger', 'valio-aimo', 's-pankki', 'aalto-university', 'cala',
  'city-of-espoo', 'exa', 'mariadb', 'afterquery', 'bahn-express',
  'astrazeneca', 'stoa', 'intel', 'context-dev', 'rokoko', 'ignite-next',
  'meta', 'tieto', 'openai-codex', 'nvidia', 'featherless', 'modal',
  'qualia', 'craci', 'atech-dev', 'scailab', 'ironshard', 'cloudinary',
  'wendy', 'aiven', 'oxylabs', 'arduino', 'verda', 'google-deepmind'
]);
const SOURCE = 'a'.repeat(40);
const OLD = 'b'.repeat(40);
const NOW = new Date('2026-11-13T00:00:00.000Z');

function manifest(company) {
  return {
    schemaVersion: 1,
    petSlug: `junction-${company}`,
    agentId: `junction-dev-${company}`,
    provider: 'codex-cloud',
    desiredName: `junction-${company}`,
    repository: 'SalesSquad/junction-pets',
    branchPattern: `codex/junction-${company}-*`,
    ownedPath: `pets/${company}/`,
    agentInstructions: 'ops/AGENTS.md',
    runtimeInstructions: `pets/${company}/AGENTS.md`,
    setupCommand: 'npm ci --ignore-scripts',
    checkCommands: ['npm run validate', 'npm test', 'npm run build'],
    provisioning: {state: 'unprovisioned', environmentId: null, verifiedAt: null, evidenceUrl: null}
  };
}

function fixture() {
  const manifests = COMPANIES.map(manifest);
  manifests.find(row => row.petSlug === 'junction-aiven').provisioning = {
    state: 'published-id-pending', environmentId: null,
    verifiedAt: '2026-11-12T22:32:40.000Z',
    evidenceUrl: 'https://chatgpt.com/local/6af63cbd-674c-8191-83e7-d7be6dd6e040',
    sourceCommit: OLD,
    publicationObservation: 'owner-observed-settings-and-task-picker',
    taskCheck: {
      suite: 'submission-gate', result: 'pass', executed: 21, passed: 21,
      sourceCommit: OLD,
      evidenceUrl: 'https://chatgpt.com/local/6af63cbd-674c-8191-83e7-d7be6dd6e040'
    }
  };
  return manifests;
}

const options = () => ({expectedCompanies: COMPANIES, sourceCommit: SOURCE, generatedAt: NOW, requestedConcurrency: 2});
const copy = value => structuredClone(value);
const planned = () => buildDeveloperRoster(fixture(), options());

test('34 distinct developer identities, 102 logical roles, zero live processes', () => {
  const roster = planned();
  assert.equal(roster.summary.companyLanes, 34);
  assert.equal(roster.summary.logicalDevelopers, 34);
  assert.equal(roster.summary.logicalRoles, 102);
  assert.equal(roster.summary.plannedCodeRoles, 34);
  assert.equal(roster.summary.plannedTestRoles, 34);
  assert.equal(roster.summary.plannedReviewRoles, 34);
  assert.equal(roster.summary.actualWorkersStarted, 0);
  assert.equal(roster.summary.actualCloudTasksDispatched, 0);
  assert.equal(roster.summary.independentlyAuthenticatedReady, 0);
  assert.equal(roster.summary.verifiedAvailableCapacity, 0);
  assert.equal(roster.summary.requestedConcurrency, 2);
  assert.equal(new Set(roster.developers.map(row => row.canonicalAgentId)).size, 34);
  assert.equal(new Set(roster.developers.flatMap(row => row.roles.map(role => role.id))).size, 102);
  assert.ok(roster.developers.every(row => !row.dispatch.admitted && !row.dispatch.actualProcessStarted));
  assert.equal(new Set(roster.developers.map(row => row.continuity.task)).size, 34);
  assert.ok(roster.developers.every(row => row.continuity.acceptance.length >= 5));
});

test('deterministic output regardless of manifest input order', () => {
  const manifests = fixture();
  const first = buildDeveloperRoster(manifests, options());
  const second = buildDeveloperRoster([...manifests].reverse(), options());
  assert.deepEqual(first, second);
});

test('strict scoped code/test writers and read-only independent reviewer', () => {
  const roster = planned();
  const aiven = roster.developers.find(row => row.companySlug === 'aiven');
  assert.deepEqual(aiven.roles.map(role => role.role), ['code', 'test', 'review']);
  assert.deepEqual(aiven.roles[0].writePaths, ['pets/aiven/']);
  assert.deepEqual(aiven.roles[1].writePaths, ['tests/pet-aiven.test.mjs']);
  assert.deepEqual(aiven.roles[2].writePaths, []);
  assert.equal(aiven.roles[2].access, 'read-only');
  assert.equal(aiven.roles[0].writerLeaseDomain, 'junction.aiven.write');
  assert.equal(aiven.roles[1].writerLeaseDomain, 'junction.aiven.write');
  assert.equal(aiven.roles[2].writerLeaseDomain, null);
  assert.equal(aiven.ownership.sharedPathsOwner, 'Monorepo integrator (not company writers)');
  assert.ok(aiven.roles.every(role =>
    role.writePaths.every(path => !path.startsWith('services/pet-adapters/'))));
  assert.equal(aiven.roles[0].workIdTemplate, 'junction.aiven.code.<slice>');
  assert.ok(aiven.roles[0].handoff.required.includes('leaseRelease'));
  assert.ok(aiven.roles[0].handoff.retry.includes('distributed lease'));
  assert.equal(aiven.cloud.verificationTier, 'owner-observed-id-pending-stale-source');
  assert.equal(aiven.cloud.providerEnvironmentId, null);
  assert.equal(aiven.continuity.task, 'junction.aiven.cloud-bootstrap');
  assert.equal(aiven.continuity.priority, 'P1-source-or-provider-identity');
  assert.equal(aiven.continuity.stage, 'current-source-retest-and-id-readback');
  assert.equal(aiven.continuity.state, 'proposed-not-enqueued');
  assert.match(aiven.continuity.fallback, /Cloud is not ready/);
});

test('malicious duplicate pet/manifests fail closed', () => {
  const manifests = fixture();
  manifests[1] = copy(manifests[0]);
  assert.throws(() => buildDeveloperRoster(manifests, options()), /Duplicate company/);
});

test('unknown company slug fails closed', () => {
  const manifests = fixture();
  manifests[0] = manifest('invented-sponsor');
  assert.throws(() => buildDeveloperRoster(manifests, options()), /Unknown company slug/);
});

test('missing manifest fails closed', () => {
  assert.throws(() => buildDeveloperRoster(fixture().slice(1), options()), /exactly 34/);
});

test('tampered company agent ID and role identity fail closed', () => {
  const manifests = fixture();
  manifests[0].agentId = 'junction-dev-aiven';
  assert.throws(() => buildDeveloperRoster(manifests, options()), /Invalid agentId/);
});

test('write-path collision and traversal fail closed', () => {
  const manifests = fixture();
  manifests[0].ownedPath = 'pets/aiven/';
  assert.throws(() => buildDeveloperRoster(manifests, options()), /Invalid ownedPath/);
  manifests[0].ownedPath = 'pets/hostinger/../../ops/';
  assert.throws(() => buildDeveloperRoster(manifests, options()), /Invalid ownedPath/);
});

test('forged manifest running cannot start without Cloud ID', () => {
  const manifests = fixture();
  manifests[0].provisioning = {
    state: 'running', environmentId: null,
    verifiedAt: '2026-11-12T23:00:00.000Z', evidenceUrl: 'https://example.org/attestation'
  };
  assert.throws(() => buildDeveloperRoster(manifests, options()), /Invalid Cloud environment ID/);
});

test('manifest reported ready, even with ID, is never independently authenticated', () => {
  const manifests = fixture();
  manifests[0].provisioning = {
    state: 'ready', environmentId: 'opaque-published-id',
    verifiedAt: '2026-11-12T23:00:00.000Z', evidenceUrl: 'https://example.org/attestation'
  };
  const roster = buildDeveloperRoster(manifests, options());
  const target = roster.developers.find(row => row.companySlug === 'hostinger');
  assert.equal(target.cloud.recordedState, 'ready');
  assert.equal(target.cloud.authenticatedProviderReady, false);
  assert.equal(roster.summary.independentlyAuthenticatedReady, 0);
  assert.equal(roster.dispatchPolicy.chibiRuntimeGrantNotRequiredForCodeOrTest, true);
  assert.equal(inspectDeveloperPreflight(roster, {
    companySlug: 'hostinger', requestedSourceCommit: SOURCE
  }).dispatchAllowed, false);
});

test('duplicate provider opaque ID fails closed', () => {
  const manifests = fixture();
  for(const row of manifests.slice(0, 2)) row.provisioning = {
    state: 'ready', environmentId: 'duplicated-opaque-id',
    verifiedAt: '2026-11-12T23:00:00.000Z', evidenceUrl: 'https://example.org/evidence'
  };
  assert.throws(() => buildDeveloperRoster(manifests, options()), /Shared Cloud environment ID/);
});

test('published-ID-pending null ID stays blocked; stale task receipt is labeled', () => {
  const aiven = planned().developers.find(row => row.companySlug === 'aiven');
  assert.equal(aiven.cloud.manifestSourceCommit, OLD);
  assert.equal(aiven.cloud.manifestSourceCurrent, false);
  assert.match(aiven.dispatch.nextAction, /stale/);
  assert.equal(aiven.dispatch.admitted, false);
});

test('fabricated publication proof does not validate', () => {
  const manifests = fixture();
  const aiven = manifests.find(row => row.petSlug === 'junction-aiven');
  aiven.provisioning.taskCheck.sourceCommit = SOURCE;
  assert.throws(() => buildDeveloperRoster(manifests, options()), /Invalid published task check/);
});

test('unknown provisioning status or secret injection fails closed', () => {
  const manifests = fixture();
  manifests[0].provisioning.state = 'verified';
  assert.throws(() => buildDeveloperRoster(manifests, options()), /Invalid cloud state/);
  manifests[0].provisioning.state = 'unprovisioned';
  manifests[0].provisioning.secret = 'nope';
  assert.throws(() => buildDeveloperRoster(manifests, options()), /Unprovisioned.*cannot claim/);
});

test('invalid concurrency, source SHA, and duplicate catalog are rejected', () => {
  assert.throws(() => buildDeveloperRoster(fixture(), {...options(), sourceCommit: OLD.slice(1)}),
    /clean source commit/);
  assert.throws(() => buildDeveloperRoster(fixture(), {...options(), requestedConcurrency: 35}),
    /Requested concurrency/);
  assert.throws(() => buildDeveloperRoster(fixture(), {...options(), expectedCompanies: [...COMPANIES.slice(1), COMPANIES[0], COMPANIES[0]]}),
    /34 unique catalog/);
});

test('missing or forged provider readiness, no verified capacity or local lease block dispatch', () => {
  const roster = planned();
  const preflight = inspectDeveloperPreflight(roster, {companySlug: 'aiven', requestedSourceCommit: SOURCE,
    providerReadback: {state: 'ready'},
    leaseReceipt: {scope: 'single-workspace-only'},
    capacityReceipt: {freeSlots: 300}});
  assert.equal(preflight.status, 'blocked-requires-trusted-executor');
  assert.equal(preflight.dispatchAllowed, false);
  assert.ok(preflight.reasons.includes('provider-readback-identity-source-or-freshness-mismatch'));
  assert.ok(preflight.reasons.includes('missing-or-invalid-distributed-fenced-lease'));
  assert.ok(preflight.reasons.includes('missing-or-stale-verified-executor-capacity'));
});

test('wrong source commit always blocks regardless of stale receipts', () => {
  const preflight = inspectDeveloperPreflight(planned(), {
    companySlug: 'aiven', requestedSourceCommit: OLD,
    providerReadback: {state: 'ready', sourceCommit: OLD, observedAt: NOW.toISOString()},
    leaseReceipt: {scope: 'distributed', sourceCommit: OLD},
    capacityReceipt: {freeSlots: 1, sourceCommit: OLD, observedAt: NOW.toISOString()}
  });
  assert.equal(preflight.dispatchAllowed, false);
  assert.ok(preflight.reasons.includes('wrong-or-unverified-source-commit'));
});

test('even well-formed self-declared provider, fenced lease and capacity cannot grant dispatch', () => {
  const manifests = fixture();
  manifests[0].provisioning = {
    state: 'ready', environmentId: 'opaque-12345',
    verifiedAt: NOW.toISOString(), evidenceUrl: 'https://example.org/receipt'
  };
  const roster = buildDeveloperRoster(manifests, options());
  const preflight = inspectDeveloperPreflight(roster, {
    companySlug: 'hostinger', requestedSourceCommit: SOURCE, now: NOW,
    providerReadback: {
      state: 'ready', provider: 'codex-cloud', environmentId: 'opaque-12345',
      repository: 'SalesSquad/junction-pets', sourceCommit: SOURCE, observedAt: NOW.toISOString()
    },
    leaseReceipt: {
      scope: 'distributed', leaseDomain: 'junction.hostinger.write',
      agentId: 'junction-dev-hostinger', companySlug: 'hostinger',
      sourceCommit: SOURCE, fencingToken: 1, expiresAt: '2026-11-13T00:30:00.000Z'
    },
    capacityReceipt: {
      sourceCommit: SOURCE, companySlug: 'hostinger', freeSlots: 4, observedAt: NOW.toISOString()
    }
  });
  assert.equal(preflight.dispatchAllowed, false);
  assert.ok(preflight.reasons.includes('provider-readback-not-authenticated-by-planning-module'));
  assert.ok(preflight.reasons.includes('distributed-lease-not-authenticated-by-planning-module'));
  assert.ok(preflight.reasons.includes('capacity-not-authenticated-by-planning-module'));
  assert.ok(!preflight.reasons.some(reason => reason.includes('host-authorization')));
});

test('stale readback and expired lease are rejected', () => {
  const manifests = fixture();
  manifests[0].provisioning = {
    state: 'ready', environmentId: 'opaque-12345',
    verifiedAt: NOW.toISOString(), evidenceUrl: 'https://example.org/receipt'
  };
  const roster = buildDeveloperRoster(manifests, options());
  const preflight = inspectDeveloperPreflight(roster, {
    companySlug: 'hostinger', requestedSourceCommit: SOURCE, now: NOW,
    providerReadback: {provider: 'codex-cloud', state: 'ready', environmentId: 'opaque-12345',
      repository: 'SalesSquad/junction-pets', sourceCommit: SOURCE,
      observedAt: '2026-11-12T23:40:00.000Z'},
    leaseReceipt: {scope: 'distributed', leaseDomain: 'junction.hostinger.write',
      agentId: 'junction-dev-hostinger', companySlug: 'hostinger',
      sourceCommit: SOURCE, fencingToken: 1, expiresAt: '2026-11-12T23:00:00.000Z'}
  });
  assert.ok(preflight.reasons.includes('provider-readback-identity-source-or-freshness-mismatch'));
  assert.ok(preflight.reasons.includes('missing-or-invalid-distributed-fenced-lease'));
});

test('unknown company or role refuses preflight rather than fabricating a lane', () => {
  assert.throws(() => inspectDeveloperPreflight(planned(), {
    companySlug: 'siemens', requestedSourceCommit: SOURCE
  }), /Unknown company developer/);
  assert.throws(() => inspectDeveloperPreflight(planned(), {
    companySlug: 'aiven', role: 'deploy', requestedSourceCommit: SOURCE
  }), /Unknown developer role/);
});
