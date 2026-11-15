import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { createTradeHttpServer } from '../src/server.mjs';
import { createTradeService } from '../src/core.mjs';

const buyerId = 'helsinki-hotel-demo';
const requirements = [
  { family: 'dairy-milk', lactoseFree: true, quantityLitres: 480, deliverBy: '2026-11-16' },
  { family: 'oat-drink', lactoseFree: true, quantityLitres: 240, deliverBy: '2026-11-16' },
];

async function fixture(fn) {
  const service = createTradeService();
  const server = createTradeHttpServer(service);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const call = async (path, data, token) => {
    const result = await fetch(base + path, { method: data === undefined ? 'GET' : 'POST',
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: data === undefined ? undefined : JSON.stringify(data) });
    return { status: result.status, ...await result.json() };
  };
  const session = () => call('/api/demo/session', { buyerId }).then((x) => x.token);
  try { return await fn({ base, call, session, service }); }
  finally { await new Promise((resolve) => server.close(resolve)); }
}

test('portfolio never commits through HTTP without a separate agent-signed handshake', async () => fixture(async ({ call, session }) => {
  const token = await session();
  const plan = (await call('/api/plans', { buyerId, requirements, budgetCents: 175000 }, token)).plan;
  const q = (await call(`/api/plans/${plan.id}/quotes`, { buyerId, optionId: plan.recommendedOptionId }, token)).quote;
  assert.equal((await call('/api/orders', { buyerId, quoteId: q.id, idempotencyKey: 'try-order-without-handshake' }, token)).error.code, 'HANDSHAKE_REQUIRED');
  assert.equal((await call(`/api/quotes/${q.id}/offer`, { buyerId }, token)).error.code, 'APPROVAL_REQUIRED');
  assert.equal((await call(`/api/quotes/${q.id}/handshake`, { buyerId, signedMandate: {} }, token)).error.code, 'APPROVAL_REQUIRED');
  const approve = await call(`/api/quotes/${q.id}/approval`, { buyerId, decision: 'approve' }, token);
  assert.equal(approve.quote.status, 'APPROVED');
  assert.equal((await call(`/api/quotes/${q.id}/handshake`, { buyerId, signedMandate: {} }, token)).error.code, 'BUYER_KEY_REQUIRED');
  const otherSession = await session();
  assert.equal((await call(`/api/quotes/${q.id}/offer`, { buyerId }, otherSession)).error.code, 'BUYER_MISMATCH');
  assert.equal((await call(`/api/plans/${plan.id}/recover`, { buyerId }, otherSession)).error.code, 'BUYER_MISMATCH');
  assert.equal((await call(`/api/plans/${plan.id}/quotes`, { buyerId, optionId: 'cost', totalCents: 1 }, token)).error.code, 'ORDER_TERMS_FORBIDDEN');
}));

test('entire autonomous frontend is served with strict CSP, including a documented no-commercial-effects warning', async () => fixture(async ({ base }) => {
  const html = await fetch(base + '/mission');
  assert.equal(html.status, 200);
  const text = await html.text();
  assert.match(text, /DEMONSTRATION ONLY/);
  assert.match(text, /proves itself/);
  assert.match(text, /zero commercial effects/);
  assert.match(html.headers.get('content-security-policy'), /script-src 'self'/);
  for (const path of ['/mission.js', '/mission.css', '/app.js', '/style.css', '/classic']) {
    const response = await fetch(base + path);
    assert.equal(response.status, 200);
    assert.ok((await response.text()).length > 200);
  }
  const apiSpec = await (await fetch(base + '/openapi.json')).json();
  for (const path of ['/api/plans', '/api/plans/{id}/quotes', '/api/plans/{id}/recover', '/api/quotes/{id}/offer', '/api/quotes/{id}/handshake', '/api/trust/buyer-key', '/api/demo/shock', '/api/audit/verify']) {
    assert.ok(apiSpec.paths[path], `Missing documented actual route ${path}`);
  }
}));

test('independent buyer process executes five real HTTP portfolio, authorization and recovery scenarios', { timeout: 30000 }, async () => {
  for (const scenario of ['happy', 'replay', 'shock', 'refusal', 'reject']) {
    await fixture(async ({ base, service }) => {
      const { stdout } = await promisify(execFile)(process.execPath,
        [fileURLToPath(new URL('../src/frontier-agent.mjs', import.meta.url)), scenario, '--decision=' + (scenario === 'reject' ? 'reject' : 'approve')],
        { env: { ...process.env, SUPPLIER_URL: base }, timeout: 10000 });
      const report = JSON.parse(stdout.trim().split('\n').at(-1));
      assert.equal(report.actor, 'INDEPENDENT_BUYER_PROCESS');
      assert.equal(report.mode, 'SYNTHETIC');
      assert.ok(report.HTTP_requests.some((request) => request.path === '/.well-known/trusted-trade'));
      assert.ok(report.HTTP_requests.some((request) => request.path === '/api/trust/buyer-key'));
      assert.equal(service.audit().filter((receipt) => receipt.event === 'ORDER_SIMULATED').length,
        ['happy', 'replay', 'shock'].includes(scenario) ? 1 : 0);
      assert.equal(service.audit().filter((receipt) => receipt.event === 'TRUST_HANDSHAKE_VERIFIED').length,
        ['happy', 'replay', 'shock'].includes(scenario) ? 1 : 0);
      if (scenario === 'shock') {
        assert.ok(report.HTTP_requests.some((request) => request.path.endsWith('/recover')));
        assert.ok(service.audit().some((receipt) => receipt.event === 'DEMO_SUPPLIER_DISRUPTION'));
        assert.ok(service.audit().some((receipt) => receipt.event === 'SUPPLY_SELF_HEALED'));
      }
    });
  }
});
