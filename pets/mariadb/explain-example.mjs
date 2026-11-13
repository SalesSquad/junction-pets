// Offline authored data only. No SQL runner, parser, connection or runtime adapter.
export const example = {
  provenance: 'offline-synthetic-authored',
  format: 'EXPLAIN EXTENDED',
  query: "SELECT sku, quantity FROM inventory WHERE warehouse_id = 7 AND quantity < 5",
  row: { table: 'inventory', type: 'ALL', possible_keys: ['idx_warehouse'], key: null,
    rows: 10000, filtered: 2, Extra: 'Using where' },
};

const own = (value, key) => Object.hasOwn(value, key);
function shape(value, allowed) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).some(key => !allowed.includes(key))) throw Error('unsupported data shape');
}
function count(value, percentage = false) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 ||
      (percentage && value > 100)) throw Error('invalid numeric evidence');
}

/** Classify supplied fields, never authenticate them or infer a real execution.
 * Deliberately limited to one table, numeric counters and no rowid-filter notation.
 * Null/missing runtime counters remain unknown; zero is an observation.
 */
export function inspectEvidence(input) {
  shape(input, ['provenance', 'format', 'query', 'row']);
  if (input.provenance !== 'offline-synthetic-authored' ||
      !['EXPLAIN', 'EXPLAIN EXTENDED', 'ANALYZE'].includes(input.format) ||
      typeof input.query !== 'string' || !input.query.trim()) throw Error('unsupported provenance or format');
  const row = input.row;
  shape(row, ['table', 'type', 'possible_keys', 'key', 'rows', 'filtered', 'Extra', 'r_rows', 'r_filtered']);
  if (typeof row.table !== 'string' || !row.table || typeof row.type !== 'string' ||
      typeof row.Extra !== 'string' || !Array.isArray(row.possible_keys) ||
      row.possible_keys.some(key => typeof key !== 'string' || !key) ||
      !(row.key === null || (typeof row.key === 'string' && row.key))) throw Error('invalid plan fields');
  count(row.rows);
  const facts = {};
  for (const field of ['table', 'type', 'possible_keys', 'key', 'Extra']) {
    facts[field] = { kind: 'supplied-plan', value: structuredClone(row[field]) };
  }
  facts.rows = { kind: 'estimate', value: row.rows };
  for (const field of ['filtered', 'r_rows', 'r_filtered']) {
    const runtime = field.startsWith('r_');
    if (runtime && own(row, field) && input.format !== 'ANALYZE') throw Error('runtime counter requires ANALYZE fixture');
    if (!own(row, field) || row[field] === null) {
      facts[field] = { kind: 'unknown', value: null };
    } else {
      count(row[field], field.endsWith('filtered'));
      facts[field] = { kind: runtime ? 'supplied-observation' : 'estimate', value: row[field] };
    }
  }
  return { provenance: input.provenance, facts,
    executionVerified: false, indexGain: { kind: 'unknown', value: null } };
}

// Read only own data descriptors: never evaluate claim getters or toJSON hooks.
function claimData(claim) {
  if (!claim || typeof claim !== 'object' ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(claim))) throw Error('unsupported claim record');
  const keys = Reflect.ownKeys(claim);
  if (keys.length !== 3 || keys.some(key => !['field', 'kind', 'value'].includes(key))) throw Error('unsupported claim shape');
  const descriptors = Object.getOwnPropertyDescriptors(claim);
  if (keys.some(key => !own(descriptors[key], 'value'))) throw Error('claim accessors are unsupported');
  return { field: descriptors.field.value, kind: descriptors.kind.value, value: descriptors.value.value };
}

function exactDataValue(expected, actual) {
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual) || Object.getPrototypeOf(actual) !== Array.prototype) return false;
    const descriptors = Object.getOwnPropertyDescriptors(actual);
    const keys = Reflect.ownKeys(descriptors);
    if (descriptors.length.value !== expected.length || keys.length !== expected.length + 1) return false;
    for (let index = 0; index < expected.length; index++) {
      const descriptor = descriptors[index];
      if (!descriptor || !own(descriptor, 'value') || typeof descriptor.value !== 'string' ||
          descriptor.value !== expected[index]) return false;
    }
    return true;
  }
  if (actual !== null && !['string', 'number'].includes(typeof actual)) return false;
  if (typeof actual === 'number' && !Number.isFinite(actual)) return false;
  return Object.is(expected, actual);
}

/** Structured claims only, not a natural-language truth detector. Fail closed.
 * A caller can claim an exact classified field; gain/execution are unsupported.
 */
export function checkClaim(input, claim) {
  const evidence = inspectEvidence(input);
  const data = claimData(claim);
  if (typeof data.field !== 'string' || typeof data.kind !== 'string' || !own(evidence.facts, data.field)) return false;
  const fact = evidence.facts[data.field];
  return fact.kind === data.kind && exactDataValue(fact.value, data.value);
}
