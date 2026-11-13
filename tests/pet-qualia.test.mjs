import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {reviewEpisode} from '../pets/qualia/episode-review.mjs';

const fixture = () => ({
  schemaVersion: 1, kind: 'fictional-robot-episode', episodeId: 'fictional-pick', recordingId: 'fictional-camera',
  durationMs: 1000, expectedFrameCount: 3,
  frames: [
    {index: 0, timestampMs: 0, frameId: 'fictional-frame-0'},
    {index: 1, timestampMs: 500, frameId: 'fictional-frame-1'},
    {index: 2, timestampMs: 1000, frameId: 'fictional-frame-2'},
  ],
  consent: {state: 'granted', recordingId: 'fictional-camera', purpose: 'annotation-review'},
  annotations: [{id: 'fictional-label', fromFrame: 0, toFrame: 2, label: 'success', source: 'operator', evidenceFrameIds: ['fictional-frame-2']}],
});
const run = value => reviewEpisode(JSON.stringify(value));
const codes = value => run(value).findings.map(f => f.code);

test('complete invented episode is structurally consistent without qualifying consent, recording or robot success', () => {
  const value = fixture(), before = JSON.stringify(value), result = run(value);
  assert.equal(result.status, 'consistent-declarations');
  assert.deepEqual(result.findings, []);
  assert.deepEqual(result.summary, {frames: 3, expectedFrames: 3, annotations: 1, consentDeclaration: 'granted'});
  assert.deepEqual(result.boundary, {synthetic: true, recordingInspected: false, consentVerified: false, outcomeVerified: false, deviceActionAuthorized: false});
  assert.equal(JSON.stringify(value), before);
  assert.deepEqual(result, run(value));
});

test('frame order must be contiguous from zero and identities cannot be reused', () => {
  const value = fixture();
  value.frames[1].index = 2;
  value.frames[2].frameId = value.frames[0].frameId;
  assert.ok(codes(value).includes('frame-sequence-mismatch'));
  assert.ok(codes(value).includes('duplicate-frame-id'));
  assert.equal(run(value).status, 'needs-review');
  value.frames.reverse();
  assert.ok(codes(value).includes('frame-sequence-mismatch'));
});

test('missing frames and empty recordings cannot satisfy declared expected coverage', () => {
  const value = fixture();
  value.frames.splice(1, 1);
  assert.deepEqual(codes(value).slice(0, 2), ['frame-count-mismatch', 'frame-sequence-mismatch']);
  value.frames = [];
  assert.ok(codes(value).includes('frame-count-mismatch'));
  assert.ok(codes(value).includes('annotation-frame-out-of-range'));
  assert.ok(codes(value).includes('unknown-evidence-frame'));
});

test('timestamps must increase strictly within the declared episode duration', () => {
  for (const timestamp of [0, 1001]) {
    const value = fixture();
    value.frames[1].timestampMs = timestamp;
    assert.equal(run(value).status, 'needs-review');
    assert.ok(codes(value).includes(timestamp === 0 ? 'nonmonotonic-timestamp' : 'timestamp-outside-episode'));
  }
  const value = fixture();
  value.frames[2].timestampMs = 500;
  assert.deepEqual(codes(value), ['nonmonotonic-timestamp']);
});

test('zero time and index are valid, null is unknown, and omitted fields are malformed', () => {
  const value = fixture();
  assert.equal(run(value).status, 'consistent-declarations');
  value.frames[0] = {index: null, timestampMs: null, frameId: null};
  assert.deepEqual(codes(value).slice(0, 3), ['unknown-frame-index', 'unknown-timestamp', 'unknown-frame-id']);
  delete value.frames[0].timestampMs;
  assert.throws(() => run(value), /frame fields/);
});

test('missing, unknown, null and withdrawn consent declarations never become readiness', () => {
  const value = fixture();
  value.consent = null;
  assert.deepEqual(codes(value), ['missing-consent-declaration']);
  for (const state of [null, 'unknown', 'withdrawn']) {
    value.consent = {state, recordingId: 'fictional-camera', purpose: 'annotation-review'};
    assert.deepEqual(codes(value), [state === 'withdrawn' ? 'consent-withdrawn' : 'consent-unknown']);
    assert.equal(run(value).status, 'needs-review');
    assert.equal(run(value).boundary.consentVerified, false);
  }
});

test('a granted declaration for another recording, purpose or unknown scope is insufficient', () => {
  const value = fixture();
  value.consent.recordingId = 'fictional-other';
  value.consent.purpose = 'training';
  assert.deepEqual(codes(value), ['consent-recording-mismatch', 'consent-purpose-mismatch']);
  value.consent.recordingId = null;
  value.consent.purpose = null;
  assert.deepEqual(codes(value), ['consent-recording-mismatch', 'consent-purpose-mismatch']);
});

test('outcome annotations need an in-range evidence reference but never authenticate a success label', () => {
  const value = fixture();
  value.annotations[0].evidenceFrameIds = [];
  assert.deepEqual(codes(value), ['outcome-without-evidence-reference']);
  value.annotations[0].evidenceFrameIds = ['fictional-absent'];
  assert.deepEqual(codes(value), ['unknown-evidence-frame']);
  value.annotations[0].fromFrame = 1;
  value.annotations[0].evidenceFrameIds = ['fictional-frame-0'];
  assert.deepEqual(codes(value), ['evidence-outside-annotation']);
  value.annotations[0].label = 'unknown';
  value.annotations[0].evidenceFrameIds = [];
  assert.equal(run(value).status, 'consistent-declarations');
  assert.equal(run(value).boundary.outcomeVerified, false);
});

test('annotation spans and provenance distinguish unsupported intervals from malformed duplicate identities', () => {
  const value = fixture();
  value.annotations[0].fromFrame = 2;
  value.annotations[0].toFrame = 0;
  assert.ok(codes(value).includes('reversed-annotation-interval'));
  value.annotations[0].toFrame = 3;
  assert.ok(codes(value).includes('annotation-frame-out-of-range'));
  value.annotations[0].source = 'model';
  assert.equal(run(value).boundary.outcomeVerified, false);
  value.annotations.push({...value.annotations[0]});
  assert.throws(() => run(value), /unique annotation/);
  value.annotations.pop();
  value.annotations[0].evidenceFrameIds = ['fictional-frame-2', 'fictional-frame-2'];
  assert.throws(() => run(value), /unique evidence/);
});

test('closed bounded JSON input rejects missing keys, unsupported authority and noninteger/overflow values', () => {
  for (const value of [null, {}, new String('{}'), '{', ' '.repeat(32769), 'é'.repeat(17000)]) assert.throws(() => reviewEpisode(value), TypeError);
  for (const mutate of [
    x => {delete x.consent;}, x => {x.recordingInspected = true;}, x => {x.frames[0].imageUrl = 'https://example.invalid';},
    x => {x.kind = 'real-robot-episode';}, x => {x.durationMs = 0;}, x => {x.durationMs = 1e100;},
    x => {x.frames[1].timestampMs = '500';}, x => {x.frames[1].timestampMs = -1;}, x => {x.frames[1].index = 1.5;},
    x => {x.consent.state = 'approved-by-agent';}, x => {x.annotations[0].source = 'verified';},
  ]) {const value = fixture(); mutate(value); assert.throws(() => run(value), TypeError);}
  const text = JSON.stringify(fixture());
  assert.throws(() => reviewEpisode(text.replace('"durationMs":1000', '"durationMs":1e999')), TypeError);
  assert.throws(() => reviewEpisode(text.replace('"timestampMs":0', '"timestampMs":-0')), TypeError);
});

test('maximum collection bounds remain finite and ordinary JSON duplicate members use the final value', () => {
  const value = fixture();
  value.expectedFrameCount = 128;
  value.frames = Array.from({length: 128}, (_, i) => ({index: i, timestampMs: i, frameId: `fictional-frame-${i}`}));
  value.annotations = [];
  assert.equal(run(value).status, 'consistent-declarations');
  value.frames.push({index: 127, timestampMs: 128, frameId: 'fictional-overflow'});
  assert.throws(() => run(value), /frames/);
  const text = JSON.stringify(fixture()).replace('"episodeId":"fictional-pick"', '"episodeId":"fictional-first","episodeId":"fictional-last"');
  assert.equal(reviewEpisode(text).episodeId, 'fictional-last');
  assert.throws(() => reviewEpisode(text.replace('"schemaVersion":1', '"schemaVersion":1,"__proto__":{"polluted":true}')), TypeError);
  assert.equal({}.polluted, undefined);
});

test('checked-in invented example validates only metadata declarations, never recording or robot execution', () => {
  const text = readFileSync(new URL('../pets/qualia/examples/fictional-episode.json', import.meta.url), 'utf8');
  const result = reviewEpisode(text);
  assert.equal(result.status, 'consistent-declarations');
  assert.equal(result.summary.frames, 3);
  assert.equal(result.boundary.deviceActionAuthorized, false);
});
