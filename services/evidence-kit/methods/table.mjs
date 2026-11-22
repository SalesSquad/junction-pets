import {createClaim} from '../src/claim.mjs';
import {fail} from '../src/json.mjs';
function decimal(value) {
  if (!/^-?\d{1,12}(?:\.\d{1,6})?$/.test(value)) return null;
  const negative = value.startsWith('-'), [whole, fraction = ''] = value.replace(/^-/, '').split('.');
  return {number: BigInt(whole + fraction) * (negative ? -1n : 1n), places: fraction.length};
}
const scale = (d, places) => d.number * 10n ** BigInt(places - d.places);
function format(value, places) {
  const negative = value < 0, digits = (negative ? -value : value).toString().padStart(places + 1, '0');
  return (negative ? '-' : '') + (places ? digits.slice(0, -places) + '.' + digits.slice(-places) : digits);
}
export async function sumCells(dataset, {valueIds, unitIds, expectedUnit, statedTotalId = null, statedUnitId = null}) {
  if (dataset.manifest().source.adapter.id !== 'comma-csv') fail('WRONG_ADAPTER', 'Cell totals require the CSV adapter.');
  if (!Array.isArray(valueIds) || !valueIds.length || valueIds.length > 500 || new Set(valueIds).size !== valueIds.length ||
      !Array.isArray(unitIds) || unitIds.length !== valueIds.length || new Set(unitIds).size !== unitIds.length || typeof expectedUnit !== 'string' || !expectedUnit.trim() || expectedUnit.length > 30) fail('INVALID_QUERY', 'Use unique value/unit cell pairs and an explicit unit.');
  if (!!statedTotalId !== !!statedUnitId) fail('INVALID_QUERY', 'A stated total needs its own source unit cell.');
  if (valueIds.some(id => unitIds.includes(id)) || valueIds.includes(statedTotalId) || unitIds.includes(statedTotalId)) fail('INVALID_QUERY', 'Value, unit and independently stated total cells must be distinct.');
  const ids = [...valueIds, ...unitIds, ...(statedTotalId ? [statedTotalId, statedUnitId] : [])];
  if (new Set(ids).size !== ids.length) fail('INVALID_QUERY', 'Source cells cannot be counted twice.');
  const cells = ids.map(id => dataset.resolve(dataset.ref(id)));
  if (cells.some(c => c.kind !== 'csv-cell' || c.data.header)) fail('INVALID_QUERY', 'Use data cells, not headers.');
  for (let i = 0; i < valueIds.length; i++) {
    if (cells[i].locator.record !== cells[valueIds.length + i].locator.record) fail('INVALID_QUERY', 'Each value and its unit must belong to the same source record.');
  }
  const spec = {method: {id: 'decimal-cell-total', version: '1.0.0', parameters: {valueIds, unitIds, expectedUnit, statedTotalId, statedUnitId}},
    question: `Sum of ${valueIds.length} source cells in ${expectedUnit}`, status: 'abstained', level: 'unavailable', value: null, refs: [], checks: [], reason: ''};
  const abstain = reason => createClaim(dataset, {...spec, reason});
  if (cells.slice(valueIds.length, valueIds.length * 2).some(c => c.data.value !== expectedUnit)) return abstain('Missing, mixed or unexpected units; no conversion is inferred.');
  if (statedTotalId && (cells.at(-1).data.value !== expectedUnit || cells.at(-2).locator.record !== cells.at(-1).locator.record)) return abstain('Stated total has a missing, mixed or mismatched source unit.');
  const values = cells.slice(0, valueIds.length).map(c => decimal(c.data.value));
  const stated = statedTotalId ? decimal(cells.at(-2).data.value) : null;
  if (values.some(v => !v) || (statedTotalId && !stated)) return abstain('Missing or ambiguous decimal value; formulas and locale guessing are unsupported.');
  const places = Math.max(...values.map(v => v.places), stated?.places ?? 0);
  const total = values.reduce((s, v) => s + scale(v, places), 0n);
  if (stated && total !== scale(stated, places)) return abstain('Source values disagree with the independently stated total.');
  return createClaim(dataset, {...spec, status: 'supported', level: stated ? 'cross_checked' : 'derived',
    value: `${format(total, places)} ${expectedUnit}`, refs: ids.map(id => dataset.ref(id)),
    checks: [{kind: 'exact-decimal-sum', terms: values.length, unit: expectedUnit, statedTotalChecked: !!stated}],
    reason: stated ? 'Exact decimal sum agrees with a separately cited source total.' : 'Exact sum of cited cells; no independent total was supplied.'});
}
