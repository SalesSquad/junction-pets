import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {canonical, createClaim, createReview, exportPacket, hashJson, openPacket, preserveStoaV1, replayPacket, restoreReview, sha256, compareRecords, assign} from '../src/index.mjs';
import {csvAdapter, parseCsv} from '../adapters/csv.mjs';
import {dxfAdapter} from '../adapters/dxf.mjs';
import {sumCells} from '../methods/table.mjs';
import {measureRoom} from '../methods/drawing.mjs';
import {tableConsumer, tableQuery} from '../examples/table-consumer.mjs';
import {drawingConsumer} from '../examples/drawing-consumer.mjs';
import {applyStudioReview} from '../components/workspace-studio.mjs';
import {benchmark} from '../benchmark/run.mjs';
const bytes = name => readFile(new URL('../fixtures/' + name, import.meta.url));
async function setup() { const b = await bytes('costs.csv'); const r = await tableConsumer(b); return {...r, bytes: b, review: await createReview(r.dataset, r.claim)}; }
function command(review, kind, rest = {}) { return {id: crypto.randomUUID(), expectedHead: review.snapshot().head, kind, reviewer: 'Synthetic reviewer', note: '', value: null, refs: [], ...rest}; }

test('strict canonical JSON is portable and never executes getters or erases invalid data', () => {
  assert.equal(canonical({b: 1, a: ' '}), '{"a":" ","b":1}');
  let touched = false;
  const getter = Object.defineProperty({}, 'x', {enumerable: true, get() {touched = true; return 1;}});
  for (const invalid of [getter, {a: undefined}, {a: NaN}, {a: Infinity}, {a: 1n}, [,1], Object.assign([1], {extra: true}), {a:'\ud800'}]) assert.throws(() => canonical(invalid));
  assert.equal(touched, false);
  const cycle = {}; cycle.self = cycle; assert.throws(() => canonical(cycle));
});

test('source pin, extraction generation, record hashes and immutability prevent stale citations', async () => {
  const r = await setup(), reference = r.dataset.ref('r2c2');
  assert.equal(r.dataset.resolve(reference).data.value, '10.10');
  assert.throws(() => r.dataset.resolve({...reference, recordSha256: 'a'.repeat(64)}), /canonical/);
  const next = await tableConsumer(await bytes('costs-revised.csv'));
  assert.throws(() => next.dataset.resolve(reference), /another source/);
  await assert.rejects(csvAdapter.ingest(r.bytes, {expectedSha256: 'a'.repeat(64)}), /pin/);
  assert.throws(() => {r.dataset.entities()[0].data.value = 'forged';}, TypeError);
  assert.equal(r.dataset.resolve(reference).data.value, '10.10');
});

test('CSV parser preserves quoted commas, escaped quotes, multiline and whitespace fields', () => {
  assert.deepEqual(parseCsv('name,note\r\n"a,b","line1\nline2"\r\n"a""b", \r\n'), [['name','note'],['a,b','line1\nline2'],['a"b',' ']]);
  for (const invalid of ['a,a\n1,2\n', 'a,b\n1\n', 'a,b\n"unterminated,2', 'a,b\n"closed"extra,2', 'a,b\nna"me,2']) assert.throws(() => parseCsv(invalid));
});

test('table totals use exact decimal arithmetic and reject unit mismatch, formula and missing values', async () => {
  const r = await setup(); assert.equal(r.claim.value, '30.30 EUR'); assert.equal(r.claim.level, 'cross_checked');
  const derived = await sumCells(r.dataset, {...tableQuery, statedTotalId: null, statedUnitId: null});
  assert.equal(derived.value, r.claim.value); assert.equal(derived.level, 'derived');
  for (const file of ['costs-mixed.csv','costs-missing.csv','costs-conflict.csv','costs-locale.csv','costs-formula.csv','costs-wrong-total-unit.csv']) {
    const {claim} = await tableConsumer(await bytes(file)); assert.equal(claim.status, 'abstained', file); assert.deepEqual(claim.refs, []);
  }
  await assert.rejects(sumCells(r.dataset, {...tableQuery, valueIds: ['r2c2','r2c2']}), /unique/);
  await assert.rejects(sumCells(r.dataset, {...tableQuery, expectedUnit: ' '}), /explicit unit/);
  await assert.rejects(sumCells(r.dataset, {...tableQuery, statedUnitId: null}), /own source unit/);
});

test('drawing adapter retains native handles, verifies area, and abstains on unsafe evidence', async () => {
  const r = await drawingConsumer(await bytes('room.dxf')); assert.equal(r.claim.value, '12.00 m²');
  assert.equal(r.dataset.resolve(r.claim.refs[0]).locator.handle, 'A1');
  for (const file of ['room-open.dxf','room-unknown-units.dxf','room-conflict.dxf','room-duplicate.dxf','room-curved.dxf','room-missing.dxf']) {
    const {claim} = await drawingConsumer(await bytes(file)); assert.equal(claim.status, 'abstained', file);
  }
  const input = await bytes('room.dxf');
  await assert.rejects(dxfAdapter.ingest(new TextEncoder().encode(new TextDecoder().decode(input)+'999\n')), /Incomplete/);
});

test('claims reject fabricated, duplicate and cross-generation evidence', async () => {
  const r = await setup(); const {schema, generation, claimSha256, ...spec} = r.claim;
  await assert.rejects(createClaim(r.dataset, {...spec, refs: [spec.refs[0], spec.refs[0]]}), /Duplicate/);
  await assert.rejects(createClaim(r.dataset, {...spec, refs: [{...spec.refs[0], generation: 'b'.repeat(64)}]}), /another source/);
  await assert.rejects(createClaim(r.dataset, {...spec, status: 'abstained', level: 'unavailable', value: null}), /fabricated/);
});

test('review history is immutable, source-bound, conflict checked and serializes competing async edits', async () => {
  const r = await setup(); const c = command(r.review, 'confirm');
  const [one, two] = await Promise.allSettled([r.review.apply(c), r.review.apply({...c, id: 'competing'})]);
  assert.equal(one.status, 'fulfilled'); assert.equal(two.status, 'rejected');
  assert.equal((await r.review.apply(c)).events.length, 1);
  await assert.rejects(r.review.apply({...c, note: 'changed content'}), /different content/);
  await r.review.apply(command(r.review, 'correct', {value: '31.00 EUR', refs: [r.dataset.ref('r2c2')]}));
  assert.equal(r.claim.value, '30.30 EUR'); assert.equal(r.review.snapshot().current.value, '31.00 EUR');
  await r.review.apply(command(r.review, 'undo')); assert.equal(r.review.snapshot().current.status, 'confirmed');
  await r.review.apply(command(r.review, 'redo')); assert.equal(r.review.snapshot().current.value, '31.00 EUR');
  const restored = await restoreReview(r.dataset, r.claim, JSON.parse(JSON.stringify(r.review.snapshot())));
  assert.deepEqual(restored.snapshot(), r.review.snapshot());
  const altered = JSON.parse(JSON.stringify(r.review.snapshot())); altered.events[0].after.reviewer = 'forged';
  await assert.rejects(restoreReview(r.dataset, r.claim, altered), /altered/);
});

test('packet consistency, external pins, raw source checks and independent extraction replay are separate', async () => {
  const r = await setup(); await r.review.apply(command(r.review, 'confirm'));
  const packet = await exportPacket(r.dataset, r.claim, r.review);
  const opened = await openPacket(JSON.parse(JSON.stringify(packet)), {expectedPacketSha256: packet.integrity.sha256, sourceBytes: r.bytes});
  assert.equal(opened.verification.trustedPinMatched, true); assert.equal(opened.verification.extractionReplayed, false);
  const replay = await replayPacket(packet, {bytes: r.bytes, adapter: csvAdapter, run: d => sumCells(d, tableQuery)});
  assert.equal(replay.status, 'replayed'); assert.equal(replay.review.snapshot().current.status, 'confirmed');
  const tampered = JSON.parse(JSON.stringify(packet)); tampered.payload.claim.value = '999.00 EUR';
  await assert.rejects(openPacket(tampered), /digest mismatch/);
  tampered.integrity.sha256 = await hashJson(tampered.payload);
  await assert.rejects(openPacket(tampered), /Claim digest/);
  await assert.rejects(openPacket(packet, {expectedPacketSha256: 'a'.repeat(64)}), /pin/);
  await assert.rejects(openPacket(packet, {sourceBytes: await bytes('costs-revised.csv')}), /source bytes differ/);
});

test('a changed method result retains old review as history and requires explicit new review', async () => {
  const r = await setup(); await r.review.apply(command(r.review, 'confirm'));
  const packet = await exportPacket(r.dataset, r.claim, r.review);
  const replay = await replayPacket(packet, {bytes: r.bytes, adapter: csvAdapter, run: d => sumCells(d, {...tableQuery, statedTotalId: null, statedUnitId: null})});
  assert.equal(replay.status, 'revalidation_required'); assert.equal(replay.review, null);
  assert.equal(replay.historical.review.snapshot().current.status, 'confirmed');
  assert.equal((await createReview(replay.dataset, replay.claim)).snapshot().current, null);
  await assert.rejects(restoreReview(replay.dataset, replay.claim, r.review.snapshot()), /different source or result/);
});

test('Studio submissions cannot set their own source, claim, evidence or review head', async () => {
  const r = await setup(), input = {sourceGeneration: r.dataset.manifest().generation, claimSha256: r.claim.claimSha256,
    operationId: 'studio-confirm', expectedHead: r.review.snapshot().head, kind: 'confirm', reviewer: 'Synthetic Studio reviewer', note: ''};
  await assert.rejects(applyStudioReview(r, {...input, sourceGeneration: 'a'.repeat(64)}), /another source/);
  assert.equal((await applyStudioReview(r, input)).current.status, 'confirmed');
});

test('revision comparison preserves duplicate-key ambiguity and requires declared geometry alignment', async () => {
  const a = await dxfAdapter.ingest(await bytes('room.dxf'), {frame:'test-frame'});
  const b = await dxfAdapter.ingest(await bytes('room-revised.dxf'), {frame:'test-frame'});
  const opts = {key: e => e.locator.handle, geometry:true, alignmentDeclared:true};
  const report = await compareRecords(a,b,opts); assert.equal(report.rows.filter(r => r.status === 'changed').length, 2);
  await assert.rejects(compareRecords(a,b,{...opts,alignmentDeclared:false}), /matching frames/);
  assert.equal((await compareRecords(a,b,{key: () => 'duplicate'})).rows[0].status,'ambiguous');
});

test('bounded assignment chooses a global optimum rather than a greedy first hit', () => {
  const result = assign(['a','b'],['x','y'],[{oldId:'a',newId:'x',cost:.1},{oldId:'a',newId:'y',cost:.2},{oldId:'b',newId:'x',cost:.15}]);
  assert.deepEqual(result.pairs.map(p => [p.oldId,p.newId]), [['a','y'],['b','x']]);
  assert.equal(assign(['a'],['x'],[{oldId:'a',newId:'x',cost:2}]).pairs.length,0);
});

test('frozen two-domain benchmark retains negative cases and exact citation expectations', async () => {
  const result = await benchmark(); assert.equal(result.correctContracts, result.cases); assert.equal(result.cases,18);
  assert.equal(result.externalRequests,0); assert.equal(result.realDataQualified,false); assert.ok(result.abstained > result.supported);
});

test('DXF room measurement refuses ambiguous or malformed geometry and signed annotations', async () => {
  const original = (await bytes('room.dxf')).toString();
  const ingest = source => dxfAdapter.ingest(Buffer.from(source));
  await assert.rejects(ingest(original.replace('20\n0\n', '')), /missing its Y coordinate/);
  for (const modified of [
    original.replace('12 m²', '-12 m²'),
    original.replace('12 m²', 'approx. 12 m²'),
    original.replace('70\n1\n', '70\n1\n210\n1\n'),
    original.replace('10\n1\n20\n1\n', '10\n0\n20\n1\n'),
  ]) {
    assert.equal((await measureRoom(await ingest(modified), {roomNumber: '2.01'})).status, 'abstained');
  }
  const offset = original.replace(/^(10|20)\n(\d+)$/gm, (_, group, value) => group + '\n' + (Number(value) + 1e8));
  assert.equal((await measureRoom(await ingest(offset), {roomNumber: '2.01'})).value, '12.00 m²');
});

test('replay requires original bytes, an adapter bound to those bytes and a valid claim', async () => {
  const fixture = await setup();
  const packet = await exportPacket(fixture.dataset, fixture.claim, fixture.review);
  const run = dataset => sumCells(dataset, tableQuery);
  await assert.rejects(replayPacket(packet, {bytes: null, adapter: csvAdapter, run}), /original source bytes/);
  const other = await csvAdapter.ingest(Buffer.from('label,value\na,1'));
  const adapter = {...csvAdapter, ingest: async () => other};
  await assert.rejects(replayPacket(packet, {bytes: fixture.bytes, adapter, run}), /different source/);
  await assert.rejects(replayPacket(packet, {bytes: fixture.bytes, adapter: csvAdapter,
    run: async () => ({...fixture.claim, value: 'fabricated'})}), /digest/i);
});
