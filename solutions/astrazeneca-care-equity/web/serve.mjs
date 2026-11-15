import http from 'node:http';
import {readFile,stat} from 'node:fs/promises';
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
// val-v3.jsonl). POST /api/scribe uses only these stored answers; free text and notes rewritten by code have no stored
// second answer, so they need editing (two-reader rule in web/scribe-demo.mjs applySecondReader, same as
// serve/demo/engine.py). POST /api/scribe/second (below) asks Nemotron live when a person presses the button.
const SECOND_FILE='data/scribe/nemotron/val-v3.jsonl';
const SECOND_HOW='stored output: Nemotron 3.5 Super VL (reader v3) read this same SYNTHETIC validation note on the Verda-hosted endpoint before the demo was built';
async function readSecond(){try{const m=new Map();for(const line of (await readFile(path.join(root,SECOND_FILE),'utf8')).split('\n'))if(line.trim()){const r=JSON.parse(line);m.set(r.id,r.prediction??null);}return m;}catch{return new Map();}}
const secondFor=(demo)=>demo&&!demo.rewritten_by_code&&scribe.data.second.has(demo.source_id)?{available:true,prediction:scribe.data.second.get(demo.source_id),how:SECOND_HOW,source:SECOND_FILE}:null;
async function loadScribeData(){
 const stamp=(await Promise.all([path.join(root,'data','scribe','demo','demo-notes.json'),path.join(root,'data','scribe','demo','demo-outputs.json'),path.join(root,SECOND_FILE)].map((f)=>stat(f).then((s)=>`${s.mtimeMs}:${s.size}`).catch(()=>'missing')))).join('|');
 if(!scribe.data||scribe.dataStamp!==stamp){const read=(f)=>readFile(path.join(root,'data','scribe','demo',f),'utf8').then(JSON.parse).catch(()=>null);scribe.data={notes:await read('demo-notes.json'),outputs:await read('demo-outputs.json'),second:await readSecond()};scribe.dataStamp=stamp;}
 return scribe.data;
}
async function scribeRoute(body){
 if(!body||typeof body!=='object'||Array.isArray(body))return [{error:'body must be a JSON object'},400];
 const mode=body.mode??'live';if(mode!=='live'&&mode!=='precomputed')return [{error:'mode must be "live" or "precomputed"'},400];
 // Reload the stored demo files whenever one of them changes on disk, so a server started before a data rebuild never
 // serves stale verdicts (no restart needed).
 await loadScribeData();
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
// POST /api/scribe/second {demo_id}: Nemotron 3.5 Super VL reads the selected SYNTHETIC demo note live, with the frozen
// reader protocol v3 (serve/demo/nemotron_live.py imports scribe/nemotron/reader.py read_note unchanged; code resolves
// the dates). One short-lived Python process per request, killed after SAMA_NEMOTRON_TIMEOUT_MS (45 s). The key stays
// in the server's environment: the helper reads it, nothing returns it. When the live call is off
// (SAMA_NEMOTRON_LIVE=0), has no key, no network, times out or fails, the stored v3 answer for the same note is
// returned (served:'stored'); a note rewritten by code has no stored answer (served:'none', HTTP 503). The page then
// applies the two-reader rule (applySecondReader) to the Gemma answer on screen. A person confirms every event.
// Env: SAMA_NEMOTRON_LIVE, SAMA_NEMOTRON_PYTHON (default python3), SAMA_NEMOTRON_HELPER, SAMA_NEMOTRON_TIMEOUT_MS,
// VERDA_INFERENCE_BASE_URL and VERDA_INFERENCE_KEY.
const NEMOTRON={model:'nemotron-3.5-super-vl',version:'v3',maxInFlight:2,inFlight:0};
const LIVE_HOW='live: Nemotron 3.5 Super VL (reader v3) read this SYNTHETIC note just now on the Verda-hosted endpoint';
async function nemotronLive(note){
 const {spawn}=await import('node:child_process');
 const ms=Number(process.env.SAMA_NEMOTRON_TIMEOUT_MS||45000);
 return await new Promise((resolve,reject)=>{
  const proc=spawn(process.env.SAMA_NEMOTRON_PYTHON||'python3',[process.env.SAMA_NEMOTRON_HELPER||path.join(root,'serve','demo','nemotron_live.py')],{cwd:root,stdio:['pipe','pipe','ignore'],env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
  let out='',done=false;
  const finish=(err,value)=>{if(done)return;done=true;clearTimeout(timer);try{proc.kill('SIGKILL');}catch{}err?reject(err):resolve(value);};
  const timer=setTimeout(()=>finish(new Error(`the live call did not finish within ${Math.round(ms/1000)} s`)),ms);
  proc.on('error',(e)=>finish(new Error(`the live reader could not start (${e.code||'error'})`)));
  proc.stdout.on('data',(d)=>{out+=d;if(out.length>200000)finish(new Error('the live reader wrote too much output'));});
  proc.on('close',(code)=>{
   let msg=null;try{msg=JSON.parse(out.trim().split('\n').pop()||'null');}catch{}
   if(!msg||typeof msg!=='object')return finish(new Error(`the live reader gave no answer (exit ${code})`));
   if(!msg.ok)return finish(new Error(typeof msg.error==='string'?msg.error.slice(0,200):'the live call failed'));
   finish(null,msg);
  });
  proc.stdin.on('error',()=>{});proc.stdin.end(JSON.stringify({...note,timeout_s:Math.max(1,ms/1000-3)}));
 });
}
async function secondRoute(body){
 if(!body||typeof body!=='object'||Array.isArray(body))return [{error:'body must be a JSON object'},400];
 const data=await loadScribeData();
 const demo=typeof body.demo_id==='string'&&/^demo-\d{2}$/.test(body.demo_id)?(data.notes?.notes??[]).find((n)=>n.demo_id===body.demo_id):null;
 if(!demo)return [{error:'unknown demo_id'},404];
 const stored=secondFor(demo), base={demo_id:demo.demo_id,model:NEMOTRON.model,version:NEMOTRON.version,synthetic:true,person_confirms:'a person confirms every event'};
 const fallback=(reason)=>stored
  ?[{...base,served:'stored',reason,prediction:stored.prediction,how:stored.how,source:stored.source},200]
  :[{...base,served:'none',reason:`${reason}; there is no stored second answer for this note (it was rewritten by code, so Nemotron did not read it before the demo was built), so it needs editing`,prediction:null},503];
 if(process.env.SAMA_NEMOTRON_LIVE==='0')return fallback('live Nemotron switched off (SAMA_NEMOTRON_LIVE=0)');
 if(!process.env.VERDA_INFERENCE_BASE_URL||!process.env.VERDA_INFERENCE_KEY)return fallback('no endpoint key in the server environment');
 if(NEMOTRON.inFlight>=NEMOTRON.maxInFlight)return fallback('another live call is still running');
 NEMOTRON.inFlight++;const started=Date.now();
 try{
  const m=await nemotronLive({note_text:demo.note_text,note_date:demo.note_date,id:demo.demo_id});
  return [{...base,served:'live',prediction:m.prediction??null,model:typeof m.model==='string'?m.model:NEMOTRON.model,latency_ms:Number.isFinite(m.latency_ms)?m.latency_ms:Date.now()-started,server_ms:Date.now()-started,calls:Number.isInteger(m.calls)?m.calls:null,flagged:m.flagged===true,how:LIVE_HOW,source:'Verda-hosted endpoint'},200];
 }catch(e){return fallback(e.message);}
 finally{NEMOTRON.inFlight--;}
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
 if(p==='/api/scribe/second'&&req.method==='POST'){
 let size=0, chunks=[];for await(const chunk of req){size+=chunk.length;if(size>4096)return json({error:'Body too large'},413);chunks.push(chunk);}
 let body;try{body=JSON.parse(Buffer.concat(chunks));}catch{return json({error:'Invalid JSON'},400);}
 return json(...await secondRoute(body));
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
