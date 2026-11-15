// web/serve.mjs failure handling: the claim check reports a real failure as ERROR (502) and keeps NOT_CONFIGURED for a
// missing key only; the live scribe fails at once when its interpreter is missing; an unreadable val-v3.jsonl is logged.
// No paid call and no model: the upstream is a local fake, the worker interpreter does not exist.
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { cpSync, mkdirSync, mkdtempSync, rmSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildBrief } from '../src/claims.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const app = JSON.parse(readFileSync(path.join(root, 'web/data/app.json'), 'utf8'));
const claims = buildBrief(app, app.analysis.regions[0].regionId).claims.slice(0, 2).map((c) => ({ id: c.id }));
const KEY = 'dummy-typesafe-key-0000';

async function startServer(env, entry = path.join(root, 'web/serve.mjs')) {
  const base = { ...process.env };
  for (const k of ['TYPESAFE_API_KEY', 'TYPESAFE_ENDPOINT', 'SAMA_SCRIBE_PYTHON', 'SAMA_SCRIBE_LIVE', 'SAMA_SCRIBE_PRELOAD']) delete base[k];
  const proc = spawn(process.execPath, [entry], { env: { ...base, PORT: '0', ...env }, stdio: ['ignore', 'pipe', 'pipe'] });
  let stderr = '';
  proc.stderr.on('data', (d) => { stderr += d; });
  const port = await new Promise((resolve, reject) => {
    proc.stdout.on('data', (d) => { const m = /127\.0\.0\.1:(\d+)/.exec(String(d)); if (m) resolve(Number(m[1])); });
    proc.on('exit', (c) => reject(new Error(`server exited ${c}`)));
  });
  const post = async (route, body) => {
    const r = await fetch(`http://127.0.0.1:${port}${route}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const text = await r.text();
    return { status: r.status, body: JSON.parse(text), text };
  };
  return { post, stderr: () => stderr, stop: () => new Promise((r) => { proc.on('exit', r); proc.kill(); }) };
}

test('claim check: no key stays NOT_CONFIGURED (200)', async () => {
  const s = await startServer({});
  try {
    const r = await s.post('/api/verify-claims', { claims });
    assert.equal(r.status, 200);
    assert.equal(r.body.status, 'NOT_CONFIGURED');
  } finally { await s.stop(); }
});

test('claim check: with a key, an upstream failure is ERROR with HTTP 502, a short reason, no key and no URL', async () => {
  const upstream = http.createServer((req, res) => { res.writeHead(500); res.end('down'); });
  await new Promise((r) => upstream.listen(0, '127.0.0.1', r));
  const endpoint = `http://127.0.0.1:${upstream.address().port}`;
  const s = await startServer({ TYPESAFE_API_KEY: KEY, TYPESAFE_ENDPOINT: endpoint });
  try {
    const r = await s.post('/api/verify-claims', { claims });
    assert.equal(r.status, 502);
    assert.equal(r.body.status, 'ERROR');
    assert.equal(typeof r.body.reason, 'string');
    assert.ok(r.body.reason.length > 0 && r.body.reason.length <= 120);
    assert.ok(!r.text.includes(KEY) && !r.text.includes(endpoint) && !r.text.includes('127.0.0.1'), 'no key, no upstream URL');
    assert.ok(!s.stderr().includes(KEY), 'the key is not logged either');
  } finally { await s.stop(); await new Promise((r) => upstream.close(r)); }
});

test('live scribe: a missing interpreter fails at once and the stored output is served with a clear reason', async () => {
  const s = await startServer({ SAMA_SCRIBE_PYTHON: path.join(root, 'no-such-venv/bin/python') });
  try {
    const t = Date.now();
    const r = await s.post('/api/scribe', { demo_id: 'demo-01' });
    assert.ok(Date.now() - t < 10000, 'no 180 s wait');
    assert.equal(r.status, 200);
    assert.equal(r.body.served, 'precomputed');
    assert.match(r.body.fallback_reason, /not set up.*SAMA_SCRIBE_PYTHON.*does not exist/);
    assert.ok(!r.text.includes(root), 'no local path in the reason');
    // a free-text note has no stored fallback: 503 with the same reason, also at once
    const f = await s.post('/api/scribe', { note_text: 'Lähete saapui.', note_date: '2026-01-05' });
    assert.equal(f.status, 503);
    assert.match(f.body.error, /not set up/);
  } finally { await s.stop(); }
});

test('second reader file: an unreadable val-v3.jsonl logs one warning and the stored fallback still works', async () => {
  const tmp = mkdtempSync(path.join(tmpdir(), 'sama-serve-'));
  try {
    mkdirSync(path.join(tmp, 'web'), { recursive: true });
    for (const f of ['serve.mjs', 'scribe-demo.mjs']) cpSync(path.join(root, 'web', f), path.join(tmp, 'web', f));
    mkdirSync(path.join(tmp, 'data/scribe/demo'), { recursive: true });
    for (const f of ['demo-notes.json', 'demo-outputs.json']) cpSync(path.join(root, 'data/scribe/demo', f), path.join(tmp, 'data/scribe/demo', f));
    const s = await startServer({ SAMA_SCRIBE_LIVE: '0' }, path.join(tmp, 'web/serve.mjs'));
    try {
      const r = await s.post('/api/scribe', { demo_id: 'demo-01', mode: 'precomputed' });
      assert.equal(r.status, 200);
      assert.equal(r.body.served, 'precomputed');
      await s.post('/api/scribe', { demo_id: 'demo-01', mode: 'precomputed' });
      const warns = s.stderr().split('\n').filter((l) => l.includes('second reader file'));
      assert.equal(warns.length, 1, 'one warning, not one per request');
      assert.match(warns[0], /val-v3\.jsonl could not be read.*ENOENT/);
    } finally { await s.stop(); }
  } finally { rmSync(tmp, { recursive: true, force: true }); }
});
