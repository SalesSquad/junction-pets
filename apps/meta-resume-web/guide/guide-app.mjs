import { createGuideSession, restoreGuideSession } from './guide-core.mjs';
import { createCaptureController, readSelectedImage, createDemoImage } from './capture.mjs';
import { registerGuideTools } from './guide-webmcp.mjs';
import { convertScreenshotContextHandoff, SCREENSHOT_CONTEXT_HANDOFF_LIMIT } from './context-handoff.mjs';
import { DATA_KEY, EPOCH_KEY, writeGuideMetadata, eraseGuideMetadata, describeGuideErasure } from './guide-storage.mjs';

const $ = id => document.getElementById(id);
let session = createGuideSession(), previewURL = null, previewSource = null, frameRequestId = null;
let mediaEpoch = 0, editItemId = null, selectedItemId = null, toolProposal = null;
let persistEnabled = false, storageAvailable = true, writeLock = false, storageConflict = false;
let storageEpoch = null, lastSavedRaw = null, releaseLock = null, toastTimer, cameraState = 'idle', cameraMessage = '';
let busy = false, disposed = false, storageNotice = '', assistantSharing = false, cleanupTools = () => {};
const compact = new URLSearchParams(location.search).get('display') === '1';
document.body.classList.toggle('compact', compact);

function notify(message) {
  clearTimeout(toastTimer); $('toast').textContent = message; $('toast').hidden = false;
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, 6500);
}
function errorMessage(error) {
  const code = error?.code ?? error?.error?.code;
  return ({ CAPTURE_CONSENT_REQUIRED: 'Open a new camera request to continue.', ACTIVE_ITEM_REQUIRED: 'Choose an active task item first.',
    FRESH_FRAME_CONFIRMATION_REQUIRED: 'Take a new camera photo for this request, then confirm it yourself.',
    STALE_REQUEST: 'That view is no longer current. Ask for a new photo.', STALE_FRAME: 'Take a new photo after opening this request.',
    DUPLICATE_FRAME: 'This exact photo was already used. Take a new view of the item.',
    MEMORY_LIMIT: 'Your workbench holds up to 10 items. Forget an item before adding another.',
    INVALID_CONTEXT: 'That card does not match the metadata template. Use only selected titles, summaries and past timestamps.',
    INVALID_CONFIRMATION: 'Use a short name and place, without links or file paths, and check the confirmation box.',
    HISTORICAL_FRAME_ONLY: 'A selected or illustrated photo is a historical preview. Use the camera for a new request.',
    FRAME_BYTE_LIMIT: 'Use a photo under 2 MB. No frame was accepted.',
  })[code] ?? error?.message ?? 'That action could not be completed. Your confirmed items are unchanged.';
}
function clearPreview() {
  mediaEpoch += 1;
  if (previewURL) URL.revokeObjectURL(previewURL);
  previewURL = null; previewSource = null; frameRequestId = null;
  $('photoPreview').removeAttribute('src'); $('photoFile').value = '';
  $('teachConfirmed').checked = false; $('packedConfirmed').checked = false;
}
function fenceMedia(message = 'Camera stopped.') { capture.stop(message); clearPreview(); toolProposal = null; }
function invalidateFromOtherTab(epoch) {
  setAssistantSharing(false);
  fenceMedia('This workbench was forgotten in another tab.'); session.reset();
  storageEpoch = epoch; lastSavedRaw = null; persistEnabled = false; storageConflict = false;
  editItemId = null; selectedItemId = null;
  $('contextInput').value = ''; $('itemName').value = ''; $('itemPlace').value = ''; render();
  notify('This workbench was forgotten in another tab. Old state will not be saved again.');
}
function persist() {
  if (!persistEnabled || !storageAvailable || !writeLock || storageConflict || disposed) return;
  try {
    const state = session.snapshot(), metadata = session.exportState({ expectedMemoryEpoch: state.memoryEpoch });
    if (!metadata) return;
    const result = writeGuideMetadata(localStorage, { epoch: storageEpoch, previousRaw: lastSavedRaw, metadata });
    if (result.code === 'EPOCH_CHANGED') {
      invalidateFromOtherTab(result.epoch);
      if (result.cleanupFailed) { storageAvailable = false; storageNotice = 'Browser storage blocked removal of an outdated saved copy. Clear this site’s storage in browser settings.'; notify(storageNotice); }
      return;
    }
    if (result.code === 'SAVE_CONFLICT') { storageConflict = true; storageNotice = 'Another tab changed the saved workbench. Reload to use its latest version.'; notify(storageNotice); return; }
    if (!result.ok) throw new Error(result.code);
    lastSavedRaw = result.raw; storageNotice = '';
  } catch { storageAvailable = false; storageNotice = 'Browser storage could not be updated. Changes stay in this tab; the saved copy may be older.'; notify(storageNotice); }
}
function clearSavedMetadata(mode) {
  let result;
  try { result = eraseGuideMetadata(localStorage, { epoch: crypto.randomUUID() }); }
  catch { result = { ok: false, dataState: 'unknown', epochReadbackVerified: false, epochConfirmed: false }; }
  if (result.epochReadbackVerified) storageEpoch = result.epoch;
  if (result.dataState === 'cleared') lastSavedRaw = null;
  storageConflict = !result.ok;
  storageAvailable = result.ok && Boolean(navigator.locks?.request);
  const message = describeGuideErasure(result, mode);
  storageNotice = result.ok ? '' : message;
  notify(message);
  return result;
}
function apply(result, { save = true } = {}) {
  if (!result.ok) { notify(errorMessage(result)); render(); return false; }
  if (save) persist(); render(); return true;
}
function ensureMemoryConsent() {
  const state = session.snapshot();
  return state.consent.memory || apply(session.setConsent({ memory: true, capture: state.consent.capture }));
}
function activeItem(state = session.snapshot()) {
  return state.task?.items.find(item => item.id === selectedItemId && (state.task.mode !== 'pack' || !item.packed))
    ?? state.task?.items.find(item => state.task.mode === 'pack' ? !item.packed : !item.userConfirmed) ?? null;
}
function freshFrame(state) {
  return Boolean(state.pending && state.acceptedFrame?.source === 'phone-camera' &&
    state.acceptedFrame.requestId === state.pending.requestId && frameRequestId === state.pending.requestId &&
    Date.now() < state.pending.expiresAtMs && state.task?.status === 'active');
}
function teachNew() {
  const state = session.snapshot();
  if (state.memories.length >= 10) { notify('Your workbench is full. Forget an item to make room.'); return false; }
  if (state.task?.mode === 'pack' && state.task.status !== 'completed') { notify('Finish your packing task before starting a new teaching task. You can pause and resume it.'); return false; }
  fenceMedia(); editItemId = null;
  if (!ensureMemoryConsent()) return false;
  selectedItemId = crypto.randomUUID();
  $('itemName').value = ''; $('itemPlace').value = 'My workbench';
  return apply(session.beginTask({ title: 'My workbench', mode: 'teach', items: [{ id: selectedItemId, name: 'New workbench item' }] }));
}
function prepareRequest(reason = 'close-up', itemId = null) {
  let state = session.snapshot();
  if (!state.task || state.task.mode === 'teach' && state.task.status === 'completed') { if (!teachNew()) return null; }
  state = session.snapshot();
  if (state.task?.status !== 'active') { notify('Resume your task first.'); return null; }
  const item = itemId ? state.task.items.find(value => value.id === itemId) : activeItem(state);
  if (!item) { notify('No unfinished item is selected.'); return null; }
  fenceMedia(); editItemId = null; selectedItemId = item.id;
  if (!apply(session.setConsent({ memory: true, capture: true }))) return null;
  const result = session.requestView({ itemId: item.id, reason });
  if (!apply(result)) return null;
  return result.request;
}

const capture = createCaptureController({ video: $('cameraVideo'), onState({ state, message }) {
  cameraState = state; cameraMessage = message; render();
} });

try {
  storageEpoch = localStorage.getItem(EPOCH_KEY);
  lastSavedRaw = localStorage.getItem(DATA_KEY);
  if (lastSavedRaw) {
    if (lastSavedRaw.length > 40000) throw new Error('SAVE_LIMIT');
    const envelope = JSON.parse(lastSavedRaw);
    if (Object.keys(envelope).length !== 2 || typeof envelope.metadata !== 'string' || envelope.epoch !== storageEpoch) {
      localStorage.removeItem(DATA_KEY); lastSavedRaw = null;
    } else {
      session = restoreGuideSession(envelope.metadata); persistEnabled = true;
      notify('Your confirmed workbench is restored. Camera permission and photos were not restored.');
    }
  }
} catch { storageAvailable = false; notify('Saved data could not be restored. A fresh workbench is ready in this tab.'); }
if (navigator.locks?.request) {
  navigator.locks.request('chibi-lens-guide-metadata-writer', { mode: 'exclusive', ifAvailable: true }, lock => {
    if (disposed) return;
    writeLock = Boolean(lock); render();
    if (!lock) return;
    return new Promise(resolve => { releaseLock = resolve; });
  }).catch(() => { storageAvailable = false; render(); });
} else { storageAvailable = false; }
window.addEventListener('storage', event => {
  if (event.key === null) invalidateFromOtherTab(null);
  else if (event.key === EPOCH_KEY && event.newValue !== storageEpoch) invalidateFromOtherTab(event.newValue);
  else if (event.key === DATA_KEY && event.newValue !== lastSavedRaw) { storageConflict = true; render(); }
});

function render() {
  if (disposed) return;
  const state = session.snapshot(), item = activeItem(state), task = state.task;
  const paused = task?.status === 'paused', complete = task?.status === 'completed', packing = task?.mode === 'pack';
  const fresh = freshFrame(state), live = cameraState === 'live', requesting = cameraState === 'requesting';
  $('networkStatus').textContent = navigator.onLine === false ? 'OFFLINE · LOCAL WORKBENCH' : 'LOCAL WORKBENCH';
  $('itemCount').textContent = `${state.memories.length} / 10`;
  $('modeLabel').textContent = paused ? 'YOUR CHECKPOINT' : packing ? 'PACK WITH CONFIDENCE' : 'ONE SMALL WORKBENCH';
  $('workbenchTitle').textContent = paused ? 'Your place is saved.' : complete ? packing ? 'Ready when you are.' : 'One thing, remembered.' : packing && item ? `Next: ${item.name}` : 'Start with one thing.';
  $('stagePlaceholder').hidden = Boolean(previewURL) || live || requesting;
  $('cameraVideo').hidden = !live && !requesting; $('photoPreview').hidden = !previewURL || live || requesting;
  $('photoBadge').textContent = live ? 'LIVE BROWSER CAMERA · NOT GLASSES' : requesting ? 'CAMERA PERMISSION REQUEST' : previewSource === 'phone-camera' ? 'NEW CAMERA PHOTO · THIS REQUEST' : previewSource === 'demo' ? 'ILLUSTRATED DEMO · PREVIEW ONLY' : previewSource ? 'SELECTED PHOTO · HISTORICAL PREVIEW' : 'ILLUSTRATION · CAMERA OFF';
  $('photoBadge').className = `photo-badge${previewSource && previewSource !== 'phone-camera' ? ' historical' : live ? ' live' : ''}`;
  $('cameraStatus').textContent = previewSource === 'selected-image' || previewSource === 'demo' ? 'Preview only. A file or demo cannot satisfy a new camera request.' : fresh ? 'A new photo is ready. Check the item yourself, then confirm below.' : cameraMessage || 'Photos stay in this tab. Nothing is uploaded.';
  $('openCamera').hidden = live; $('takePhoto').hidden = !live; $('stopCamera').hidden = !live && !requesting;
  $('openCamera').disabled = busy || requesting || paused || packing && complete;
  $('openCamera').textContent = state.pending && !fresh ? 'Open camera for this view ↗' : 'Use my camera ↗';
  $('takePhoto').disabled = busy; $('choosePhoto').disabled = busy || paused;
  $('clearPhoto').hidden = !previewURL; $('tryDemo').disabled = busy || paused;
  $('requestCard').hidden = !state.pending;
  if (state.pending) {
    const target = task?.items.find(entry => entry.id === state.pending.itemId);
    $('requestTitle').textContent = state.pending.reason === 'side' ? 'Show a distinctive side.' : state.pending.reason === 'overview' ? 'Show the item and its surroundings.' : 'A closer look would help.';
    $('requestDescription').textContent = `Show ${target?.name === 'New workbench item' ? 'the item’s' : `${target?.name ?? 'the item'}’s`} label or identifying details. You will still make the final check.`;
    $('requestCountdown').textContent = `${Math.max(0, Math.ceil((state.pending.expiresAtMs - Date.now()) / 1000))}s`;
  }
  $('teachForm').hidden = packing && !editItemId || !editItemId && !previewURL;
  $('teachTitle').textContent = editItemId ? 'Correct your description.' : 'Make the connection.';
  $('teachSource').textContent = editItemId ? 'METADATA CORRECTION' : fresh ? 'NEW CAMERA PHOTO' : 'PREVIEW ONLY';
  $('teachHint').textContent = editItemId ? 'This changes your words, not the item’s observed identity or current location.' : fresh ? 'Check the item yourself, then tell us what you call it and where you put it.' : 'You can preview the form. Take a new camera photo to confirm an association.';
  $('saveAssociation').disabled = busy || !$('teachConfirmed').checked || !editItemId && !fresh;
  $('saveAssociation').textContent = editItemId ? 'Confirm correction' : 'Confirm name & place';
  $('cancelEdit').hidden = !editItemId;
  $('packingControls').hidden = !packing || paused || complete || Boolean(editItemId);
  $('packingTitle').textContent = item?.name ?? 'All items confirmed';
  $('packingHint').textContent = fresh ? 'Check that this is your item and put it in the bag. The photo does not mark it packed.' : `Remembered place: ${item?.place ?? 'not recorded'}. Take a new close-up, then make your own check.`;
  $('confirmPacked').disabled = busy || !fresh || !$('packedConfirmed').checked;
  $('newItem').disabled = state.memories.length >= 10 || packing && !complete;
  $('newItem').hidden = !state.memories.length && !complete;
  $('pauseTask').hidden = !task || paused || complete;
  $('resumeTask').hidden = !paused;
  $('stepLook').className = fresh ? 'done' : 'current'; $('stepName').className = fresh ? 'current' : '';
  $('stepConfirm').className = complete ? 'done' : '';
  renderMemories(state);
  $('saveLocally').checked = persistEnabled;
  // Revocation stays available even when the storage writer has failed or is in another tab.
  $('saveLocally').disabled = !persistEnabled && (!storageAvailable || !writeLock || storageConflict);
  $('storageStatus').textContent = storageNotice || (!storageAvailable ? 'Saving is unavailable. Changes stay in this tab only.' : storageConflict ? 'Saved workbench changed in another tab. Reload before saving.' : !writeLock ? 'Another tab owns saving. This tab is read-only for saved data.' : persistEnabled ? 'Confirmed metadata is saved on this browser. Photos and camera permission are never saved.' : 'Session only. Choose this option to keep confirmed metadata after closing.');
  $('assistantSharing').checked = assistantSharing;
  $('toolProposal').hidden = !toolProposal;
  if (toolProposal) $('proposalText').textContent = toolProposal.kind === 'resume' ? 'Resume from your last confirmed step?' : `Ask for a ${toolProposal.reason} of the selected item? The camera stays off until you open it.`;
  $('contextList').replaceChildren(...state.selectedContext.map(entry => {
    const row = document.createElement('li'), title = document.createElement('strong'), text = document.createElement('p'), tag = document.createElement('small');
    title.textContent = entry.title; text.textContent = entry.summary;
    const timeLabel = entry.timeBasis === 'handoff-export' ? 'HANDOFF EXPORT TIME' : entry.timeBasis === 'captured' ? 'REPORTED CAPTURE TIME' : 'USER NOTE TIME';
    tag.textContent = `${timeLabel} · ${new Date(entry.observedAtMs).toLocaleString()} · HISTORICAL`;
    row.append(title, text, tag); return row;
  }));
}
function renderMemories(state) {
  $('emptyMemory').hidden = state.memories.length > 0;
  $('memoryList').replaceChildren(...state.memories.map((memory, index) => {
    const row = document.createElement('li'); row.className = 'memory-row';
    const marker = document.createElement('span'); marker.className = 'memory-marker';
    const taskItem = state.task?.mode === 'pack' && state.task.items.find(item => item.id === memory.itemId);
    marker.textContent = taskItem?.packed ? '✓' : String(index + 1).padStart(2, '0');
    const body = document.createElement('div'); body.className = 'memory-copy';
    const name = document.createElement('strong'), place = document.createElement('small'), tag = document.createElement('em');
    name.textContent = memory.name; place.textContent = memory.place;
    tag.textContent = taskItem?.packed ? taskItem.previouslyPacked ? 'PREVIOUSLY CONFIRMED PACKED BY YOU' : 'PACKED · CONFIRMED BY YOU' : 'YOUR CONFIRMED ASSOCIATION';
    body.append(name, place, tag);
    const actions = document.createElement('div'); actions.className = 'memory-options';
    for (const [action, text] of [['edit', 'Edit'], ['forget', 'Forget']]) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'text-button';
      button.textContent = text; button.dataset.item = memory.itemId; button.dataset.action = action;
      button.disabled = persistEnabled && (!writeLock || storageConflict);
      button.setAttribute('aria-label', `${text} ${memory.name}`); actions.append(button);
    }
    row.append(marker, body, actions); return row;
  }));
  const pack = state.task?.mode === 'pack' ? state.task : null, count = pack?.items.filter(item => item.packed).length ?? 0;
  $('startPacking').disabled = !state.memories.length || pack?.status === 'active';
  $('startPacking').textContent = pack?.status === 'paused' ? 'Resume packing →' : pack?.status === 'active' ? 'Packing in progress' : pack?.status === 'completed' ? 'Pack these items again →' : 'Pack these items →';
  $('packProgress').hidden = !pack;
  if (pack) { $('progressLabel').textContent = pack.status === 'paused' ? 'Paused · checkpoint kept' : pack.status === 'completed' ? 'Confirmed by you' : 'Packing your things';
    $('progressCount').textContent = `${count} / ${pack.items.length}`; $('packingProgress').max = pack.items.length; $('packingProgress').value = count;
    $('progressDetail').textContent = pack.items.some(item => item.previouslyPacked) ? 'Earlier confirmations are preserved. They do not verify where items are now.' : 'Only your explicit confirmations mark items packed.'; }
}

async function showHistorical(factory) {
  fenceMedia(); session.cancelRequest(); editItemId = null;
  const epoch = mediaEpoch; busy = true; render();
  try {
    const frame = await factory();
    if (disposed || epoch !== mediaEpoch || document.hidden) return;
    previewURL = URL.createObjectURL(frame.blob); previewSource = frame.source; $('photoPreview').src = previewURL;
    cameraMessage = ''; render();
  } catch (error) { notify(errorMessage(error)); }
  finally { busy = false; render(); }
}
$('openCamera').addEventListener('click', async () => {
  const request = prepareRequest(session.snapshot().pending?.reason ?? 'close-up');
  if (!request) return;
  try { await capture.start({ userGesture: true, requestId: request.requestId, expiresAtMs: request.expiresAtMs }); }
  catch (error) { cameraMessage = errorMessage(error); notify(cameraMessage); render(); }
});
$('takePhoto').addEventListener('click', async () => {
  const request = session.snapshot().pending, epoch = mediaEpoch;
  if (!request || busy) return;
  busy = true; render();
  try {
    const frame = await capture.takePhoto();
    if (epoch !== mediaEpoch || disposed || document.hidden) return;
    const { blob, ...input } = frame;
    const result = await session.acceptFrame({ ...input, requestId: request.requestId, binding: request.binding });
    if (epoch !== mediaEpoch || disposed || document.hidden) return;
    if (!apply(result, { save: false })) return;
    previewURL = URL.createObjectURL(blob); previewSource = frame.source; frameRequestId = request.requestId;
    $('photoPreview').src = previewURL; $('teachConfirmed').checked = false; $('packedConfirmed').checked = false;
    render(); if (session.snapshot().task?.mode === 'teach') $('itemName').focus();
  } catch (error) { notify(errorMessage(error)); }
  finally { busy = false; render(); }
});
$('stopCamera').addEventListener('click', () => { fenceMedia(); apply(session.cancelRequest(), { save: false }); });
$('choosePhoto').addEventListener('click', () => $('photoFile').click());
$('photoFile').addEventListener('change', () => { const file = $('photoFile').files?.[0]; if (file) showHistorical(() => readSelectedImage(file)); });
$('tryDemo').addEventListener('click', () => showHistorical(createDemoImage));
$('clearPhoto').addEventListener('click', () => { fenceMedia(); apply(session.cancelRequest(), { save: false }); });
$('newItem').addEventListener('click', () => { if (teachNew()) $('openCamera').focus(); });
$('teachConfirmed').addEventListener('change', render); $('packedConfirmed').addEventListener('change', render);
$('teachForm').addEventListener('submit', event => {
  event.preventDefault(); if (!$('teachConfirmed').checked) return;
  const state = session.snapshot(), values = { name: $('itemName').value.trim(), place: $('itemPlace').value.trim(), confirmed: true };
  const result = editItemId ? session.correctMemory({ itemId: editItemId, ...values }) : session.confirmMemory({ requestId: state.pending?.requestId, itemId: state.pending?.itemId, ...values });
  if (apply(result)) { fenceMedia(); editItemId = null; render(); notify('Your description is confirmed. It is a remembered association, not a live location.'); }
});
$('cancelEdit').addEventListener('click', () => { editItemId = null; $('teachConfirmed').checked = false; render(); });
$('memoryList').addEventListener('click', event => {
  const button = event.target.closest('button[data-action]'); if (!button) return;
  const memory = session.snapshot().memories.find(item => item.itemId === button.dataset.item); if (!memory) return;
  fenceMedia(); session.cancelRequest();
  if (button.dataset.action === 'forget') {
    setAssistantSharing(false); editItemId = null;
    if (!apply(session.forgetMemory({ itemId: memory.itemId }))) return;
    const savedCopyMayRemain = (persistEnabled || lastSavedRaw !== null) && (!storageAvailable || !writeLock || storageConflict);
    notify(savedCopyMayRemain ? `${memory.name} was removed from this tab, but saved metadata could not be updated. Clear this site’s storage to remove the saved copy.` : persistEnabled ? `${memory.name} was removed from this workbench and its saved metadata.` : `${memory.name} was removed from this tab.`);
  }
  else { editItemId = memory.itemId; $('itemName').value = memory.name; $('itemPlace').value = memory.place; render(); $('itemName').focus(); }
});
$('startPacking').addEventListener('click', () => {
  const state = session.snapshot();
  if (state.task?.mode === 'pack' && state.task.status === 'paused') { apply(session.resume()); return; }
  fenceMedia(); editItemId = null; selectedItemId = null;
  apply(session.beginTask({ title: 'Pack my workbench items', mode: 'pack', items: state.memories.map(item => ({ id: item.itemId, name: item.name })) }));
});
$('confirmPacked').addEventListener('click', () => {
  const state = session.snapshot(); if (!$('packedConfirmed').checked || !freshFrame(state)) return;
  if (apply(session.confirmPacked({ requestId: state.pending.requestId, itemId: state.pending.itemId, confirmed: true }))) {
    fenceMedia(); selectedItemId = null; render(); notify('Packed — confirmed by you.');
  }
});
$('pauseTask').addEventListener('click', () => { fenceMedia('Task paused. Camera stopped.'); apply(session.pause()); });
$('resumeTask').addEventListener('click', () => { fenceMedia(); apply(session.resume()); });
$('revokeCapture').addEventListener('click', () => { setAssistantSharing(false); fenceMedia('Camera access revoked for this page.'); const state = session.snapshot(); apply(session.setConsent({ memory: state.consent.memory, capture: false })); });
$('saveLocally').addEventListener('change', () => {
  const requested = $('saveLocally').checked;
  if (!requested) {
    persistEnabled = false; clearSavedMetadata('opt-out'); render(); return;
  }
  if (!storageAvailable || !writeLock || storageConflict) { render(); return; }
  persistEnabled = true;
  if (persistEnabled) {
    try {
      if (!localStorage.getItem(EPOCH_KEY)) { storageEpoch = crypto.randomUUID(); localStorage.setItem(EPOCH_KEY, storageEpoch); }
    } catch { storageAvailable = false; }
    ensureMemoryConsent(); persist();
  }
  render();
});
$('forgetAll').addEventListener('click', () => { $('forgetDialog').returnValue = ''; $('forgetDialog').showModal(); });
$('forgetDialog').addEventListener('close', () => {
  if ($('forgetDialog').returnValue !== 'forget') return;
  $('forgetDialog').returnValue = ''; setAssistantSharing(false);
  fenceMedia('Workbench forgotten. Camera stopped.'); session.reset(); persistEnabled = false; editItemId = null; selectedItemId = null;
  clearSavedMetadata('forget');
  $('contextInput').value = ''; $('itemName').value = ''; $('itemPlace').value = ''; render();
});
const contextTemplate = JSON.stringify({ schema: 'lens.selected-context/v1', selectionId: 'my-selected-card', source: 'screenshotcontext', selectedByUser: true,
  entries: [{ id: 'packing-note', title: 'Tomorrow’s camera bag', summary: 'Bring my charger and microphone.', observedAtMs: Date.now() - 60000, timeBasis: 'user-note' }] }, null, 2);
$('contextExample').textContent = contextTemplate;
$('copyTemplate').addEventListener('click', async () => {
  $('contextInput').value = contextTemplate;
  try { await navigator.clipboard.writeText(contextTemplate); notify('Template copied. Replace its text with the context you selected.'); }
  catch { $('contextInput').focus(); $('contextInput').select(); notify('Template added below. You can copy it from the text field.'); }
});
function importContextText(raw) {
  if (!ensureMemoryConsent()) return;
  if (typeof raw !== 'string' || new TextEncoder().encode(raw).length > 65536) { notify('Choose a context card under 64 KB. Images and archives are not imported.'); return; }
  let schema;
  try { schema = JSON.parse(raw)?.schema; } catch { notify('That card is not valid JSON. Check the visible template.'); return; }
  let input = raw;
  if (schema === 'ScreenshotContext.handoff.v1') {
    const converted = convertScreenshotContextHandoff(raw, { selectedByUser: true });
    if (!converted.ok) {
      notify(converted.error.code === 'HANDOFF_TOO_LARGE' ? 'Choose a ScreenshotContext card under 16 KB. Images and archives are not accepted.' : converted.error.code === 'NOTE_REQUIRES_MANUAL_SANITIZATION' ? 'This note contains a link or file path. Use the visible template to select only the text you want to remember.' : 'That ScreenshotContext export has no supported, safely selected note. No images or archive were opened.'); return;
    }
    input = converted.context;
  }
  const result = session.importSelectedContext(input);
  if (apply(result)) { fenceMedia('Context updated. Open a new camera request when needed.'); $('contextInput').value = ''; render(); notify('Selected text added as historical context. No screenshot or image archive was read.'); }
}
$('importContext').addEventListener('click', () => importContextText($('contextInput').value));
$('chooseContext').addEventListener('click', () => $('contextFile').click());
$('contextFile').addEventListener('change', async () => {
  const file = $('contextFile').files?.[0], epoch = mediaEpoch;
  $('contextFile').value = '';
  if (!file) return;
  if (file.name !== 'context.json' || file.size > SCREENSHOT_CONTEXT_HANDOFF_LIMIT) { notify('Select only the exported context.json card, up to 16 KB. Images and archives are not accepted.'); return; }
  try { const raw = await file.text(); if (!disposed && epoch === mediaEpoch && !document.hidden) importContextText(raw); }
  catch { notify('That selected context card could not be read.'); }
});
const toolPorts = { read: () => session.snapshot(), isEnabled: () => assistantSharing && !disposed,
  onStatus(status) { $('webmcpStatus').textContent = !assistantSharing ? 'Assistant sharing is off. No tool can read this workbench.' : ({ disabled: 'Assistant sharing is off. No tools are registered.', unavailable: 'Optional assistant tools are unavailable in this browser. All visible controls work without them.', registered: 'Sharing enabled for this page. The browser assistant can read names, places, task metadata and selected text. You still approve each proposed action.', failed: 'Assistant tool registration failed. The visible workbench still works.' })[status]; },
  onProposal(proposal) {
    if (!assistantSharing || disposed) return { error: true, message: 'Assistant sharing is off.', actionAuthorized: false };
    const state = session.snapshot();
    if (proposal.sessionId !== state.sessionId || proposal.expectedRevision !== state.revision || toolProposal ||
      proposal.kind === 'view' && !state.task?.items.some(item => item.id === proposal.itemId) ||
      proposal.kind === 'resume' && state.task?.status !== 'paused') return { error: true, message: 'State changed or a suggestion is already waiting. Read the current state.', actionAuthorized: false };
    toolProposal = proposal; render();
    return { proposed: true, requiresUserConfirmation: true, actionAuthorized: false, next_action: 'Explain the visible suggestion and wait. Do not capture, confirm memory or mark an item packed.' };
  } };
function setAssistantSharing(enabled) {
  assistantSharing = Boolean(enabled) && !disposed;
  cleanupTools(); cleanupTools = () => {}; toolProposal = null;
  $('assistantSharing').checked = assistantSharing;
  if (assistantSharing) cleanupTools = registerGuideTools(document, toolPorts);
  else $('webmcpStatus').textContent = 'Assistant sharing is off. No tool can read this workbench.';
}
$('assistantSharing').addEventListener('change', () => { setAssistantSharing($('assistantSharing').checked); render(); });
$('dismissProposal').addEventListener('click', () => { toolProposal = null; render(); });
$('approveProposal').addEventListener('click', () => {
  const proposal = toolProposal, state = session.snapshot(); toolProposal = null;
  if (!proposal || proposal.sessionId !== state.sessionId || proposal.expectedRevision !== state.revision) { render(); notify('That suggestion is out of date. Ask again from the current task.'); return; }
  if (proposal.kind === 'resume') apply(session.resume()); else prepareRequest(proposal.reason, proposal.itemId);
});
const expiryTimer = setInterval(() => {
  const request = session.snapshot().pending;
  if (request) {
    const result = session.expire({ requestId: request.requestId });
    if (result.expired) { fenceMedia('Photo request expired. Open a new view to continue.'); render(); }
    else $('requestCountdown').textContent = `${Math.max(0, Math.ceil((request.expiresAtMs - Date.now()) / 1000))}s`;
  }
}, 1000);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) return;
  fenceMedia('Page hidden. Camera stopped.');
  const state = session.snapshot();
  if (state.task?.status === 'active') apply(session.pause()); else apply(session.setConsent({ memory: state.consent.memory, capture: false }));
});
window.addEventListener('online', render); window.addEventListener('offline', render);
document.addEventListener('keydown', event => {
  if (!compact || !['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight'].includes(event.key) ||
    event.target.matches('input:not([type=checkbox]),textarea,select') || document.querySelector('dialog[open]')) return;
  const controls = [...document.querySelectorAll('button:not(:disabled),a,input:not(:disabled),summary')].filter(element => element.getClientRects().length);
  if (!controls.length) return;
  const current = controls.indexOf(document.activeElement), direction = ['ArrowUp', 'ArrowLeft'].includes(event.key) ? -1 : 1;
  event.preventDefault(); controls[(current + direction + controls.length) % controls.length].focus();
});
window.addEventListener('pagehide', () => {
  setAssistantSharing(false);
  fenceMedia('Page closed. Camera stopped.'); disposed = true; clearInterval(expiryTimer); clearTimeout(toastTimer);
  capture.dispose(); cleanupTools(); releaseLock?.();
}, { once: true });
window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
render();
