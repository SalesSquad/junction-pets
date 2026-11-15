/** Local user-owned guide metadata. No host authentication, provider calls or identity authority. */
const copy = value => structuredClone(value);
const plain = value => value !== null && typeof value === 'object' && !Array.isArray(value) &&
  [Object.prototype, null].includes(Object.getPrototypeOf(value));
const exact = (value, keys) => plain(value) && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const ident = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(value);
const integer = value => Number.isSafeInteger(value) && value >= 0 && value < Number.MAX_SAFE_INTEGER - 100000;
const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const unsafeReference = /(?:[a-z][a-z0-9+.-]*:\/\/|\b(?:https?|data|file|javascript|mailto):|\bwww\.|\b(?:[a-z0-9][a-z0-9-]*\.)+[a-z]{2,63}\b|(?:^|\s)(?:~?\/|\.{1,2}\/|[A-Za-z]:[\\/]|\\\\)\S+)/i;
const label = (value, limit) => typeof value === 'string' && value.trim().length > 0 && value.length <= limit &&
  !/[\x00-\x1f\x7f]/.test(value) && !unsafeReference.test(value);
export const isSafeGuideContextText = (value, limit = 240) => typeof value === 'string' && value.trim().length > 0 &&
  value.length <= limit && !/[\x00-\x08\x0b-\x1f\x7f\\/]/.test(value) && !unsafeReference.test(value);
const reasons = ['close-up', 'side', 'overview'];
const authority = { physicalIdentityVerified: false, currentPresenceVerified: false, actionAuthorized: false };
const MAX_SAVE_BYTES = 32768;
const MAX_FRAME_BYTES = 2_000_000;
const FRESH_MS = 30_000;
const bindingKeys = ['sessionId', 'generation', 'taskId', 'taskRevision', 'memoryEpoch'];
const itemKeys = ['id', 'name', 'place', 'packed', 'packedAtMs', 'packedSource', 'userConfirmed', 'previouslyPacked'];
const memoryKeys = ['itemId', 'name', 'place', 'confirmedAtMs', 'version', 'frameSha256', 'viewReason',
  'association', 'physicalIdentityVerified', 'currentPresenceVerified'];
const contextKeys = ['id', 'title', 'summary', 'observedAtMs', 'timeBasis', 'selectionId', 'source', 'historical'];
const failError = code => Object.assign(new Error(code), { code });
const restorePorts = new WeakMap();

/** Small bounded JSON parser: duplicate keys and nonfinite numbers are rejected. */
function parseMetadata(text) {
  if (typeof text !== 'string' || text.length > MAX_SAVE_BYTES || new TextEncoder().encode(text).length > MAX_SAVE_BYTES) throw failError('INVALID_SAVE');
  let cursor = 0;
  const white = () => { while (/[ \t\n\r]/.test(text[cursor] ?? '') && cursor < text.length) cursor++; };
  function string() {
    const start = cursor++;
    while (cursor < text.length) {
      if (text[cursor] === '\\') { cursor += 2; continue; }
      if (text[cursor++] === '"') return JSON.parse(text.slice(start, cursor));
    }
    throw failError('INVALID_SAVE');
  }
  function value(depth = 0) {
    if (depth > 12) throw failError('INVALID_SAVE');
    white(); const ch = text[cursor];
    if (ch === '"') return string();
    if (ch === '{' || ch === '[') {
      cursor++; const end = ch === '{' ? '}' : ']';
      const result = ch === '{' ? Object.create(null) : [];
      white(); if (text[cursor] === end) { cursor++; return result; }
      for (let count = 0; count < 200; count++) {
        white();
        if (ch === '{') {
          if (text[cursor] !== '"') throw failError('INVALID_SAVE');
          const key = string(); white();
          if (Object.hasOwn(result, key) || text[cursor++] !== ':') throw failError('INVALID_SAVE');
          result[key] = value(depth + 1);
        } else result.push(value(depth + 1));
        white(); if (text[cursor] === end) { cursor++; return result; }
        if (text[cursor++] !== ',') throw failError('INVALID_SAVE');
      }
      throw failError('INVALID_SAVE');
    }
    const match = /^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(text.slice(cursor));
    if (!match) throw failError('INVALID_SAVE');
    cursor += match[0].length;
    const parsed = JSON.parse(match[0]);
    if (typeof parsed === 'number' && !Number.isFinite(parsed)) throw failError('INVALID_SAVE');
    return parsed;
  }
  const parsed = value(); white();
  if (cursor !== text.length) throw failError('INVALID_SAVE');
  return parsed;
}

export { parseMetadata as parseGuideMetadata };

function validContextRow(row, time) {
  return exact(row, contextKeys) && ident(row.id) && label(row.title, 80) && isSafeGuideContextText(row.title, 80) && isSafeGuideContextText(row.summary) &&
    integer(row.observedAtMs) && row.observedAtMs <= time && ident(row.selectionId) &&
    ['captured', 'handoff-export', 'user-note'].includes(row.timeBasis) &&
    ['screenshotcontext', 'manual'].includes(row.source) && row.historical === true;
}
function validItem(item, time) {
  return exact(item, itemKeys) && ident(item.id) && label(item.name, 80) &&
    (item.place === null || label(item.place, 120)) && typeof item.packed === 'boolean' &&
    typeof item.userConfirmed === 'boolean' && typeof item.previouslyPacked === 'boolean' &&
    (!item.packed || item.userConfirmed) && (!item.previouslyPacked || item.packed) &&
    (item.packed ? integer(item.packedAtMs) && item.packedAtMs <= time && item.packedSource === 'user'
      : item.packedAtMs === null && item.packedSource === null);
}
function validMemory(memory, time) {
  return exact(memory, memoryKeys) && ident(memory.itemId) && label(memory.name, 80) && label(memory.place, 120) &&
    integer(memory.confirmedAtMs) && memory.confirmedAtMs <= time && integer(memory.version) && memory.version > 0 &&
    (memory.association === 'user-confirmed-photo' && hash(memory.frameSha256) && reasons.includes(memory.viewReason) ||
      memory.association === 'user-corrected-metadata' && memory.frameSha256 === null && memory.viewReason === null) &&
    memory.physicalIdentityVerified === false && memory.currentPresenceVerified === false;
}

export function createGuideSession({ now = Date.now, id = () => globalThis.crypto.randomUUID() } = {}) {
  if (typeof now !== 'function' || typeof id !== 'function') throw failError('INVALID_OPTIONS');
  const freshId = () => { const result = id(); if (!ident(result) || result.length > 96) throw failError('INVALID_ID'); return result; };
  const clock = () => { const time = now(); if (!integer(time)) throw failError('INVALID_CLOCK'); return time; };
  let state = { schema: 'lens.guide-state/v1', sessionId: freshId(), generation: 1, revision: 0,
    taskRevision: 0, memoryEpoch: 0, consent: { memory: false, capture: false }, task: null,
    memories: [], pending: null, acceptedFrame: null, frameWatermark: 0, selectedContext: [], ...authority };
  let requestSequence = 0;
  const seenHashes = new Set();
  const completed = new Map();
  const snapshot = () => copy(state);
  const bad = code => ({ ok: false, error: { code }, state: snapshot() });
  const good = extra => ({ ok: true, state: snapshot(), ...extra });
  function invalidate({ memory = false, task = false } = {}) {
    state.generation++; state.revision++;
    if (memory) state.memoryEpoch++;
    if (task) state.taskRevision++;
    state.pending = null; state.acceptedFrame = null; completed.clear();
  }
  const binding = () => ({ sessionId: state.sessionId, generation: state.generation,
    taskId: state.task?.id ?? null, taskRevision: state.taskRevision, memoryEpoch: state.memoryEpoch });
  const matches = value => exact(value, bindingKeys) && bindingKeys.every(key => value[key] === binding()[key]);
  function current(requestId) {
    const time = clock(), request = state.pending;
    return state.consent.capture && state.task?.status === 'active' && request?.requestId === requestId &&
      matches(request.binding) && time >= request.createdAtMs && time < request.expiresAtMs &&
      request.expiresAtMs - request.createdAtMs === FRESH_MS;
  }
  function accepted(requestId, itemId) {
    const frame = state.acceptedFrame;
    return current(requestId) && state.pending.itemId === itemId && frame?.requestId === requestId &&
      frame.sequence === state.frameWatermark && frame.sequence > state.pending.frameWatermark &&
      frame.capturedAtMs > state.pending.createdAtMs && clock() - frame.capturedAtMs <= FRESH_MS &&
      frame.source === 'phone-camera' && matches(frame.binding);
  }
  function replay(kind, data) {
    const previous = completed.get(data.requestId);
    if (!previous) return null;
    return previous.kind === kind && previous.fingerprint === JSON.stringify(data) &&
      previous.generation === state.generation && previous.memoryEpoch === state.memoryEpoch
      ? good({ replayed: true }) : bad('CONFIRMATION_COLLISION');
  }
  function commitConfirmation(kind, data) {
    invalidate({ memory: kind === 'memory', task: true });
    completed.set(data.requestId, { kind, fingerprint: JSON.stringify(data), generation: state.generation, memoryEpoch: state.memoryEpoch });
    return good({ replayed: false });
  }
  function setConsent(value) {
    if (!exact(value, ['memory', 'capture']) || typeof value.memory !== 'boolean' || typeof value.capture !== 'boolean') return bad('INVALID_CONSENT');
    if (state.consent.memory === value.memory && state.consent.capture === value.capture) return good({ replayed: true });
    const memoryChanged = state.consent.memory !== value.memory;
    if (memoryChanged && !value.memory) { state.memories = []; state.selectedContext = []; state.task = null; }
    state.consent = copy(value); invalidate({ memory: memoryChanged, task: memoryChanged });
    return good();
  }
  function beginTask(value) {
    if (!exact(value, ['title', 'items', 'mode']) || !label(value.title, 100) || !['teach', 'pack'].includes(value.mode) ||
      !Array.isArray(value.items) || value.items.length < 1 || value.items.length > 10 ||
      !value.items.every(item => exact(item, ['id', 'name']) && ident(item.id) && label(item.name, 80)) ||
      new Set(value.items.map(item => item.id)).size !== value.items.length) return bad('INVALID_TASK');
    state.task = { id: freshId(), title: value.title, mode: value.mode, status: 'active', items: value.items.map(item => ({
      id: item.id, name: item.name, place: state.memories.find(memory => memory.itemId === item.id)?.place ?? null,
      packed: false, packedAtMs: null, packedSource: null, userConfirmed: false, previouslyPacked: false })) };
    invalidate({ task: true }); return good();
  }
  function requestView(value) {
    if (!exact(value, ['itemId', 'reason']) || !ident(value.itemId) || !reasons.includes(value.reason)) return bad('INVALID_REQUEST');
    if (!state.consent.capture) return bad('CAPTURE_CONSENT_REQUIRED');
    if (state.task?.status !== 'active' || !state.task.items.some(item => item.id === value.itemId)) return bad('ACTIVE_ITEM_REQUIRED');
    invalidate(); const createdAtMs = clock();
    state.pending = { requestId: freshId() + ':' + (++requestSequence), itemId: value.itemId, reason: value.reason,
      createdAtMs, expiresAtMs: createdAtMs + FRESH_MS, frameWatermark: state.frameWatermark, binding: binding() };
    return good({ request: copy(state.pending) });
  }
  async function acceptFrame(value) {
    if (!exact(value, ['requestId', 'binding', 'bytes', 'sha256', 'mimeType', 'capturedAtMs', 'sequence', 'source']) ||
      !ident(value.requestId) || !hash(value.sha256) || !integer(value.capturedAtMs) || !integer(value.sequence) ||
      !['phone-camera', 'selected-image', 'demo'].includes(value.source) ||
      !['image/jpeg', 'image/png', 'image/webp'].includes(value.mimeType)) return bad('INVALID_FRAME');
    if (value.source !== 'phone-camera') return bad('HISTORICAL_FRAME_ONLY');
    if (!current(value.requestId) || !matches(value.binding)) return bad('STALE_REQUEST');
    if (state.acceptedFrame) return bad('FRAME_ALREADY_BOUND');
    if (value.capturedAtMs <= state.pending.createdAtMs || value.capturedAtMs > clock() ||
      clock() - value.capturedAtMs > FRESH_MS || value.sequence <= state.pending.frameWatermark || value.sequence <= state.frameWatermark) return bad('STALE_FRAME');
    if (!(value.bytes instanceof Uint8Array || value.bytes instanceof ArrayBuffer)) return bad('INVALID_FRAME_BYTES');
    const length = value.bytes.byteLength;
    if (length < 12 || length > MAX_FRAME_BYTES || seenHashes.size >= 256) return bad('FRAME_BYTE_LIMIT');
    const bytes = value.bytes instanceof Uint8Array ? new Uint8Array(value.bytes) : new Uint8Array(value.bytes.slice(0));
    const expectedMime = bytes[0] === 137 && bytes[1] === 80 && bytes[2] === 78 && bytes[3] === 71 ? 'image/png'
      : bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255 ? 'image/jpeg'
      : String.fromCharCode(...bytes.slice(0, 4)) === 'RIFF' && String.fromCharCode(...bytes.slice(8, 12)) === 'WEBP' ? 'image/webp' : null;
    if (expectedMime !== value.mimeType) return bad('IMAGE_FORMAT_MISMATCH');
    const captured = { requestId: value.requestId, binding: copy(value.binding), sha256: value.sha256,
      mimeType: value.mimeType, capturedAtMs: value.capturedAtMs, sequence: value.sequence, source: value.source };
    let actual;
    try { actual = [...new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256', bytes))].map(byte => byte.toString(16).padStart(2, '0')).join(''); }
    catch { return bad('HASH_UNAVAILABLE'); }
    if (!current(captured.requestId) || !matches(captured.binding) || state.acceptedFrame ||
      captured.sequence <= state.frameWatermark || captured.sequence <= state.pending.frameWatermark ||
      captured.capturedAtMs <= state.pending.createdAtMs || captured.capturedAtMs > clock() || clock() - captured.capturedAtMs > FRESH_MS) return bad('STALE_REQUEST');
    if (actual !== captured.sha256) return bad('FRAME_HASH_MISMATCH');
    if (seenHashes.has(actual)) return bad('DUPLICATE_FRAME');
    seenHashes.add(actual); state.frameWatermark = captured.sequence;
    state.acceptedFrame = { ...captured, byteLength: bytes.length, distinguishingViewConfirmed: false, ...authority };
    state.revision++; return good();
  }
  function confirmMemory(value) {
    if (!exact(value, ['requestId', 'itemId', 'name', 'place', 'confirmed']) || value.confirmed !== true ||
      !ident(value.requestId) || !ident(value.itemId) || !label(value.name, 80) || !label(value.place, 120)) return bad('INVALID_CONFIRMATION');
    const duplicate = replay('memory', value); if (duplicate) return duplicate;
    if (!state.consent.memory) return bad('MEMORY_CONSENT_REQUIRED');
    if (!accepted(value.requestId, value.itemId)) return bad('FRESH_FRAME_CONFIRMATION_REQUIRED');
    const existing = state.memories.find(memory => memory.itemId === value.itemId);
    if (!existing && state.memories.length >= 10) return bad('MEMORY_LIMIT');
    const memory = { itemId: value.itemId, name: value.name, place: value.place, confirmedAtMs: clock(),
      version: (existing?.version ?? 0) + 1, frameSha256: state.acceptedFrame.sha256, viewReason: state.pending.reason,
      association: 'user-confirmed-photo', physicalIdentityVerified: false, currentPresenceVerified: false };
    state.memories = [...state.memories.filter(item => item.itemId !== value.itemId), memory];
    const item = state.task.items.find(item => item.id === value.itemId);
    Object.assign(item, { name: value.name, place: value.place, userConfirmed: true });
    if (state.task.mode === 'teach' && state.task.items.every(item => item.userConfirmed)) state.task.status = 'completed';
    return commitConfirmation('memory', value);
  }
  function correctMemory(value) {
    if (!exact(value, ['itemId', 'name', 'place', 'confirmed']) || value.confirmed !== true ||
      !ident(value.itemId) || !label(value.name, 80) || !label(value.place, 120)) return bad('INVALID_CONFIRMATION');
    if (!state.consent.memory) return bad('MEMORY_CONSENT_REQUIRED');
    const memory = state.memories.find(item => item.itemId === value.itemId);
    if (!memory) return bad('UNKNOWN_MEMORY');
    if (memory.name === value.name && memory.place === value.place) return good({ replayed: true });
    Object.assign(memory, { name: value.name, place: value.place, confirmedAtMs: clock(), version: memory.version + 1,
      frameSha256: null, viewReason: null, association: 'user-corrected-metadata' });
    const item = state.task?.items.find(item => item.id === value.itemId);
    if (item) Object.assign(item, { name: value.name, place: value.place });
    invalidate({ memory: true, task: true }); return good();
  }
  function forgetMemory(value) {
    if (!exact(value, ['itemId']) || !ident(value.itemId)) return bad('INVALID_ITEM');
    state.memories = state.memories.filter(item => item.itemId !== value.itemId);
    if (state.task?.items.some(item => item.id === value.itemId)) state.task = null;
    invalidate({ memory: true, task: true }); return good();
  }
  function forgetAll() {
    state.memories = []; state.selectedContext = []; state.task = null; state.consent.capture = false;
    invalidate({ memory: true, task: true }); return good();
  }
  function reset() {
    forgetAll(); state.consent.memory = false; state.sessionId = freshId();
    return good();
  }
  function confirmPacked(value) {
    if (!exact(value, ['requestId', 'itemId', 'confirmed']) || value.confirmed !== true || !ident(value.requestId) || !ident(value.itemId)) return bad('INVALID_CONFIRMATION');
    const duplicate = replay('packed', value); if (duplicate) return duplicate;
    if (state.task?.mode !== 'pack' || !accepted(value.requestId, value.itemId)) return bad('FRESH_FRAME_CONFIRMATION_REQUIRED');
    const item = state.task.items.find(item => item.id === value.itemId);
    Object.assign(item, { packed: true, packedAtMs: clock(), packedSource: 'user', userConfirmed: true, previouslyPacked: false });
    if (state.task.items.every(item => item.packed)) state.task.status = 'completed';
    return commitConfirmation('packed', value);
  }
  function pause() {
    if (!state.task) return bad('TASK_REQUIRED');
    if (state.task.status === 'active') state.task.status = 'paused';
    state.consent.capture = false; invalidate({ task: true }); return good();
  }
  function resume() {
    if (!state.task) return bad('TASK_REQUIRED');
    if (state.task.status !== 'paused') return good({ replayed: true });
    state.task.status = 'active'; state.consent.capture = false;
    invalidate({ task: true }); return good();
  }
  function cancelRequest() { invalidate(); return good(); }
  function expire({ requestId } = {}) {
    if (!state.pending || requestId !== undefined && requestId !== state.pending.requestId || clock() < state.pending.expiresAtMs) return good({ expired: false });
    invalidate(); state.consent.capture = false; return good({ expired: true });
  }
  function importSelectedContext(input) {
    if (!state.consent.memory) return bad('MEMORY_CONSENT_REQUIRED');
    let envelope;
    try { envelope = typeof input === 'string' ? parseMetadata(input) : input; }
    catch { return bad('INVALID_CONTEXT'); }
    if (!exact(envelope, ['schema', 'selectionId', 'source', 'selectedByUser', 'entries']) ||
      envelope.schema !== 'lens.selected-context/v1' || !ident(envelope.selectionId) || envelope.selectedByUser !== true ||
      !['screenshotcontext', 'manual'].includes(envelope.source) || !Array.isArray(envelope.entries) ||
      envelope.entries.length < 1 || envelope.entries.length > 10 || new Set(envelope.entries.map(row => row?.id)).size !== envelope.entries.length) return bad('INVALID_CONTEXT');
    const time = clock();
    const entries = [];
    for (const row of envelope.entries) {
      if (!exact(row, ['id', 'title', 'summary', 'observedAtMs', 'timeBasis'])) return bad('INVALID_CONTEXT');
      const entry = { ...row, selectionId: envelope.selectionId, source: envelope.source, historical: true };
      if (!validContextRow(entry, time)) return bad('INVALID_CONTEXT');
      entries.push(entry);
    }
    if (JSON.stringify(entries) === JSON.stringify(state.selectedContext)) return good({ replayed: true });
    state.selectedContext = entries; invalidate({ memory: true }); return good();
  }
  function exportState({ expectedMemoryEpoch = state.memoryEpoch } = {}) {
    if (!state.consent.memory || expectedMemoryEpoch !== state.memoryEpoch) return null;
    const result = JSON.stringify({ schema: 'lens.guide-save/v1', memoryConsent: true, memoryEpoch: state.memoryEpoch,
      revision: state.revision, taskRevision: state.taskRevision, savedAtMs: clock(), task: state.task,
      memories: state.memories, selectedContext: state.selectedContext });
    if (new TextEncoder().encode(result).length > MAX_SAVE_BYTES) throw failError('SAVE_LIMIT');
    return result;
  }
  function restoreMetadata(saved) {
    state.memories = copy(saved.memories); state.selectedContext = copy(saved.selectedContext); state.task = copy(saved.task);
    state.memoryEpoch = saved.memoryEpoch; state.revision = saved.revision + 1; state.taskRevision = saved.taskRevision + 1;
    state.consent = { memory: true, capture: false };
    if (state.task) {
      if (state.task.status === 'active') state.task.status = 'paused';
      for (const item of state.task.items) item.previouslyPacked = item.packed;
    }
    for (const memory of state.memories) if (memory.frameSha256 !== null) seenHashes.add(memory.frameSha256);
  }
  const api = { snapshot, setConsent, beginTask, requestView, acceptFrame, confirmMemory, correctMemory,
    forgetMemory, forgetAll, reset, confirmPacked, pause, resume, cancelRequest, expire, importSelectedContext,
    exportState };
  restorePorts.set(api, restoreMetadata);
  return api;
}

export function restoreGuideSession(serialized, options = {}) {
  try {
    const saved = parseMetadata(serialized), time = (options.now ?? Date.now)();
    const keys = ['schema', 'memoryConsent', 'memoryEpoch', 'revision', 'taskRevision', 'savedAtMs', 'task', 'memories', 'selectedContext'];
    if (!integer(time) || !exact(saved, keys) || saved.schema !== 'lens.guide-save/v1' || saved.memoryConsent !== true ||
      !['memoryEpoch', 'revision', 'taskRevision', 'savedAtMs'].every(key => integer(saved[key])) || saved.savedAtMs > time ||
      saved.memoryEpoch > saved.revision || saved.taskRevision > saved.revision || !Array.isArray(saved.memories) || saved.memories.length > 10 ||
      !saved.memories.every(row => validMemory(row, time)) || new Set(saved.memories.map(row => row.itemId)).size !== saved.memories.length ||
      !Array.isArray(saved.selectedContext) || saved.selectedContext.length > 10 || !saved.selectedContext.every(row => validContextRow(row, time)) ||
      new Set(saved.selectedContext.map(row => row.id)).size !== saved.selectedContext.length) throw failError('INVALID_SAVE');
    if (saved.task !== null && (!exact(saved.task, ['id', 'title', 'mode', 'status', 'items']) || !ident(saved.task.id) ||
      !label(saved.task.title, 100) || !['teach', 'pack'].includes(saved.task.mode) || !['active', 'paused', 'completed'].includes(saved.task.status) ||
      !Array.isArray(saved.task.items) || saved.task.items.length < 1 || saved.task.items.length > 10 ||
      !saved.task.items.every(item => validItem(item, time)) || new Set(saved.task.items.map(item => item.id)).size !== saved.task.items.length)) throw failError('INVALID_SAVE');
    if (saved.task?.status === 'completed' && !saved.task.items.every(item => saved.task.mode === 'pack' ? item.packed : item.userConfirmed)) throw failError('INVALID_SAVE');
    const session = createGuideSession(options); restorePorts.get(session)(saved);
    return session;
  } catch { throw failError('INVALID_SAVE'); }
}

export const GUIDE_LIMITS = Object.freeze({ maxItems: 10, maxSaveBytes: MAX_SAVE_BYTES, maxFrameBytes: MAX_FRAME_BYTES, freshnessMs: FRESH_MS });
