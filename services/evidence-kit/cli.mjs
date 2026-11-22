#!/usr/bin/env node
import {readFile, writeFile, stat} from 'node:fs/promises';
import {openPacket, replayPacket, preserveStoaV1, createReview, exportPacket} from './src/index.mjs';
import {csvAdapter} from './adapters/csv.mjs';
import {dxfAdapter} from './adapters/dxf.mjs';
import {sumCells} from './methods/table.mjs';
import {measureRoom} from './methods/drawing.mjs';
const args = process.argv.slice(2), [command, input, sourcePath] = args;
const option = name => { const index = args.indexOf(name); return index < 0 ? null : args[index + 1]; };
async function bounded(path, limit) {
  if (!path || !(await stat(path)).isFile() || (await stat(path)).size > limit) throw new Error('Input is missing, not a regular file or exceeds its byte budget.');
  const bytes = await readFile(path);
  if (bytes.length > limit) throw new Error('Input grew beyond its byte budget.');
  return bytes;
}
if (!['verify', 'replay', 'migrate-stoa'].includes(command) || !input) throw new Error('Usage: evidence-kit verify packet.json [source] | replay packet.json source [--output result.json] | migrate-stoa legacy.json source --room NUMBER --output result.json');
const packet = JSON.parse(await bounded(input, 8 * 1024 * 1024));
const bytes = sourcePath && !sourcePath.startsWith('--') ? new Uint8Array(await bounded(sourcePath, 16 * 1024 * 1024)) : null;
let output, report;
if (command === 'verify') {
  const result = await openPacket(packet, {sourceBytes: bytes});
  report = {...result.verification, source: result.dataset.manifest().source.sha256, claim: result.claim.claimSha256};
} else if (command === 'replay') {
  if (!bytes) throw new Error('Replay needs the original source file.');
  const adapter = packet.payload?.dataset?.manifest?.source?.adapter?.id === 'ascii-dxf' ? dxfAdapter : csvAdapter;
  const method = packet.payload?.claim?.method;
  const run = method?.id === 'room-area' ? d => measureRoom(d, method.parameters) : method?.id === 'decimal-cell-total' ? d => sumCells(d, method.parameters) : null;
  if (!run) throw new Error('No registered replay method.');
  const result = await replayPacket(packet, {bytes, adapter, run});
  const history = result.status === 'replayed' ? packet.payload.historical : [{schema:'evidence-kit.historical/v1', originalSchema:packet.payload.schema,
    originalPacketSha256:packet.integrity.sha256, original:packet, status:'historical_requires_revalidation', independentVerification:false}];
  output = await exportPacket(result.dataset, result.claim, result.review ?? await createReview(result.dataset, result.claim), {historical:history});
  report = {status:result.status, verification:result.verification, review:output.payload.review.current};
} else {
  if (!bytes || !option('--room')) throw new Error('Stoa migration needs original DXF bytes and an explicitly selected --room.');
  const historical = await preserveStoaV1(packet);
  if (!historical.sourceSha256) throw new Error('Legacy packet needs an original-file SHA-256 for migration.');
  const dataset = await dxfAdapter.ingest(bytes, {filename:packet.payload.source.filename, expectedSha256:historical.sourceSha256,
    rights:{kind:'user_supplied',attribution:'Original source rights remain applicable.'}});
  const claim = await measureRoom(dataset, {roomNumber:option('--room')});
  output = await exportPacket(dataset, claim, await createReview(dataset,claim), {historical:[historical]});
  report = {status:'migrated_with_historical_review', currentReview:null, currentValue:claim.value, historicalPacketSha256:historical.originalPacketSha256};
}
if (option('--output')) {
  if (!output) throw new Error('Verify does not rewrite packets.');
  await writeFile(option('--output'), JSON.stringify(output,null,2)+'\n', {flag:'wx',mode:0o600});
  report.output = option('--output');
}
console.log(JSON.stringify(report,null,2));
