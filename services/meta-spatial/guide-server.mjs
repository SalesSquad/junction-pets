import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const root = fileURLToPath(new URL('../../apps/meta-resume-web/guide/', import.meta.url));
const files = new Map([
  ['/guide/', ['index.html', 'text/html; charset=utf-8']],
  ['/guide/index.html', ['index.html', 'text/html; charset=utf-8']],
  ...['guide-app.mjs', 'guide-core.mjs', 'guide-webmcp.mjs', 'capture.mjs', 'context-handoff.mjs', 'guide-storage.mjs'].map(name =>
    ['/guide/' + name, [name, 'text/javascript; charset=utf-8']]),
  ['/guide/guide.css', ['guide.css', 'text/css; charset=utf-8']],
]);

/** Fixed local static routes: no arbitrary filesystem, network or host API. */
export async function serveGuide(request, response) {
  if (request.method !== 'GET') return false;
  const item = files.get(request.url?.split('?')[0]);
  if (!item) return false;
  try {
    const bytes = await readFile(resolve(root, item[0]));
    response.writeHead(200, { 'Content-Type': item[1], 'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
      'Permissions-Policy': 'camera=(self), microphone=(), geolocation=()' });
    response.end(bytes);
  } catch { response.writeHead(404); response.end('Guide asset unavailable'); }
  return true;
}

/** Standalone, loopback-only notebook; no model configuration is loaded. */
export function createGuideServer() {
  const server = http.createServer(async (request, response) => {
    const origin = 'http://127.0.0.1:' + server.address().port;
    if (request.headers.host !== new URL(origin).host ||
        request.headers.origin && request.headers.origin !== origin ||
        request.headers['sec-fetch-site'] === 'cross-site') {
      response.writeHead(403); return response.end('Origin rejected');
    }
    if (request.method === 'GET' && request.url === '/') {
      response.writeHead(303, { Location: '/guide/' }); return response.end();
    }
    if (await serveGuide(request, response)) return;
    response.writeHead(404); response.end('Not found');
  });
  server.requestTimeout = 10_000; server.headersTimeout = 5_000;
  return server;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const port = Number(process.argv[2] ?? 8790);
  if (process.argv.length > 3 || !Number.isSafeInteger(port) || port < 1024 || port > 65535)
    throw new Error('Usage: node services/meta-spatial/guide-server.mjs [unprivileged-port]');
  const server = createGuideServer();
  server.listen(port, '127.0.0.1', () => console.log('Lens Guide: http://127.0.0.1:' + port + '/guide/'));
  for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => server.close());
}
