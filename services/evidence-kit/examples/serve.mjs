import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {resolve, extname, sep} from 'node:path';
const root = fileURLToPath(new URL('../', import.meta.url));
const types = {'.html':'text/html', '.css':'text/css', '.mjs':'text/javascript', '.json':'application/json', '.csv':'text/csv', '.dxf':'application/dxf'};
export function createDemoServer() {
  return http.createServer(async (req, res) => {
    try {
      if (req.method !== 'GET') {res.writeHead(405);res.end();return;}
      if (req.url === '/') {res.writeHead(302, {Location:'/examples/index.html'});res.end();return;}
      const path = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
      const file = resolve(root, '.' + (path === '/' ? '/examples/index.html' : path));
      if (!file.startsWith(root) || !['examples','src','adapters','methods','components','fixtures'].some(dir => file.startsWith(resolve(root,dir) + sep))) {res.writeHead(404);res.end();return;}
      const data = await readFile(file);
      res.writeHead(200, {'Content-Type': types[extname(file)] ?? 'application/octet-stream', 'Cache-Control':'no-store',
        'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'", 'X-Content-Type-Options':'nosniff'});
      res.end(data);
    } catch {res.writeHead(404);res.end();}
  });
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.PORT || 4326);
  createDemoServer().listen(port, '127.0.0.1', () => console.log(`Evidence Kit pilot: http://127.0.0.1:${port}`));
}
