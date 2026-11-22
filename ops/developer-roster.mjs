/**
 * Source-bound, planning-only developer continuity for the 34 Junction pets.
 *
 * This module cannot authenticate Codex Cloud, acquire distributed leases, or
 * start agents. Manifests and caller-supplied receipts are untrusted inputs.
 * A host-side executor must independently recheck environment, source,
 * lease, and capacity before doing work. Chibi runtime grants are a distinct
 * boundary, not a prerequisite for code/test developer tasks. No result from this
 * module is permission to dispatch a task.
 */

export const DEVELOPER_ROSTER_SCHEMA_VERSION = 1;

const REPOSITORY = 'SalesSquad/junction-pets';
const PROVIDER = 'codex-cloud';
const CLOUD_STATES = new Set([
  'unprovisioned', 'published-id-pending', 'provisioning', 'ready',
  'running', 'blocked', 'failed', 'stale'
]);
const SHA_RE = /^[a-f0-9]{40}$/;
const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const ATTEMPT_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/;
const LEASE_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$/;
const UTC_INSTANT_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const REQUIRED_CHECKS = ['npm run validate', 'npm test', 'npm run build'];
const REQUIRED_KEYS = [
  'schemaVersion', 'petSlug', 'agentId', 'provider', 'desiredName',
  'repository', 'branchPattern', 'ownedPath', 'agentInstructions',
  'runtimeInstructions', 'setupCommand', 'checkCommands', 'provisioning'
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function utcInstant(value) {
  return typeof value === 'string' && UTC_INSTANT_RE.test(value) &&
    Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value;
}

// Provider settings receipts retain their original microsecond precision.
// This compatibility rule is ONLY for recorded, untrusted manifest metadata:
// live readbacks, leases and fencing keep the strict millisecond contract above.
// Check the calendar at JavaScript's precision without rewriting the receipt.
function recordedUtcObservation(value) {
  if (utcInstant(value)) return true;
  return typeof value === 'string' &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$/.test(value) &&
    utcInstant(value.slice(0, 23) + 'Z');
}

function sortedKeys(object) {
  return Object.keys(object).sort().join('|');
}

function expectedManifest(company) {
  return {
    schemaVersion: 1,
    petSlug: `junction-${company}`,
    agentId: `junction-dev-${company}`,
    provider: PROVIDER,
    desiredName: `junction-${company}`,
    repository: REPOSITORY,
    branchPattern: `codex/junction-${company}-*`,
    ownedPath: `pets/${company}/`,
    agentInstructions: 'ops/AGENTS.md',
    runtimeInstructions: `pets/${company}/AGENTS.md`,
    setupCommand: company === 'verda' ? 'bash ops/cloud/rml1/setup.sh && npm ci --ignore-scripts' : 'npm ci --ignore-scripts',
    checkCommands: REQUIRED_CHECKS
  };
}

function checkManifest(manifest, company) {
  assert(manifest && typeof manifest === 'object' && !Array.isArray(manifest),
    `Invalid environment manifest for ${company}`);
  assert(sortedKeys(manifest) === [...REQUIRED_KEYS].sort().join('|'),
    `Unknown or missing environment manifest field for ${company}`);
  const expected = expectedManifest(company);
  for (const [key, value] of Object.entries(expected)) {
    assert(JSON.stringify(manifest[key]) === JSON.stringify(value),
      `Invalid ${key} in ${company} environment`);
  }

  const provision = manifest.provisioning;
  assert(provision && typeof provision === 'object' && !Array.isArray(provision) &&
    CLOUD_STATES.has(provision.state), `Invalid cloud state for ${company}`);
  if (provision.state === 'unprovisioned') {
    assert(sortedKeys(provision) === 'environmentId|evidenceUrl|state|verifiedAt' &&
      provision.environmentId === null && provision.verifiedAt === null &&
      provision.evidenceUrl === null,
    `Unprovisioned ${company} cannot claim Cloud identity or evidence`);
  } else if (provision.state === 'published-id-pending') {
    assert(sortedKeys(provision) ===
      'environmentId|evidenceUrl|publicationObservation|sourceCommit|state|taskCheck|verifiedAt',
    `Published-ID-pending ${company} has missing/unknown provenance fields`);
    assert(provision.environmentId === null && utcInstant(provision.verifiedAt) &&
      SHA_RE.test(provision.sourceCommit || '') &&
      provision.publicationObservation === 'owner-observed-settings-and-task-picker' &&
      /^https:\/\/chatgpt\.com\/local\/[a-f0-9-]{36}$/.test(provision.evidenceUrl || ''),
    `Invalid published-ID-pending evidence for ${company}`);
    const task = provision.taskCheck;
    assert(task && typeof task === 'object' && !Array.isArray(task) &&
      sortedKeys(task) === 'evidenceUrl|executed|passed|result|sourceCommit|suite' &&
      task.suite === 'submission-gate' && task.result === 'pass' &&
      Number.isSafeInteger(task.executed) && task.executed > 0 &&
      task.passed === task.executed && task.sourceCommit === provision.sourceCommit &&
      task.evidenceUrl === provision.evidenceUrl,
    `Invalid published task check for ${company}`);
  } else {
    assert(sortedKeys(provision) === 'environmentId|evidenceUrl|state|verifiedAt',
      `Unexpected Cloud provisioning fields for ${company}`);
    const needsId = ['ready', 'running', 'stale'].includes(provision.state);
    assert(needsId
      ? typeof provision.environmentId === 'string' && provision.environmentId.length >= 5
      : provision.environmentId === null ||
        (typeof provision.environmentId === 'string' && provision.environmentId.length >= 5),
    `Invalid Cloud environment ID for ${company}`);
    assert(recordedUtcObservation(provision.verifiedAt) &&
      typeof provision.evidenceUrl === 'string' &&
      provision.evidenceUrl.startsWith('https://'),
    `Cloud provisioning metadata lacks recorded evidence for ${company}`);
  }
}

function roleDefinitions(company, agentId, branchPrefix, sourceCommit) {
  const ownership = [
    ['code', [`pets/${company}/`], 'write'],
    ['test', [`tests/pet-${company}.test.mjs`], 'write'],
    ['review', [], 'read-only']
  ];
  return ownership.map(([role, writePaths, access]) => ({
    id: `${agentId}:${role}`,
    companySlug: company,
    role,
    access,
    writePaths,
    writerLeaseDomain: access === 'write' ? `junction.${company}.write` : null,
    reviewerMustBeIndependentFromAuthors: role === 'review',
    workIdTemplate: `junction.${company}.${role}.<slice>`,
    taskBranchPrefix: branchPrefix,
    sourceCommit,
    state: 'logical-planned-not-running',
    handoff: {
      required: [
        'workId', 'exactSourceCommit', 'ownedPaths', 'dirtyBaseline',
        'taskBranch', 'taskHeadSha', 'checks', 'evidenceUrls',
        'blockers', 'nextAction', 'leaseRelease',
        ...(role === 'review' ? ['reviewerIdentity', 'authorIdentity', 'independenceEvidence'] : [])
      ],
      retry: 'Recheck exact source/branch HEAD, current provider identity, ' +
        'distributed lease and capacity; use same work ID only for an idempotent retry, ' +
        'with a distinct attempt ID and monotonic fencing token.',
      writePolicy: access === 'write'
        ? 'Exclusive company-scoped distributed writer lease shared by code and test roles; ' +
          'only one active writer for this company, even on disjoint paths. ' +
          'Integrators own all services/pet-adapters and other shared paths.'
        : 'Independent read-only review; no writes and no authority to approve a deployment.'
    }
  }));
}

function nextAction(state, manifestSourceCurrent) {
  if (state === 'unprovisioned')
    return 'Publish the desired Codex Cloud environment; read back its opaque provider ID via an authenticated API.';
  if (state === 'published-id-pending')
    return manifestSourceCurrent
      ? 'Read back the provider environment ID; an owner-observed task is not authenticated environment readiness.'
      : 'Re-run current-SHA source checks, then read back the provider environment ID; previous task provenance is stale.';
  if (state === 'ready' || state === 'running')
    return 'Re-authenticate and recheck current provider environment ID, exact source SHA, distributed lease and capacity.';
  return 'Repair the recorded provisioning failure/state; re-read provider identity and source before dispatch.';
}

function continuityProposal(company, state, manifestSourceCurrent) {
  const stage = state === 'unprovisioned' ? 'cloud-environment-publication'
    : state === 'published-id-pending'
      ? manifestSourceCurrent ? 'authenticated-cloud-id-readback' : 'current-source-retest-and-id-readback'
      : state === 'ready' || state === 'running'
        ? 'provider-readback-and-dispatch-preflight' : 'cloud-provisioning-recovery';
  return {
    stage,
    priority: state === 'published-id-pending' ? 'P1-source-or-provider-identity'
      : state === 'ready' || state === 'running' ? 'P1-recheck-declared-readiness'
        : state === 'unprovisioned' ? 'P2-provision-environment' : 'P1-repair-cloud-state',
    task: `junction.${company}.cloud-bootstrap`,
    state: 'proposed-not-enqueued',
    nextAction: nextAction(state, manifestSourceCurrent),
    acceptance: [
      'authenticated immutable Cloud environment ID bound to this company',
      'fresh evidence bound to exact task/PR HEAD, source SHA and current provider state',
      'verified distributed lease and executor capacity before any code/test writer starts',
      'code and tests pass for exact task commit; independent reviewer reports evidence',
      'integrator owns shared paths, PR follow-through and release decision'
    ],
    fallback: 'If Cloud is not ready, perform scoped offline/local tests on a clean, pinned source; ' +
      'record as local-only and never promote that evidence to Cloud-ready.'
  };
}

/**
 * Build one deterministic logical developer with three logical roles per pet.
 * Exactly 34 canonical company slugs must come from the catalog, not the input
 * manifests themselves. No side effects or provider calls are made.
 */
export function buildDeveloperRoster(manifests, {
  expectedCompanies,
  sourceCommit,
  generatedAt = new Date('1970-01-01T00:00:00.000Z'),
  requestedConcurrency = 0
} = {}) {
  assert(SHA_RE.test(sourceCommit || ''), 'Roster requires exact clean source commit SHA');
  assert(Array.isArray(expectedCompanies) && expectedCompanies.length === 34 &&
    expectedCompanies.every(slug => typeof slug === 'string' && SLUG_RE.test(slug)) &&
    new Set(expectedCompanies).size === 34,
  'Roster requires 34 unique catalog company slugs');
  assert(Array.isArray(manifests) && manifests.length === 34,
    'Roster requires exactly 34 Cloud environment manifests');
  assert(generatedAt instanceof Date && Number.isFinite(generatedAt.valueOf()),
    'Roster requires a valid generatedAt');
  assert(Number.isSafeInteger(requestedConcurrency) && requestedConcurrency >= 0 &&
    requestedConcurrency <= 34, 'Requested concurrency must be in 0..34');

  const companySet = new Set(expectedCompanies);
  const encountered = new Set();
  const environmentIds = new Set();
  const reservedPaths = new Map();
  const agents = [];

  for (const manifest of manifests) {
    const slug = typeof manifest?.petSlug === 'string' &&
      manifest.petSlug.startsWith('junction-')
      ? manifest.petSlug.slice('junction-'.length) : '';
    assert(companySet.has(slug), `Unknown company slug in Cloud manifest: ${slug || '(missing)'}`);
    assert(!encountered.has(slug), `Duplicate company or developer role: ${slug}`);
    encountered.add(slug);
    checkManifest(manifest, slug);

    const id = manifest.provisioning.environmentId;
    if (id !== null) {
      assert(!environmentIds.has(id), `Shared Cloud environment ID is forbidden: ${id}`);
      environmentIds.add(id);
    }

    const roles = roleDefinitions(slug, manifest.agentId,
      `codex/junction-${slug}-`, sourceCommit);
    for (const role of roles) {
      for (const path of role.writePaths) {
        for (const existing of reservedPaths.keys()) {
          assert(!(path === existing || path.startsWith(existing) || existing.startsWith(path)),
            `Developer role write-path collision: ${path} versus ${existing}`);
        }
        reservedPaths.set(path, role.id);
      }
    }

    const p = manifest.provisioning;
    const manifestSourceCurrent = p.state === 'published-id-pending' &&
      p.sourceCommit === sourceCommit;
    agents.push({
      companySlug: slug,
      petSlug: manifest.petSlug,
      canonicalAgentId: manifest.agentId,
      state: 'logical-planned-not-running',
      ownership: {
        petPath: manifest.ownedPath,
        agentInstructions: manifest.agentInstructions,
        runtimeInstructions: manifest.runtimeInstructions,
        untrustedRuntimePersonaPath: manifest.runtimeInstructions,
        runtimePersonaTrust: 'company-specific-task-data-not-executor-policy',
        branchPattern: manifest.branchPattern,
        sharedPathsOwner: 'Monorepo integrator (not company writers)',
        companyWriterLeaseDomain: `junction.${slug}.write`
      },
      cloud: {
        provider: manifest.provider,
        desiredName: manifest.desiredName,
        recordedState: p.state,
        providerEnvironmentId: id,
        manifestSourceCommit: p.sourceCommit ?? null,
        manifestSourceCurrent,
        evidenceUrl: p.evidenceUrl,
        recordedAt: p.verifiedAt,
        verificationTier: p.state === 'unprovisioned'
          ? 'not-provisioned'
          : p.state === 'published-id-pending'
            ? manifestSourceCurrent
              ? 'owner-observed-id-pending-source-matched'
              : 'owner-observed-id-pending-stale-source'
            : 'manifest-declaration-not-live-authenticated',
        authenticatedProviderReady: false
      },
      roles,
      dispatch: {
        state: 'blocked-awaiting-authoritative-recheck',
        admitted: false,
        actualProcessStarted: false,
        requiredGates: [
          'authenticated-live-provider-id',
          'exact-current-source-SHA',
          'exclusive-distributed-write-lease-with-fencing',
          'verified-executor-capacity'
        ],
        localLeaseNotSufficient: true,
        nextAction: nextAction(p.state, manifestSourceCurrent)
      },
      continuity: continuityProposal(slug, p.state, manifestSourceCurrent)
    });
  }

  assert(encountered.size === companySet.size, 'Missing canonical company manifest');
  agents.sort((a, b) => a.companySlug.localeCompare(b.companySlug, 'en'));
  const roles = agents.flatMap(a => a.roles);
  assert(roles.length === 102 && new Set(roles.map(role => role.id)).size === 102,
    'Developer role identity collision');

  return {
    schemaVersion: DEVELOPER_ROSTER_SCHEMA_VERSION,
    generatedAt: generatedAt.toISOString(),
    source: {
      repository: REPOSITORY,
      commit: sourceCommit,
      verification: 'caller-provided-source-SHA-not-independently-verified',
      hostedCiQualified: false
    },
    summary: {
      companyLanes: 34,
      logicalDevelopers: agents.length,
      logicalRoles: roles.length,
      plannedCodeRoles: 34,
      plannedTestRoles: 34,
      plannedReviewRoles: 34,
      environmentsWithRecordedId: agents.filter(a => a.cloud.providerEnvironmentId).length,
      ownerObservedIdPending: agents.filter(a => a.cloud.recordedState === 'published-id-pending').length,
      independentlyAuthenticatedReady: 0,
      actualWorkersStarted: 0,
      actualCloudTasksDispatched: 0,
      requestedConcurrency,
      verifiedAvailableCapacity: 0,
      planningOnly: true
    },
    dispatchPolicy: {
      mode: 'fail-closed-planning-only',
      provider: PROVIDER,
      noDispatchAuthority: true,
      localLeaseCannotAuthorizeDistributedWork: true,
      authenticatedReadbackRequiredPerAttempt: true,
      exactSourceRequired: true,
      exactWorkIdAttemptBranchAndRemoteHeadRequired: true,
      monotonicallyFencedLedgerReadbackRequiredForWriters: true,
      capacityMustBeProvenByExecutor: true,
      reviewRoleReadOnly: true,
      chibiRuntimeGrantNotRequiredForCodeOrTest: true,
      recheckBeforeEveryRetry: true
    },
    developers: agents
  };
}

/**
 * Explain blockers for a proposed dispatch. Supplying a string named "ready",
 * a stale task receipt, an untrusted readback, or a local lease never converts
 * this advisory plan into dispatch authority. Trusted provider/lease verification
 * must be implemented by the eventual control-plane executor, not by JSON.
 */
export function inspectDeveloperPreflight(roster, {
  companySlug,
  role = 'code',
  requestedSourceCommit,
  workId = null,
  attemptId = null,
  taskBranch = null,
  expectedRemoteHead = null,
  providerReadback = null,
  remoteHeadReadback = null,
  leaseReceipt = null,
  ledgerReadback = null,
  capacityReceipt = null,
  now = new Date()
} = {}) {
  assert(roster?.schemaVersion === DEVELOPER_ROSTER_SCHEMA_VERSION &&
    Array.isArray(roster.developers), 'Invalid developer roster plan');
  assert(now instanceof Date && Number.isFinite(now.valueOf()), 'Invalid preflight instant');
  const developer = roster.developers.find(row => row.companySlug === companySlug);
  assert(developer, 'Unknown company developer');
  const selectedRole = developer.roles.find(item => item.role === role);
  assert(selectedRole, 'Unknown developer role');

  const reasons = [];
  const exactSource = SHA_RE.test(requestedSourceCommit || '') &&
    requestedSourceCommit === roster.source.commit;
  if (!exactSource) reasons.push('wrong-or-unverified-source-commit');
  const exactWork = typeof workId === 'string' &&
    workId.startsWith(`junction.${companySlug}.${role}.`) &&
    workId.length <= 160 &&
    /^[a-z0-9][a-z0-9._-]*$/.test(workId.slice(`junction.${companySlug}.${role}.`.length));
  const exactAttempt = ATTEMPT_RE.test(attemptId || '');
  if (!exactWork || !exactAttempt)
    reasons.push('missing-or-invalid-work-id-or-distinct-attempt-id');
  const exactBranch = typeof taskBranch === 'string' &&
    taskBranch.startsWith(selectedRole.taskBranchPrefix) &&
    /^[a-z0-9][a-z0-9_-]*$/.test(taskBranch.slice(selectedRole.taskBranchPrefix.length)) &&
    taskBranch.length <= 200;
  const exactHead = SHA_RE.test(expectedRemoteHead || '');
  if (!exactBranch || !exactHead) reasons.push('missing-or-invalid-task-branch-or-expected-remote-head');
  const env = developer.cloud;
  if (!['ready', 'running'].includes(env.recordedState))
    reasons.push('manifest-does-not-report-ready-environment');
  if (!env.providerEnvironmentId)
    reasons.push('missing-immutable-cloud-environment-id');

  if (!providerReadback || typeof providerReadback !== 'object') {
    reasons.push('missing-authenticated-provider-readback');
  } else {
    if (providerReadback.provider !== PROVIDER ||
      providerReadback.environmentId !== env.providerEnvironmentId ||
      providerReadback.repository !== REPOSITORY ||
      providerReadback.sourceCommit !== requestedSourceCommit ||
      providerReadback.state !== 'ready' ||
      !utcInstant(providerReadback.observedAt) ||
      now.valueOf() - Date.parse(providerReadback.observedAt) > 5 * 60_000 ||
      Date.parse(providerReadback.observedAt) > now.valueOf()) {
      reasons.push('provider-readback-identity-source-or-freshness-mismatch');
    }
    // A caller-controlled object has no provider API provenance.
    reasons.push('provider-readback-not-authenticated-by-planning-module');
  }

  if (!remoteHeadReadback || typeof remoteHeadReadback !== 'object') {
    reasons.push('missing-current-git-remote-head-readback');
  } else {
    if (remoteHeadReadback.repository !== REPOSITORY ||
      remoteHeadReadback.branch !== taskBranch ||
      remoteHeadReadback.headSha !== expectedRemoteHead ||
      !utcInstant(remoteHeadReadback.observedAt) ||
      now.valueOf() - Date.parse(remoteHeadReadback.observedAt) > 60_000 ||
      Date.parse(remoteHeadReadback.observedAt) > now.valueOf()) {
      reasons.push('stale-or-mismatched-git-remote-head-readback');
    }
    reasons.push('git-remote-head-readback-not-authenticated-by-planning-module');
  }

  if (selectedRole.access === 'write') {
    if (!leaseReceipt || typeof leaseReceipt !== 'object' ||
      leaseReceipt.scope !== 'distributed' ||
      leaseReceipt.leaseDomain !== developer.ownership.companyWriterLeaseDomain ||
      leaseReceipt.companySlug !== companySlug ||
      leaseReceipt.agentId !== developer.canonicalAgentId ||
      leaseReceipt.sourceCommit !== requestedSourceCommit ||
      leaseReceipt.workId !== workId ||
      leaseReceipt.attemptId !== attemptId ||
      leaseReceipt.taskBranch !== taskBranch ||
      leaseReceipt.expectedRemoteHead !== expectedRemoteHead ||
      !LEASE_ID_RE.test(leaseReceipt.leaseId || '') ||
      !Number.isSafeInteger(leaseReceipt.fencingToken) ||
      leaseReceipt.fencingToken <= 0 ||
      !utcInstant(leaseReceipt.expiresAt) ||
      Date.parse(leaseReceipt.expiresAt) <= now.valueOf()) {
      reasons.push('missing-or-invalid-distributed-fenced-lease');
    } else {
      reasons.push('distributed-lease-not-authenticated-by-planning-module');
    }

    // Caller-provided ledgers are not authenticated. Shape/binding checks catch
    // stale fences, identity swaps and retry-ID reuse before a trusted executor
    // independently verifies the actual distributed ledger's current record.
    if (!ledgerReadback || typeof ledgerReadback !== 'object') {
      reasons.push('missing-authoritative-distributed-ledger-readback');
    } else {
      const fence = leaseReceipt?.fencingToken;
      const previous = ledgerReadback.lastCommittedFencingToken;
      const ledgerMatches = ledgerReadback.scope === 'distributed-lease-ledger' &&
        ledgerReadback.leaseDomain === developer.ownership.companyWriterLeaseDomain &&
        ledgerReadback.companySlug === companySlug &&
        ledgerReadback.agentId === developer.canonicalAgentId &&
        ledgerReadback.sourceCommit === requestedSourceCommit &&
        ledgerReadback.workId === workId &&
        ledgerReadback.attemptId === attemptId &&
        ledgerReadback.previousAttemptId !== attemptId &&
        (ledgerReadback.previousAttemptId === null ||
          ATTEMPT_RE.test(ledgerReadback.previousAttemptId || '')) &&
        ledgerReadback.taskBranch === taskBranch &&
        ledgerReadback.expectedRemoteHead === expectedRemoteHead &&
        ledgerReadback.leaseId === leaseReceipt?.leaseId &&
        Number.isSafeInteger(previous) && previous >= 0 &&
        Number.isSafeInteger(fence) && fence > previous &&
        ledgerReadback.currentFencingToken === fence &&
        utcInstant(ledgerReadback.observedAt) &&
        now.valueOf() >= Date.parse(ledgerReadback.observedAt) &&
        now.valueOf() - Date.parse(ledgerReadback.observedAt) <= 60_000;
      if (!ledgerMatches) reasons.push('stale-or-mismatched-distributed-fencing-ledger-readback');
      reasons.push('distributed-ledger-readback-not-authenticated-by-planning-module');
    }
  }

  if (!capacityReceipt || typeof capacityReceipt !== 'object' ||
    capacityReceipt.sourceCommit !== requestedSourceCommit ||
    capacityReceipt.companySlug !== companySlug ||
    !Number.isSafeInteger(capacityReceipt.freeSlots) ||
    capacityReceipt.freeSlots < 1 ||
    !utcInstant(capacityReceipt.observedAt) ||
    now.valueOf() - Date.parse(capacityReceipt.observedAt) > 60_000 ||
    Date.parse(capacityReceipt.observedAt) > now.valueOf()) {
    reasons.push('missing-or-stale-verified-executor-capacity');
  } else {
    reasons.push('capacity-not-authenticated-by-planning-module');
  }

  return {
    companySlug,
    role,
    workIdTemplate: selectedRole.workIdTemplate,
    requestedWorkId: workId,
    requestedAttemptId: attemptId,
    requestedTaskBranch: taskBranch,
    expectedRemoteHead,
    sourceCommit: roster.source.commit,
    status: 'blocked-requires-trusted-executor',
    dispatchAllowed: false,
    processStarted: false,
    reasons: [...new Set(reasons)]
  };
}
