import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const web=fileURLToPath(new URL('./',import.meta.url)), root=path.dirname(web);
const csp="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'";
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
 if(req.method!=='GET'&&req.method!=='HEAD')return json({error:'Method not allowed'},405);
 if(p.includes('..')||p.includes('\\')||p.includes('\0'))return json({error:'Forbidden'},403);
 let base=web, relative=p==='/'?'index.html':p.slice(1);
 if(p.startsWith('/src/')){if(!/^\/src\/[\w-]+\.mjs$/.test(p))return json({error:'Forbidden'},403);base=root;}
 if(p.startsWith('/data/')&&!['/data/app.json','/data/counties.geo.json'].includes(p)){if(!p.endsWith('.json'))return json({error:'Forbidden'},403);base=root;}
 const file=path.resolve(base,relative);if(!file.startsWith(base+path.sep)&&!file.startsWith(base))return json({error:'Forbidden'},403);
 const content=await readFile(file);res.writeHead(200,{'Content-Type':({'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.json':'application/json','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream'});res.end(req.method==='HEAD'?undefined:content);
 }catch(e){json({error:e.code==='ENOENT'?'Not found':'Request failed'},e.code==='ENOENT'?404:400);}
});
server.listen(Number(process.env.PORT||4179),'127.0.0.1',()=>console.log(`SAMA http://127.0.0.1:${server.address().port}`));
