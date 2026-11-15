import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {createLiveService} from './live/service.mjs';
import {safeCode} from './live/compare.mjs';
import {WatchService} from './watch/service.mjs';
import {safeError,problem} from './watch/model.mjs';
const files={'/':['live/index.html','text/html'],'/live/':['live/index.html','text/html'],'/live/app.mjs':['live/app.mjs','text/javascript'],'/live/style.css':['live/style.css','text/css'],'/watches/':['watch/index.html','text/html'],'/watches/app.mjs':['watch/app.mjs','text/javascript'],'/watches/style.css':['watch/style.css','text/css'],'/replay':['index.html','text/html'],'/style.css':['style.css','text/css'],'/app.mjs':['app.mjs','text/javascript'],'/engine.mjs':['engine.mjs','text/javascript'],'/fixtures.mjs':['fixtures.mjs','text/javascript']};
async function watchBody(req){
  const timer=setTimeout(()=>req.destroy(),5_000);let size=0;const chunks=[];
  try{for await(const chunk of req){size+=chunk.length;if(size>8192)throw problem('INVALID_REQUEST');chunks.push(chunk);}const value=JSON.parse(Buffer.concat(chunks).toString('utf8'));if(!value||typeof value!=='object'||Array.isArray(value))throw problem('INVALID_REQUEST');return value;}
  catch{throw problem('INVALID_REQUEST');}finally{clearTimeout(timer);}
}
export function createServer(options={}){const live=options.liveService??createLiveService(options);let watches=options.watchService;
const getWatches=()=>watches??=new WatchService({...options.watchOptions,apiKey:options.apiKey??process.env.CONTEXT_DEV_API_KEY,scheduler:false});
const server=http.createServer(async(req,res)=>{
  const host=req.headers.host;
  res.setHeader('Content-Security-Policy',`default-src 'none'; script-src 'self'; style-src 'self'; connect-src ${req.url==='/replay'?"'none'":"'self'"}; img-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`);
  res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Cache-Control','no-store');res.setHeader('Referrer-Policy','no-referrer');
  const expectedHost=`127.0.0.1:${req.socket?.localPort}`;
  if(host!==expectedHost){res.writeHead(404);return res.end();}
  const json=(status,data)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify(data));};
  if(req.url==='/watches'&&['GET','HEAD'].includes(req.method)){res.writeHead(302,{Location:'/watches/'});return res.end();}
  const watchRoute=req.url==='/api/watches'?[]:/^\/api\/watches\/([0-9a-f-]{36})(?:\/(run|research|pause|resume|archive))?$/.exec(req.url??'');
  if(watchRoute){
    try{
      if(req.method==='GET'){
        if(watchRoute.length===0)return json(200,getWatches().overview());
        if(!watchRoute[2])return json(200,getWatches().detail(watchRoute[1]));
      }
      if(['POST','PATCH'].includes(req.method)){
        if(req.headers.origin!==`http://${expectedHost}`||req.headers['x-supplypulse-refresh']!=='1'||req.headers['content-type']!=='application/json')return json(403,{error:'ORIGIN_REQUIRED'});
        const body=await watchBody(req);const service=getWatches();
        if(watchRoute.length===0&&req.method==='POST'){
          if(Object.keys(body).some(k=>!['definition','idempotencyKey'].includes(k)))throw problem('INVALID_REQUEST');
          return json(201,{watch:service.create(body.definition,body.idempotencyKey)});
        }
        const [,id,action]=watchRoute;
        if(!action&&req.method==='PATCH'){
          if(Object.keys(body).some(k=>!['revision','definition'].includes(k))||!Number.isInteger(body.revision))throw problem('INVALID_REQUEST');
          return json(200,{watch:service.update(id,body.revision,body.definition)});
        }
        if(action&&req.method==='POST'){
          if(['run','research'].includes(action)){
            if(Object.keys(body).length)throw problem('INVALID_REQUEST');return json(202,service.start(id,{kind:action==='research'?'research':'search'}));
          }
          if(Object.keys(body).length!==1||!Number.isInteger(body.revision))throw problem('INVALID_REQUEST');
          return json(200,{watch:service.action(id,body.revision,action)});
        }
      }
      return json(404,{error:'WATCH_NOT_FOUND'});
    }catch(e){if(res.destroyed)return;const code=safeError(e);return json(code==='WATCH_NOT_FOUND'?404:['REVISION_CONFLICT','RUN_BUSY','IDEMPOTENCY_CONFLICT'].includes(code)?409:['RUN_LIMIT_REACHED','DAILY_REQUEST_LIMIT','REQUEST_LIMIT','WATCH_LIMIT'].includes(code)?429:code==='CONNECTION_REQUIRED'||code==='STORE_UNAVAILABLE'?503:code.startsWith('PROVIDER_')?502:400,{error:code});}
  }
  if(req.url==='/api/comparison' && req.method==='GET'){
    try{return json(200,await live.current());}catch{return json(500,{error:'CAPTURE_INVALID'});}
  }
  if(req.url==='/api/refresh' && req.method==='POST'){
    // Same-origin JS only. A hostile page cannot trigger paid calls via forms,
    // image tags, DNS rebinding, CORS or a GET prefetch.
    if(req.headers.origin!==`http://${expectedHost}` || req.headers['x-supplypulse-refresh']!=='1' || req.headers['content-type']!=='application/json')return json(403,{error:'ORIGIN_REQUIRED'});
    let size=0;const chunks=[];
    const readDeadline=setTimeout(()=>{if(!res.writableEnded){json(408,{error:'BODY_TIMEOUT'});req.destroy();}},5_000);
    try{
      for await(const chunk of req){size+=chunk.length;if(size>16)return json(413,{error:'EMPTY_OBJECT_REQUIRED'});chunks.push(chunk);}
      clearTimeout(readDeadline);
      if(Buffer.concat(chunks).toString('utf8')!=='{}')return json(400,{error:'EMPTY_OBJECT_REQUIRED'});
      return json(200,await live.refresh());
    }catch(e){if(res.writableEnded||res.destroyed)return;const code=safeCode(e);return json(code==='CONNECTION_REQUIRED'?503:code==='PROVIDER_CREDITS_EXHAUSTED'?402:['REFRESH_BUSY','REFRESH_COOLDOWN','SESSION_REFRESH_LIMIT'].includes(code)?429:502,{error:code});}
    finally{clearTimeout(readDeadline);}
  }
  if(!['GET','HEAD'].includes(req.method)||!Object.hasOwn(files,req.url)){res.writeHead(404);return res.end();}
  const [file,type]=files[req.url];try{const data=await readFile(new URL(file,import.meta.url));res.writeHead(200,{'Content-Type':type+'; charset=utf-8'});res.end(req.method==='HEAD'?undefined:data);}catch{res.writeHead(500);res.end();}
});server.on('listening',()=>{if(options.enableWatchScheduler)getWatches().startScheduler();});server.on('close',()=>{watches?.close().catch(()=>{});});return server;}
if(process.argv[1]===fileURLToPath(import.meta.url)){
  const port=Number(process.env.PORT??4173);const server=createServer({enableWatchScheduler:true});server.listen(port,'127.0.0.1',()=>console.log(`SupplyPulse http://127.0.0.1:${port} · product watches /watches/ · synthetic controls /replay`));
  for(const event of ['SIGINT','SIGTERM'])process.once(event,()=>server.close());
}
