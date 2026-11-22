import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
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
    setupCommand: company === 'verda' ? 'bash ops/cloud/rml1/setup.sh && npm ci --ignore-scripts' : 'npm ci --ignore-scripts',
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

function readyRoster() {
  const manifests = fixture();
  manifests[0].provisioning = {
    state: 'ready', environmentId: 'opaque-12345',
    verifiedAt: NOW.toISOString(), evidenceUrl: 'https://example.org/receipt'
  };
  return buildDeveloperRoster(manifests, options());
}

function boundPreflight() {
  const workId = 'junction.hostinger.code.wave5';
  const attemptId = 'attempt-hostinger-001';
  const taskBranch = 'codex/junction-hostinger-wave5';
  const expectedRemoteHead = 'c'.repeat(40);
  const leaseId = 'lease-hostinger-000001';
  return {
    companySlug: 'hostinger', role: 'code', requestedSourceCommit: SOURCE,
    workId, attemptId, taskBranch, expectedRemoteHead, now: NOW,
    providerReadback: {
      state: 'ready', provider: 'codex-cloud', environmentId: 'opaque-12345',
      repository: 'SalesSquad/junction-pets', sourceCommit: SOURCE,
      observedAt: NOW.toISOString()
    },
    remoteHeadReadback: {
      repository: 'SalesSquad/junction-pets', branch: taskBranch,
      headSha: expectedRemoteHead, observedAt: NOW.toISOString()
    },
    leaseReceipt: {
      scope: 'distributed', leaseDomain: 'junction.hostinger.write',
      agentId: 'junction-dev-hostinger', companySlug: 'hostinger', sourceCommit: SOURCE,
      workId, attemptId, taskBranch, expectedRemoteHead, leaseId,
      fencingToken: 42, expiresAt: '2026-11-13T00:30:00.000Z'
    },
    ledgerReadback: {
      scope: 'distributed-lease-ledger', leaseDomain: 'junction.hostinger.write',
      agentId: 'junction-dev-hostinger', companySlug: 'hostinger', sourceCommit: SOURCE,
      workId, attemptId, previousAttemptId: 'attempt-hostinger-000',
      taskBranch, expectedRemoteHead, leaseId,
      lastCommittedFencingToken: 41, currentFencingToken: 42,
      observedAt: NOW.toISOString()
    },
    capacityReceipt: {
      sourceCommit: SOURCE, companySlug: 'hostinger', freeSlots: 4, observedAt: NOW.toISOString()
    }
  };
}

test('Verda RML1 setup is exactly scoped; shell substitutions remain invalid', () => {
  assert.doesNotThrow(() => buildDeveloperRoster(fixture(), options()));
  const tampered = fixture();
  const verda = tampered.find(row => row.petSlug === 'junction-verda');
  assert.equal(verda.setupCommand, 'bash ops/cloud/rml1/setup.sh && npm ci --ignore-scripts');
  verda.setupCommand = 'bash ops/cloud/rml1/other.sh && npm ci --ignore-scripts';
  assert.throws(() => buildDeveloperRoster(tampered, options()), /Invalid setupCommand in verda environment/);
  const unrelated = fixture();
  unrelated.find(row => row.petSlug === 'junction-hostinger').setupCommand =
    'bash ops/cloud/rml1/setup.sh && npm ci --ignore-scripts';
  assert.throws(() => buildDeveloperRoster(unrelated, options()),
    /Invalid setupCommand in hostinger environment/);
});

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
  assert.equal(aiven.roles[2].reviewerMustBeIndependentFromAuthors, true);
  assert.equal(aiven.roles[0].reviewerMustBeIndependentFromAuthors, false);
  assert.ok(aiven.roles[2].handoff.required.includes('independenceEvidence'));
  assert.equal(aiven.ownership.untrustedRuntimePersonaPath, 'pets/aiven/AGENTS.md');
  assert.equal(aiven.ownership.runtimePersonaTrust, 'company-specific-task-data-not-executor-policy');
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

test('recorded provider microseconds are preserved without granting readiness', () => {
  const manifests = fixture();
  const verifiedAt = '2026-11-13T00:26:59.476670Z';
  manifests[0].provisioning = {
    state: 'ready', environmentId: 'opaque-recorded-id', verifiedAt,
    evidenceUrl: 'https://example.org/provider-observation'
  };
  const roster = buildDeveloperRoster(manifests, options());
  const target = roster.developers.find(row => row.companySlug === 'hostinger');
  assert.equal(target.cloud.recordedAt, verifiedAt);
  assert.equal(manifests[0].provisioning.verifiedAt, verifiedAt);
  assert.equal(target.cloud.authenticatedProviderReady, false);
  assert.equal(target.dispatch.admitted, false);
  assert.equal(roster.summary.actualWorkersStarted, 0);
});

test('all 34 source manifests produce a planning-only developer roster', async () => {
  // Read immutable source inputs; never mutate the source or write shared caches.
  const manifests = await Promise.all(COMPANIES.map(async company =>
    JSON.parse(await readFile(new URL(`./environments/${company}.json`, import.meta.url), 'utf8'))));
  const roster = buildDeveloperRoster(manifests, options());
  assert.equal(roster.summary.companyLanes, 34);
  assert.equal(roster.summary.logicalRoles, 102);
  assert.equal(roster.summary.actualCloudTasksDispatched, 0);
  assert.equal(roster.summary.independentlyAuthenticatedReady, 0);
  for (const manifest of manifests) {
    const target = roster.developers.find(row => row.petSlug === manifest.petSlug);
    assert.equal(target.cloud.recordedAt, manifest.provisioning.verifiedAt);
    assert.equal(target.dispatch.admitted, false);
    assert.equal(target.dispatch.actualProcessStarted, false);
  }
});

test('provider observation precision does not accept malformed dates or time zones', () => {
  for (const verifiedAt of [
    '2026-02-30T00:26:59.476670Z', '2026-13-13T00:26:59.476670Z',
    '2026-11-13T24:00:00.000000Z', '2026-11-13T00:26:60.476670Z',
    '2026-11-13T00:26:59.476670+00:00', '2026-11-13T00:26:59.47667Z',
    '2026-11-13T00:26:59.4766700Z', '2026-11-13T00:26:59.476670Zjunk',
    '2026-11-13T00:26:59.476670Z\n', null, 1794529619476
  ]) {
    const manifests = fixture();
    manifests[0].provisioning = {
      state: 'ready', environmentId: 'opaque-recorded-id', verifiedAt,
      evidenceUrl: 'https://example.org/provider-observation'
    };
    assert.throws(() => buildDeveloperRoster(manifests, options()),
      /lacks recorded evidence/, String(verifiedAt));
  }
});

test('microsecond metadata compatibility does not alter live readback admission', () => {
  const input = boundPreflight();
  input.providerReadback.observedAt = '2026-11-13T00:00:00.000000Z';
  input.leaseReceipt.expiresAt = '2026-11-13T00:30:00.000000Z';
  const result = inspectDeveloperPreflight(readyRoster(), input);
  assert.equal(result.dispatchAllowed, false);
  assert.ok(result.reasons.includes('provider-readback-identity-source-or-freshness-mismatch'));
  assert.ok(result.reasons.includes('missing-or-invalid-distributed-fenced-lease'));
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
  const preflight = inspectDeveloperPreflight(readyRoster(), boundPreflight());
  assert.equal(preflight.dispatchAllowed, false);
  assert.equal(preflight.requestedWorkId, 'junction.hostinger.code.wave5');
  assert.equal(preflight.requestedAttemptId, 'attempt-hostinger-001');
  assert.ok(!preflight.reasons.includes('missing-or-invalid-distributed-fenced-lease'));
  assert.ok(!preflight.reasons.includes('stale-or-mismatched-distributed-fencing-ledger-readback'));
  assert.ok(preflight.reasons.includes('provider-readback-not-authenticated-by-planning-module'));
  assert.ok(preflight.reasons.includes('distributed-lease-not-authenticated-by-planning-module'));
  assert.ok(preflight.reasons.includes('distributed-ledger-readback-not-authenticated-by-planning-module'));
  assert.ok(preflight.reasons.includes('git-remote-head-readback-not-authenticated-by-planning-module'));
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

test('P1: work ID must be scoped to the exact pet and role', () => {
  const input = boundPreflight();
  input.workId = 'junction.aiven.code.wave5';
  const result = inspectDeveloperPreflight(readyRoster(), input);
  assert.equal(result.dispatchAllowed, false);
  assert.ok(result.reasons.includes('missing-or-invalid-work-id-or-distinct-attempt-id'));
  assert.ok(result.reasons.includes('missing-or-invalid-distributed-fenced-lease'));
  assert.ok(result.reasons.includes('stale-or-mismatched-distributed-fencing-ledger-readback'));
});

test('P1: attempt ID required, separately bound to both ledger and lease', () => {
  const input = boundPreflight();
  input.attemptId = null;
  const result = inspectDeveloperPreflight(readyRoster(), input);
  assert.ok(result.reasons.includes('missing-or-invalid-work-id-or-distinct-attempt-id'));
  assert.ok(result.reasons.includes('missing-or-invalid-distributed-fenced-lease'));
  assert.equal(result.dispatchAllowed, false);
});

test('P1: reused attempt ID from ledger is rejected', () => {
  const input = boundPreflight();
  input.ledgerReadback.previousAttemptId = input.attemptId;
  const result = inspectDeveloperPreflight(readyRoster(), input);
  assert.ok(result.reasons.includes('stale-or-mismatched-distributed-fencing-ledger-readback'));
  assert.equal(result.dispatchAllowed, false);
});

test('P1: task branch outside pet scope or invalid expected HEAD is blocked', () => {
  const input = boundPreflight();
  input.taskBranch = 'codex/junction-aiven-wave5';
  input.expectedRemoteHead = 'unexpected-short-sha';
  const result = inspectDeveloperPreflight(readyRoster(), input);
  assert.ok(result.reasons.includes('missing-or-invalid-task-branch-or-expected-remote-head'));
  assert.ok(result.reasons.includes('stale-or-mismatched-git-remote-head-readback'));
  assert.equal(result.dispatchAllowed, false);
});

test('P1: lease receipt must bind immutable expected Git HEAD and branch', () => {
  const input = boundPreflight();
  input.leaseReceipt.expectedRemoteHead = 'd'.repeat(40);
  input.leaseReceipt.taskBranch = 'codex/junction-hostinger-old';
  const result = inspectDeveloperPreflight(readyRoster(), input);
  assert.ok(result.reasons.includes('missing-or-invalid-distributed-fenced-lease'));
  assert.equal(result.dispatchAllowed, false);
});

test('P1: stale fencing token or mismatched current ledger lease is blocked', () => {
  const input = boundPreflight();
  input.ledgerReadback.lastCommittedFencingToken = 42;
  input.ledgerReadback.leaseId = 'lease-forged-owner-99999';
  const result = inspectDeveloperPreflight(readyRoster(), input);
  assert.ok(result.reasons.includes('stale-or-mismatched-distributed-fencing-ledger-readback'));
  assert.equal(result.dispatchAllowed, false);
});

test('P1: stale ledger readback or future timestamp cannot pass preflight', () => {
  for (const observedAt of ['2026-11-12T23:45:00.000Z', '2026-11-13T00:01:00.000Z']) {
    const input = boundPreflight();
    input.ledgerReadback.observedAt = observedAt;
    const result = inspectDeveloperPreflight(readyRoster(), input);
    assert.ok(result.reasons.includes('stale-or-mismatched-distributed-fencing-ledger-readback'));
  }
});

test('P1: stale or substituted Git remote HEAD readback is blocked', () => {
  const input = boundPreflight();
  input.remoteHeadReadback.headSha = 'e'.repeat(40);
  input.remoteHeadReadback.observedAt = '2026-11-12T23:00:00.000Z';
  const result = inspectDeveloperPreflight(readyRoster(), input);
  assert.ok(result.reasons.includes('stale-or-mismatched-git-remote-head-readback'));
  assert.equal(result.dispatchAllowed, false);
});

test('P1: reviewer remains read-only and does not require a company writer lease', () => {
  const input = boundPreflight();
  input.role = 'review';
  input.workId = 'junction.hostinger.review.wave5';
  input.leaseReceipt = null;
  input.ledgerReadback = null;
  const result = inspectDeveloperPreflight(readyRoster(), input);
  assert.equal(result.dispatchAllowed, false);
  assert.ok(!result.reasons.includes('missing-or-invalid-distributed-fenced-lease'));
  assert.ok(!result.reasons.includes('missing-authoritative-distributed-ledger-readback'));
});
