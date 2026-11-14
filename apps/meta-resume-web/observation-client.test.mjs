import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { FIXTURE, id } from './fixture.mjs';
import { parseObservationBundle, observationRequest, validateObservationResponse, contextKey } from './observation-client.mjs';

const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jVEcAAAAASUVORK5CYII=';
const hash = createHash('sha256').update(Buffer.from(png, 'base64')).digest('hex');
function fixture() {
  const observation = {
    schemaVersion: 1, kind: 'meta.sam31.observation', evidenceMode: 'SYNTHETIC',
    episodeId: 'sample', sessionId: FIXTURE.sessionId, captureGeneration: 1, runId: 'sample-run',
    trackGeneration: 1, sourceThroughFrameIndex: 0,
    frame: { frameIndex: 0, sha256: hash, capturedAt: FIXTURE.now, width: 1, height: 1 },
    model: { id: 'facebook/sam3.1', codeCommit: 'eef6839bcfc3458dd52ea80535dc6bd62aea86b1',
      weightsRevision: 'daa63191845a41281374e725f4c9e51c7a824460', checkpointSha256: '0567debeec80ba4ac6369540c6c248025283cb3ff2b92827509e57e2b3541cb6' },
    tracks: [{ trackId: 'charger-1', label: '<img src=x onerror=alert(1)>', bbox: [0, 0, 1, 1], maskSha256: hash,
      crop: { sha256: hash, width: 1, height: 1, mimeType: 'image/png' }, visibility: 'visible' }],
  };
  return { observation, image: { kind: 'frame', dataUrl: 'data:image/png;base64,' + png, sha256: hash, trackId: null } };
}
const state = { taskId: FIXTURE.taskId, revision: 3, status: 'interrupted', nextUnconfirmedStep: id(203),
  steps: FIXTURE.steps.map((s, index) => ({ ...s, userConfirmed: index < 2 })) };
const policy = { sessionId: FIXTURE.sessionId, captureGeneration: 1, captureEnabled: true };
function reply(request) {
  const o = request.observation;
  return { status: 'proposed', binding: { taskId: request.task.taskId, expectedRevision: request.task.revision,
    episodeId: o.episodeId, sessionId: o.sessionId, captureGeneration: o.captureGeneration, frameSha256: o.frame.sha256,
    frameIndex: o.frame.frameIndex, runId: o.runId, trackGeneration: o.trackGeneration },
  proposal: { summary: 'Check the charger before packing.', observations: [{ trackId: 'charger-1', text: 'A charger-shaped item is visible.' }],
    uncertainties: ['Its identity is unverified.'], nextQuestion: 'Is this your charger?',
    nextStepProposal: { stepId: id(203), label: 'Your charger' }, physicalIdentityVerified: false, taskCompletionAuthorized: false }, receipt: {} };
}

test('bounded image bundle binds actual bytes and never accepts remote image URLs', async () => {
  const bundle = await parseObservationBundle(JSON.stringify(fixture()));
  assert.equal(bundle.observation.tracks[0].label, '<img src=x onerror=alert(1)>');
  const tampered = fixture();
  tampered.image.sha256 = tampered.observation.frame.sha256 = 'a'.repeat(64);
  await assert.rejects(parseObservationBundle(JSON.stringify(tampered)), /does not match/);
  const remote = fixture(); remote.image.dataUrl = 'https://example.invalid/secret.png';
  await assert.rejects(parseObservationBundle(JSON.stringify(remote)), /not supported/);
  const future = fixture(); future.observation.sourceThroughFrameIndex = 1;
  await assert.rejects(parseObservationBundle(JSON.stringify(future)), /not supported/);
});

test('an advisory reply does not alter task state or admit an identity/completion grant', () => {
  const before = structuredClone(state), request = observationRequest(fixture(), state, policy);
  assert.equal(validateObservationResponse(reply(request), request, state, policy).proposal.nextQuestion, 'Is this your charger?');
  assert.deepEqual(state, before);
  for (const field of ['physicalIdentityVerified', 'taskCompletionAuthorized']) {
    const invalid = reply(request); invalid.proposal[field] = true;
    assert.throws(() => validateObservationResponse(invalid, request, state, policy), /not supported/);
  }
  const wrongStep = reply(request); wrongStep.proposal.nextStepProposal.stepId = id(202);
  assert.throws(() => validateObservationResponse(wrongStep, request, state, policy), /not supported/);
});

test('late replies cannot cross task revisions, revoked capture or source bindings', () => {
  const request = observationRequest(fixture(), state, policy), response = reply(request);
  assert.throws(() => validateObservationResponse(response, request, { ...state, revision: 4 }, policy), /task changed/);
  assert.throws(() => validateObservationResponse(response, request, state, { ...policy, captureEnabled: false, captureGeneration: 2 }), /task changed/);
  const other = reply(request); other.binding.runId = 'another-run';
  assert.throws(() => validateObservationResponse(other, request, state, policy), /does not match/);
  assert.notEqual(contextKey(state, policy), contextKey(state, { ...policy, captureGeneration: 2 }));
});
