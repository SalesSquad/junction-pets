import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {listenStudio,CSP} from './server.mjs';
import {Studio,seedValue,REASONS,MAX_BYTES} from './model.mjs';
import {plan,runBatch,replayBatch} from '../cell.mjs';
async function withServer(fn){const s=await listenStudio(0);try{await fn(s.address());}finally{await new Promise(resolve=>s.close(resolve));}}
function request(address,path='/',headers={},method='GET'){
  return new Promise((resolve,reject)=>{const req=http.request({host:'127.0.0.1',port:address.port,path,headers,method},res=>{let body='';res.setEncoding('utf8');res.on('data',chunk=>body+=chunk);res.on('end',()=>resolve({status:res.statusCode,headers:res.headers,body}));});req.on('error',reject);req.end();});
}
test('local HTTP serves exact assets, JavaScript MIME and strict CSP on loopback only',()=>withServer(async address=>{
  assert.equal(address.address,'127.0.0.1');
  for(const path of ['/','/index.html','/style.css','/app.mjs','/model.mjs','/cell.mjs','/core.mjs']){
    const r=await request(address,path);assert.equal(r.status,200,path);assert.equal(r.headers['content-security-policy'],CSP);assert.equal(r.headers['x-content-type-options'],'nosniff');assert.equal(r.headers['cache-control'],'no-store');
    if(path.endsWith('.mjs'))assert.equal(r.headers['content-type'],'text/javascript; charset=utf-8');
  }
  const head=await request(address,'/',{},'HEAD');assert.equal(head.status,200);assert.equal(head.body,'');
  assert.match(CSP,/connect-src 'none'/);assert.match(CSP,/form-action 'none'/);
}));
test('hostile Host, Origin and Fetch Metadata are refused by actual HTTP',()=>withServer(async address=>{
  for(const headers of [{Host:'evil.test'},{Host:`localhost:${address.port}`},{Host:`127.0.0.1:${address.port+1}`},{Origin:'https://evil.test'},{Origin:'null'},{'Sec-Fetch-Site':'cross-site'},{'Sec-Fetch-Site':'same-site'}])assert.equal((await request(address,'/',headers)).status,403);
  assert.equal((await request(address,'/',{Origin:`http://127.0.0.1:${address.port}`,'Sec-Fetch-Site':'same-origin'})).status,200);
}));
test('raw traversal, query variants, nonassets, POST and request bodies are refused',()=>withServer(async address=>{
  for(const path of ['/../core.mjs','/%2e%2e/core.mjs','//core.mjs','/style.css?x=1','/server.mjs','/studio.test.mjs','/README.md','/app.mjs/','/..%2fcore.mjs','/core.mjs%00','/favicon.ico'])assert.equal((await request(address,path)).status,404,path);
  for(const method of ['POST','PUT','DELETE','OPTIONS'])assert.equal((await request(address,'/',{},method)).status,405);
  assert.equal((await request(address,'/',{'Content-Length':'1'})).status,405);
}));
test('seed validation and eight-brick deterministic plan preserve policy/truth boundary',()=>{
  for(const v of ['0','330','4294967295'])assert.equal(seedValue(v),Number(v));
  for(const v of ['','-1','1.2','4294967296','1e3',' 1','NaN',330])assert.throws(()=>seedValue(v));
  const s=new Studio();assert.deepEqual(s.generate('330'),plan(330));assert.equal(s.request.episodes.length,8);assert.equal(JSON.stringify(s.request).includes('groundTruth'),false);
});
test('direct M2 run and replay preserve immutable results, holds, no placement and baseline',async()=>{
  const r=await runBatch(plan(330));assert.deepEqual(await replayBatch(r),r);assert.ok(Object.isFrozen(r.steps[0].data));
  assert.deepEqual(r.evaluation.rows.map(x=>x.conservative),['good','defect','hold','hold','hold','hold','stop','defect']);
  assert.equal(r.evaluation.conservative.coverage,3/8);assert.equal(r.evaluation.alwaysSortWithoutGate.unsafeSorted,5);
  const decisions=r.steps.filter(s=>s.stage==='operator-decision');for(const i of [3,4,5,6])assert.equal(decisions[i].data.coreReceipt.final.bowl,null);
  assert.equal(decisions[2].data.coreReceipt.final.bowl,'hold');
});
test('whole receipt, nested M1, evaluation and provenance tampering are refused without repair',async()=>{
  const receipt=await runBatch();
  for(const mutate of [r=>r.root='bad',r=>r.steps[3].data.coreReceipt.final.bowl='defect',r=>r.evaluation.rows[0].groundTruth='defect',r=>r.provenance.inference=true,r=>r.request.episodes[0].operator.reason='changed',r=>r.steps[0].data.slot++,r=>r.extra='untrusted']){
    const bad=structuredClone(receipt);mutate(bad);await assert.rejects(()=>replayBatch(bad));
    const s=new Studio();s.generate('330');await s.run();await assert.rejects(()=>s.importText(JSON.stringify(bad)));assert.equal(s.receipt,null);assert.equal(s.verified,false);assert.throws(()=>s.exportText());
  }
});
test('operator edits, seed changes and invalid imports clear export; explicit STOP remains terminal per episode',async()=>{
  const s=new Studio();s.generate('330');await s.run();const text=s.exportText();await s.importText(text);assert.equal(s.verified,true);
  s.edit(0,'stop',REASONS[3]);assert.equal(s.receipt,null);assert.throws(()=>s.exportText());await s.run();assert.equal(s.receipt.evaluation.rows[0].conservative,'stop');assert.equal(s.receipt.evaluation.rows[1].conservative,'defect');
  assert.throws(()=>s.edit(0,'continue',''));assert.throws(()=>s.exportText());
  await s.run();assert.throws(()=>s.generate('4294967296'));assert.equal(s.request,null);assert.throws(()=>s.exportText());
  for(const text of ['{broken', ' '.repeat(MAX_BYTES+1)]){await assert.rejects(()=>s.importText(text));assert.equal(s.verified,false);assert.equal(s.request,null);assert.throws(()=>s.exportText());}
});
test('edit during asynchronous run invalidates pending receipt and no stale export is accepted',async()=>{
  const s=new Studio();s.generate('0');const pending=s.run();s.edit(0,'stop',REASONS[1]);await assert.rejects(()=>pending,/changed/);assert.equal(s.verified,false);assert.throws(()=>s.exportText());
});
