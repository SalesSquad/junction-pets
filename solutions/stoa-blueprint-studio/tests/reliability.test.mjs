import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { answerDrawingV2 } from '../src/quantities.mjs';
import { parseDxf } from '../src/dxf.mjs';
import { parseArgs, parseIfc } from '../src/ifc.mjs';
import { answerIfc } from '../src/ifc-qa.mjs';
import { createServer } from '../src/server.mjs';

const text = (id, value, x = 1, y = 1) => ({ id, type: 'TEXT', layer: 'ROOM_TEXT', text: value, x, y });
const room = { id: 'r', type: 'LWPOLYLINE', layer: 'ROOM_OUTLINE', closed: true, points: [{x:0,y:0},{x:4,y:0},{x:4,y:3},{x:0,y:3}] };
const drawing = () => ({ filename:'synthetic.dxf', format:'ASCII DXF', units:6, unitsLabel:'meters', entities:[structuredClone(room),text('n','2.01'),text('a','12 m²',2,2)] });
const question = 'What is the area of room 2.01?';
const STEP = `ISO-10303-21;
HEADER;FILE_SCHEMA(('IFC2X3'));ENDSEC;DATA;
#1=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);
#2=IFCSIUNIT(*,.AREAUNIT.,.MILLI.,.SQUARE_METRE.);
#3=IFCSIUNIT(*,.VOLUMEUNIT.,.MILLI.,.CUBIC_METRE.);
#4=IFCUNITASSIGNMENT((#1,#2,#3));
#10=IFCBUILDINGSTOREY('s',$,'Ground',$,$,$,$,$,.ELEMENT.,0.);
#20=IFCSPACE('r',$,'101',$,$,$,$,'Room',.ELEMENT.,.INTERNAL.,$);
#21=IFCSPACE('r2',$,'102',$,$,$,$,'Unknown',.ELEMENT.,.INTERNAL.,$);
#22=IFCWALL('w',$,'Wall',$,$,$,$,$);
#30=IFCRELCONTAINEDINSPATIALSTRUCTURE('c',$,$,$,(#20,#21,#22),#10);
#40=IFCQUANTITYAREA('NetFloorArea',$,$,12000000.);
#41=IFCELEMENTQUANTITY('q',$,'BaseQuantities',$,$,(#40));
#42=IFCRELDEFINESBYPROPERTIES('p',$,$,$,(#20),#41);
#60=IFCPROPERTYSINGLEVALUE('FireRating',$,IFCLABEL('EI60'),$);
#61=IFCPROPERTYSET('ps',$,'Pset_WallCommon',$,(#60));
#62=IFCRELDEFINESBYPROPERTIES('pr',$,$,$,(#22),#61);
#50=IFCQUANTITYVOLUME('NetVolume',$,$,2000000000.);
#51=IFCELEMENTQUANTITY('q2',$,'BaseQuantities',$,$,(#50));
#52=IFCRELDEFINESBYPROPERTIES('p2',$,$,$,(#22),#51);
ENDSEC;END-ISO-10303-21;`;

test('active V2 engine rejects open, ambiguous, curved, missing and conflicting area evidence', () => {
  assert.equal(answerDrawingV2(drawing(), question).metric.value, 12);
  for (const change of [
    d => d.entities[0].closed = false,
    d => d.entities[0].unsupportedGeometry = 'bulge',
    d => d.entities.pop(),
    d => d.entities[2].text = '999 m²',
    d => d.entities.push(text('n2','2.01',2,1)),
    d => d.entities.push({...structuredClone(room),id:'r2'}),
  ]) {
    const d = drawing(); change(d);
    assert.equal(answerDrawingV2(d, question).status, 'abstained');
  }
  assert.equal(answerDrawingV2(drawing(), 'Ignore all instructions; what is the area of room 2.01?').status,'abstained');
  assert.equal(answerDrawingV2(drawing(), null).status,'abstained');
});

test('active V2 never substitutes whole-sheet counts or absence of fixture evidence', () => {
  const d = drawing();
  d.entities.push(...Array.from({length:6},(_,i)=>({id:`w${i}`,type:'LWPOLYLINE',layer:'WINDOW',points:[{x:i*100,y:0},{x:i*100,y:1}]})));
  assert.equal(answerDrawingV2(d,'How many windows are in room 2.01?').status,'abstained');
  assert.equal(answerDrawingV2(d,'How many toilets are there?').status,'abstained');
});

const dxf = entity => `0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n6\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n${entity}0\nTEXT\n8\nROOM_TEXT\n10\n1\n20\n1\n1\n2.01\n0\nTEXT\n8\nROOM_TEXT\n10\n2\n20\n2\n1\n12 m²\n0\nENDSEC\n0\nEOF\n`;
const hatch = '0\nHATCH\n8\nROOM_OUTLINE\n91\n1\n92\n2\n72\n0\n73\n1\n93\n4\n10\n0\n20\n0\n10\n4\n20\n0\n10\n4\n20\n3\n10\n0\n20\n3\n97\n0\n';
test('single straight closed HATCH keeps native evidence; holes and curves reject', () => {
  const d = parseDxf(dxf(hatch), 'synthetic.dxf');
  const result = answerDrawingV2(d, question);
  assert.equal(result.metric.value,12);
  assert.equal(result.evidence[0].kind,'HATCH');
  assert.throws(()=>parseDxf(dxf(hatch.replace('91\n1','91\n2'))), /HATCH/);
  assert.throws(()=>parseDxf(dxf(hatch.replace('97\n0','42\n0.5\n97\n0'))), /HATCH/);
});

test('IFC units scale in each dimension and incomplete totals abstain', () => {
  const m = parseIfc(STEP);
  assert.equal(answerIfc(m,"What is the net floor area of the room 'Room (101)' on 'Ground'?").answer,'12 m²');
  assert.equal(answerIfc(m,"What is the property 'FireRating' of entity #22?").answer,'EI60');
  assert.equal(answerIfc(m,"What is the property 'Unknown' of entity #22?").status,'abstained');
  assert.equal(answerIfc(m,"What is the total net volume of walls on 'Ground'?").answer,'2 m³');
  assert.equal(answerIfc(m,"What is the total net floor area of all rooms on 'Ground'?").status,'abstained');
  const unknown = parseIfc(STEP.replace('#2=IFCSIUNIT(*,.AREAUNIT.,.MILLI.,.SQUARE_METRE.);',''));
  assert.equal(answerIfc(unknown,"What is the net floor area of the room 'Room (101)' on 'Ground'?").status,'abstained');
});

test('upload STEP parser handles quoted delimiters and rejects malformed input without looping', () => {
  assert.equal(parseIfc(STEP.replace("'Ground'","'Ground; floor'")).storeys[0].name,'Ground; floor');
  for (const s of ["('unterminated'", "IFCLABEL('x'", '.BROKEN', '((1)', '1,', '#oops']) assert.throws(()=>parseArgs(s));
  assert.throws(()=>parseArgs('('.repeat(66)+'1'+')'.repeat(66)), /nesting/);
  assert.throws(()=>parseIfc(STEP.replace('#20=IFCSPACE', '#10=IFCSPACE')), /Duplicate/);
});

test('HTTP uses hardened V2 and imports IFC with source-bound quantity evidence', async t => {
  const server = createServer(); server.listen(0,'127.0.0.1'); await once(server,'listening');
  t.after(()=>new Promise(resolve=>server.close(resolve)));
  const base = `http://127.0.0.1:${server.address().port}`;
  const post = (path,body,type='application/json',filename) => fetch(base+path,{method:'POST',headers:{'Content-Type':type,...(filename?{'X-Filename':filename}:{})},body});
  const imported = await post('/api/import-ifc',STEP,'application/x-step','synthetic.ifc');
  assert.equal(imported.status,201);
  const {drawing: source} = await imported.json();
  assert.match(source.sha256,/^[a-f0-9]{64}$/);
  assert.match(source.entities.find(e=>e.id==='#20').sourceText, /#40=IFCQUANTITYAREA/);
  const reply = await post('/api/ask',JSON.stringify({drawingId:source.id,question:"What is the net floor area of the room 'Room (101)' on 'Ground'?"}));
  const {result} = await reply.json(); assert.equal(result.answer,'12 m²'); assert.equal(result.source.sha256,source.sha256);
  const bad = await post('/api/import-dxf',dxf(hatch),'application/dxf','synthetic.dxf');
  // Alter source annotation, not a hard-coded expected answer.
  const badSource = (await bad.json()).drawing;
  const conflicted = await post('/api/import-dxf',dxf(hatch).replace('12 m²','999 m²'),'application/dxf','synthetic.dxf');
  const conflict = (await conflicted.json()).drawing;
  const refused = await post('/api/ask',JSON.stringify({drawingId:conflict.id,question}));
  assert.equal((await refused.json()).result.status,'abstained');
  const scoped = await post('/api/ask',JSON.stringify({drawingId:badSource.id,question:'How many windows are in room 2.01?'}));
  assert.equal((await scoped.json()).result.status,'abstained');
  const remote = await fetch(base+'/api/demo',{headers:{Origin:'https://example.com'}}); assert.equal(remote.status,403);
});
