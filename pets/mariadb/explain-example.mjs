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

/** Structured claims only, not a natural-language truth detector. Fail closed.
 * A caller can claim an exact classified field; gain/execution are unsupported.
 */
export function checkClaim(input, claim) {
  const evidence = inspectEvidence(input);
  shape(claim, ['field', 'kind', 'value']);
  if (Object.keys(claim).length !== 3 || !own(evidence.facts, claim.field)) return false;
  const fact = evidence.facts[claim.field];
  return fact.kind === claim.kind && JSON.stringify(fact.value) === JSON.stringify(claim.value);
}
