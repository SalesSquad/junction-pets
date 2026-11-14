import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import {benchmark} from './benchmark.mjs';
import {report,aggregate} from './stress/report.mjs';
// One immutable, server-only evaluation per process; no OOD work on refresh.
let robustness;
const stressAggregate=()=>robustness??=(report().then(aggregate));
const files=new Map([['/',['index.html','text/html']],['/style.css',['style.css','text/css']],['/app.mjs',['app.mjs','text/javascript']],['/detector.mjs',['detector.mjs','text/javascript']],['/scenarios.mjs',['scenarios.mjs','text/javascript']],['/generator.mjs',['generator.mjs','text/javascript']]]);
for(const [path,type] of [['index.html','text/html'],['app.mjs','text/javascript'],['core.mjs','text/javascript'],['style.css','text/css']])files.set('/traffic/'+path,['traffic/'+path,type]);
export function createServer() {return http.createServer(async(req,res)=>{
 const headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"};
 if(!['GET','HEAD'].includes(req.method)){res.writeHead(405,{...headers,Allow:'GET, HEAD'});res.end();return;}
 try {if(req.url==='/api/benchmark'){const [existing,ood]=await Promise.all([benchmark(),stressAggregate()]);const data=JSON.stringify({...existing,robustness:ood});res.writeHead(200,{...headers,'Content-Type':'application/json'});res.end(req.method==='HEAD'?undefined:data);return;}
 const entry=files.get(req.url);if(!entry){res.writeHead(404,headers);res.end('Not found');return;}
 const data=await readFile(new URL(`./public/${entry[0]}`,import.meta.url));res.writeHead(200,{...headers,'Content-Type':`${entry[1]}; charset=utf-8`});res.end(req.method==='HEAD'?undefined:data);
 }catch{res.writeHead(500,headers);res.end('Unable to load local resource');}
 });}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const port=Number(process.env.PORT||4173);createServer().listen(port,'127.0.0.1',()=>console.log(`SYNTHETIC Radar: http://127.0.0.1:${port} (Hostinger NOT VERIFIED)`));}
