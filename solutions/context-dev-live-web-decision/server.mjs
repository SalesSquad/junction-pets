import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const files={'/':['index.html','text/html'],'/style.css':['style.css','text/css'],'/app.mjs':['app.mjs','text/javascript'],'/engine.mjs':['engine.mjs','text/javascript'],'/fixtures.mjs':['fixtures.mjs','text/javascript']};
export function createServer(){return http.createServer(async(req,res)=>{
  const host=req.headers.host;
  res.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'");
  res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Cache-Control','no-store');res.setHeader('Referrer-Policy','no-referrer');
  if(!/^127\.0\.0\.1:\d+$/.test(host??'')||!['GET','HEAD'].includes(req.method)||!Object.hasOwn(files,req.url)){res.writeHead(404);return res.end();}
  const [file,type]=files[req.url];try{const data=await readFile(new URL(file,import.meta.url));res.writeHead(200,{'Content-Type':type+'; charset=utf-8'});res.end(req.method==='HEAD'?undefined:data);}catch{res.writeHead(500);res.end();}
});}
if(process.argv[1]===fileURLToPath(import.meta.url)){createServer().listen(4173,'127.0.0.1',()=>console.log('SYNTHETIC_REPLAY http://127.0.0.1:4173'));}
