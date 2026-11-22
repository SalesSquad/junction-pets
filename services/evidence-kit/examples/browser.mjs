import '../components/review-element.mjs';
import {createReview, replayPacket} from '../src/index.mjs';
import {drawingConsumer} from './drawing-consumer.mjs';
import {tableConsumer, tableQuery} from './table-consumer.mjs';
import {dxfAdapter} from '../adapters/dxf.mjs';
import {csvAdapter} from '../adapters/csv.mjs';
import {measureRoom} from '../methods/drawing.mjs';
import {sumCells} from '../methods/table.mjs';
const widget = document.querySelector('evidence-review');
let version = 0;
async function bytes(name) {
  const response = await fetch('../fixtures/' + name);
  if (!response.ok) throw new Error('Fixture unavailable.');
  return new Uint8Array(await response.arrayBuffer());
}
async function show(name, consumer) {
  const request = ++version;
  try {
    const {dataset, claim} = await consumer(await bytes(name));
    const review = await createReview(dataset, claim);
    if (request !== version) return;
    widget.context = {dataset, claim, review};
    document.querySelector('#status').textContent = `${name} · ${claim.level} · ${claim.status}`;
  } catch (e) { if (request === version) document.querySelector('#status').textContent = e.message; }
}
for (const [id, name, consumer] of [['drawing','room.dxf',drawingConsumer],['table','costs.csv',tableConsumer],['changed','costs-revised.csv',tableConsumer],['conflict','costs-conflict.csv',tableConsumer]]) {
  document.querySelector('#' + id).addEventListener('click', () => show(name, consumer));
}
document.querySelector('#restore').addEventListener('change', async event => {
  const request = ++version;
  try {
    const file = event.target.files[0]; if (!file) return;
    if (file.size > 8 * 1024 * 1024) throw new Error('Packet exceeds 8 MiB.');
    const packet = JSON.parse(await file.text());
    const isDrawing = packet.payload?.dataset?.manifest?.source?.adapter?.id === dxfAdapter.id;
    const name = isDrawing ? 'room.dxf' : 'costs.csv';
    const replay = await replayPacket(packet, {bytes: await bytes(name), adapter: isDrawing ? dxfAdapter : csvAdapter,
      run: d => isDrawing ? measureRoom(d, {roomNumber:'2.01'}) : sumCells(d, tableQuery)});
    if (request !== version) return;
    widget.context = {dataset: replay.dataset, claim: replay.claim, review: replay.review ?? await createReview(replay.dataset, replay.claim)};
    document.querySelector('#status').textContent = `${replay.dataset.manifest().source.filename} · ${replay.claim.level} · ${replay.claim.status}`;
    document.querySelector('#restore-status').textContent = replay.status === 'replayed' ? 'Source extraction and claim replayed; historical review restored.' : 'Current result differs. Historical review preserved separately; a new review is required.';
  } catch (e) { if (request === version) document.querySelector('#restore-status').textContent = e.message; }
  finally { event.target.value = ''; }
});
show('room.dxf', drawingConsumer);
