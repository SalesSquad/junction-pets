import { MAX_INPUT_BYTES, parseMeterDocument, reviewMeterDocument, syntheticMeterDocument } from './measurement.mjs';
const $ = id => document.getElementById(id);
function show(result) {
  $('meter-status').textContent = `${result.evidence} · ${result.status} · ${result.coverage}`;
  $('meter-caveat').textContent = result.caveat;
  for (const [id, kind] of [['meter-baseline', 'baseline'], ['meter-scenario', 'scenario'], ['meter-device', 'device']]) {
    $(id).textContent = `${result.totalsMWh[kind]} mWh`;
  }
  $('meter-net').textContent = `${result.netDifferenceMWh} mWh (${result.netDifferenceKWh.toFixed(6)} kWh)`;
  $('meter-coverage').textContent = `${result.intervalCount} paired intervals · ${result.windowEndMs - result.windowStartMs} ms · no gaps in supplied records`;
}
function error(message) {
  $('meter-status').textContent = 'REFUSED · no comparison';
  $('meter-caveat').textContent = message;
  for (const id of ['meter-baseline', 'meter-scenario', 'meter-device', 'meter-net', 'meter-coverage']) $(id).textContent = '—';
}
$('meter-demo').addEventListener('click', () => show(reviewMeterDocument(syntheticMeterDocument('positive'))));
$('meter-negative').addEventListener('click', () => show(reviewMeterDocument(syntheticMeterDocument('negative'))));
$('meter-file').addEventListener('change', async event => {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    if (file.size > MAX_INPUT_BYTES) throw Error('File exceeds 128 KiB');
    show(parseMeterDocument(await file.text()));
  } catch (cause) { error(cause.message); }
  finally { event.target.value = ''; }
});
error('Choose a synthetic example or a local JSON document; no readings are stored or transmitted.');
