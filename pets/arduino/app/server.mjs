import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {buildWorkspace, compareDesigns, WorkspaceError} from './workspace.mjs';

const MAX_BODY = 256 * 1024;
const files = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/index.html', ['index.html', 'text/html; charset=utf-8']],
  ['/styles.css', ['styles.css', 'text/css; charset=utf-8']],
  ['/app.mjs', ['app.mjs', 'text/javascript; charset=utf-8']],
]);
function securityHeaders(response) {
  response.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'");
  response.setHeader('X-Content-Type-Options', 'nosniff');
  response.setHeader('Referrer-Policy', 'no-referrer');
  response.setHeader('Cache-Control', 'no-store');
}
function sendJSON(response, status, value, head = false) {
  const body = JSON.stringify(value);
  response.writeHead(status, {'Content-Type': 'application/json; charset=utf-8', 'Content-Length': Buffer.byteLength(body)});
  response.end(head ? undefined : body);
}
function bodyJSON(request) {
  return new Promise((resolve, reject) => {
    let length = 0, settled = false;
    const chunks = [];
    const fail = (status, message) => {
      if (!settled) { settled = true; chunks.length = 0; reject(new WorkspaceError(status, message)); }
    };
    const declared = request.headers['content-length'];
    if (declared !== undefined && (!/^\d+$/.test(declared) || Number(declared) > MAX_BODY)) fail(413, 'JSON request exceeds 256 KiB.');
    request.on('data', chunk => {
      if (settled) return;
      length += chunk.length;
      if (length > MAX_BODY) fail(413, 'JSON request exceeds 256 KiB.');
      else chunks.push(chunk);
    });
    request.on('end', () => {
      if (settled) return;
      settled = true;
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); }
      catch { reject(new WorkspaceError(400, 'Request body must be valid JSON.')); }
    });
    request.on('error', () => fail(400, 'Request body could not be read.'));
    request.on('aborted', () => fail(400, 'Request body was interrupted.'));
  });
}

export async function startServer({port = 4177, host = '127.0.0.1'} = {}) {
  if (host !== '127.0.0.1') throw new Error('This local app may bind only to 127.0.0.1.');
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('PORT must be an integer from 0 to 65535.');
  const server = http.createServer(async (request, response) => {
    securityHeaders(response);
    try {
      const actualPort = server.address().port;
      const allowedHosts = new Set([`127.0.0.1:${actualPort}`, `localhost:${actualPort}`]);
      if (actualPort === 80) { allowedHosts.add('127.0.0.1'); allowedHosts.add('localhost'); }
      if (!allowedHosts.has(request.headers.host)) throw new WorkspaceError(403, 'Only local host requests are supported.');
      const path = request.url.split('?')[0];
      const head = request.method === 'HEAD';
      if (request.method === 'POST') {
        if (request.headers.origin !== undefined && request.headers.origin !== `http://${request.headers.host}`) throw new WorkspaceError(403, 'Cross-origin requests are not allowed.');
        if (request.headers['sec-fetch-site'] === 'cross-site') throw new WorkspaceError(403, 'Cross-site requests are not allowed.');
        if (!['/api/review', '/api/compare'].includes(path)) throw new WorkspaceError(404, 'Unknown local route.');
        if ((request.headers['content-type'] ?? '').split(';')[0].trim().toLowerCase() !== 'application/json') throw new WorkspaceError(415, 'Use Content-Type application/json.');
        const input = await bodyJSON(request);
        return sendJSON(response, 200, path === '/api/review' ? buildWorkspace(input) : compareDesigns(input));
      }
      if (request.method !== 'GET' && !head) {
        response.setHeader('Allow', 'GET, HEAD, POST');
        throw new WorkspaceError(405, 'Unsupported request method.');
      }
      if (path === '/api/example') {
        const [design, pet] = await Promise.all([
          readFile(new URL('../example-v2.json', import.meta.url), 'utf8'),
          readFile(new URL('../pet.json', import.meta.url), 'utf8'),
        ]);
        return sendJSON(response, 200, {design: JSON.parse(design), checkerVersion: JSON.parse(pet).version}, head);
      }
      const entry = files.get(path);
      if (!entry) throw new WorkspaceError(404, 'Unknown local route.');
      const body = await readFile(new URL(`./${entry[0]}`, import.meta.url));
      response.writeHead(200, {'Content-Type': entry[1], 'Content-Length': body.length});
      response.end(head ? undefined : body);
    } catch (error) {
      const status = error instanceof WorkspaceError ? error.status : 500;
      const message = error instanceof WorkspaceError ? error.message : 'Local app could not complete the request.';
      if (!response.headersSent && !response.destroyed) sendJSON(response, status, {error: message}, request.method === 'HEAD');
      else if (!response.destroyed) response.end();
    }
  });
  server.requestTimeout = 15000;
  server.headersTimeout = 10000;
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, host, () => { server.off('error', reject); resolve(); });
  });
  return server;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const port = process.env.PORT === undefined ? 4177 : Number(process.env.PORT);
  startServer({port}).then(server => {
    console.log(`Arduino fictional review workspace: http://127.0.0.1:${server.address().port}`);
  }).catch(() => { console.error('Could not start the loopback workspace. Check PORT and local port availability.'); process.exitCode = 1; });
}
