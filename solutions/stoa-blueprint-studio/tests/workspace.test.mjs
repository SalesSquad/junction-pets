import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { makeDemo } from '../src/demo.mjs';
import { answerDrawingV2 } from '../src/quantities.mjs';
import { sourceRevision, digest, evidencePacket, verifyPacket } from '../src/evidence.mjs';
import { createReviewStore } from '../src/review.mjs';
import { compareSources } from '../src/revisions.mjs';
import { assign } from '../src/assignment.mjs';
import { instanceMetrics } from '../benchmark/instances.mjs';
import { createServer } from '../src/server.mjs';
const SHA='a'.repeat(64),OTH='b'.repeat(64);
const source=()=>makeDemo();
function setup(){const d=source(),q='What is the area of room A-101?',r={id:'answer-1',question:q,sourceRevision:sourceRevision(d),result:answerDrawingV2(d,q)};return {d,r,store:createReviewStore(d,r)};}
const command=(d,revision,kind,extra={})=>({operationId:`operation_${revision}_${kind}`,expectedRevision:revision,sourceRevision:sourceRevision(d),kind,reviewer:'Local engineer',...extra});

test('human corrections retain the engine answer, enforce source/revision, and undo/redo idempotently',()=>{
  const {d,r,store}=setup(),original=r.result.answer,entityId=r.result.evidence[0].entityId;
  const correct=command(d,0,'correct',{answer:'13.70 m²',entityIds:[entityId],note:'Manual review'});
  const first=store.apply(correct);assert.equal(first.current.answer,'13.70 m²');assert.equal(r.result.answer,original);
  assert.equal(store.apply(correct).revision,1);
  assert.throws(()=>store.apply({...correct,answer:'99'}),/already used/);
  assert.throws(()=>store.apply(command(d,0,'confirm',{note:''})),/changed/);
  assert.throws(()=>store.apply({...command(d,1,'undo'),sourceRevision:OTH}),/different source/);
  assert.equal(store.apply(command(d,1,'undo')).current,null);
  assert.equal(store.apply(command(d,2,'redo')).current.answer,'13.70 m²');
  assert.equal(store.snapshot().independentVerification,false);
  assert.throws(()=>store.apply(command(d,3,'correct',{answer:'5',entityIds:['forged-id'],note:''})),/current source/);
  assert.equal(store.snapshot().revision,3);
});

test('export resolves original source entities and detects byte tampering without claiming authenticity',()=>{
  const {d,r,store}=setup(),packet=evidencePacket(d,r,{sha256:SHA,files:{}},store.snapshot());
  assert.equal(packet.payload.evidence.length,3);assert.equal(verifyPacket(packet).authenticity,'not-verified');
  const changed=structuredClone(packet);changed.payload.result.answer='999 m²';assert.throws(()=>verifyPacket(changed),/mismatch/);
  assert.throws(()=>evidencePacket({...d,sha256:OTH},r,{sha256:SHA},store.snapshot()),/Stale/);
  const fake={...r,result:{...r.result,evidence:[{entityId:'forged',kind:'TEXT'}]}};assert.throws(()=>evidencePacket(d,fake,{},store.snapshot()),/does not resolve/);
});

test('evidence levels distinguish source observation, derived heuristics and cross-checked areas',()=>{
  const {d,r}=setup();assert.equal(r.result.evidenceLevel,'cross_checked');
  assert.equal(answerDrawingV2(d,'How many rooms labelled Stanza?').evidenceLevel,'source_observed');
  assert.equal(answerDrawingV2(d,'How many toilets are there?').evidenceLevel,'unavailable');
});

function roomDrawing(width=4){return {id:'d',filename:'synthetic.dxf',format:'ASCII DXF',units:6,unitsLabel:'meters',entities:[
  {id:'p',type:'LWPOLYLINE',layer:'ROOM_OUTLINE',closed:true,points:[{x:0,y:0},{x:width,y:0},{x:width,y:3},{x:0,y:3}]},
  {id:'n',type:'TEXT',layer:'ROOM_TEXT',x:1,y:1,text:'2.01'},
  {id:'a',type:'TEXT',layer:'ROOM_TEXT',x:2,y:2,text:`${width*3} m²`}]};}
test('room revisions require declared alignment and supported units, and expose invalid area evidence',()=>{
  const a=roomDrawing(),b=roomDrawing(5),options={alignmentDeclared:true};
  const r=compareSources(a,b,options).payload;assert.equal(r.changes[0].areaDelta,3);assert.equal(r.changes[0].status,'area_changed');assert.equal(r.physicalChangeVerified,false);
  assert.throws(()=>compareSources(a,b),/origin/);assert.throws(()=>compareSources({...a,units:0},b,options),/units/);
  b.entities[2].text='999 m²';assert.equal(compareSources(a,b,options).payload.changes[0].status,'incomparable');
});

test('IFC revision comparison uses GUIDs rather than unstable STEP IDs, preserving ambiguity',()=>{
  const a={filename:'a.ifc',format:'IFC STEP',sha256:SHA,unitsLabel:'SI',entities:[{id:'#20',guid:'guid-1',sourceText:'IFCSPACE(record A)'}]};
  const b={...a,sha256:OTH,entities:[{id:'#300',guid:'guid-1',sourceText:'IFCSPACE(record B)'}]};
  const r=compareSources(a,b,{mode:'ifc'}).payload.changes[0];assert.equal(r.status,'record_changed');assert.equal(r.afterId,'#300');
  b.entities.push({...b.entities[0],id:'#301'});assert.equal(compareSources(a,b,{mode:'ifc'}).payload.changes[0].status,'ambiguous');
});

test('assignment beats a greedy choice, preserves unmatched ties, and fails work budgets explicitly',()=>{
  const r=assign(['a','b'],['x','y'],[{oldId:'a',newId:'x',cost:.1},{oldId:'a',newId:'y',cost:.2},{oldId:'b',newId:'x',cost:.15}]);
  assert.deepEqual(r.pairs.map(p=>[p.oldId,p.newId]),[['a','y'],['b','x']]);
  assert.equal(assign(['a'],['x'],[{oldId:'a',newId:'x',cost:2}]).pairs.length,0);
  assert.throws(()=>assign(['a','b'],['x','y'],[{oldId:'a',newId:'x',cost:0},{oldId:'a',newId:'y',cost:0},{oldId:'b',newId:'x',cost:0}],{maxComponent:3}),/budget/);
});

test('assignment agrees with exhaustive independent optima on small finite cost graphs',()=>{
  let seed=17;const random=()=>((seed=(seed*1664525+1013904223)>>>0)/2**32);
  for(let trial=0;trial<80;trial++){
    const n=3,old=['a','b','c'],next=['x','y','z'],edges=[];
    for(const o of old)for(const v of next)if(random()<.6)edges.push({oldId:o,newId:v,cost:Math.floor(random()*30)/10});
    const cost=new Map(edges.map(e=>[e.oldId+e.newId,e.cost]));
    const brute=(i,used)=>{if(i===n)return n-used.size;let best=1+brute(i+1,used);for(const v of next)if(!used.has(v)&&cost.has(old[i]+v)){const s=new Set(used);s.add(v);best=Math.min(best,cost.get(old[i]+v)+brute(i+1,s));}return best;};
    const r=assign(old,next,edges),actual=r.pairs.reduce((s,p)=>s+p.cost,0)+r.unmatchedOld.length+r.unmatchedNew.length;
    assert.ok(Math.abs(actual-brute(0,new Set()))<1e-9);
  }
});

test('instance metrics expose merged/split objects even when total count agrees',()=>{
  const r=instanceMetrics({sourceSha256:SHA,truthSourceSha256:SHA,truth:[['a','b'],['c','d']],predicted:[['a','c'],['b','d']]});
  assert.equal(r.truthInstances,r.predictedInstances);assert.equal(r.mergedPredictions,2);assert.equal(r.splitTruthInstances,2);assert.equal(r.matchedInstances,0);
  assert.throws(()=>instanceMetrics({sourceSha256:SHA,truthSourceSha256:OTH,truth:[],predicted:[]}),/same source/);
  assert.throws(()=>instanceMetrics({sourceSha256:SHA,truthSourceSha256:SHA,truth:[['a'],['a']],predicted:[]}),/overlapping/);
});

test('HTTP canonical export, review conflict, restoration and source comparison use actual stored answers',async t=>{
  const server=createServer();server.listen(0,'127.0.0.1');await once(server,'listening');t.after(()=>new Promise(resolve=>server.close(resolve)));
  const base=`http://127.0.0.1:${server.address().port}`;
  const post=async(path,input)=>{const response=await fetch(base+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input)});return {status:response.status,...await response.json()};};
  const d=(await(await fetch(base+'/api/demo')).json()).drawing;
  const asked=await post('/api/ask',{drawingId:'demo',question:'What is the area of room A-101?'});assert.equal(asked.result.evidenceLevel,'cross_checked');
  const id={drawingId:'demo',answerId:asked.answerId};
  const c=command(d,0,'correct',{answer:'13.70 m²',entityIds:[asked.result.evidence[0].entityId],note:'Manual correction'});
  assert.equal((await post('/api/review',{...id,command:c})).review.revision,1);
  assert.equal((await post('/api/review',{...id,command:command(d,0,'confirm',{note:''})})).status,409);
  assert.equal((await post('/api/export-evidence',{...id,expectedReviewRevision:0})).status,409);
  const exported=await post('/api/export-evidence',{...id,expectedReviewRevision:1});assert.equal(verifyPacket(exported.packet).integrity,'matched');
  const restored=await post('/api/restore-review',{drawingId:'demo',packet:exported.packet});assert.equal(restored.review.current.answer,'13.70 m²');assert.equal(restored.result.answer,'13.69 m²');
  const tampered=structuredClone(exported.packet);tampered.payload.review.events[0].state.answer='forged';assert.equal((await post('/api/restore-review',{drawingId:'demo',packet:tampered})).status,422);
  const stale=structuredClone(exported.packet);stale.payload.engine.sha256=OTH;stale.integrity.sha256=digest(stale.payload);assert.equal((await post('/api/restore-review',{drawingId:'demo',packet:stale})).status,409);
  const compared=await post('/api/compare',{beforeId:'demo',afterId:'demo',options:{mode:'rooms',alignmentDeclared:true}});assert.equal(compared.comparison.payload.summary.unchanged,6);assert.equal(compared.comparison.payload.engine.sha256,asked.result.provenance.engineSha256);assert.equal(digest(compared.comparison.payload),compared.comparison.integrity.sha256);
});
