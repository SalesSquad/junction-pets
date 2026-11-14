import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createLearningSession } from '../../apps/meta-resume-web/learning-core.mjs';
import { createLearningObservationBridge } from '../../apps/meta-resume-web/learning-observation.mjs';
import { createSession } from '../../apps/meta-resume-web/state.mjs';
import { FIXTURE, id } from '../../apps/meta-resume-web/fixture.mjs';
import { observationRequest } from '../../apps/meta-resume-web/observation-client.mjs';

const clone = (x) => structuredClone(x);
const hash = (x) => createHash('sha256').update(x).digest('hex');
const epoch = Date.parse('2026-11-14T12:00:00Z');
const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+XlZsAAAAASUVORK5CYII=';
const imageHash = hash(Buffer.from(png, 'base64'));

async function environment(style = 'one_step') {
  const env = { time: epoch, task: createSession(), learningOverride: null };
  env.learning = createLearningSession({ scope: { tenantId: 'synthetic-tenant', ownerId: 'synthetic-owner', contextId: 'camera-bag' }, now: () => env.time });
  let sequence = 0;
  env.command = async (operation, payload) => {
    const result = await env.learning.dispatch({ schema: 'lens.learning-command/v1', commandId: 'learning-' + (++sequence),
      expectedRevision: env.learning.snapshot().revision, operation, payload });
    assert.equal(result.ok, true, operation);
    return result;
  };
  env.bridge = createLearningObservationBridge({ read: () => ({ state: env.task.snapshot(), policy: env.task.getPolicy(),
    learning: env.learningOverride ?? env.learning.snapshot() }), now: () => env.time });
  env.recommend = () => {
    const s = env.task.snapshot();
    return env.learning.recommend({ taskId: s.taskId, revision: s.revision, status: s.status, nextStepId: s.nextUnconfirmedStep });
  };
  await env.command('setConsent', { enabled: true });
  await env.command('startEpisode', { episodeId: 'practice-a', templateId: 'camera-bag-v1' });
  await env.command('proposeMemory', { memoryId: 'help-style', style });
  await env.command('confirmMemory', { memoryId: 'help-style' });
  return env;
}

function payload(env) {
  const policy = env.task.getPolicy();
  const observation = {
    schemaVersion: 1, kind: 'meta.sam31.observation', evidenceMode: 'SYNTHETIC',
    episodeId: 'synthetic-capture-episode', sessionId: policy.sessionId, captureGeneration: policy.captureGeneration,
    runId: 'synthetic-run', trackGeneration: 0, sourceThroughFrameIndex: 0,
    frame: { frameIndex: 0, sha256: imageHash, capturedAt: new Date(env.time).toISOString(), width: 1, height: 1 },
    model: { id: 'facebook/sam3.1', codeCommit: 'eef6839bcfc3458dd52ea80535dc6bd62aea86b1',
      weightsRevision: 'daa63191845a41281374e725f4c9e51c7a824460', checkpointSha256: '0567debeec80ba4ac6369540c6c248025283cb3ff2b92827509e57e2b3541cb6' },
    tracks: [{ trackId: 'synthetic-candidate', label: 'Synthetic camera', bbox: [0, 0, 1, 1], maskSha256: hash('synthetic-mask'),
      crop: { sha256: imageHash, width: 1, height: 1, mimeType: 'image/png' }, visibility: 'visible' }],
  };
  const request = observationRequest({ observation, image: { kind: 'frame', dataUrl: 'data:image/png;base64,' + png,
    sha256: imageHash, trackId: null } }, env.task.snapshot(), policy);
  const result = {
    status: 'proposed',
    binding: { taskId: request.task.taskId, expectedRevision: request.task.revision, episodeId: observation.episodeId,
      sessionId: observation.sessionId, captureGeneration: observation.captureGeneration, frameSha256: imageHash,
      frameIndex: 0, runId: observation.runId, trackGeneration: 0 },
    proposal: { summary: 'A synthetic camera candidate is visible.',
      observations: [{ trackId: 'synthetic-candidate', text: 'A camera-shaped fixture is visible.' }],
      uncertainties: ['Visual similarity does not establish ownership.'], nextQuestion: 'Check the camera yourself before confirming.',
      nextStepProposal: clone(request.task.nextStep), physicalIdentityVerified: false, taskCompletionAuthorized: false },
  };
  return { request, result };
}

const checks = [];
async function check(name, fn) { await fn(); checks.push({ name, passed: true }); }

await check('Approved preference and observation compose without task or memory mutation', async () => {
  const env = await environment(), p = payload(env), beforeMemory = env.learning.exportState(), beforeTask = env.task.exportJournal();
  const ticket = env.bridge.begin(p.request);
  assert.deepEqual(ticket, {});
  assert.equal(await env.bridge.accept({ ...p, ticket }).then((x) => x.ok), true);
  const context = env.bridge.context(env.recommend());
  assert.equal(context.assistance.action, 'one_step');
  assert.equal(context.assistance.appliedMemoryId, 'help-style');
  assert.equal(context.summary, p.result.proposal.summary);
  assert.equal(context.physicalIdentityVerified, false);
  assert.equal(context.taskCompletionAuthorized, false);
  assert.equal(context.memoryMutationAuthorized, false);
  assert.equal(context.evidenceMode, 'SYNTHETIC');
  assert.equal(context.learningEvidenceMode, 'SYNTHETIC');
  assert.match(context.observationSha256, /^[a-f0-9]{64}$/);
  assert.equal(JSON.stringify(context).includes(png), false);
  context.summary = 'mutated returned value';
  assert.equal(env.bridge.context(env.recommend()).summary, p.result.proposal.summary);
  assert.deepEqual(env.learning.exportState(), beforeMemory);
  assert.deepEqual(env.task.exportJournal(), beforeTask);
});

await check('Both learning consent and capture permission are required', async () => {
  const env = await environment(), p = payload(env);
  await env.command('setConsent', { enabled: false });
  assert.equal(env.bridge.begin(p.request), null);
  await env.command('setConsent', { enabled: true });
  env.task.revokeCapture();
  assert.equal(env.bridge.begin(p.request), null);
});

await check('Correction invalidates old context and confirmed quiet preference suppresses guidance', async () => {
  const env = await environment(), p = payload(env);
  assert.equal((await env.bridge.accept({ ...p, ticket: env.bridge.begin(p.request) })).ok, true);
  await env.command('correctMemory', { memoryId: 'help-style', style: 'quiet' });
  assert.equal(env.bridge.context(env.recommend()), null);
  assert.equal((await env.bridge.accept({ ...p, ticket: env.bridge.begin(p.request) })).ok, true);
  const context = env.bridge.context(env.recommend());
  assert.equal(context.assistance.action, 'stay_silent');
  assert.equal(context.summary, null);
  assert.deepEqual(context.observations, []);
  assert.deepEqual(context.uncertainties, []);
  assert.equal(context.nextQuestion, null);
  assert.equal(context.nextStepProposal, null);
});

await check('A response started before forgetting cannot attach to a new learning episode', async () => {
  const env = await environment(), p = payload(env), ticket = env.bridge.begin(p.request);
  await env.command('forgetAll', {});
  await env.command('startEpisode', { episodeId: 'practice-after-forget', templateId: 'camera-bag-travel' });
  const result = await env.bridge.accept({ ...p, ticket });
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'STALE_OBSERVATION');
  assert.equal(env.bridge.context(env.recommend()), null);
  assert.deepEqual(env.learning.snapshot().memories, []);
});

await check('Capture revocation during image hashing fences the eventual result', async () => {
  const env = await environment(), p = payload(env), ticket = env.bridge.begin(p.request);
  const subtle = globalThis.crypto.subtle, original = subtle.digest;
  let release, entered, paused = false;
  const waiting = new Promise((resolve) => { release = resolve; });
  const started = new Promise((resolve) => { entered = resolve; });
  subtle.digest = async function (...args) {
    if (!paused) { paused = true; entered(); await waiting; }
    return original.apply(this, args);
  };
  try {
    const pending = env.bridge.accept({ ...p, ticket });
    await started;
    env.task.revokeCapture();
    release();
    assert.equal((await pending).ok, false);
    assert.equal(env.bridge.context(env.recommend()), null);
  } finally { release(); subtle.digest = original; }
});

await check('Expiry, scope changes and actual task progress invalidate the composed view', async () => {
  const env = await environment(), p = payload(env);
  assert.equal((await env.bridge.accept({ ...p, ticket: env.bridge.begin(p.request) })).ok, true);
  env.time += 30_000;
  assert.equal(env.bridge.context(env.recommend()), null);
  assert.equal(env.bridge.begin(p.request), null);
  env.time = epoch;
  const scoped = env.bridge.begin(p.request);
  env.learningOverride = env.learning.snapshot();
  env.learningOverride.scope.ownerId = 'another-synthetic-owner';
  assert.equal((await env.bridge.accept({ ...p, ticket: scoped })).ok, false);
  env.learningOverride = null;
  const progressing = env.bridge.begin(p.request);
  assert.equal(env.task.dispatch({ schemaVersion: 1, taskId: FIXTURE.taskId, commandId: id(701), expectedRevision: 0,
    operation: 'confirmStep', payload: { stepId: FIXTURE.steps[0].stepId } }).error, undefined);
  assert.equal((await env.bridge.accept({ ...p, ticket: progressing })).ok, false);
});

await check('Mutated request, forged completion authority and mismatched image bytes are rejected', async () => {
  const env = await environment();
  let p = payload(env), ticket = env.bridge.begin(p.request);
  p.request.observation.runId = 'changed-after-start';
  p.result.binding.runId = 'changed-after-start';
  assert.equal((await env.bridge.accept({ ...p, ticket })).ok, false);
  p = payload(env); ticket = env.bridge.begin(p.request);
  p.result.proposal.taskCompletionAuthorized = true;
  assert.equal((await env.bridge.accept({ ...p, ticket })).ok, false);
  p = payload(env); ticket = env.bridge.begin(p.request);
  p.request.image.dataUrl = 'data:image/png;base64,' + Buffer.from('synthetic-wrong-pixels').toString('base64');
  assert.equal((await env.bridge.accept({ ...p, ticket })).ok, false);
});

await check('Clear, forged tickets and old completions never resurrect or erase newer context', async () => {
  const env = await environment(), p = payload(env);
  const old = env.bridge.begin(p.request);
  env.bridge.clear();
  assert.equal((await env.bridge.accept({ ...p, ticket: old })).ok, false);
  const newer = env.bridge.begin(p.request);
  assert.equal((await env.bridge.accept({ ...p, ticket: { ...newer } })).ok, false);
  assert.equal((await env.bridge.accept({ ...p, ticket: newer })).ok, true);
  const before = env.bridge.context(env.recommend()).observationSha256;
  assert.equal((await env.bridge.accept({ ...p, ticket: old })).ok, false);
  assert.equal(env.bridge.context(env.recommend()).observationSha256, before);
});

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const files = ['apps/meta-resume-web/learning-observation.mjs', 'apps/meta-resume-web/learning-core.mjs',
  'apps/meta-resume-web/observation-client.mjs', 'apps/meta-resume-web/state.mjs', 'apps/meta-resume-web/fixture.mjs',
  'services/lens-learning/observation-simulation.mjs'];
const report = { schema: 'lens.learning-observation-simulation/v1', evidenceMode: 'SYNTHETIC',
  source: { baseCommit: 'ae5b4dcbeb380d1aafcb5ef8154efdadec38e130', files: Object.fromEntries(files.map((p) => [p, hash(readFileSync(resolve(root, p)))])) },
  checks, passed: checks.length, providerCalls: 0, physicalDeviceVerified: false, privateHostVerified: false,
  limits: ['One synthetic image/interpretation fixture; no SAM, NVIDIA or camera execution.',
    'Browser composition only; not production identity, durable memory or measured learning.'] };
const output = process.argv.indexOf('--output');
if (output !== -1) {
  const path = resolve(process.argv[output + 1]);
  mkdirSync(dirname(path), { recursive: true }); writeFileSync(path, JSON.stringify(report, null, 2) + '\n');
}
console.log(JSON.stringify(report, null, 2));
