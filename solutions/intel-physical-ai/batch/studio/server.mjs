import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';

export const CSP = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'none'; img-src 'none'; font-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";
// Raw request targets are matched before any URL normalization or decoding.
const assets = new Map([
  ['/', ['index.html','text/html; charset=utf-8']],
  ['/index.html', ['index.html','text/html; charset=utf-8']],
  ['/style.css', ['style.css','text/css; charset=utf-8']],
  ['/app.mjs', ['app.mjs','text/javascript; charset=utf-8']],
  ['/model.mjs', ['model.mjs','text/javascript; charset=utf-8']],
  ['/cell.mjs', ['../cell.mjs','text/javascript; charset=utf-8']],
  ['/core.mjs', ['../../core.mjs','text/javascript; charset=utf-8']],
]);
export function createStudioServer() {
  return http.createServer(async (req,res) => {
    const origin = `http://127.0.0.1:${res.socket.localPort}`;
    const finish = (status,text) => {res.writeHead(status,{'Content-Type':'text/plain; charset=utf-8'});res.end(text);};
    res.setHeader('Content-Security-Policy',CSP);
    res.setHeader('X-Content-Type-Options','nosniff');
    res.setHeader('Referrer-Policy','no-referrer');
    res.setHeader('Cross-Origin-Resource-Policy','same-origin');
    res.setHeader('Cache-Control','no-store');
    res.setHeader('Permissions-Policy','camera=(), microphone=(), geolocation=(), usb=(), serial=()');
    if(req.headers.host !== `127.0.0.1:${res.socket.localPort}`) return finish(403,'Unexpected Host');
    if((req.headers.origin && req.headers.origin !== origin) || (req.headers['sec-fetch-site'] && !['same-origin','none'].includes(req.headers['sec-fetch-site']))) return finish(403,'Cross-origin request refused');
    if(!['GET','HEAD'].includes(req.method) || req.headers['transfer-encoding'] || (req.headers['content-length'] && req.headers['content-length'] !== '0')) return finish(405,'Read-only server; request bodies refused');
    const asset=assets.get(req.url);
    if(!asset) return finish(404,'Asset not allowed');
    try {
      const bytes=await readFile(new URL(asset[0],import.meta.url));
      res.writeHead(200,{'Content-Type':asset[1]});res.end(req.method==='HEAD'?undefined:bytes);
    } catch {finish(500,'Asset unavailable');}
  });
}
export async function listenStudio(port=3300) {
  if(!Number.isInteger(port) || port<0 || port>65535) throw Error('Invalid port');
  const server=createStudioServer();
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(port,'127.0.0.1',resolve);});
  return server;
}
if(process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const value=process.argv[2] ?? '3300';
  try {
    if(!/^\d+$/.test(value)) throw Error('Invalid port');
    const server=await listenStudio(Number(value));
    console.log(`Inspect / Action · OFFLINE SYNTHETIC · http://127.0.0.1:${server.address().port}`);
    for(const signal of ['SIGINT','SIGTERM'])process.once(signal,()=>server.close());
  } catch {console.error('Studio could not start. Use Node 22+ and an available local port (0–65535).');process.exitCode=1;}
}
