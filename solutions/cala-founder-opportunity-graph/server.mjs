import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const files = new Map([
  ['/', ['public/index.html','text/html; charset=utf-8']], ['/app.mjs',['public/app.mjs','text/javascript; charset=utf-8']],
  ['/style.css',['public/style.css','text/css; charset=utf-8']], ['/core.mjs',['core.mjs','text/javascript; charset=utf-8']], ['/fixture.mjs',['fixture.mjs','text/javascript; charset=utf-8']]
]);
export async function handleRequest(req,res) {
    const headers = { 'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'none'; img-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'; object-src 'none'", 'X-Content-Type-Options':'nosniff', 'Referrer-Policy':'no-referrer', 'Cache-Control':'no-store', 'Permissions-Policy':'camera=(), microphone=(), geolocation=()' };
    const port = res.socket.localPort;
    if (![ `127.0.0.1:${port}`, `localhost:${port}` ].includes(req.headers.host)) { res.writeHead(403,headers); return res.end('Local host required'); }
    if (req.method !== 'GET' && req.method !== 'HEAD') { res.writeHead(405,{...headers,Allow:'GET, HEAD'}); return res.end('Read-only localhost app'); }
    const file = files.get(req.url);
    if (!file) { res.writeHead(404,headers); return res.end('Not found'); }
    try { const body = await readFile(new URL(file[0],import.meta.url)); res.writeHead(200,{...headers,'Content-Type':file[1]}); res.end(req.method === 'HEAD' ? undefined : body); }
    catch { res.writeHead(500,headers); res.end('Local asset unavailable'); }
}
export function createServer() { return http.createServer(handleRequest); }
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const port = Number(process.env.PORT ?? 4173);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw Error('PORT must be 1024–65535');
  createServer().listen(port,'127.0.0.1',()=>console.log(`RoundLens FICTIONAL_FIXTURE → http://127.0.0.1:${port}`));
}
