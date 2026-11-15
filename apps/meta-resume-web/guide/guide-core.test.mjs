import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createGuideSession, restoreGuideSession, GUIDE_LIMITS } from './guide-core.mjs';

function setup(mode = 'teach', items = [{ id: 'keys', name: 'Avaimet' }, { id: 'charger', name: 'Laturi' }]) {
  let time = 1000, serial = 0;
  const options = { now: () => time, id: () => `test-${++serial}` };
  const guide = createGuideSession(options);
  assert.equal(guide.setConsent({ memory: true, capture: true }).ok, true);
  assert.equal(guide.beginTask({ title: 'Lähtö', mode, items }).ok, true);
  return { guide, options, advance: ms => { time += ms; }, now: () => time };
}
function image(seed = 1) {
  // A bounded synthetic byte fixture with PNG magic; this is not an inference/image-decoder test.
  return Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10, 1, 2, 3, 4, seed, 6, 7, 8]);
}
function frame(env, request, seed = 1, sequence = env.guide.snapshot().frameWatermark + 1) {
  env.advance(1);
  const bytes = image(seed);
  return { requestId: request.requestId, binding: request.binding, bytes,
    sha256: createHash('sha256').update(bytes).digest('hex'), mimeType: 'image/png',
    capturedAtMs: env.now(), sequence, source: 'phone-camera' };
}
async function associate(env, itemId = 'keys', seed = 1) {
  const { request } = env.guide.requestView({ itemId, reason: 'close-up' });
  assert.equal((await env.guide.acceptFrame(frame(env, request, seed))).ok, true);
  return { request, confirmation: { requestId: request.requestId, itemId, name: itemId, place: 'Eteisen hylly', confirmed: true } };
}

test('verified bytes remain a proposed association until explicit user confirmation', async () => {
  const env = setup();
  const { request, confirmation } = await associate(env);
  const before = env.guide.snapshot();
  assert.equal(before.acceptedFrame.distinguishingViewConfirmed, false);
  assert.equal(before.memories.length, 0);
  assert.equal(env.guide.confirmMemory({ ...confirmation, confirmed: false }).error.code, 'INVALID_CONFIRMATION');
  const confirmed = env.guide.confirmMemory(confirmation);
  assert.equal(confirmed.ok, true);
  assert.equal(confirmed.state.memories[0].association, 'user-confirmed-photo');
  assert.equal(confirmed.state.memories[0].physicalIdentityVerified, false);
  assert.equal(confirmed.state.currentPresenceVerified, false);
  assert.equal(confirmed.state.pending, null);
  assert.equal(env.guide.confirmMemory(confirmation).replayed, true);
  assert.equal(env.guide.confirmMemory({ ...confirmation, place: 'Muu hylly' }).error.code, 'CONFIRMATION_COLLISION');
  assert.equal(request.itemId, 'keys');
});

test('hash mismatch, old timestamps/watermarks and historical image origins are rejected', async () => {
  const env = setup(); const { request } = env.guide.requestView({ itemId: 'keys', reason: 'side' });
  const input = frame(env, request);
  assert.equal((await env.guide.acceptFrame({ ...input, source: 'selected-image' })).error.code, 'HISTORICAL_FRAME_ONLY');
  assert.equal((await env.guide.acceptFrame({ ...input, capturedAtMs: request.createdAtMs })).error.code, 'STALE_FRAME');
  assert.equal((await env.guide.acceptFrame({ ...input, sequence: 0 })).error.code, 'STALE_FRAME');
  assert.equal((await env.guide.acceptFrame({ ...input, sha256: '0'.repeat(64) })).error.code, 'FRAME_HASH_MISMATCH');
  assert.equal((await env.guide.acceptFrame({ ...input, mimeType: 'image/jpeg' })).error.code, 'IMAGE_FORMAT_MISMATCH');
  assert.equal(env.guide.snapshot().acceptedFrame, null);
});

test('caller mutation during SHA cannot change copied input bytes or accepted binding', async () => {
  const env = setup(); const { request } = env.guide.requestView({ itemId: 'keys', reason: 'overview' });
  const input = frame(env, request);
  const expectedHash = input.sha256;
  const pending = env.guide.acceptFrame(input);
  input.bytes.fill(0); input.binding.generation = 999; input.sha256 = '0'.repeat(64);
  assert.equal((await pending).ok, true);
  assert.equal(env.guide.snapshot().acceptedFrame.sha256, expectedHash);
  const exported = env.guide.exportState();
  assert.equal(exported.includes(expectedHash), false); // Unconfirmed frame is never serialized.
  assert.equal(exported.includes('acceptedFrame'), false);
});

test('revocation, forget, reset, task change and pause win against in-flight SHA', async () => {
  const invalidators = [
    guide => guide.setConsent({ memory: true, capture: false }),
    guide => guide.forgetAll(),
    guide => guide.reset(),
    guide => guide.beginTask({ title: 'Uusi', mode: 'pack', items: [{ id: 'other', name: 'Muu' }] }),
    guide => guide.pause(),
  ];
  for (const invalidate of invalidators) {
    const env = setup(); const { request } = env.guide.requestView({ itemId: 'keys', reason: 'side' });
    const pending = env.guide.acceptFrame(frame(env, request));
    invalidate(env.guide);
    assert.equal((await pending).error.code, 'STALE_REQUEST');
    assert.equal(env.guide.snapshot().acceptedFrame, null);
  }
});

test('expiry is rechecked after SHA and at confirmation; an old expiry callback cannot cancel new request', async () => {
  const env = setup(); const old = env.guide.requestView({ itemId: 'keys', reason: 'overview' }).request;
  const pending = env.guide.acceptFrame(frame(env, old)); env.advance(GUIDE_LIMITS.freshnessMs);
  assert.equal((await pending).error.code, 'STALE_REQUEST');
  assert.equal(env.guide.expire({ requestId: old.requestId }).expired, true);
  env.guide.setConsent({ memory: true, capture: true });
  const current = env.guide.requestView({ itemId: 'keys', reason: 'close-up' }).request;
  assert.equal(env.guide.expire({ requestId: old.requestId }).expired, false);
  assert.equal(env.guide.snapshot().pending.requestId, current.requestId);
  await env.guide.acceptFrame(frame(env, current, 2)); env.advance(GUIDE_LIMITS.freshnessMs);
  assert.equal(env.guide.confirmMemory({ requestId: current.requestId, itemId: 'keys', name: 'Avaimet', place: 'Hylly', confirmed: true }).error.code,
    'FRESH_FRAME_CONFIRMATION_REQUIRED');
});

test('same image cannot fulfil the next request and concurrent frames cannot both commit', async () => {
  const env = setup(); const { confirmation } = await associate(env);
  env.guide.confirmMemory(confirmation);
  const next = env.guide.requestView({ itemId: 'charger', reason: 'side' }).request;
  assert.equal((await env.guide.acceptFrame(frame(env, next, 1))).error.code, 'DUPLICATE_FRAME');
  const first = env.guide.acceptFrame(frame(env, next, 2, 2));
  const second = env.guide.acceptFrame(frame(env, next, 3, 3));
  const results = await Promise.all([first, second]);
  assert.equal(results.filter(result => result.ok).length, 1);
  assert.equal(results.filter(result => !result.ok).length, 1);
});

test('memory correction invalidates pending frames without claiming a new captured view', async () => {
  const env = setup(); const { confirmation } = await associate(env); env.guide.confirmMemory(confirmation);
  const request = env.guide.requestView({ itemId: 'charger', reason: 'overview' }).request;
  const pending = env.guide.acceptFrame(frame(env, request, 2));
  assert.equal(env.guide.correctMemory({ itemId: 'keys', name: 'Vara-avaimet', place: 'Laatikko', confirmed: true }).ok, true);
  assert.equal((await pending).error.code, 'STALE_REQUEST');
  const memory = env.guide.snapshot().memories[0];
  assert.equal(memory.association, 'user-corrected-metadata');
  assert.equal(memory.frameSha256, null);
  assert.equal(memory.currentPresenceVerified, false);
});

test('restore retains user packing progress but no pending frame, capture consent or current presence', async () => {
  const env = setup('pack'); const { request } = await associate(env);
  assert.equal(env.guide.confirmPacked({ requestId: request.requestId, itemId: 'keys', confirmed: true }).ok, true);
  env.guide.requestView({ itemId: 'charger', reason: 'overview' });
  const serialized = env.guide.exportState();
  const restored = restoreGuideSession(serialized, env.options);
  const state = restored.snapshot();
  assert.equal(state.task.status, 'paused');
  assert.equal(state.task.items[0].packed, true);
  assert.equal(state.task.items[0].packedSource, 'user');
  assert.equal(state.task.items[0].previouslyPacked, true);
  assert.equal(state.currentPresenceVerified, false);
  assert.equal(state.pending, null); assert.equal(state.acceptedFrame, null);
  assert.equal(state.consent.capture, false);
  assert.notEqual(state.sessionId, env.guide.snapshot().sessionId);
  assert.equal(restored.confirmPacked({ requestId: request.requestId, itemId: 'keys', confirmed: true }).ok, false);
  assert.equal(Object.hasOwn(restored, '_restoreMetadata'), false);
  restored.resume(); assert.equal(restored.snapshot().task.items[0].packed, true);
});

test('explicit local memory consent and epoch gate govern export; forgotten confirmation cannot replay', async () => {
  const env = setup(); const { confirmation } = await associate(env); env.guide.confirmMemory(confirmation);
  const epoch = env.guide.snapshot().memoryEpoch;
  env.guide.forgetAll();
  assert.equal(env.guide.exportState({ expectedMemoryEpoch: epoch }), null);
  assert.equal(env.guide.confirmMemory(confirmation).ok, false);
  env.guide.setConsent({ memory: false, capture: false });
  assert.equal(env.guide.exportState(), null);
  assert.deepEqual(env.guide.snapshot().memories, []);
});

test('restore rejects authority escalation, extra data, duplicate keys, oversized and inconsistent saves', async () => {
  const env = setup(); const { confirmation } = await associate(env); env.guide.confirmMemory(confirmation);
  const original = JSON.parse(env.guide.exportState());
  for (const change of [
    value => { value.captureConsent = true; },
    value => { value.memories[0].physicalIdentityVerified = true; },
    value => { value.memories[0].image = 'data:image/png;base64,abc'; },
    value => { value.task.status = 'completed'; },
    value => { value.task.items[0].packed = true; },
    value => { value.taskRevision = value.revision + 1; },
  ]) {
    const bad = structuredClone(original); change(bad);
    assert.throws(() => restoreGuideSession(JSON.stringify(bad), env.options), { code: 'INVALID_SAVE' });
  }
  assert.throws(() => restoreGuideSession('{"schema":1,"schema":2}', env.options), { code: 'INVALID_SAVE' });
  assert.throws(() => restoreGuideSession(' '.repeat(32769), env.options), { code: 'INVALID_SAVE' });
  assert.throws(() => restoreGuideSession('{"x":1e999}', env.options), { code: 'INVALID_SAVE' });
});

test('selected context accepts only bounded user-selected metadata, persists historically and never confirms items', () => {
  const env = setup();
  const envelope = { schema: 'lens.selected-context/v1', selectionId: 'choice-1', source: 'screenshotcontext', selectedByUser: true,
    entries: [{ id: 'note-1', title: 'Matkalista', summary: 'Muista laturi', observedAtMs: 900, timeBasis: 'user-note' }] };
  assert.equal(env.guide.importSelectedContext(envelope).ok, true);
  assert.equal(env.guide.snapshot().selectedContext[0].historical, true);
  assert.equal(env.guide.snapshot().task.items[0].packed, false);
  const restored = restoreGuideSession(env.guide.exportState(), env.options);
  assert.equal(restored.snapshot().selectedContext[0].summary, 'Muista laturi');
  for (const change of [
    value => { value.selectedByUser = false; },
    value => { value.entries[0].imagePath = '/Users/private/pixel.png'; },
    value => { value.entries[0].summary = 'https://example.com/private'; },
    value => { value.entries[0].summary = '/Users/private/screenshot.png'; },
    value => { value.entries[0].observedAtMs = 999999; },
    value => { delete value.entries[0].timeBasis; },
    value => { value.entries[0].timeBasis = 'verified-now'; },
    value => { value.entries = Array.from({ length: 11 }, (_, index) => ({ ...value.entries[0], id: `note-${index}` })); },
  ]) {
    const invalid = structuredClone(envelope); change(invalid);
    assert.equal(env.guide.importSelectedContext(invalid).error.code, 'INVALID_CONTEXT');
  }
});

test('task item bounds and cloned snapshots protect session state', () => {
  const env = setup(); const before = env.guide.snapshot();
  const bad = env.guide.beginTask({ title: 'Liikaa', mode: 'pack', items: Array.from({ length: 11 }, (_, index) => ({ id: `i${index}`, name: 'Esine' })) });
  assert.equal(bad.error.code, 'INVALID_TASK'); assert.deepEqual(env.guide.snapshot(), before);
  before.task.items[0].packed = true; before.consent.capture = false;
  assert.equal(env.guide.snapshot().task.items[0].packed, false);
  assert.equal(env.guide.snapshot().consent.capture, true);
});
