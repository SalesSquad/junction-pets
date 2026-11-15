// Foreground only. No state API, request bodies, logs, cookies or storage.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const root = new URL('./', import.meta.url);
const files = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/index.html', ['index.html', 'text/html; charset=utf-8']],
  ['/styles.css', ['styles.css', 'text/css; charset=utf-8']],
  ['/app.mjs', ['app.mjs', 'text/javascript; charset=utf-8']],
  ['/outcomes.mjs', ['outcomes.mjs', 'text/javascript; charset=utf-8']],
  ['/event-meetings.mjs', ['../event-meetings.mjs', 'text/javascript; charset=utf-8']],
  ['/demo-validation.mjs', ['../demo-validation.mjs', 'text/javascript; charset=utf-8']],
]);

export async function handleRequest(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'none'; img-src 'none'; font-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; worker-src 'none'");
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'no-referrer');
  // Reject browser DNS rebinding/cross-origin embedding. Use only the printed URL.
  if (!/^127\.0\.0\.1:\d{1,5}$/.test(req.headers.host ?? '') ||
      (req.headers['sec-fetch-site'] && !['same-origin', 'none'].includes(req.headers['sec-fetch-site']))) {
    res.writeHead(403); res.end('Use the local pilot URL.'); return;
  }
  if (!['GET', 'HEAD'].includes(req.method)) {
    res.setHeader('Allow', 'GET, HEAD'); res.writeHead(405); res.end('Read-only local pilot.'); return;
  }
  // Exact raw routes: no decoding, traversal, queries or arbitrary filesystem reads.
  const asset = files.get(req.url);
  if (!asset) { res.writeHead(404); res.end('Local pilot route not found.'); return; }
  try {
    const bytes = await readFile(new URL(asset[0], root));
    res.setHeader('Content-Type', asset[1]);
    res.writeHead(200); res.end(req.method === 'HEAD' ? undefined : bytes);
  } catch {
    res.writeHead(500); res.end('Local pilot asset unavailable.');
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const value = process.env.PORT ?? '4187';
  if (!/^\d{4,5}$/.test(value) || Number(value) < 1024 || Number(value) > 65535) throw new TypeError('PORT must be an integer from 1024 to 65535.');
  const server = createServer(handleRequest);
  server.requestTimeout = 5000;
  server.headersTimeout = 5000;
  server.maxRequestsPerSocket = 50;
  server.on('error', () => { console.error('Pilot could not bind its loopback port; choose another PORT.'); process.exitCode = 1; });
  server.listen(Number(value), '127.0.0.1', () => console.log(`SIMULATED private pilot: http://127.0.0.1:${value}/ — Ctrl-C stops it.`));
}
