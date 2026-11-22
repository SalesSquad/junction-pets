import {canonical, exact, fail, freeze, hashJson, isHash, jsonCopy, sha256, text} from './json.mjs';
/** Source byte pins are consistency roots supplied by the host, not authentication. */
function validateMetadata(metadata) {
  const m = jsonCopy(metadata);
  exact(m, ['filename', 'mediaType', 'adapter', 'units', 'frame', 'rights'], 'source metadata');
  text(m.filename, 'filename', 120);
  text(m.mediaType, 'media type', 100);
  exact(m.adapter, ['id', 'version'], 'adapter');
  text(m.adapter.id, 'adapter ID'); text(m.adapter.version, 'adapter version');
  if (m.units !== null) {
    exact(m.units, ['label', 'toMetres'], 'units');
    text(m.units.label, 'unit label', 40);
    if (m.units.toMetres !== null && (!Number.isFinite(m.units.toMetres) || m.units.toMetres <= 0)) fail('INVALID_UNITS', 'Invalid metric scale.');
  }
  if (m.frame !== null) text(m.frame, 'declared frame ID', 100);
  exact(m.rights, ['kind', 'attribution'], 'rights');
  if (!['synthetic', 'user_supplied', 'licensed', 'unknown'].includes(m.rights.kind) || typeof m.rights.attribution !== 'string' || m.rights.attribution.length > 1000) fail('INVALID_RIGHTS', 'Rights must be explicitly declared.');
  return m;
}
export async function admitSource(input, metadata, {expectedSha256 = null} = {}) {
  if (!(input instanceof Uint8Array) || input.length > 16 * 1024 * 1024) fail('INVALID_BYTES', 'Source exceeds 16 MiB.');
  const bytes = new Uint8Array(input), m = validateMetadata(metadata);
  const hash = await sha256(bytes);
  if (expectedSha256 !== null && (!isHash(expectedSha256) || expectedSha256 !== hash)) fail('TRUSTED_PIN_MISMATCH', 'Source differs from the separately supplied pin.');
  return freeze({schema: 'evidence-kit.source/v1', sha256: hash, sizeBytes: bytes.length, ...m});
}
export async function createDataset(source, entities) {
  const s = jsonCopy(source), rows = jsonCopy(entities);
  exact(s, ['schema', 'sha256', 'sizeBytes', 'filename', 'mediaType', 'adapter', 'units', 'frame', 'rights'], 'source');
  if (s.schema !== 'evidence-kit.source/v1' || !isHash(s.sha256) || !Number.isSafeInteger(s.sizeBytes) || s.sizeBytes < 0 || s.sizeBytes > 16 * 1024 * 1024) fail('INVALID_SOURCE', 'Invalid source descriptor.');
  const {schema, sha256: sourceHash, sizeBytes, ...metadata} = s;
  validateMetadata(metadata);
  if (!Array.isArray(rows) || !rows.length || rows.length > 5000) fail('RESOURCE_EXHAUSTED', 'Use 1–5,000 normalized entities.');
  const ids = new Set();
  for (const row of rows) {
    exact(row, ['id', 'kind', 'locator', 'data'], 'entity');
    text(row.id, 'entity ID', 100); text(row.kind, 'entity kind', 80);
    if (ids.has(row.id)) fail('DUPLICATE_ID', 'Duplicate source entity ID.');
    ids.add(row.id);
    if (!row.locator || typeof row.locator !== 'object' || Array.isArray(row.locator) || !row.data || typeof row.data !== 'object' || Array.isArray(row.data)) fail('INVALID_ENTITY', 'Locator and data must be objects.');
  }
  const generation = await hashJson({source: s, entities: rows});
  const records = new Map();
  for (const row of rows) records.set(row.id, {row, recordSha256: await hashJson(row)});
  const manifest = freeze({schema: 'evidence-kit.dataset/v1', source: s, generation, entityCount: rows.length});
  return Object.freeze({
    manifest: () => manifest,
    entities: () => freeze(jsonCopy(rows)),
    ref(id) {
      const record = records.get(id);
      if (!record) fail('NOT_FOUND', `Unknown source entity ${id}.`);
      return freeze({sourceSha256: s.sha256, generation, id, recordSha256: record.recordSha256});
    },
    resolve(reference) {
      const ref = jsonCopy(reference);
      exact(ref, ['sourceSha256', 'generation', 'id', 'recordSha256'], 'reference');
      if (ref.sourceSha256 !== s.sha256 || ref.generation !== generation) fail('STALE_SOURCE', 'Reference belongs to another source or extraction generation.');
      const record = records.get(ref.id);
      if (!record || ref.recordSha256 !== record.recordSha256) fail('INVALID_REFERENCE', 'Reference does not resolve to the canonical source record.');
      return freeze(jsonCopy(record.row));
    },
    snapshot: () => freeze({manifest, entities: jsonCopy(rows)})
  });
}
export async function restoreDataset(snapshot) {
  const s = jsonCopy(snapshot);
  exact(s, ['manifest', 'entities'], 'dataset snapshot');
  const dataset = await createDataset(s.manifest.source, s.entities);
  if (canonical(dataset.manifest()) !== canonical(s.manifest)) fail('INVALID_GENERATION', 'Dataset generation mismatch.');
  return dataset;
}
