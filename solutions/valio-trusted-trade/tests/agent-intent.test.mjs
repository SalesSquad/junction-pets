import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { createTradeService, FIXTURE_CATALOG, FIXTURE_POLICY } from '../src/core.mjs';
import { createTradeHttpServer } from '../src/server.mjs';
import { verifyBuyerTerms, verifyBuyerBody } from '../src/buyer-terms.mjs';
import { runDiagnostics } from '../src/diagnose-agent.mjs';
import { unsignedQuoteBody } from '../src/core.mjs';

const need = { family: 'dairy-milk', quantityLitres: 12, lactoseFree: true, deliverBy: '2026-11-16' };
const policy = { ...FIXTURE_POLICY, deliveryFeeCents: 99, taxBps: 2500 };
const buyerId = FIXTURE_POLICY.buyerId;
const intent = { requirements: [need], budgetCents: 250000 };
const single = () => createTradeService({ policy }).requestQuote({ buyerId, need });
const retotal = (quote, terms = policy) => {
  const subtotal = quote.lines.reduce((sum, line) => sum + line.quantityLitres * line.unitPriceCents, 0);
  quote.lines.forEach((line) => { line.totalCents = line.quantityLitres * line.unitPriceCents; });
  const base = subtotal + terms.deliveryFeeCents;
  const tax = Number((BigInt(base) * BigInt(terms.taxBps) + 5000n) / 10000n);
  quote.costBreakdown = { subtotalCents: subtotal, deliveryFeeCents: terms.deliveryFeeCents, taxCents: tax, taxBps: terms.taxBps };
  quote.totalCents = base + tax;
};
const lineFor = (source, quantityLitres) => ({
  sku: source.sku, name: source.name, family: source.family, supplierId: source.supplierId,
  quantityLitres, packs: quantityLitres / source.packLitres, packLitres: source.packLitres,
  minOrderPacks: source.minOrderPacks, unitPriceCents: source.priceCents,
  totalCents: quantityLitres * source.priceCents, stockVersion: source.version,
  certification: source.certification, deliverBy: source.deliverBy,
});

test('caller-owned single-family intent and charged quote pass before approval', () => {
  const quote = single();
  verifyBuyerTerms(quote, policy, intent);
  verifyBuyerTerms(quote, policy); // Existing pricing-only library callers remain compatible.
  verifyBuyerBody(unsignedQuoteBody(quote), quote);
});

test('charged mixed-pack portfolio fulfils every independently requested family exactly', () => {
  const catalog = FIXTURE_CATALOG.map((p) => ({ ...p,
    packLitres: p.sku === 'DEMO-LF-1' ? 6 : p.sku === 'DEMO-LF-2' ? 4 : p.family === 'oat-drink' ? 5 : 1,
    minOrderPacks: p.sku === 'DEMO-LF-1' ? 2 : 1,
  }));
  const requirements = [need, { ...need, family: 'oat-drink', quantityLitres: 10 }];
  const service = createTradeService({ policy, initialCatalog: catalog });
  const plan = service.planBasket({ buyerId, requirements, budgetCents: 50000 });
  const quote = service.quoteBasketPlan({ buyerId, planId: plan.id, optionId: 'cost' });
  verifyBuyerTerms(quote, policy, { requirements, budgetCents: 50000 });
  verifyBuyerBody(unsignedQuoteBody(quote), quote);
  assert.equal(quote.costBreakdown.subtotalCents, 3708);
  assert.equal(quote.totalCents, 4759);
  assert.ok(quote.lines.some((line) => line.packLitres === 6 && line.packs === 2));
  assert.ok(quote.lines.some((line) => line.packLitres === 5 && line.packs === 2));
});

test('a self-consistent cheaper underfill or overfill cannot replace original intent', () => {
  for (const quantity of [11, 13]) {
    const quote = single();
    quote.lines[0].quantityLitres = quantity;
    quote.lines[0].packs = quantity;
    retotal(quote);
    assert.throws(() => verifyBuyerTerms(quote, policy, intent), /Exactly requested volume/);
  }
});

test('self-consistent wrong family, unsupported diet and late delivery are rejected', () => {
  for (const sku of ['DEMO-OAT-1', 'DEMO-REG-1', 'DEMO-LF-3']) {
    const quote = single();
    const source = FIXTURE_CATALOG.find((p) => p.sku === sku);
    if (!quote.sourceSnapshot.products.some((p) => p.sku === sku)) quote.sourceSnapshot.products.push(structuredClone(source));
    quote.lines = [lineFor(source, need.quantityLitres)];
    retotal(quote);
    assert.throws(() => verifyBuyerTerms(quote, policy, intent));
  }
});

test('supplier-controlled request echoes cannot redefine the caller-owned requirement', () => {
  for (const field of ['requested', 'constraints']) {
    const quote = single();
    if (field === 'requested') quote.requested.quantityLitres = 11;
    else quote.sourceSnapshot.constraints.quantityLitres = 11;
    assert.throws(() => verifyBuyerTerms(quote, policy, intent), /match original intent/);
  }
});

test('duplicate quote/source SKUs and untyped eligibility facts fail closed', () => {
  const split = single();
  split.lines = [lineFor(split.sourceSnapshot.products[0], 6), lineFor(split.sourceSnapshot.products[0], 6)];
  retotal(split);
  assert.throws(() => verifyBuyerTerms(split, policy, intent), /unique/);
  const duplicateSource = single();
  duplicateSource.sourceSnapshot.products.push(structuredClone(duplicateSource.sourceSnapshot.products[0]));
  assert.throws(() => verifyBuyerTerms(duplicateSource, policy, intent), /unique/);
  for (const patch of [{ lactoseFree: 'true' }, { deliverBy: 'tomorrow' },
    { unitsAvailable: '780' }, { packLitres: undefined }, { priceCents: NaN }]) {
    const quote = single();
    Object.assign(quote.sourceSnapshot.products.find((p) => p.sku === quote.lines[0].sku), patch);
    assert.throws(() => verifyBuyerTerms(quote, policy, intent), /explicit typed values/);
  }
});

test('policy and original declared ceilings are both enforced independently of quote fields', () => {
  const quote = single();
  assert.throws(() => verifyBuyerTerms(quote, policy, { ...intent, budgetCents: quote.totalCents - 1 }), /original caller-owned budget/);
  assert.throws(() => verifyBuyerTerms(quote, { ...policy, perOrderBudgetCents: quote.totalCents - 1 }, intent), /policy budget ceiling/);
  for (const malformed of [{}, { requirements: [need, need], budgetCents: 250000 },
    { requirements: [{ ...need, quantityLitres: 1.5 }], budgetCents: 250000 },
    { requirements: [{ ...need, lactoseFree: undefined }], budgetCents: 250000 },
    { requirements: [need], budgetCents: '250000' }]) {
    assert.throws(() => verifyBuyerTerms(quote, policy, malformed));
  }
});

test('forged delivery, tax, unit price, quantity and stock cannot pass intent checks', () => {
  for (const change of [
    (q) => { q.costBreakdown.deliveryFeeCents = 0; },
    (q) => { q.costBreakdown.taxCents -= 1; },
    (q) => { q.lines[0].packLitres = 1.5; },
    (q) => { q.lines[0].unitPriceCents -= 1; retotal(q); },
    (q) => { q.lines[0].stockVersion += 1; },
    (q) => { q.lines[0].family = 'oat-drink'; },
    (q) => { q.sourceSnapshot.products.find((p) => p.sku === q.lines[0].sku).unitsAvailable = 0; },
  ]) {
    const quote = single(); change(quote);
    assert.throws(() => verifyBuyerTerms(quote, policy, intent));
  }
});

async function fixture(service, run) {
  const server = createTradeHttpServer(service);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  try { await run({ server, base: 'http://127.0.0.1:' + server.address().port }); }
  finally { server.closeAllConnections(); await new Promise((done) => server.close(done)); }
}

test('read-only diagnostic CLI includes the same declared delivery/tax terms as the supplier', async () => {
  const charged = { ...FIXTURE_POLICY, deliveryFeeCents: 1200, taxBps: 2500 };
  const service = createTradeService({ policy: charged });
  await fixture(service, async ({ base }) => {
    const result = await runDiagnostics({ supplierUrl: base, args: ['--milk-litres=1000', '--budget-cents=140000'] });
    assert.equal(result.minimumCostCents, 223125);
    assert.equal(result.additionalBudgetCents, 83125);
    assert.equal(result.costBreakdown.deliveryFeeCents, 1200);
    assert.equal(result.costBreakdown.taxCents, 44625);
    assert.equal(service.audit().length, 0, 'Diagnostics still creates no session, quote, approval or order');
  });
});

test('independent frontier process refuses a supplier underfill before approving or signing', async () => {
  const service = createTradeService();
  await fixture(service, async ({ server, base }) => {
    server.on('request', (request, response) => {
      if (request.method !== 'POST' || !/^\/api\/plans\/[^/]+\/quotes$/.test(request.url)) return;
      const end = response.end;
      response.end = function (data, ...args) {
        const body = JSON.parse(data);
        if (body.quote) {
          const line = body.quote.lines[0];
          line.quantityLitres -= line.packLitres;
          line.packs -= 1;
          retotal(body.quote, FIXTURE_POLICY);
          data = JSON.stringify(body);
        }
        return end.call(this, data, ...args);
      };
    });
    const script = fileURLToPath(new URL('../src/frontier-agent.mjs', import.meta.url));
    await assert.rejects(promisify(execFile)(process.execPath, [script, 'happy', '--decision=approve'], {
      env: { ...process.env, SUPPLIER_URL: base }, timeout: 10000, maxBuffer: 262144,
    }), (error) => error.code === 1 && error.stderr.includes('Exactly requested volume'));
    assert.equal(service.audit().filter((event) => ['HUMAN_DECISION_SIMULATED', 'ORDER_SIMULATED', 'KATTELY_HANDSHAKE_VERIFIED'].includes(event.event)).length, 0);
  });
});
