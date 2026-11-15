import {createServer} from 'node:http';
import {readFile, stat} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {loadDataset, inspect, reverts, utc} from '../src/chronicle.mjs';

// Read-only loopback studio. This is NOT an authenticated MariaDB/Wikipedia host.
export const MAX_REQUEST_BYTES = 2048;
export const LABEL = 'SYNTHETIC_REPLAY_NO_MARIADB';
const mode = d => d.provenance === 'WIKIPEDIA_API_SNAPSHOT' ? 'REAL_LOCAL_SNAPSHOT_NO_MARIADB' : LABEL;
const fixturePath = fileURLToPath(new URL('../fixtures/synthetic.json', import.meta.url));
const assets = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/index.html', ['index.html', 'text/html; charset=utf-8']],
  ['/app.js', ['app.js', 'text/javascript; charset=utf-8']],
  ['/style.css', ['style.css', 'text/css; charset=utf-8']]
]);
const assetRoot = new URL('./', import.meta.url);
const headers = Object.freeze({
  'Cache-Control': 'no-store',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Cross-Origin-Resource-Policy': 'same-origin',
  'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
});
export async function loadFixture() {
  return loadDataset(JSON.parse(await readFile(fixturePath, 'utf8')));
}
export function makeCatalog(dataset) {
  const pages = new Map();
  for (const revision of dataset.revisions) {
    if (!pages.has(revision.page_id)) pages.set(revision.page_id, []);
    pages.get(revision.page_id).push({
      revision_id: revision.revision_id, revised_at: revision.revised_at,
      title: revision.title, sha256: revision.hash
    });
  }
  return {
    status: 'OK', mode: mode(dataset), live: false,
    retrieved_at:dataset.retrieved_at || null, snapshot_sha256:dataset.snapshot_sha256 || null,
    attribution:dataset.attribution || null, window:dataset.window || null, has_more:dataset.has_more ?? null,
    dataset_id: dataset.dataset_id, dataset_license: dataset.dataset_license,
    provenance: dataset.provenance,
    pages: [...pages].map(([page_id, rows]) => {
      rows.sort((a, b) => a.revised_at.localeCompare(b.revised_at) ||
        a.revision_id.localeCompare(b.revision_id));
      return {page_id, title: rows.at(-1).title, revisions: rows};
    }).sort((a, b) => a.page_id.localeCompare(b.page_id))
  };
}
export function evaluate(dataset, request) {
  if (!request || Array.isArray(request) || typeof request !== 'object' ||
      Object.keys(request).length !== 3 ||
      !['page_id','as_of','compare_at'].every(k => Object.hasOwn(request, k)) ||
      typeof request.page_id !== 'string' || request.page_id.length > 128 ||
      typeof request.as_of !== 'string' || typeof request.compare_at !== 'string')
    throw new Error('INVALID_QUERY_SHAPE');
  const now = utc(request.as_of), earlier = utc(request.compare_at);
  if (earlier > now) throw new Error('COMPARISON_AFTER_TARGET');
  if (!dataset.revisions.some(r => r.page_id === request.page_id))
    throw new Error('UNKNOWN_PAGE');
  const snapshot = inspect(dataset, request.page_id, request.as_of, request.compare_at);
  // The shared kernel currently returns ALL revert candidates. The as-of
  // studio must never call a future revert a historical observation.
  const known = dataset.revisions.filter(r => r.ms <= now);
  return {
    ...snapshot,
    mode: mode(dataset),
    verified_live_source: false,
    suspected_reverts: reverts({...dataset, revisions: known}, request.page_id),
    as_of_boundary: request.as_of,
    note: 'Full fixture timeline is browsable; as-of findings exclude future revisions.'
  };
}
function json(res, status, body) {
  res.writeHead(status, {...headers, 'Content-Type': 'application/json; charset=utf-8'});
  res.end(JSON.stringify(body));
}
async function readJson(req) {
  const parts = [];
  let bytes = 0;
  for await (const part of req) {
    bytes += part.length;
    if (bytes > MAX_REQUEST_BYTES) throw new Error('REQUEST_TOO_LARGE');
    parts.push(part);
  }
  try { return JSON.parse(Buffer.concat(parts).toString('utf8')); }
  catch { throw new Error('INVALID_JSON'); }
}
export function createStudioServer(dataset, realSnapshot = null) {
  return createServer(async (req, res) => {
    try {
      const serverPort = req.socket.localPort;
      const allowedHost = ['127.0.0.1:' + serverPort, 'localhost:' + serverPort];
      if (!allowedHost.includes(req.headers.host))
        return json(res, 403, {status:'REFUSED', reason:'LOOPBACK_HOST_ONLY'});
      if (req.headers.origin &&
          !allowedHost.some(h => req.headers.origin === 'http://' + h))
        return json(res, 403, {status:'REFUSED', reason:'ORIGIN_REFUSED'});
      const url = new URL(req.url, 'http://127.0.0.1');
      const pathname = url.pathname;
      const selected = url.searchParams.get('source') || 'synthetic';
      if (!['synthetic','real'].includes(selected)) return json(res,422,{status:'REFUSED',reason:'UNKNOWN_SOURCE'});
      const active = selected === 'real' ? realSnapshot : dataset;
      if (!active) return json(res,422,{status:'REFUSED',reason:'NO_ADMITTED_REAL_SNAPSHOT'});
      if (req.method === 'GET' && pathname === '/api/catalog')
        return json(res, 200, makeCatalog(active));
      if (req.method === 'POST' && pathname === '/api/compare') {
        if ((req.headers['content-type'] || '').split(';')[0].trim() !== 'application/json')
          return json(res, 415, {status:'REFUSED', reason:'JSON_REQUIRED'});
        try { return json(res, 200, evaluate(active, await readJson(req))); }
        catch (err) {
          const reason = err.message || 'INVALID_REQUEST';
          return json(res, reason === 'REQUEST_TOO_LARGE' ? 413 : 422,
            {status:'REFUSED', reason});
        }
      }
      if (req.method === 'GET' && assets.has(pathname)) {
        const [name, mime] = assets.get(pathname);
        const bytes = await readFile(new URL(name, assetRoot));
        res.writeHead(200, {...headers, 'Content-Type': mime});
        return res.end(bytes);
      }
      return json(res, 404, {status:'NOT_FOUND'});
    } catch {
      return json(res, 500, {status:'REFUSED', reason:'LOCAL_SERVER_ERROR'});
    }
  });
}
if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try {
    const args = process.argv.slice(2);
    if (args.length && (args.length !== 2 || args[0] !== '--snapshot')) throw new Error('USAGE: [--snapshot LOCAL_FILE]');
    let real = null;
    if (args.length) {
      if ((await stat(args[1])).size > 4 * 1048576) throw new Error('SNAPSHOT_TOO_LARGE');
      real = loadDataset(JSON.parse(await readFile(args[1], 'utf8')));
      if (real.provenance !== 'WIKIPEDIA_API_SNAPSHOT') throw new Error('REAL_SNAPSHOT_REQUIRED');
    }
    const server = createStudioServer(await loadFixture(), real);
    server.listen(4177, '127.0.0.1', () => {
      process.stdout.write('Chronicle Studio: http://127.0.0.1:4177 (local read-only snapshots, loopback only)\n');
    });
  } catch (err) {
    process.stderr.write('STUDIO_START_REFUSED: ' + err.message + '\n');
    process.exitCode = 1;
  }
}
