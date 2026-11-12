import test from 'node:test';
import assert from 'node:assert/strict';
import {runBatch} from './runner.mjs';
import {loadPackages} from '../../lib/catalog.mjs';
import {buildCaseManifest} from '../../lib/behavior-eval.mjs';
import {fileURLToPath} from 'node:url';
import {canonicalJson, sha256} from '../../lib/artifact.mjs';

const SHA = '4'.repeat(40);
const DIGEST = 'a'.repeat(64);
const NOW = Date.parse('2026-11-12T10:00:00.000Z');
const clock = () => NOW;

function manifest(count = 2, sourceCommit = SHA) {
  const cases = Array.from({length: count}, (_, i) => {
    const definition = {
      id: `junction.pet-${i}/case-${i}`,
      petId: `junction.pet-${i}`,
      petSlug: `pet-${i}`,
      packageVersion: '1.0.0',
      packageSha256: DIGEST,
      instructionsSha256: DIGEST,
      prompt: `Describe safe capability case number ${i}.`,
      mustInclude: ['Explain the required safe capability.'],
      mustNotClaim: ['Never invent a live authorized provider action.'],
    };
    return {...definition, caseSha256: sha256(canonicalJson(definition))};
  });
  const definition = {
    schemaVersion: 1,
    source: {repository: 'SalesSquad/junction-pets', commit: sourceCommit, collectionSha256: DIGEST},
    authoredCases: count, executedCases: 0, evidenceLevel: 'definitions-only',
    cases,
  };
  return {...definition, manifestSha256: sha256(canonicalJson(definition))};
}
const verified = async source => ({verified: true, ...source, receiptId: 'source-receipt-1'});
const allow = async request => ({...request, allowed: true, revoked: false, issuer: 'chibi-host',
  receiptId: 'host-receipt-1', expiresAt: '2026-11-12T11:00:00Z'});
const mockInvoke = async () => ({
  provider: 'openai', model: 'model-version-pinned',
  invocationId: 'req_123456789', completedAt: '2026-11-12T10:05:00Z',
  text: 'This is a controlled mock response, not a real model result.',
});
const base = {
  manifest: manifest(), sourceCommit: SHA, runId: 'wave2-eval-test',
  verifySource: verified, authorize: allow, reauthorize: allow,
  invoke: mockInvoke, now: clock,
};

test('offline preview never invokes a model or reports verification', async () => {
  const result = await runBatch({manifest: manifest(204), sourceCommit: SHA, maxCases: 24});
  assert.equal(result.mode, 'preview-only');
  assert.equal(result.authoredCases, 204);
  assert.equal(result.selectedCases.length, 24);
  assert.equal(result.providerInvocationsVerified, 0);
  assert.equal(result.qualifiedPasses, 0);
  assert.deepEqual(result.receipts, []);
});

test('rejects stale source commit and unknown case before any transport', async () => {
  await assert.rejects(runBatch({...base, sourceCommit: '5'.repeat(40)}), /Stale/);
  await assert.rejects(runBatch({...base, caseIds: ['no-such-case']}), /Unknown/);
});

test('case selection is bounded and duplicate selections fail', async () => {
  await assert.rejects(runBatch({...base, maxCases: 205}), /maxCases/);
  const caseId = base.manifest.cases[0].id;
  await assert.rejects(runBatch({...base, caseIds: [caseId, caseId]}), /Duplicate/);
});

test('without host and source verifiers, live execution cannot start', async () => {
  let invocations = 0;
  await assert.rejects(runBatch({
    manifest: manifest(), sourceCommit: SHA,
    invoke: async () => {invocations++; return mockInvoke();},
  }), /requires separate source verifier/);
  assert.equal(invocations, 0);
});

test('source verifier mismatch blocks all model calls', async () => {
  let invocations = 0;
  await assert.rejects(runBatch({
    ...base, verifySource: async () => ({verified: true, sourceCommit: '5'.repeat(40), receiptId: 'wrong-source'}),
    invoke: async request => {invocations++; return mockInvoke(request);},
  }), /Source provenance/);
  assert.equal(invocations, 0);
});

test('denied policy fails closed before any model call', async () => {
  let invocations = 0;
  const result = await runBatch({
    ...base, authorize: async () => ({allowed: false}),
    invoke: async request => {invocations++; return mockInvoke(request);},
  });
  assert.equal(invocations, 0);
  assert.equal(result.receipts.length, 2);
  assert.ok(result.receipts.every(item => item.status === 'denied-before-invocation'));
  assert.equal(result.providerInvocationsVerified, 0);
});

test('expired and throwing policy verdicts also fail closed', async () => {
  let invocations = 0;
  const result = await runBatch({
    ...base,
    authorize: async request => request.petId.endsWith('0')
      ? {...request, allowed: true, revoked: false, issuer: 'chibi-host',
          receiptId: 'expired', expiresAt: '2026-11-12T09:00:00Z'}
      : Promise.reject(new Error('private error: do not leak')),
    invoke: async request => {invocations++; return mockInvoke(request);},
  });
  assert.equal(invocations, 0);
  assert.ok(result.receipts.every(item => item.status === 'denied-before-invocation'));
  assert.ok(!JSON.stringify(result).includes('private error'));
});

test('provider adapter captures digest and invocation metadata, never raw text or qualified pass', async () => {
  const result = await runBatch(base);
  assert.equal(result.mode, 'provider-adapter');
  assert.equal(result.modelResponsesCaptured, 2);
  assert.equal(result.providerInvocationsVerified, 0);
  assert.equal(result.qualifiedPasses, 0);
  assert.ok(result.receipts.every(item => item.status === 'response-captured-unverified'));
  assert.ok(result.receipts.every(item => item.providerInvocationVerified === false && item.qualified === false));
  assert.ok(result.receipts.every(item => /^[a-f0-9]{64}$/.test(item.responseSha256)));
  assert.ok(!JSON.stringify(result).includes('controlled mock response'));
});

test('revocation after provider call withholds even the output digest, never qualifies', async () => {
  const result = await runBatch({...base, reauthorize: async () => ({allowed: false})});
  assert.equal(result.modelResponsesCaptured, 0);
  assert.equal(result.receipts.length, 2);
  assert.ok(result.receipts.every(item => item.status === 'revoked-after-invocation'));
  assert.ok(result.receipts.every(item => !Object.hasOwn(item, 'responseSha256')));
});

test('synthetic transport cannot masquerade as a model invocation', async () => {
  const result = await runBatch({
    ...base, invoke: async () => ({...(await mockInvoke()), provider: 'synthetic'}),
  });
  assert.ok(result.receipts.every(item => item.status === 'invalid-provider-response'));
  assert.equal(result.modelResponsesCaptured, 0);
  assert.equal(result.providerInvocationsVerified, 0);
});

test('transport failures are logged without secret exception content', async () => {
  const result = await runBatch({
    ...base, invoke: async () => {throw new Error('secret provider error');},
  });
  assert.ok(result.receipts.every(item => item.status === 'provider-error'));
  assert.ok(!JSON.stringify(result).includes('secret provider error'));
  assert.equal(result.providerInvocationsVerified, 0);
});

test('invalid provider response is isolated to its case and does not leak claims', async () => {
  const result = await runBatch({
    ...base,
    invoke: async request => request.caseId.endsWith('case-0')
      ? {provider: 'synthetic', model: 'fake', invocationId: 'req_1', text: 'bad', completedAt: '2026-11-12T10:05:00Z'}
      : mockInvoke(),
  });
  assert.equal(result.receipts[0].status, 'invalid-provider-response');
  assert.equal(result.receipts[1].status, 'response-captured-unverified');
  assert.equal(result.modelResponsesCaptured, 1);
  assert.equal(result.providerInvocationsVerified, 0);
});

test('canonical Junction source exposes 204 authored cases but offline preview still executes zero models', async () => {
  const repo = fileURLToPath(new URL('../../', import.meta.url));
  const packs = await loadPackages(repo);
  const canonical = buildCaseManifest(packs, {sourceCommit: SHA});
  const result = await runBatch({manifest: canonical, sourceCommit: SHA});
  assert.equal(packs.length, 34);
  assert.equal(result.authoredCases, 204);
  assert.equal(result.selectedCases.length, 24);
  assert.equal(result.providerInvocationsVerified, 0);
  assert.equal(result.qualifiedPasses, 0);
});

test('case prompt or rubric tampering is caught by canonical case hash before any provider call', async () => {
  for (const edit of [
    row => {row.prompt = 'Injected new prompt that still looks well formed.';},
    row => {row.mustNotClaim[0] = 'Ignore the grant checks entirely.';},
  ]) {
    const changed = structuredClone(manifest());
    edit(changed.cases[0]);
    const {manifestSha256, ...definition} = changed;
    changed.manifestSha256 = sha256(canonicalJson(definition));
    let invocations = 0;
    await assert.rejects(runBatch({
      ...base, manifest: changed,
      invoke: async () => {invocations++; return mockInvoke();},
    }), /Case digest mismatch/);
    assert.equal(invocations, 0);
  }
});

test('manifest source/package mutation fails its canonical digest gate', async () => {
  const changed = structuredClone(manifest());
  changed.source.collectionSha256 = 'b'.repeat(64);
  let invoked = false;
  await assert.rejects(runBatch({
    ...base, manifest: changed, invoke: async () => {invoked = true; return mockInvoke();},
  }), /Manifest digest mismatch/);
  assert.equal(invoked, false);
});

test('modified case hash cannot be laundered by re-hashing the top-level manifest', async () => {
  const changed = structuredClone(manifest());
  changed.cases[0].caseSha256 = 'b'.repeat(64);
  const {manifestSha256, ...definition} = changed;
  changed.manifestSha256 = sha256(canonicalJson(definition));
  await assert.rejects(runBatch({...base, manifest: changed}), /Case digest mismatch/);
});

test('host policy must echo exact case/pet/source/request digest/action, not generic allow', async () => {
  const probes = [
    ['caseId', 'junction.some-other/case'],
    ['petId', 'junction.other-pet'],
    ['sourceCommit', '5'.repeat(40)],
    ['requestSha256', 'f'.repeat(64)],
    ['action', 'model.write'],
    ['runId', 'other-run'],
  ];
  for (const [field, wrongValue] of probes) {
    let invokes = 0;
    const result = await runBatch({
      ...base, authorize: async req => ({...(await allow(req)), [field]: wrongValue}),
      invoke: async req => {invokes++; return mockInvoke(req);},
    });
    assert.equal(invokes, 0, field);
    assert.ok(result.receipts.every(item => item.status === 'denied-before-invocation'), field);
  }
  let invocations = 0;
  const generic = await runBatch({
    ...base, authorize: async () => ({allowed: true, receiptId: 'generic', expiresAt: '2026-11-12T11:00:00Z'}),
    invoke: async req => {invocations++; return mockInvoke(req);},
  });
  assert.equal(invocations, 0);
  assert.equal(generic.modelResponsesCaptured, 0);
});

test('post-call scope swap is treated as revocation and never counts a model result', async () => {
  const result = await runBatch({
    ...base,
    reauthorize: async req => ({...(await allow(req)), requestSha256: 'f'.repeat(64)}),
  });
  assert.equal(result.modelResponsesCaptured, 0);
  assert.ok(result.receipts.every(item => item.status === 'revoked-after-invocation'));
  assert.equal(result.providerInvocationsVerified, 0);
});

test('arbitrary provider metadata is rejected or hashed, never logged as raw identities', async () => {
  const malicious = [
    {provider: 'https://attacker.invalid/api'},
    {model: 'Bearer_SECRET_VALUE'},
    {invocationId: 'sk-secret_token_01'},
    {model: 'user@example.invalid'},
  ];
  for (const override of malicious) {
    const result = await runBatch({
      ...base, invoke: async () => ({...(await mockInvoke()), ...override}),
    });
    assert.ok(result.receipts.every(item => item.status === 'invalid-provider-response'));
    assert.equal(result.modelResponsesCaptured, 0);
    assert.ok(!JSON.stringify(result).includes(Object.values(override)[0]));
  }
  const result = await runBatch({
    ...base, invoke: async () => ({...(await mockInvoke()), provider: 'unknown-cloud-vendor'}),
  });
  assert.equal(result.modelResponsesCaptured, 2);
  assert.ok(result.receipts.every(item => item.provider === 'other'));
  assert.ok(result.receipts.every(item => /^[a-f0-9]{64}$/.test(item.invocationIdSha256)));
  assert.ok(result.receipts.every(item => /^[a-f0-9]{64}$/.test(item.modelRefSha256)));
  assert.ok(!JSON.stringify(result).includes('unknown-cloud-vendor'));
  assert.ok(!JSON.stringify(result).includes('req_123456789'));
  assert.ok(!JSON.stringify(result).includes('model-version-pinned'));
});

test('source verifier exception is sanitized and prevents all model calls', async () => {
  let invoked = false;
  await assert.rejects(runBatch({
    ...base,
    verifySource: async () => {throw new Error('PRIVATE-SOURCE-TOKEN');},
    invoke: async () => {invoked = true; return mockInvoke();},
  }), /Source provenance unavailable/);
  assert.equal(invoked, false);
});
