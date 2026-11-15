import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import {benchmark} from './benchmark.mjs';
import {report,aggregate} from './stress/report.mjs';
import {evaluateV2} from './evaluation-v2.mjs';
import {createServices,ServiceError} from './services.mjs';
let robustness;
const stressAggregate=()=>robustness??=(report().then(aggregate));
const files=new Map([
 ['/',['home.html','text/html']],['/index.html',['home.html','text/html']],
 ['/legacy/index.html',['index.html','text/html']],
 ['/style.css',['style.css','text/css']],['/app.mjs',['app.mjs','text/javascript']],
 ['/health.mjs',['health.mjs','text/javascript']],['/home.css',['home.css','text/css']],
 ['/detector.mjs',['detector.mjs','text/javascript']],['/coordination.mjs',['coordination.mjs','text/javascript']],
 ['/scenarios.mjs',['scenarios.mjs','text/javascript']],['/generator.mjs',['generator.mjs','text/javascript']]
]);
for(const [dir,names] of Object.entries({traffic:['index.html','app.mjs','core.mjs','style.css'],text:['index.html','app.mjs','style.css'],coordination:['index.html','app.mjs']})) {
 for(const name of names)files.set('/'+dir+'/'+name,[dir+'/'+name,name.endsWith('.html')?'text/html':name.endsWith('.css')?'text/css':'text/javascript']);
}
const headers={
 'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
 'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
 'Permissions-Policy':'camera=(), microphone=(), geolocation=()'
};
function readJSON(req) {
 return new Promise((resolve,reject)=>{
  let bytes=0,chunks=[],settled=false;
  const refuse=(status,code)=>{if(!settled){settled=true;chunks=[];reject(new ServiceError(status,code));}};
  req.on('data',chunk=>{bytes+=chunk.length;if(bytes>8192){refuse(413,'BODY_TOO_LARGE');return;}if(!settled)chunks.push(chunk);});
  req.on('end',()=>{if(settled)return;settled=true;try{resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));}catch{reject(new ServiceError(400,'INVALID_JSON'));}});
  req.on('error',()=>refuse(400,'INVALID_REQUEST'));
  req.on('aborted',()=>refuse(400,'INVALID_REQUEST'));
 });
}
export function createServer({env=process.env,services=createServices({env})}={}) {
 const send=(res,status,data,method)=>{res.writeHead(status,{...headers,'Content-Type':'application/json; charset=utf-8'});res.end(method==='HEAD'?undefined:JSON.stringify(data));};
 if(env.SIGNAL_DEPLOYMENT_PROVIDER==='hostinger'&&!/^https:\/\/[a-z0-9.-]+(?::\d+)?$/.test(env.SIGNAL_PUBLIC_ORIGIN||''))throw new Error('Hostinger deployment requires an exact HTTPS SIGNAL_PUBLIC_ORIGIN.');
 if(services.status().aiRouter!=='NOT_CONFIGURED'&&!env.SIGNAL_PUBLIC_ORIGIN)throw new Error('Configured AI credentials require an exact SIGNAL_PUBLIC_ORIGIN, including local development.');
 const server=http.createServer(async(req,res)=>{
  try {
   if(req.url==='/api/interpret'&&req.method==='POST') {
    const origin=req.headers?.origin;
    const allowed=env.SIGNAL_PUBLIC_ORIGIN;
    const local=typeof origin==='string'&&/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(origin);
    if(!origin||(allowed?origin!==allowed:!local))throw new ServiceError(403,'ORIGIN_NOT_ALLOWED');
    if(req.headers?.['content-type']!=='application/json')throw new ServiceError(415,'JSON_REQUIRED');
    if(Number(req.headers?.['content-length']||0)>8192)throw new ServiceError(413,'BODY_TOO_LARGE');
    const body=await readJSON(req);
    if(!body||typeof body!=='object'||Array.isArray(body))throw new ServiceError(400,'INVALID_JSON');
    send(res,200,await services.interpret(body),req.method);return;
   }
   if(!['GET','HEAD'].includes(req.method)){res.writeHead(405,{...headers,Allow:req.url==='/api/interpret'?'POST':'GET, HEAD'});res.end();return;}
   if(req.url==='/api/ready'){const state=await services.readiness();send(res,state.ready?200:503,state,req.method);return;}
   if(req.url==='/api/status'){send(res,200,{...services.status(),sourceRevision:/^[a-f0-9]{40}$/.test(env.SIGNAL_SOURCE_REVISION||'')?env.SIGNAL_SOURCE_REVISION:null},req.method);return;}
   if(req.url==='/api/evaluation-v2'){send(res,200,evaluateV2(),req.method);return;}
   if(req.url==='/api/benchmark'){const [existing,ood]=await Promise.all([benchmark(),stressAggregate()]);send(res,200,{...existing,robustness:ood},req.method);return;}
   const entry=files.get(req.url);
   if(!entry){res.writeHead(404,headers);res.end(req.method==='HEAD'?undefined:'Not found');return;}
   const data=await readFile(new URL('./public/'+entry[0],import.meta.url));
   res.writeHead(200,{...headers,'Content-Type':entry[1]+'; charset=utf-8'});res.end(req.method==='HEAD'?undefined:data);
  } catch(error) {
   send(res,error instanceof ServiceError?error.status:500,{error:error instanceof ServiceError?error.code:'INTERNAL_ERROR'},req.method);
  }
 });
 server.headersTimeout=5000;server.requestTimeout=15000;server.maxRequestsPerSocket=100;
 return server;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 const port=Number(process.env.PORT||4173),host=process.env.HOST||'127.0.0.1';
 createServer().listen(port,host,()=>console.log('Signal Desk listening on '+host+':'+port+'; provider configuration at /api/status'));
}
