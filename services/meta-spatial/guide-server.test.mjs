import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { createGuideServer } from './guide-server.mjs';

test('Guide serves only fixed assets from its exact loopback origin', async () => {
  const server = createGuideServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  const request = (path, headers = {}, method = 'GET') => new Promise((resolve, reject) => {
    const req = http.request({ hostname: '127.0.0.1', port, path, method, headers }, response => {
      let body = '';
      response.on('data', chunk => { body += chunk; });
      response.on('end', () => resolve({ status: response.statusCode, headers: response.headers, body }));
    });
    req.on('error', reject); req.end();
  });
  try {
    for (const path of ['/guide/', '/guide/index.html', '/guide/guide-app.mjs',
      '/guide/guide-core.mjs', '/guide/context-handoff.mjs', '/guide/guide-storage.mjs',
      '/guide/capture.mjs', '/guide/guide-webmcp.mjs', '/guide/guide.css']) {
      const result = await request(path);
      assert.equal(result.status, 200, path);
      assert.ok(result.body.length > 0);
      assert.equal(result.headers['cache-control'], 'no-store');
      assert.equal(result.headers['permissions-policy'], 'camera=(self), microphone=(), geolocation=()');
    }
    for (const path of ['/guide/../../AGENTS.md', '/guide/%2e%2e/AGENTS.md',
      '/guide/guide-core.test.mjs', '/guide/README.md', '/api/observe']) {
      assert.equal((await request(path)).status, 404, path);
    }
    assert.equal((await request('/guide/', { Origin: 'https://example.invalid' })).status, 403);
    assert.equal((await request('/guide/', { Host: 'localhost:' + port })).status, 403);
    assert.equal((await request('/guide/', { 'Sec-Fetch-Site': 'cross-site' })).status, 403);
    assert.equal((await request('/guide/', {}, 'POST')).status, 404);
  } finally {
    server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
  }
});
