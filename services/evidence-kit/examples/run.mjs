import {readFile} from 'node:fs/promises';
import {createReview, exportPacket, openPacket, replayPacket, preserveStoaV1} from '../src/index.mjs';
import {drawingConsumer} from './drawing-consumer.mjs';
import {tableConsumer, tableQuery} from './table-consumer.mjs';
import {csvAdapter} from '../adapters/csv.mjs';
import {sumCells} from '../methods/table.mjs';
const drawing = await drawingConsumer(await readFile(new URL('../fixtures/room.dxf', import.meta.url)));
const bytes = await readFile(new URL('../fixtures/costs.csv', import.meta.url));
const table = await tableConsumer(bytes);
const review = await createReview(table.dataset, table.claim);
await review.apply({id: 'example-confirm', expectedHead: review.snapshot().head, kind: 'confirm', reviewer: 'Synthetic example reviewer', note: 'Example declaration only.', value: null, refs: []});
const packet = await exportPacket(table.dataset, table.claim, review);
const opened = await openPacket(JSON.parse(JSON.stringify(packet)), {sourceBytes: bytes});
const replayed = await replayPacket(packet, {bytes, adapter: csvAdapter, run: d => sumCells(d, tableQuery)});
console.log(JSON.stringify({drawing: drawing.claim.value, table: table.claim.value, packetIntegrity: opened.verification.integrity,
  replay: replayed.status, review: replayed.review.snapshot().current.status,
  sourceAuthenticity: opened.verification.authenticity, externalRequests: 0}, null, 2));
const legacy = await preserveStoaV1(JSON.parse(await readFile(new URL('../fixtures/legacy-stoa-v1.json', import.meta.url),'utf8')));
const freshReview = await createReview(drawing.dataset, drawing.claim);
const migrated = await exportPacket(drawing.dataset, drawing.claim, freshReview, {historical:[legacy]});
console.log(JSON.stringify({legacySchema: legacy.originalSchema, preservedReview: legacy.original.payload.review.current.status,
  currentReview: migrated.payload.review.current, migration: 'historical retained; fresh review required'},null,2));
