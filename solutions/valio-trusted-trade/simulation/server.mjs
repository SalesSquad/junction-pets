/** Explicit local simulation UI. Never mounted by the normal trade server. */
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { createHash, randomUUID } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createSimulationLab, scenarios } from './lab.mjs';

const directory = dirname(fileURLToPath(import.meta.url));
const solution = resolve(directory, '..');
const security = { 'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff',
  'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" };
const files = new Map([['/',['index.html','text/html; charset=utf-8']],['/app.js',['app.js','text/javascript; charset=utf-8']],['/style.css',['style.css','text/css; charset=utf-8']]]);
const readBody = request => new Promise((resolveBody,reject) => {
  const chunks=[]; let bytes=0,done=false;
  const finish=error=>{if(done)return;done=true;clearTimeout(timer);request.off('data',onData);request.off('end',onEnd);request.off('aborted',onAbort);request.off('error',onAbort);
    if(error){request.pause();reject(error);}else{try{const parsed=JSON.parse(Buffer.concat(chunks).toString('utf8'));if(!parsed||typeof parsed!=='object'||Array.isArray(parsed))throw Error();resolveBody(parsed);}catch{reject(Error('INVALID_REQUEST'));}}};
  const onData=chunk=>{bytes+=chunk.length;if(bytes>1024)return finish(Error('REQUEST_TOO_LARGE'));chunks.push(chunk);};
  const onEnd=()=>finish();const onAbort=()=>finish(Error('UPLOAD_ABORTED'));
  const timer=setTimeout(()=>finish(Error('UPLOAD_TIMEOUT')),3000);
  request.on('data',onData);request.once('end',onEnd);request.once('aborted',onAbort);request.once('error',onAbort);
});
async function sourceReceipt() {
  const command=spawnSync('git',['rev-parse','HEAD'],{cwd:solution,encoding:'utf8',timeout:2000});
  const commit=/^[a-f0-9]{40}$/.test(command.stdout?.trim()??'')?command.stdout.trim():null;
  const hashes={};
  for(const name of ['lab.mjs','server.mjs','index.html','app.js','style.css']) hashes['simulation/'+name]=createHash('sha256').update(await readFile(resolve(directory,name))).digest('hex');
  const status=spawnSync('git',['status','--porcelain','--','.'],{cwd:solution,encoding:'utf8',timeout:2000});
  return {commit,worktreeDirty:status.status!==0||Boolean(status.stdout?.trim()),filesSha256:hashes};
}
export async function createSimulationServer() {
  const source=await sourceReceipt();
  const lab=await createSimulationLab();
  let active=null;
  let state={mode:'LOCAL_SIMULATION',disclosure:'SCRIPTED_TEST_ACTORS_NO_REAL_ORDERS_OR_PAYMENTS',source,
    runId:null,busy:false,startedAt:null,completedAt:null,outcome:'NOT_RUN',results:[],scenarios,externalProviderCalls:0};
  const snapshot=()=>structuredClone(state);
  const run=async selected=>{
    state={...state,runId:randomUUID(),busy:true,startedAt:new Date().toISOString(),completedAt:null,outcome:'RUNNING',results:[]};
    try {
      for(const scenario of selected) {
        const result=await lab.runScenario(scenario.id);
        if(!result||!['PASS','FAIL'].includes(result.outcome)||result.scenarioId!==scenario.id||result.externalProviderCalls!==0)throw Error('INVALID_SIMULATION_RESULT');
        state.results.push(result);
      }
      state.outcome=state.results.every(result=>result.outcome==='PASS')?'PASS':'FAIL';
    } catch {
      state.outcome='FAIL';state.error='SIMULATION_EXECUTION_FAILED';
    } finally {state.busy=false;state.completedAt=new Date().toISOString();}
    return snapshot();
  };
  const server=createServer(async(request,response)=>{
    const send=(status,body,extra={})=>{if(response.destroyed)return;response.writeHead(status,{...security,'Content-Type':'application/json; charset=utf-8',...(status>=400&&request.method==='POST'?{Connection:'close'}:{}),...extra});response.end(JSON.stringify(body));};
    try {
      const host=request.headers.host??'';
      if(!/^(?:127\.0\.0\.1|localhost|\[::1\])(?::[0-9]{1,5})?$/.test(host))return send(403,{error:'LOOPBACK_ONLY'});
      if(request.headers.origin&&request.headers.origin!=='http://'+host)return send(403,{error:'ORIGIN_REFUSED'});
      const url=new URL(request.url??'/','http://'+host);
      if(url.search)return send(400,{error:'QUERY_REFUSED'});
      if(request.method==='GET'&&files.has(url.pathname)){
        const [name,type]=files.get(url.pathname),body=await readFile(resolve(directory,name));
        response.writeHead(200,{...security,'Content-Type':type});response.end(body);return;
      }
      if(request.method==='GET'&&url.pathname==='/api/simulation/status')return send(200,snapshot());
      if(request.method==='GET'&&url.pathname==='/api/simulation/report')return send(200,snapshot(),{'Content-Disposition':'attachment; filename="valio-local-simulation.json"'});
      if(request.method!=='POST'||url.pathname!=='/api/simulation/run')return send(404,{error:'NOT_FOUND'});
      if(request.headers.origin!=='http://'+host)return send(403,{error:'SAME_ORIGIN_REQUIRED'});
      if(!/^application\/json(?:\s*;|$)/i.test(request.headers['content-type']??''))return send(415,{error:'JSON_REQUIRED'});
      const body=await readBody(request);
      if(Object.keys(body).some(key=>key!=='scenario')||typeof body.scenario!=='string')return send(400,{error:'INVALID_SCENARIO'});
      const selected=body.scenario==='all'?scenarios:scenarios.filter(scenario=>scenario.id===body.scenario);
      if(selected.length===0)return send(400,{error:'INVALID_SCENARIO'});
      if(active)return send(409,{error:'SIMULATION_BUSY'});
      const promise=run(selected);active=promise;
      try {return send(200,await promise);} finally {if(active===promise)active=null;}
    } catch(error) {send(error.message==='REQUEST_TOO_LARGE'?413:['INVALID_REQUEST','UPLOAD_ABORTED','UPLOAD_TIMEOUT'].includes(error.message)?400:500,{error:'SIMULATION_REQUEST_REFUSED'});}
  });
  server.maxConnections=16;server.maxHeadersCount=24;server.requestTimeout=10000;server.headersTimeout=5000;server.keepAliveTimeout=1500;
  let closed=false;
  return {server,status:snapshot,async close(){if(closed)return;closed=true;if(active)await active.catch(()=>{});server.closeAllConnections();if(server.listening)await new Promise(resolveClose=>server.close(resolveClose));await lab.close();}};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const port=Number(process.env.VALIO_SIMULATION_PORT??'4188');
  if(!Number.isSafeInteger(port)||port<0||port>65535)throw Error('Invalid simulation port');
  const app=await createSimulationServer();
  app.server.listen(port,'127.0.0.1',()=>process.stdout.write('LOCAL SIMULATION ONLY at http://127.0.0.1:'+app.server.address().port+'/\n'));
  const shutdown=()=>{void app.close().then(()=>process.exit(0));};process.once('SIGINT',shutdown);process.once('SIGTERM',shutdown);
}
