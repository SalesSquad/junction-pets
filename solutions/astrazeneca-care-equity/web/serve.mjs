import http from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
const root = path.resolve(import.meta.dirname, '..');
const files = new Map([
  ['/', ['web/index.html', 'text/html; charset=utf-8']],
  ['/styles.css',['web/styles.css','text/css; charset=utf-8']],
  ['/app.mjs',['web/app.mjs','text/javascript; charset=utf-8']],
  ['/src/engine.mjs',['src/engine.mjs','text/javascript; charset=utf-8']],
  ['/fixtures/regions.json',['fixtures/regions.json','application/json; charset=utf-8']],
]);
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (req.method !== 'GET' || !files.has(url.pathname)) { res.writeHead(404);res.end('Not found');return; }
  const [rel,type]=files.get(url.pathname);
  try { const bytes=await readFile(path.join(root,rel));res.writeHead(200,{'Content-Type':type,'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; connect-src 'self'",'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(bytes);}
  catch { res.writeHead(500);res.end('Unavailable'); }
});
const port=Number(process.env.PORT || 4179);
server.listen(port,'127.0.0.1',()=>console.log(`SYNTHETIC ONLY — http://127.0.0.1:${port}`));
