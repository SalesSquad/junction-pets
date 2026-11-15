import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {createLiveService} from './live/service.mjs';
import {safeCode} from './live/compare.mjs';
const files={'/':['live/index.html','text/html'],'/live/':['live/index.html','text/html'],'/live/app.mjs':['live/app.mjs','text/javascript'],'/live/style.css':['live/style.css','text/css'],'/replay':['index.html','text/html'],'/style.css':['style.css','text/css'],'/app.mjs':['app.mjs','text/javascript'],'/engine.mjs':['engine.mjs','text/javascript'],'/fixtures.mjs':['fixtures.mjs','text/javascript']};
export function createServer(options={}){const live=options.liveService??createLiveService(options);return http.createServer(async(req,res)=>{
  const host=req.headers.host;
  res.setHeader('Content-Security-Policy',`default-src 'none'; script-src 'self'; style-src 'self'; connect-src ${req.url==='/replay'?"'none'":"'self'"}; img-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`);
  res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Cache-Control','no-store');res.setHeader('Referrer-Policy','no-referrer');
  const expectedHost=`127.0.0.1:${req.socket.localPort}`;
  if(host!==expectedHost){res.writeHead(404);return res.end();}
  const json=(status,data)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify(data));};
  if(req.url==='/api/comparison' && req.method==='GET'){
    try{return json(200,await live.current());}catch{return json(500,{error:'CAPTURE_INVALID'});}
  }
  if(req.url==='/api/refresh' && req.method==='POST'){
    // Same-origin JS only. A hostile page cannot trigger paid calls via forms,
    // image tags, DNS rebinding, CORS or a GET prefetch.
    if(req.headers.origin!==`http://${expectedHost}` || req.headers['x-supplypulse-refresh']!=='1' || req.headers['content-type']!=='application/json')return json(403,{error:'ORIGIN_REQUIRED'});
    let size=0;const chunks=[];
    try{
      for await(const chunk of req){size+=chunk.length;if(size>16)return json(413,{error:'EMPTY_OBJECT_REQUIRED'});chunks.push(chunk);}
      if(Buffer.concat(chunks).toString('utf8')!=='{}')return json(400,{error:'EMPTY_OBJECT_REQUIRED'});
      return json(200,await live.refresh());
    }catch(e){const code=safeCode(e);return json(code==='CONNECTION_REQUIRED'?503:['REFRESH_BUSY','REFRESH_COOLDOWN','SESSION_REFRESH_LIMIT'].includes(code)?429:502,{error:code});}
  }
  if(!['GET','HEAD'].includes(req.method)||!Object.hasOwn(files,req.url)){res.writeHead(404);return res.end();}
  const [file,type]=files[req.url];try{const data=await readFile(new URL(file,import.meta.url));res.writeHead(200,{'Content-Type':type+'; charset=utf-8'});res.end(req.method==='HEAD'?undefined:data);}catch{res.writeHead(500);res.end();}
});}
if(process.argv[1]===fileURLToPath(import.meta.url)){const port=Number(process.env.PORT??4173);createServer().listen(port,'127.0.0.1',()=>console.log(`SupplyPulse http://127.0.0.1:${port} · synthetic controls /replay`));}
