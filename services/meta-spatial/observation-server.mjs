import http from 'node:http';
import { randomBytes, timingSafeEqual } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { resolve, extname } from 'node:path';
import { runTaskObservation } from '../nemotron-vl/task-observation.mjs';
import { createObservationGate } from './observation-contract.mjs';
import { demoObservation, syntheticObservationTransport } from './observation-demo.mjs';
import { FIXTURE } from '../../apps/meta-resume-web/fixture.mjs';
import { serveGuide } from './guide-server.mjs';

const webRoot=fileURLToPath(new URL('../../apps/meta-resume-web/',import.meta.url));
const modes={synthetic:'nvidia-hosted',hosted:'nvidia-hosted',local:'nemotron-local-nvfp4'};
const types={'.html':'text/html; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'};
function sameToken(a,b) {return typeof a==='string' && a.length===b.length && timingSafeEqual(Buffer.from(a),Buffer.from(b));}
function json(response,status,body) {
  response.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});
  response.end(JSON.stringify(body));
}
async function readJson(request) {
  if(!/^application\/json(?:;|$)/i.test(request.headers['content-type']??''))throw new Error('JSON_REQUIRED');
  let bytes=0;const chunks=[];
  for await(const chunk of request) {bytes+=chunk.length;if(bytes>2*1024*1024)throw new Error('INPUT_TOO_LARGE');chunks.push(chunk);}
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

/** Loopback development adapter. It is not the authenticated private Chibi API. */
export function createObservationServer({mode='synthetic',apiKey='',maxCalls=20}={}) {
  if(!Object.hasOwn(modes,mode))throw new Error('Unsupported observation mode');
  if(mode==='hosted' && !apiKey)throw new Error('Hosted mode requires an explicitly supplied NVIDIA_API_KEY');
  const csrfToken=randomBytes(32).toString('hex'),gate=createObservationGate();
  let busy=false,calls=0;
  const server=http.createServer(async(request,response)=>{
    const origin='http://127.0.0.1:'+server.address().port;
    // No remote binding, wildcard Host, CORS, credential proxy or arbitrary provider URL.
    if(request.headers.host!==new URL(origin).host || request.headers.origin && request.headers.origin!==origin ||
      request.headers['sec-fetch-site']==='cross-site')return json(response,403,{error:{code:'ORIGIN_REJECTED'}});
    const path=request.url?.split('?')[0];
    try {
      if(await serveGuide(request,response))return;
      if(request.method==='GET' && path==='/api/config')return json(response,200,{mode,csrfToken,privateHostConnected:false});
      if(request.method==='GET' && path==='/api/demo-observation')return json(response,200,demoObservation());
      if(request.method==='POST' && path==='/api/observe') {
        if(!sameToken(request.headers['x-meta-csrf'],csrfToken))return json(response,403,{error:{code:'CSRF_REJECTED'}});
        if(busy)return json(response,409,{error:{code:'OBSERVATION_BUSY'}});
        if(calls>=maxCalls)return json(response,429,{error:{code:'SESSION_BUDGET_EXHAUSTED'}});
        busy=true;
        try {
          const input=await readJson(request);
          // The development shell only serves the visible local packing fixture.
          const step=FIXTURE.steps.find(s=>s.stepId===input?.task?.nextStep?.stepId);
          if(input?.task?.taskId!==FIXTURE.taskId || !step || step.label!==input.task.nextStep.label)
            return json(response,400,{error:{code:'DEVELOPMENT_TASK_MISMATCH'}});
          if(mode==='synthetic' && input?.observation?.evidenceMode!=='SYNTHETIC')
            return json(response,400,{error:{code:'SYNTHETIC_MODE_REQUIRES_SYNTHETIC_INPUT'}});
          const context=()=>({taskId:FIXTURE.taskId,revision:input.task.revision,sessionId:FIXTURE.sessionId,
            captureGeneration:FIXTURE.captureGeneration,captureEnabled:true,nowMs:Date.now()});
          const result=await runTaskObservation(input,{profile:modes[mode],apiKey:mode==='synthetic'?'synthetic-no-provider':apiKey,
            ...(mode==='synthetic'?{fetchImpl:syntheticObservationTransport}:{}),context,gate});
          if(result.receipt.providerCalls.length)calls++;
          result.receipt.developmentShell=true;
          if(mode==='synthetic')result.receipt.execution='synthetic-fixture';
          return json(response,result.status==='failed'?422:200,result);
        } finally {busy=false;}
      }
      if(request.method==='GET' && (path==='/' || /^\/[A-Za-z0-9_-]+\.(?:html|mjs|css)$/.test(path))) {
        const filename=path==='/'?'index.html':path.slice(1),extension=extname(filename);
        const bytes=await readFile(resolve(webRoot,filename));
        response.writeHead(200,{'Content-Type':types[extension],'X-Content-Type-Options':'nosniff','Cache-Control':'no-store'});
        return response.end(bytes);
      }
      json(response,404,{error:{code:'NOT_FOUND'}});
    } catch {json(response,400,{error:{code:'INVALID_REQUEST'}});}
  });
  server.requestTimeout=10000;server.headersTimeout=5000;
  return server;
}

if(process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href) {
  const args=process.argv.slice(2),allowed=new Set(['--mode','--port']);
  const options={};
  for(let i=0;i<args.length;i+=2) {
    if(!allowed.has(args[i]) || !args[i+1])throw new Error('Usage: node observation-server.mjs [--mode synthetic|hosted|local] [--port 8787]');
    options[args[i].slice(2)]=args[i+1];
  }
  const port=Number(options.port??8787);
  if(!Number.isSafeInteger(port) || port<1024 || port>65535)throw new Error('Use an unprivileged port');
  const server=createObservationServer({mode:options.mode??'synthetic',apiKey:options.mode==='hosted'?process.env.NVIDIA_API_KEY??'':''});
  server.listen(port,'127.0.0.1',()=>console.log(JSON.stringify({url:'http://127.0.0.1:'+port,mode:options.mode??'synthetic',privateHostConnected:false})));
  for(const signal of ['SIGINT','SIGTERM'])process.once(signal,()=>server.close());
}
