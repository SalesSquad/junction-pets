import http from 'node:http';
import { createHash, randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { parseDxf, DXF_LIMITS } from './dxf.mjs';
import { answerDrawing } from './grounding.mjs';
import { makeDemo } from './demo.mjs';

const publicDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public');
const cache = new Map([['demo', { drawing: makeDemo(), created: Date.now() }]]);
const MAX_FILES = 3;
const MAX_AGE_MS = 30 * 60 * 1000;

function send(res, code, data) {
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer' });
  res.end(JSON.stringify(data));
}
async function body(req, limit) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > limit) { const error = new Error('Request is too large.'); error.status = 413; throw error; }
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}
function getDrawing(id) {
  const item = cache.get(id);
  if (!item) return null;
  if (id !== 'demo' && Date.now() - item.created > MAX_AGE_MS) { cache.delete(id); return null; }
  return item.drawing;
}
function remember(drawing) {
  for (const [id, value] of cache) if (id !== 'demo' && Date.now() - value.created > MAX_AGE_MS) cache.delete(id);
  while (cache.size >= MAX_FILES + 1) cache.delete([...cache.keys()].find(id => id !== 'demo'));
  cache.set(drawing.id, { drawing, created: Date.now() });
}

export function createServer() {
  return http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url || '/', 'http://localhost');
      const origin = req.headers.origin;
      if (origin && !/^https?:\/\/(?:localhost|127\.0\.0\.1)(?::\d+)?$/.test(origin)) {
        return send(res, 403, { error: 'Remote origins cannot access private drawings.' });
      }
      if (req.method === 'GET' && url.pathname === '/api/health') return send(res, 200, { ok: true, engine: 'deterministic', externalInference: false });
      if (req.method === 'GET' && url.pathname === '/api/demo') return send(res, 200, { drawing: getDrawing('demo') });
      if (req.method === 'POST' && url.pathname === '/api/import-dxf') {
        if (!/^application\/(?:dxf|octet-stream)/i.test(req.headers['content-type'] || '')) return send(res, 415, { error: 'Use application/dxf or application/octet-stream.' });
        const bytes = await body(req, DXF_LIMITS.bytes);
        const filename = String(req.headers['x-filename'] || 'uploaded.dxf');
        const drawing = parseDxf(bytes.toString('utf8'), filename);
        drawing.sha256 = createHash('sha256').update(bytes).digest('hex');
        drawing.id = randomUUID();
        drawing.sourceNotice = 'USER-IMPORTED LOCAL FILE · Geometry extracted; claims require human verification';
        remember(drawing);
        return send(res, 201, { drawing });
      }
      if (req.method === 'POST' && url.pathname === '/api/ask') {
        if (!/^application\/json/i.test(req.headers['content-type'] || '')) return send(res, 415, { error: 'Use application/json.' });
        const input = JSON.parse((await body(req, 2048)).toString('utf8'));
        const drawing = getDrawing(input.drawingId);
        if (!drawing) return send(res, 404, { error: 'The drawing expired. Reimport the DXF file.' });
        return send(res, 200, { result: answerDrawing(drawing, input.question) });
      }
      const staticFiles = new Map([
        ['/', ['index.html', 'text/html; charset=utf-8']],
        ['/app.js', ['app.js', 'text/javascript; charset=utf-8']],
        ['/style.css', ['style.css', 'text/css; charset=utf-8']],
      ]);
      if (req.method === 'GET' && staticFiles.has(url.pathname)) {
        const [name, mime] = staticFiles.get(url.pathname);
        const data = await readFile(join(publicDir, name));
        res.writeHead(200, { 'Content-Type': mime, 'Cache-Control': 'no-store',
          'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'" });
        return res.end(data);
      }
      return send(res, 404, { error: 'No route at this path.' });
    } catch (error) {
      const code = error.status || (error instanceof SyntaxError ? 400 : 422);
      send(res, code, { error: String(error.message || error).slice(0, 240) });
    }
  });
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const port = Number(process.env.PORT || 4315);
  const host = process.env.HOST || '127.0.0.1';
  createServer().listen(port, host, () => console.info(`Stoa Blueprint Studio listening on http://${host}:${port}`));
}
