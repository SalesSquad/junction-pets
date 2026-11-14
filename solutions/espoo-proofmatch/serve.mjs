import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
const publicFiles = new Map([['/', 'index.html'], ...['index.html', 'styles.css', 'app.mjs', 'matcher.mjs', 'data.mjs', 'benchmark.mjs', 'sw.js'].map(file => [`/${file}`, file])]);
const mime = { html: 'text/html; charset=utf-8', css: 'text/css; charset=utf-8', mjs: 'text/javascript; charset=utf-8', js: 'text/javascript; charset=utf-8' };
const port = Number(process.env.PORT ?? 4173);
if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('PORT must be an integer from 0 to 65535.');
const server = createServer(async (req, res) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'no-referrer');
  res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'");
  res.setHeader('Cache-Control', 'no-store');
  if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405, { Allow: 'GET, HEAD' }); res.end('Read-only demo server'); return; }
  let path;
  try { path = new URL(req.url, 'http://localhost').pathname; } catch { res.writeHead(400); res.end('Invalid URL'); return; }
  const file = publicFiles.get(path);
  if (!file) { res.writeHead(404); res.end('Not found'); return; }
  try {
    const bytes = await readFile(new URL(file, import.meta.url));
    res.writeHead(200, { 'Content-Type': mime[file.split('.').pop()], 'Content-Length': bytes.length });
    res.end(req.method === 'HEAD' ? undefined : bytes);
  } catch { res.writeHead(500); res.end('Demo file unavailable'); }
});
server.on('error', error => {
  console.error(`ProofMatch server could not listen on 127.0.0.1:${port} (${error.code}). Check local port availability and executor permissions.`);
  process.exitCode = 1;
});
server.listen(port, '127.0.0.1', () => console.log(`ProofMatch SYNTHETIC demo: http://127.0.0.1:${server.address().port}`));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close(() => process.exit(0)));
