import {createServer} from 'node:http';
import {readFile, stat} from 'node:fs/promises';
import {dirname, extname, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const mime = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8'};
// Public allowlist: NEVER expose data/customer.json, developer instructions,
// tests, importer source or another file inside this working directory.
const publicFiles = new Set(['/web/index.html', '/web/styles.css', '/web/app.mjs', '/src/coach.mjs', '/src/demo-data.mjs']);
const host = '127.0.0.1'; // source-only local demo; never binds public by default
const port = Number(process.env.LUMO_PORT || 4173);

if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('LUMO_PORT must be an available TCP port');
const server = createServer(async (request, response) => {
  const headers = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'"};
  if (!['GET','HEAD'].includes(request.method ?? '')) {
    response.writeHead(405, {...headers, Allow: 'GET, HEAD'}); response.end(); return;
  }
  let location;
  try {
    const name = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
    const publicName = name === '/' ? '/web/index.html' : name;
    if (!publicFiles.has(publicName)) throw new Error('Not a public asset');
    location = resolve(root, '.' + publicName);
    if (!location.startsWith(root + sep) && location !== root) throw new Error('Path outside demo');
    const info = await stat(location);
    if (!info.isFile()) throw new Error('Not a file');
    const content = await readFile(location);
    const type = mime[extname(location)] ?? 'application/octet-stream';
    response.writeHead(200, {...headers, 'Content-Type': type, 'Content-Length': content.length});
    response.end(request.method === 'HEAD' ? undefined : content);
  } catch {
    response.writeHead(404, {...headers, 'Content-Type': 'text/plain; charset=utf-8'});
    response.end('Not found');
  }
});
server.listen(port, host, () => process.stdout.write(`Lumo local demo: http://${host}:${port}\n`));
