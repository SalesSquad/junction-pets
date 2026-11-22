import {dxfAdapter} from '../adapters/dxf.mjs';
import {measureRoom} from '../methods/drawing.mjs';
export async function drawingConsumer(bytes) {
  const dataset = await dxfAdapter.ingest(bytes, {filename: 'room.dxf', frame: 'synthetic-plan-A', rights: {kind: 'synthetic', attribution: 'Evidence Kit CC0 fixtures'}});
  return {dataset, claim: await measureRoom(dataset, {roomNumber: '2.01'})};
}
