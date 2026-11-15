/** Independent deterministic buyer agent: HTTP only, never imports supplier/core. */
import { createInterface } from 'node:readline/promises';
import { stdin, stdout } from 'node:process';
import { randomUUID } from 'node:crypto';
import assert from 'node:assert/strict';
import { verifyBuyerTerms, verifyBuyerBody } from './buyer-terms.mjs';

const args = process.argv.slice(2);
const scenario = args.find((x) => ['success', 'refusal', 'replay', 'stale'].includes(x)) ?? 'success';
const base = new URL(process.env.SUPPLIER_URL ?? 'http://127.0.0.1:4177');
if (base.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname) || base.username || base.password) throw new Error('Localhost HTTP supplier only.');
let token;
const timings = [];
const api = async (path, payload, expectedCode) => {
  const url = new URL(path, base);
  if (url.origin !== base.origin) throw new Error('Discovery cannot redirect buyer authority to another origin.');
  const started = performance.now();
  const response = await fetch(url, { method: payload === undefined ? 'GET' : 'POST', redirect: 'error', signal: AbortSignal.timeout(5000),
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: payload === undefined ? undefined : JSON.stringify(payload) });
  const body = await response.json();
  timings.push({ method: payload === undefined ? 'GET' : 'POST', path, elapsed_ms: +(performance.now() - started).toFixed(3), status: response.status });
  if (expectedCode) { assert.equal(body.error?.code, expectedCode); assert.ok(!response.ok); }
  else if (!response.ok) throw new Error(`${body.error?.code}: ${body.error?.message}`);
  return body;
};
const started = performance.now();
const discovery = await api('/.well-known/trusted-trade');
assert.equal(discovery.mode, 'SYNTHETIC_NONCOMMERCIAL');
const spec = await api(discovery.openapi);
const routes = discovery.endpoints;
for (const route of Object.values(routes)) assert.ok(spec.paths[route], `Undocumented route ${route}`);
const policy = await api(routes.policy);
const catalog = await api(routes.catalog);
assert.equal(catalog.mode, 'INVENTED_FIXTURE');
const family = args.includes('--oat') ? 'oat-drink' : 'dairy-milk';
assert.ok(catalog.products.some((p) => p.family === family && Number.isSafeInteger(p.priceCents) && p.version > 0));
const buyerId = policy.buyerId;
({ token } = await api(routes.session, { buyerId }));
const need = { family, quantityLitres: 1000, lactoseFree: true, deliverBy: discovery.fixtureDeliveryDate };
const quoteRequest = { buyerId, need, budgetCents: policy.perOrderBudgetCents };
if (scenario === 'refusal') {
  await api(routes.quotes, { ...quoteRequest, budgetCents: 1 }, 'BUDGET_EXCEEDED');
} else {
  const { quote } = await api(routes.quotes, quoteRequest);
  for (const line of quote.lines) {
    const fact = catalog.products.find((p) => p.sku === line.sku);
    assert.ok(fact && fact.family === family && fact.lactoseFree && fact.deliverBy <= need.deliverBy);
    assert.equal(line.unitPriceCents, fact.priceCents);
    assert.equal(line.stockVersion, fact.version);
    assert.ok(line.quantityLitres <= fact.unitsAvailable);
  }
  verifyBuyerTerms(quote, policy, { requirements: [need], budgetCents: quoteRequest.budgetCents });
  assert.equal(quote.lines.reduce((sum, line) => sum + line.quantityLitres, 0), need.quantityLitres);
  stdout.write(`SYNTHETIC ${quote.id}: ${quote.totalCents} EUR cents. ${quote.explanation}\n`);
  const interop = await api(`${routes.quotes}/${quote.id}/body`);
  assert.equal(interop.signature, 'UNSIGNED');
  assert.equal(interop.body.total_cents, quote.totalCents);
  verifyBuyerBody(interop.body, quote);
  const orderRequest = { buyerId, quoteId: quote.id, idempotencyKey: randomUUID() };
  if (quote.approvalRequired) {
    await api(routes.orders, orderRequest, 'APPROVAL_REQUIRED');
    let decision = args.find((x) => x.startsWith('--decision='))?.split('=')[1];
    if (!decision) {
      const rl = createInterface({ input: stdin, output: stdout });
      try { decision = (await rl.question('SYNTHETIC human decision only; no purchase. Type approve or reject: ')).trim(); }
      finally { rl.close(); }
    }
    assert.ok(['approve', 'reject'].includes(decision), 'Explicit approve/reject required (or --decision=approve for scripted SYNTHETIC tests).');
    await api(`${routes.quotes}/${quote.id}/approval`, { buyerId, decision, approver: 'CLI synthetic human (UNAUTHENTICATED)' });
    if (decision === 'reject') {
      await api(routes.orders, orderRequest, 'APPROVAL_REJECTED');
      stdout.write(JSON.stringify({ mode: 'SYNTHETIC', scenario, outcome: 'HUMAN_REJECTED', requests: timings }) + '\n');
      process.exit(0);
    }
  }
  if (scenario === 'stale') {
    const line = quote.lines[0];
    await api(routes.reprice, { sku: line.sku, priceCents: line.unitPriceCents + 1 });
    await api(routes.orders, orderRequest, 'QUOTE_STALE');
  } else {
    const { order } = await api(routes.orders, orderRequest);
    assert.equal(order.status, 'SIMULATED_COMMITTED');
    assert.equal((await api(`${routes.orders}/${order.id}`)).order.id, order.id);
    if (scenario === 'replay') {
      const replay = await api(routes.orders, orderRequest);
      assert.equal(replay.order.id, order.id);
      assert.equal(replay.order.idempotentReplay, true);
      await api(routes.orders, { ...orderRequest, idempotencyKey: randomUUID() }, 'ALREADY_COMMITTED');
      const next = (await api(routes.quotes, { ...quoteRequest, need: { ...need, quantityLitres: 1 } })).quote;
      await api(routes.orders, { ...orderRequest, quoteId: next.id }, 'IDEMPOTENCY_CONFLICT');
    }
    stdout.write(`SIMULATED receipt ${order.id}; quote ${order.quoteId}; no commercial order.\n`);
  }
}
const audit = await api(routes.audit);
stdout.write(JSON.stringify({ mode: 'SYNTHETIC', scenario, manual_baseline: 'UNMEASURED', elapsed_ms_including_human: +(performance.now() - started).toFixed(3), processing_ms: +timings.reduce((sum, x) => sum + x.elapsed_ms, 0).toFixed(3), requests: timings, audit_receipts: audit.receipts.length }) + '\n');
