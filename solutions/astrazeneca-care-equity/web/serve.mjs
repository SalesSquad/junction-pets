import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {applySecondReader} from './scribe-demo.mjs';
const web=fileURLToPath(new URL('./',import.meta.url)), root=path.dirname(web);
const ROOT_DATA=new Set(['/data/planner/plans-v1.json','/data/scribe/demo/demo-notes.json','/data/scribe/demo/demo-outputs.json']);
const csp="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'";
// POST /api/scribe helper. One persistent local CPU process (serve/demo/worker.py: Gemma 3 270M + LoRA adapter, then the
// frozen date resolver), started on the first request and reused; the precomputed SYNTHETIC demo outputs in
// data/scribe/demo/ are the fallback. Nothing leaves this computer. A person confirms every event.
// Env: SAMA_SCRIBE_LIVE=0 (precomputed only), SAMA_SCRIBE_PRELOAD=1 (start the process with the server, so the first
// request does not wait for the model to load), SAMA_SCRIBE_PYTHON, SAMA_SCRIBE_WORKER, SAMA_SCRIBE_TIMEOUT_MS.
const scribe={ready:null,pending:new Map(),seq:0,failedAt:0,error:null,data:null};
function scribeWorker(){
 if(scribe.ready)return scribe.ready;
 if(process.env.SAMA_SCRIBE_LIVE==='0')return Promise.reject(new Error('live scribe switched off (SAMA_SCRIBE_LIVE=0)'));
 if(Date.now()-scribe.failedAt<60000)return Promise.reject(new Error(`live scribe failed less than a minute ago: ${scribe.error}`));
 scribe.ready=(async()=>{
  const {spawn}=await import('node:child_process'), {createInterface}=await import('node:readline');
  const proc=spawn(process.env.SAMA_SCRIBE_PYTHON||path.join(root,'serve','.venv','bin','python'),[process.env.SAMA_SCRIBE_WORKER||path.join(root,'serve','demo','worker.py')],{cwd:root,stdio:['pipe','pipe','ignore'],env:{...process.env,HF_HUB_OFFLINE:'1'}});
  return await new Promise((resolve,reject)=>{
   let started=false;
   const fail=(e)=>{clearTimeout(timer);if(scribe.proc!==proc&&started)return;scribe.failedAt=Date.now();scribe.error=e.message;scribe.ready=null;scribe.proc=null;for(const [id,w] of scribe.pending){clearTimeout(w.timer);w.reject(e);scribe.pending.delete(id);}if(!started)reject(e);try{proc.kill();}catch{}};
   const timer=setTimeout(()=>fail(new Error('live scribe did not start within 180 s')),180000);
   scribe.proc=proc;proc.on('error',fail);proc.on('exit',(code)=>fail(new Error(`live scribe process exited (${code})`)));proc.stdin.on('error',()=>{});
   createInterface({input:proc.stdout}).on('line',(line)=>{
    let msg;try{msg=JSON.parse(line);}catch{return;}
    if(!started){clearTimeout(timer);if(msg.event==='ready'){started=true;resolve({proc,provenance:msg.provenance});}else fail(new Error(msg.error||'live scribe failed to start'));return;}
    const w=scribe.pending.get(msg.id);if(!w)return;scribe.pending.delete(msg.id);clearTimeout(w.timer);msg.ok?w.resolve(msg.result):w.reject(Object.assign(new Error(msg.error||'live scribe error'),{badInput:msg.input_error===true}));
   });
  });
 })();
 return scribe.ready;
}
async function scribeLive(note){
 const {proc}=await scribeWorker(), id=`r${++scribe.seq}`;
 return await new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{scribe.pending.delete(id);reject(new Error('live scribe timed out'));},Number(process.env.SAMA_SCRIBE_TIMEOUT_MS||60000));
  scribe.pending.set(id,{resolve,reject,timer});proc.stdin.write(JSON.stringify({id,op:'extract',...note})+'\n');
 });
}
if(process.env.SAMA_SCRIBE_PRELOAD==='1')scribeWorker().catch(()=>{});
// Second reader: Nemotron 3.5 Super VL's stored v3 answers on the SYNTHETIC validation notes (data/scribe/nemotron/
// val-v3.jsonl). The page never calls a hosted model; free text and notes rewritten by code have no second answer, so
// they need editing (two-reader rule in web/scribe-demo.mjs applySecondReader, same as serve/demo/engine.py).
const SECOND_FILE='data/scribe/nemotron/val-v3.jsonl';
const SECOND_HOW='stored output: Nemotron 3.5 Super VL (reader v3) read this same SYNTHETIC validation note on the Verda-hosted endpoint before the demo was built; the page does not call it';
async function readSecond(){try{const m=new Map();for(const line of (await readFile(path.join(root,SECOND_FILE),'utf8')).split('\n'))if(line.trim()){const r=JSON.parse(line);m.set(r.id,r.prediction??null);}return m;}catch{return new Map();}}
const secondFor=(demo)=>demo&&!demo.rewritten_by_code&&scribe.data.second.has(demo.source_id)?{available:true,prediction:scribe.data.second.get(demo.source_id),how:SECOND_HOW,source:SECOND_FILE}:null;
async function scribeRoute(body){
 if(!body||typeof body!=='object'||Array.isArray(body))return [{error:'body must be a JSON object'},400];
 const mode=body.mode??'live';if(mode!=='live'&&mode!=='precomputed')return [{error:'mode must be "live" or "precomputed"'},400];
 if(!scribe.data){const read=(f)=>readFile(path.join(root,'data','scribe','demo',f),'utf8').then(JSON.parse).catch(()=>null);scribe.data={notes:await read('demo-notes.json'),outputs:await read('demo-outputs.json'),second:await readSecond()};}
 let note,demo=null;
 if(body.demo_id!==undefined){
  demo=typeof body.demo_id==='string'&&/^demo-\d{2}$/.test(body.demo_id)?(scribe.data.notes?.notes??[]).find((n)=>n.demo_id===body.demo_id):null;
  if(!demo)return [{error:'unknown demo_id'},404];
  note={note_text:demo.note_text,note_date:demo.note_date,note_id:demo.demo_id,synthetic:true};
 }else{
  const t=body.note_text,d=body.note_date;
  if(typeof t!=='string'||!t.trim()||t.length>6000)return [{error:'note_text must be a non-empty string of at most 6000 characters'},400];
  if(typeof d!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(d)||new Date(`${d}T00:00:00Z`).toISOString().slice(0,10)!==d)return [{error:'note_date must be a real date YYYY-MM-DD'},400];
  note={note_text:t,note_date:d,note_id:null,synthetic:null};
 }
 const stored=demo&&scribe.data.outputs?.results?.[demo.demo_id];
 const fallback=(reason)=>stored?[{served:'precomputed',fallback_reason:reason,person_confirms:'a person confirms every event',result:stored},200]:[{status:'UNAVAILABLE',error:reason,person_confirms:'a person confirms every event'},503];
 if(mode==='precomputed')return fallback('precomputed output requested');
 const started=Date.now();
 try{
  const result=applySecondReader(await scribeLive(note),secondFor(demo));
  if(demo){
   const same=(a,b)=>!!a&&!!b&&a.entry_route===b.entry_route&&a.events.length===b.events.length&&a.events.every((e,i)=>e.type===b.events[i].type&&e.date===b.events[i].date&&e.precision===b.events[i].precision);
   result.answer_key=demo.answer_key;result.exact_match_with_answer_key=same(result.resolved?.prediction,demo.answer_key);
   result.demo=Object.fromEntries(['demo_id','source_split','source_id','writer','kind','stratum','rewritten_by_code','rewrite_kind','rewrite'].map((k)=>[k,demo[k]]));
  }
  return [{served:'live',server_seconds:(Date.now()-started)/1000,person_confirms:'a person confirms every event',result},200];
 }catch(e){return e.badInput?[{error:e.message},400]:fallback(e.message);}
}
const server=http.createServer(async(req,res)=>{
 res.setHeader('Content-Security-Policy',csp);res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','no-referrer');
 const json=(x,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(x));};
 try{
 const url=new URL(req.url,'http://localhost'); const p=decodeURIComponent(url.pathname);
 if(p==='/api/health'&&req.method==='GET')return json({status:'OK'});
 if(p==='/api/verify-claims'&&req.method==='POST'){
 let size=0, chunks=[];for await(const chunk of req){size+=chunk.length;if(size>65536)return json({error:'Body too large'},413);chunks.push(chunk);}
 let body;try{body=JSON.parse(Buffer.concat(chunks));}catch{return json({error:'Invalid JSON'},400);}
 if(!Array.isArray(body.claims))return json({error:'claims must be an array'},400);
 try{const {verifyClaims}=await import('../src/claim-check.mjs');return json(await verifyClaims(body.claims));}catch{return json({status:'NOT_CONFIGURED',results:[]});}
 }
 if(p==='/api/scribe'&&req.method==='POST'){
 let size=0, chunks=[];for await(const chunk of req){size+=chunk.length;if(size>65536)return json({error:'Body too large'},413);chunks.push(chunk);}
 let body;try{body=JSON.parse(Buffer.concat(chunks));}catch{return json({error:'Invalid JSON'},400);}
 return json(...await scribeRoute(body));
 }
 if(req.method!=='GET'&&req.method!=='HEAD')return json({error:'Method not allowed'},405);
 if(p.includes('..')||p.includes('\\')||p.includes('\0'))return json({error:'Forbidden'},403);
 let base=web, relative=p==='/'?'index.html':p.slice(1);
 if(p.startsWith('/src/')){if(!/^\/src\/[\w-]+\.mjs$/.test(p))return json({error:'Forbidden'},403);base=root;}
 // /data/: an allowlist of the files the page reads. Other result files stay off the network (some carry local paths).
 if(p.startsWith('/data/')&&!['/data/app.json','/data/counties.geo.json'].includes(p)){if(!ROOT_DATA.has(p))return json({error:'Not found'},404);base=root;}
 const file=path.resolve(base,relative);if(!file.startsWith(base+path.sep)&&!file.startsWith(base))return json({error:'Forbidden'},403);
 const content=await readFile(file);res.writeHead(200,{'Content-Type':({'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.json':'application/json','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream'});res.end(req.method==='HEAD'?undefined:content);
 }catch(e){json({error:e.code==='ENOENT'?'Not found':'Request failed'},e.code==='ENOENT'?404:400);}
});
server.listen(Number(process.env.PORT||4179),'127.0.0.1',()=>console.log(`SAMA http://127.0.0.1:${server.address().port}`));
