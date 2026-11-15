import test from 'node:test';
import assert from 'node:assert/strict';
import { convertScreenshotContextHandoff } from './context-handoff.mjs';
import { createGuideSession, restoreGuideSession } from './guide-core.mjs';

const time = Date.parse('2026-11-15T09:00:00Z');
const options = { selectedByUser: true, now: () => time, id: () => 'selected-1' };
const fixture = () => ({ schema: 'ScreenshotContext.handoff.v1', mode: 'context', generatedAt: '2026-11-15T08:59:00Z',
  sourceFilename: '/Users/private/source.png', annotatedFilename: 'annotated-private.png', originalFilename: 'private-original.png',
  note: 'Muista laturi\nja avaimet.', application: 'Private application', windowTitle: 'Private window',
  url: 'https://private.example.com/path', ocrText: 'PRIVATE OCR NOT SELECTED' });

test('format adapter preserves only explicit note plus export timestamp and safely roundtrips local metadata', () => {
  const result = convertScreenshotContextHandoff(JSON.stringify(fixture()), options);
  assert.equal(result.ok, true);
  assert.equal(result.context.entries[0].summary, fixture().note);
  assert.equal(result.context.entries[0].timeBasis, 'handoff-export');
  assert.equal(result.context.entries[0].observedAtMs, Date.parse(fixture().generatedAt));
  const text = JSON.stringify(result.context);
  for (const forbidden of ['sourceFilename', 'annotatedFilename', 'originalFilename', '/Users/', 'https:', 'PRIVATE OCR', 'Private application', 'Private window']) {
    assert.equal(text.includes(forbidden), false);
  }
  const session = createGuideSession({ now: options.now });
  session.setConsent({ memory: true, capture: false });
  assert.equal(session.importSelectedContext(result.context).ok, true);
  const restored = restoreGuideSession(session.exportState(), { now: options.now }).snapshot();
  assert.equal(restored.selectedContext[0].timeBasis, 'handoff-export');
  assert.equal(restored.selectedContext[0].historical, true);
  assert.equal(restored.currentPresenceVerified, false);
});

test('user selection, exact format, duplicate JSON, oversize, empty note and time bounds fail closed', () => {
  assert.equal(convertScreenshotContextHandoff(JSON.stringify(fixture())).error.code, 'USER_SELECTION_REQUIRED');
  assert.equal(convertScreenshotContextHandoff('{"schema":1,"schema":2}', options).error.code, 'INVALID_HANDOFF_JSON');
  assert.equal(convertScreenshotContextHandoff(' '.repeat(16385), options).error.code, 'HANDOFF_TOO_LARGE');
  for (const [change, code] of [
    [value => { value.imageData = 'raw'; }, 'INVALID_HANDOFF_SCHEMA'],
    [value => { delete value.sourceFilename; }, 'INVALID_HANDOFF_SCHEMA'],
    [value => { value.note = ''; }, 'NOTE_REQUIRED'],
    [value => { value.note = 'a'.repeat(241); }, 'NOTE_TOO_LONG'],
    [value => { value.generatedAt = '2026-11-16T09:00:00Z'; }, 'FUTURE_EXPORT_TIME'],
    [value => { value.generatedAt = '2026-11-15'; }, 'INVALID_EXPORT_TIME'],
    [value => { value.generatedAt = '2026-02-30T09:00:00Z'; }, 'INVALID_EXPORT_TIME'],
  ]) {
    const input = fixture(); change(input);
    assert.equal(convertScreenshotContextHandoff(JSON.stringify(input), options).error.code, code);
  }
});

test('unsafe explicit notes require manual sanitization, while markup is preserved only as text', () => {
  for (const note of ['Read https://example.com/private', 'Open /Users/private/file.png', 'File /etc/passwd',
    'Use ../private/file', 'Open C:\\Private\\note.txt', 'file:///private/pixel.png', 'data:image/png;base64,secret',
    'Open "/Users/private/file.png"', 'Read notes/private.txt', 'Visit example.com']) {
    const result = convertScreenshotContextHandoff(JSON.stringify({ ...fixture(), note }), options);
    assert.equal(result.error.code, 'NOTE_REQUIRES_MANUAL_SANITIZATION');
    assert.equal(JSON.stringify(result).includes(note), false);
  }
  const note = '<img onerror=alert(1)> Muista laturi';
  assert.equal(convertScreenshotContextHandoff(JSON.stringify({ ...fixture(), note }), options).context.entries[0].summary, note);
});
