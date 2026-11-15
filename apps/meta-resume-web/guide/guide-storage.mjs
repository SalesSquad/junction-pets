/** Synchronous metadata storage boundaries. No pixels, permissions or network. */
export const DATA_KEY = 'chibi.lens-guide.metadata.v1';
export const EPOCH_KEY = 'chibi.lens-guide.forget-epoch.v1';

export function writeGuideMetadata(storage, { epoch, previousRaw, metadata }) {
  if (typeof epoch !== 'string' || !epoch || typeof metadata !== 'string') return { ok: false, code: 'INVALID_SAVE_INPUT' };
  const raw = JSON.stringify({ epoch, metadata });
  try {
    let currentEpoch = storage.getItem(EPOCH_KEY);
    if (currentEpoch !== epoch) return { ok: false, code: 'EPOCH_CHANGED', epoch: currentEpoch };
    if (storage.getItem(DATA_KEY) !== previousRaw) return { ok: false, code: 'SAVE_CONFLICT' };
    storage.setItem(DATA_KEY, raw);
    currentEpoch = storage.getItem(EPOCH_KEY);
    if (currentEpoch !== epoch) {
      let cleanupFailed = false;
      try { if (storage.getItem(DATA_KEY) === raw) storage.removeItem(DATA_KEY); }
      catch { cleanupFailed = true; }
      return { ok: false, code: 'EPOCH_CHANGED', epoch: currentEpoch, cleanupFailed };
    }
    if (storage.getItem(DATA_KEY) !== raw) return { ok: false, code: 'SAVE_CONFLICT' };
    return { ok: true, raw };
  } catch { return { ok: false, code: 'STORAGE_UNAVAILABLE' }; }
}

export function eraseGuideMetadata(storage, { epoch }) {
  const failures = [];
  // Neither deletion nor readback may depend on a successful tombstone write.
  try { storage.setItem(EPOCH_KEY, epoch); } catch { failures.push('EPOCH_WRITE_FAILED'); }
  try { storage.removeItem(DATA_KEY); } catch { failures.push('DATA_DELETE_FAILED'); }
  let dataState = 'unknown', observedEpoch = null, epochReadbackVerified = false;
  try { dataState = storage.getItem(DATA_KEY) === null ? 'cleared' : 'saved'; }
  catch { failures.push('DATA_READBACK_FAILED'); }
  try { observedEpoch = storage.getItem(EPOCH_KEY); epochReadbackVerified = true; }
  catch { failures.push('EPOCH_READBACK_FAILED'); }
  const epochConfirmed = epochReadbackVerified && observedEpoch === epoch;
  return { ok: dataState === 'cleared' && epochConfirmed, dataState, epochConfirmed,
    epochReadbackVerified, epoch: observedEpoch, failures };
}

export function describeGuideErasure(result, mode = 'forget') {
  const local = mode === 'opt-out' ? 'Saving is off.' : 'This tab’s workbench is cleared.';
  if (result.ok) return mode === 'opt-out'
    ? 'Saving is off. Saved metadata was removed; your current workbench stays in this tab.'
    : 'This workbench and its saved metadata were forgotten.';
  if (result.dataState === 'saved') return `${local} Browser storage kept the saved metadata. Clear this site’s storage in browser settings to remove it.`;
  if (result.dataState === 'unknown') return `${local} Saved-data removal could not be verified. Metadata may still be saved; clear this site’s storage in browser settings.`;
  return `${local} Saved metadata was removed, but other tabs could not be invalidated. Close other Guide tabs and clear this site’s storage before saving again.`;
}
