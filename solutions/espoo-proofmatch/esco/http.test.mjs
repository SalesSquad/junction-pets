import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const dir = fileURLToPath(new URL('../', import.meta.url));
test('local-only private demo serves pinned ESCO assets and refuses non-GET/private file paths', async () => {
  const child = spawn(process.execPath, ['serve.mjs'], {
    cwd: dir, env: { ...process.env, PORT: '0' }, stdio: ['ignore', 'pipe', 'pipe'],
  });
  let timer;
  const base = await new Promise((resolve, reject) => {
    timer = setTimeout(() => reject(new Error('local server timeout')), 5000);
    child.on('error', reject);
    child.on('exit', code => reject(new Error('server exited ' + code)));
    child.stdout.on('data', buffer => {
      const match = buffer.toString().match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) resolve(match[0]);
    });
  }).finally(() => clearTimeout(timer));
  try {
    for (const p of ['/', '/app.mjs', '/esco/catalog.mjs', '/esco/validation.mjs', '/sw.js']) {
      const r = await fetch(base + p);
      assert.equal(r.status, 200, p);
      assert.match(r.headers.get('content-security-policy'), /connect-src 'self'/);
    }
    assert.equal((await fetch(base + '/esco/refresh.mjs')).status, 404);
    assert.equal((await fetch(base + '/../../.git/config')).status, 404);
    assert.equal((await fetch(base + '/', { method: 'POST', body: 'unsafe' })).status, 405);
    const page = await (await fetch(base + '/')).text();
    assert.match(page, /Explore public skill vocabulary/);
    assert.match(page, /does not validate a candidate/i);
    const js = await readFile(new URL('../app.mjs', import.meta.url), 'utf8');
    assert.equal(/fetch\(['"]https:\/\/ec\.europa\.eu/.test(js), false);
  } finally {
    child.kill('SIGTERM');
  }
});
