import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createReview, exportPacket, openPacket, preserveStoaV1} from '../src/index.mjs';
import {drawingConsumer} from '../examples/drawing-consumer.mjs';
test('a real Stoa v1 fixture keeps its old review without binding it to a new engine claim',async()=>{
  const original=JSON.parse(await readFile(new URL('../fixtures/legacy-stoa-v1.json',import.meta.url),'utf8'));
  const legacy=await preserveStoaV1(original);
  assert.equal(legacy.original.payload.review.current.status,'confirmed');
  const {dataset,claim}=await drawingConsumer(await readFile(new URL('../fixtures/room.dxf',import.meta.url)));
  assert.equal(legacy.sourceSha256,dataset.manifest().source.sha256);
  const review=await createReview(dataset,claim),packet=await exportPacket(dataset,claim,review,{historical:[legacy]});
  const loaded=await openPacket(JSON.parse(JSON.stringify(packet)));
  assert.equal(loaded.review.snapshot().current,null);
  assert.equal(loaded.historical[0].original.payload.review.current.status,'confirmed');
  assert.equal(loaded.historical[0].status,'historical_requires_revalidation');
  const changed=structuredClone(original);changed.payload.result.answer='999 m²';
  await assert.rejects(preserveStoaV1(changed),/integrity mismatch/);
});
