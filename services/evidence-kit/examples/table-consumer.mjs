import {csvAdapter} from '../adapters/csv.mjs';
import {sumCells} from '../methods/table.mjs';
export const tableQuery = Object.freeze({valueIds: ['r2c2', 'r3c2'], unitIds: ['r2c3', 'r3c3'], expectedUnit: 'EUR', statedTotalId: 'r4c2', statedUnitId: 'r4c3'});
export async function tableConsumer(bytes) {
  const dataset = await csvAdapter.ingest(bytes, {filename: 'costs.csv', rights: {kind: 'synthetic', attribution: 'Evidence Kit CC0 fixtures'}});
  return {dataset, claim: await sumCells(dataset, tableQuery)};
}
