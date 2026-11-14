/** Format-only adapter for a user-selected ScreenshotContext context.json.
 * Format source: SalesSquad/screenshot-context@0f8bf49b585ee770669b54f875cd206ea498e50b,
 * ChatGPTHandoff.swift, ScreenshotContext.handoff.v1. No private implementation is copied.
 * generatedAt describes export time. No file reference, URL, OCR or app metadata is retained.
 */
import { parseGuideMetadata, isSafeGuideContextText } from './guide-core.mjs';

const MAX_HANDOFF_BYTES = 16384;
const required = ['schema', 'mode', 'generatedAt', 'sourceFilename', 'annotatedFilename', 'note'];
const optional = ['application', 'windowTitle', 'url', 'ocrText', 'originalFilename'];
const allowed = new Set([...required, ...optional]);
const failure = code => ({ ok: false, error: { code } });

export function convertScreenshotContextHandoff(serialized, {
  selectedByUser = false, now = Date.now, id = () => globalThis.crypto.randomUUID(),
} = {}) {
  if (selectedByUser !== true) return failure('USER_SELECTION_REQUIRED');
  if (typeof serialized !== 'string' || serialized.length > MAX_HANDOFF_BYTES ||
    new TextEncoder().encode(serialized).length > MAX_HANDOFF_BYTES) return failure('HANDOFF_TOO_LARGE');
  let value;
  try { value = parseGuideMetadata(serialized); }
  catch { return failure('INVALID_HANDOFF_JSON'); }
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
    !required.every(key => Object.hasOwn(value, key)) || Object.keys(value).some(key => !allowed.has(key)) ||
    value.schema !== 'ScreenshotContext.handoff.v1') return failure('INVALID_HANDOFF_SCHEMA');
  if (typeof value.mode !== 'string' || value.mode.length < 1 || value.mode.length > 64 ||
    typeof value.generatedAt !== 'string' || value.generatedAt.length > 64 ||
    !['sourceFilename', 'annotatedFilename'].every(key => typeof value[key] === 'string' && value[key].length <= 4096) ||
    !optional.every(key => !Object.hasOwn(value, key) || value[key] === null || typeof value[key] === 'string' && value[key].length <= 8192)) {
    return failure('INVALID_HANDOFF_SCHEMA');
  }
  if (typeof value.note !== 'string' || value.note.trim().length === 0) return failure('NOTE_REQUIRED');
  if (value.note.length > 240) return failure('NOTE_TOO_LONG');
  if (!isSafeGuideContextText(value.note)) return failure('NOTE_REQUIRES_MANUAL_SANITIZATION');
  const parts = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?(?:Z|[+-](\d{2}):(\d{2}))$/.exec(value.generatedAt);
  if (!parts) return failure('INVALID_EXPORT_TIME');
  const [, year, month, day, hour, minute, second, offsetHour = '00', offsetMinute = '00'] = parts;
  if (+month < 1 || +month > 12 || +day < 1 || +day > new Date(Date.UTC(+year, +month, 0)).getUTCDate() ||
    +hour > 23 || +minute > 59 || +second > 59 || +offsetHour > 23 || +offsetMinute > 59) return failure('INVALID_EXPORT_TIME');
  const exportedAtMs = Date.parse(value.generatedAt);
  let time, selectionId;
  try { time = now(); selectionId = id(); } catch { return failure('INVALID_ADAPTER_OPTIONS'); }
  if (!Number.isSafeInteger(time) || time < 0 || !Number.isSafeInteger(exportedAtMs) || exportedAtMs < 0) return failure('INVALID_EXPORT_TIME');
  if (exportedAtMs > time) return failure('FUTURE_EXPORT_TIME');
  if (typeof selectionId !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$/.test(selectionId)) return failure('INVALID_ADAPTER_OPTIONS');
  return { ok: true, context: {
    schema: 'lens.selected-context/v1', selectionId, source: 'screenshotcontext', selectedByUser: true,
    entries: [{ id: selectionId + '-note', title: 'Selected note', summary: value.note,
      observedAtMs: exportedAtMs, timeBasis: 'handoff-export' }],
  } };
}

export const SCREENSHOT_CONTEXT_HANDOFF_LIMIT = MAX_HANDOFF_BYTES;
