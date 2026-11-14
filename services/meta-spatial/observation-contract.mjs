/** Public evidence proposal contract. No identity, grant or task mutation lives here. */
export const SAM31 = Object.freeze({
  id: 'facebook/sam3.1', codeCommit: 'eef6839bcfc3458dd52ea80535dc6bd62aea86b1',
  weightsRevision: 'daa63191845a41281374e725f4c9e51c7a824460',
  checkpointSha256: '0567debeec80ba4ac6369540c6c248025283cb3ff2b92827509e57e2b3541cb6',
});
const id = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value);
const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const integer = value => Number.isSafeInteger(value) && value >= 0 && value <= 2147483647;
const dimensions = value => Number.isSafeInteger(value) && value >= 1 && value <= 4096;
export const exact = (value, keys) => value !== null && typeof value === 'object' &&
  Object.getPrototypeOf(value) === Object.prototype && Object.keys(value).length === keys.length &&
  keys.every(key => Object.hasOwn(value, key));
export function reject(code) { const error = new Error(code); error.code = code; throw error; }
export function validateObservation(observation) {
  const o = observation;
  if (!exact(o, ['schemaVersion','kind','evidenceMode','episodeId','sessionId','captureGeneration','runId',
    'trackGeneration','sourceThroughFrameIndex','frame','model','tracks']) || o.schemaVersion !== 1 ||
    o.kind !== 'meta.sam31.observation' || !['MODEL','SYNTHETIC'].includes(o.evidenceMode) ||
    ![o.episodeId,o.sessionId,o.runId].every(id) || ![o.captureGeneration,o.trackGeneration,o.sourceThroughFrameIndex].every(integer)) reject('invalid-observation');
  const f = o.frame;
  if (!exact(f,['frameIndex','sha256','capturedAt','width','height']) || !integer(f.frameIndex) || !hash(f.sha256) ||
    !dimensions(f.width) || !dimensions(f.height) || typeof f.capturedAt !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/.test(f.capturedAt) ||
    !Number.isFinite(Date.parse(f.capturedAt)) || o.sourceThroughFrameIndex !== f.frameIndex) reject('noncausal-or-invalid-frame');
  if (!exact(o.model,Object.keys(SAM31)) || !Object.entries(SAM31).every(([key,value]) => o.model[key] === value)) reject('unexpected-sam-model');
  if (!Array.isArray(o.tracks) || o.tracks.length > 8) reject('invalid-tracks');
  const ids = new Set();
  for (const t of o.tracks) {
    if (!exact(t,['trackId','label','bbox','maskSha256','crop','visibility']) || !id(t.trackId) || ids.has(t.trackId) ||
      typeof t.label !== 'string' || !t.label.trim() || t.label.length > 80 || !hash(t.maskSha256) ||
      t.visibility !== 'visible' || !Array.isArray(t.bbox) || t.bbox.length !== 4 ||
      !t.bbox.every(n => Number.isFinite(n) && n >= 0 && n <= 1) || t.bbox[0] >= t.bbox[2] || t.bbox[1] >= t.bbox[3] ||
      !exact(t.crop,['sha256','width','height','mimeType']) || !hash(t.crop.sha256) || !dimensions(t.crop.width) ||
      !dimensions(t.crop.height) || !['image/png','image/jpeg'].includes(t.crop.mimeType)) reject('invalid-track');
    ids.add(t.trackId);
  }
  return o;
}

/** Snapshot binding is repeated at the UI and at the actual private host boundary. */
export function observationBinding(request) {
  const o = request.observation;
  return {taskId:request.task.taskId,expectedRevision:request.task.revision,episodeId:o.episodeId,
    sessionId:o.sessionId,captureGeneration:o.captureGeneration,frameSha256:o.frame.sha256,
    frameIndex:o.frame.frameIndex,runId:o.runId,trackGeneration:o.trackGeneration};
}

function iou(a,b) {
  const overlap = Math.max(0,Math.min(a[2],b[2])-Math.max(a[0],b[0])) * Math.max(0,Math.min(a[3],b[3])-Math.max(a[1],b[1]));
  return overlap / ((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-overlap);
}

/** Bounded attention policy; this schedules interpretation, never verifies identity. */
export function createObservationGate({maxEntries=32,minIntervalMs=750,refreshMs=15000}={}) {
  const entries = new Map();
  return {
    inspect(request,{nowMs=Date.now(),force=false}={}) {
      const o=request.observation, key=JSON.stringify([request.task.taskId,o.sessionId,o.captureGeneration]);
      const old=entries.get(key);
      if (old && (o.frame.frameIndex < old.frameIndex || request.task.revision < old.revision || o.trackGeneration < old.trackGeneration)) return {analyze:false,reason:'older-frame-or-task'};
      let reason=force?'user-request':!old?'first-observation':null;
      if (!reason && old.revision !== request.task.revision) reason='task-changed';
      if (!reason && old.trackGeneration !== o.trackGeneration) reason='tracking-restarted';
      if (!reason && old.frameSha256 === o.frame.sha256) return {analyze:false,reason:'same-frame'};
      if (!reason && nowMs-old.at < minIntervalMs) return {analyze:false,reason:'rate-limited'};
      if (!reason && (old.tracks.length !== o.tracks.length || o.tracks.some(t => {
        const prior=old.tracks.find(p=>p.trackId===t.trackId);
        return !prior || prior.label!==t.label || iou(prior.bbox,t.bbox)<0.6;
      }))) reason='visible-change';
      if (!reason && nowMs-old.at >= refreshMs) reason='freshness-check';
      if (!reason) return {analyze:false,reason:'no-meaningful-change'};
      return {analyze:true,reason,commit() {
        const current=entries.get(key);
        if(current && (current.frameIndex>o.frame.frameIndex || current.revision>request.task.revision ||
          current.trackGeneration>o.trackGeneration || current!==old && current.frameIndex===o.frame.frameIndex && current.revision===request.task.revision)) return false;
        entries.delete(key);
        entries.set(key,{at:nowMs,revision:request.task.revision,frameIndex:o.frame.frameIndex,
          frameSha256:o.frame.sha256,trackGeneration:o.trackGeneration,
          tracks:o.tracks.map(t=>({trackId:t.trackId,label:t.label,bbox:[...t.bbox]}))});
        while(entries.size>maxEntries)entries.delete(entries.keys().next().value);
        return true;
      }};
    },
    clear(){entries.clear();}
  };
}
