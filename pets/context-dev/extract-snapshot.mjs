import {createHash} from 'node:crypto';

// Offline fictional snapshots only. Neither URLs nor instructions are executed.
const URLS = new Set([
  'https://paper-tern.invalid/public/product',
  'https://paper-tern.invalid/public/release-notes',
]);
const LABELS = [['title', 'Title: '], ['version', 'Version: '], ['summary', 'Summary: ']];
const shape = (value, keys) => value !== null && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
function timestamp(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value)) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) && new Date(ms).toISOString() === value ? ms : null;
}

/** Accept a bounded JSON string, not executable objects. See EXTRACTION.md. */
export function extractSnapshotFields(json) {
  const boundary = {fixtureOnly: true, sourceFetched: false, factVerified: false, providerExecuted: false, authorization: false};
  const reject = issue => ({...boundary, status: 'rejected', source: null, fields: [], issues: [issue]});
  if (typeof json !== 'string' || json.length > 32768) return reject('invalid-input');
  let input;
  try { input = JSON.parse(json); } catch { return reject('invalid-input'); }
  if (!shape(input, ['schemaVersion', 'mode', 'targetUrl', 'asOf', 'maxAgeSeconds', 'fields', 'source'])
    || input.schemaVersion !== 1 || input.mode !== 'fictional-only'
    || !Number.isSafeInteger(input.maxAgeSeconds) || input.maxAgeSeconds < 0 || input.maxAgeSeconds > 86400
    || !Array.isArray(input.fields) || input.fields.length < 1 || input.fields.length > 3
    || new Set(input.fields).size !== input.fields.length
    || input.fields.some(field => !LABELS.some(([allowed]) => field === allowed))) return reject('invalid-input');
  if (!URLS.has(input.targetUrl)) return reject('disallowed-target');
  const source = input.source;
  if (source === null) return reject('missing-source-evidence');
  if (!shape(source, ['url', 'observedAt', 'visibility', 'text'])) return reject('invalid-input');
  if (source.url !== input.targetUrl) return reject('source-mismatch');
  if (source.visibility !== 'public') return reject('non-public-source');
  if (typeof source.text !== 'string' || source.text.length > 8192 || !source.text.isWellFormed()
    || /\r(?!\n)/.test(source.text)) return reject('invalid-input');
  if (!source.text.trim()) return reject('missing-source-evidence');
  const lines = source.text.split('\n');
  if (lines.length > 128) return reject('invalid-input');
  const asOf = timestamp(input.asOf), observedAt = timestamp(source.observedAt);
  if (asOf === null || observedAt === null) return reject('invalid-time');
  const ageMs = asOf - observedAt;
  if (ageMs < 0) return reject('future-source');
  if (ageMs > input.maxAgeSeconds * 1000) return reject('stale-source');

  const fields = LABELS.filter(([field]) => input.fields.includes(field)).map(([field, label]) => {
    const evidence = [];
    let offset = 0;
    lines.forEach((raw, index) => {
      const line = raw.endsWith('\r') ? raw.slice(0, -1) : raw;
      if (line.startsWith(label)) {
        const start = offset + label.length, end = offset + line.length;
        evidence.push({start, end, line: index + 1, quote: source.text.slice(start, end)});
      }
      offset += raw.length + 1;
    });
    const reason = evidence.length === 0 ? 'missing-field'
      : evidence.length > 1 ? 'ambiguous-field'
        : evidence[0].quote.trim() === '' ? 'blank-field' : null;
    return {field, state: reason ? 'unknown' : 'known', value: reason ? null : evidence[0].quote, reason, evidence};
  });
  return {
    ...boundary,
    status: fields.some(field => field.state === 'unknown') ? 'needs-review' : 'extracted',
    source: {url: source.url, observedAt: source.observedAt, asOf: input.asOf, ageMs,
      snapshotSha256: createHash('sha256').update(source.text, 'utf8').digest('hex')},
    fields,
    issues: [],
  };
}
