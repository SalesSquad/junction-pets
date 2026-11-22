import {admitSource, createDataset} from '../src/dataset.mjs';
import {decode, fail} from '../src/json.mjs';
/** RFC4180-style comma CSV: quoted commas/newlines and escaped quotes; no locale guessing. */
export function parseCsv(text) {
  const rows = [], row = [];
  let value = '', quoted = false, closed = false, fieldStarted = false;
  const field = () => { row.push(value); value = ''; quoted = false; closed = false; fieldStarted = false; };
  const endRow = () => { field(); rows.push(row.splice(0)); };
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') { value += '"'; i++; }
      else if (char === '"') { quoted = false; closed = true; }
      else value += char;
    } else if (char === ',') field();
    else if (char === '\n' || char === '\r') { endRow(); if (char === '\r' && text[i + 1] === '\n') i++; }
    else if (char === '"' && !fieldStarted) { quoted = true; fieldStarted = true; }
    else {
      if (closed || char === '"') fail('INVALID_CSV', 'Unexpected text after a quoted field or unescaped quote.');
      value += char; fieldStarted = true;
    }
    if (value.length > 32768 || row.length > 100 || rows.length > 1000) fail('RESOURCE_EXHAUSTED', 'CSV row/cell budget exceeded.');
  }
  if (quoted) fail('INVALID_CSV', 'Unterminated CSV quotation.');
  if (fieldStarted || value || row.length || closed) endRow();
  if (!rows.length || !rows[0].length || rows[0].some(s => !s.trim()) || new Set(rows[0]).size !== rows[0].length) fail('INVALID_CSV', 'Headers must be nonempty and unique.');
  if (rows.some(r => r.length !== rows[0].length)) fail('INVALID_CSV', 'Every record must have the header column count.');
  if (rows.length * rows[0].length > 5000) fail('RESOURCE_EXHAUSTED', 'CSV exceeds 5,000 cells.');
  return rows;
}
export const csvAdapter = Object.freeze({
  id: 'comma-csv', version: '1.0.0',
  capabilities: Object.freeze(['source-cell-locators', 'quoted-records', 'literal-values']),
  limitations: Object.freeze(['No formulas, XLSX, automatic locale or currency conversion.', 'Row numbers identify logical CSV records, not physical line numbers.']),
  async ingest(input, {filename = 'table.csv', frame = null, expectedSha256 = null, rights = {kind: 'unknown', attribution: ''}} = {}) {
    if (!(input instanceof Uint8Array) || input.length > 2 * 1024 * 1024) fail('RESOURCE_EXHAUSTED', 'CSV exceeds 2 MiB.');
    const bytes = new Uint8Array(input), rows = parseCsv(decode(bytes).replace(/^\uFEFF/, ''));
    const source = await admitSource(bytes, {filename, mediaType: 'text/csv', adapter: {id: 'comma-csv', version: '1.0.0'}, units: null, frame, rights}, {expectedSha256});
    return createDataset(source, rows.flatMap((r, ri) => r.map((value, ci) => ({
      id: `r${ri + 1}c${ci + 1}`, kind: 'csv-cell', locator: {kind: 'csv-cell', record: ri + 1, column: ci + 1, header: rows[0][ci]},
      data: {value, header: ri === 0}
    }))));
  }
});
