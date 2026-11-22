import {admitSource, createDataset} from '../src/dataset.mjs';
import {decode, fail} from '../src/json.mjs';
import {parseDxf, DXF_LIMITS} from './dxf-parser.mjs';
export const dxfAdapter = Object.freeze({
  id: 'ascii-dxf', version: '1.1.0',
  capabilities: Object.freeze(['source-entity-locators', 'explicit-units', 'straight-room-boundaries']),
  limitations: Object.freeze(['No DWG, blocks/INSERT, OCR or IFC.', 'Ordinal IDs are scoped to exact source bytes, never persistent physical identities.']),
  async ingest(input, {filename = 'drawing.dxf', frame = null, expectedSha256 = null, rights = {kind: 'unknown', attribution: ''}} = {}) {
    if (!(input instanceof Uint8Array) || input.length > DXF_LIMITS.bytes) fail('RESOURCE_EXHAUSTED', 'DXF exceeds 6 MiB.');
    const bytes = new Uint8Array(input);
    const drawing = parseDxf(decode(bytes), filename);
    if (drawing.entities.length > 5000) fail('RESOURCE_EXHAUSTED', 'Portable adapter caps extraction at 5,000 entities.');
    const factor = {1: .0254, 2: .3048, 4: .001, 5: .01, 6: 1}[drawing.units] ?? null;
    const source = await admitSource(bytes, {filename, mediaType: 'application/dxf',
      adapter: {id: 'ascii-dxf', version: '1.1.0'}, units: {label: drawing.unitsLabel, toMetres: factor}, frame, rights}, {expectedSha256});
    return createDataset(source, drawing.entities.map((e, i) => ({id: e.id, kind: e.type,
      locator: {kind: 'dxf-entity', entityIndex: i + 1, handle: e.handle}, data: e})));
  }
});
