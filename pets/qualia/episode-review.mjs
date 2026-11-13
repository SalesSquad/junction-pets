// Offline checks of invented metadata only: no recording, model, device or consent authority.
const ID = /^fictional-[a-z0-9][a-z0-9-]{0,63}$/;
function requireValue(ok, message) { if (!ok) throw new TypeError(message); }
function fields(value, keys, name) {
  requireValue(value !== null && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key)), `${name} fields must be exactly ${keys.join(', ')}`);
}
function id(value, name, nullable = false) {
  requireValue(nullable && value === null || typeof value === 'string' && ID.test(value), `invalid fictional ${name}`);
}
function integer(value, min, max, name, nullable = false) {
  requireValue(nullable && value === null || Number.isSafeInteger(value) && !Object.is(value, -0) && value >= min && value <= max, `invalid ${name}`);
}

export function reviewEpisode(jsonText) {
  requireValue(typeof jsonText === 'string' && jsonText.length <= 32768 && new TextEncoder().encode(jsonText).length <= 32768,
    'expected primitive JSON text of at most 32768 UTF-8 bytes');
  let episode;
  try { episode = JSON.parse(jsonText); } catch { throw new TypeError('invalid JSON text'); }
  fields(episode, ['schemaVersion', 'kind', 'episodeId', 'recordingId', 'durationMs', 'expectedFrameCount', 'frames', 'consent', 'annotations'], 'episode');
  requireValue(episode.schemaVersion === 1 && episode.kind === 'fictional-robot-episode', 'unsupported schemaVersion or kind');
  id(episode.episodeId, 'episodeId'); id(episode.recordingId, 'recordingId');
  integer(episode.durationMs, 1, 3600000, 'durationMs');
  integer(episode.expectedFrameCount, 1, 128, 'expectedFrameCount');
  requireValue(Array.isArray(episode.frames) && episode.frames.length <= 128, 'frames must contain 0..128 records');
  for (const frame of episode.frames) {
    fields(frame, ['index', 'timestampMs', 'frameId'], 'frame');
    integer(frame.index, 0, 127, 'frame index', true);
    integer(frame.timestampMs, 0, 3600000, 'frame timestampMs', true);
    id(frame.frameId, 'frameId', true);
  }
  if (episode.consent !== null) {
    fields(episode.consent, ['state', 'recordingId', 'purpose'], 'consent');
    requireValue([null, 'granted', 'unknown', 'withdrawn'].includes(episode.consent.state), 'invalid consent state');
    id(episode.consent.recordingId, 'consent recordingId', true);
    requireValue([null, 'annotation-review', 'training'].includes(episode.consent.purpose), 'invalid consent purpose');
  }
  requireValue(Array.isArray(episode.annotations) && episode.annotations.length <= 32, 'annotations must contain 0..32 records');
  const annotationIds = new Set();
  for (const annotation of episode.annotations) {
    fields(annotation, ['id', 'fromFrame', 'toFrame', 'label', 'source', 'evidenceFrameIds'], 'annotation');
    id(annotation.id, 'annotation ID');
    requireValue(!annotationIds.has(annotation.id), 'unique annotation IDs required'); annotationIds.add(annotation.id);
    integer(annotation.fromFrame, 0, 127, 'annotation fromFrame'); integer(annotation.toFrame, 0, 127, 'annotation toFrame');
    requireValue(['attempt', 'success', 'failure', 'unknown'].includes(annotation.label), 'invalid annotation label');
    requireValue(['operator', 'model'].includes(annotation.source), 'invalid annotation source');
    requireValue(Array.isArray(annotation.evidenceFrameIds) && annotation.evidenceFrameIds.length <= 8, 'evidenceFrameIds must contain 0..8 IDs');
    const seen = new Set();
    for (const ref of annotation.evidenceFrameIds) {
      id(ref, 'evidence frame ID'); requireValue(!seen.has(ref), 'unique evidence frame IDs required'); seen.add(ref);
    }
  }

  const findings = [], frameIds = new Map();
  const flag = (code, field) => findings.push({code, field});
  if (episode.frames.length !== episode.expectedFrameCount) flag('frame-count-mismatch', 'frames');
  let previousTime = null;
  for (const [position, frame] of episode.frames.entries()) {
    const field = `frames[${position}]`;
    if (frame.index === null) flag('unknown-frame-index', `${field}.index`);
    else if (frame.index !== position) flag('frame-sequence-mismatch', `${field}.index`);
    if (frame.timestampMs === null) flag('unknown-timestamp', `${field}.timestampMs`);
    else {
      if (frame.timestampMs > episode.durationMs) flag('timestamp-outside-episode', `${field}.timestampMs`);
      if (previousTime !== null && frame.timestampMs <= previousTime) flag('nonmonotonic-timestamp', `${field}.timestampMs`);
      previousTime = frame.timestampMs;
    }
    if (frame.frameId === null) flag('unknown-frame-id', `${field}.frameId`);
    else if (frameIds.has(frame.frameId)) flag('duplicate-frame-id', `${field}.frameId`);
    else frameIds.set(frame.frameId, position);
  }
  if (episode.consent === null) flag('missing-consent-declaration', 'consent');
  else {
    if (episode.consent.state !== 'granted') flag(episode.consent.state === 'withdrawn' ? 'consent-withdrawn' : 'consent-unknown', 'consent.state');
    if (episode.consent.recordingId !== episode.recordingId) flag('consent-recording-mismatch', 'consent.recordingId');
    if (episode.consent.purpose !== 'annotation-review') flag('consent-purpose-mismatch', 'consent.purpose');
  }
  for (const [position, annotation] of episode.annotations.entries()) {
    const field = `annotations[${position}]`;
    if (annotation.fromFrame > annotation.toFrame) flag('reversed-annotation-interval', field);
    if (annotation.fromFrame >= episode.expectedFrameCount || annotation.toFrame >= episode.expectedFrameCount ||
      episode.frames[annotation.fromFrame]?.index !== annotation.fromFrame || episode.frames[annotation.toFrame]?.index !== annotation.toFrame) {
      flag('annotation-frame-out-of-range', field);
    }
    if (['success', 'failure'].includes(annotation.label) && annotation.evidenceFrameIds.length === 0) flag('outcome-without-evidence-reference', `${field}.evidenceFrameIds`);
    for (const ref of annotation.evidenceFrameIds) {
      const framePosition = frameIds.get(ref);
      if (framePosition === undefined) flag('unknown-evidence-frame', `${field}.evidenceFrameIds`);
      else if (framePosition < annotation.fromFrame || framePosition > annotation.toFrame) flag('evidence-outside-annotation', `${field}.evidenceFrameIds`);
    }
  }
  return {
    schemaVersion: 1, kind: 'fictional-episode-review', episodeId: episode.episodeId,
    status: findings.length ? 'needs-review' : 'consistent-declarations', findings,
    summary: {frames: episode.frames.length, expectedFrames: episode.expectedFrameCount, annotations: episode.annotations.length,
      consentDeclaration: episode.consent === null ? 'missing' : episode.consent.state ?? 'unknown'},
    boundary: {synthetic: true, recordingInspected: false, consentVerified: false, outcomeVerified: false, deviceActionAuthorized: false},
  };
}
