import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { createServer } from 'node:http';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { diagnoseProcurement } from '../src/procurement-diagnostics.mjs';
import { parseDiagnosticArgs, runDiagnostics } from '../src/diagnose-agent.mjs';
import { FIXTURE_CATALOG, createTradeService } from '../src/core.mjs';
import { createTradeHttpServer } from '../src/server.mjs';

const milk = { family: 'dairy-milk', quantityLitres: 1000, lactoseFree: true, deliverBy: '2026-11-16' };
const oat = { ...milk, family: 'oat-drink' };
const diagnose = (extra = {}) => diagnoseProcurement({
  catalog: structuredClone(FIXTURE_CATALOG), requirements: [milk],
  budgetCents: 140_000, policyBudgetCents: 250_000, ...extra,
});
const code = (expected) => (error) => error.code === expected;

test('budget diagnosis gives the exact smallest increase without granting authority', () => {
  const result = diagnose();
  assert.equal(result.outcome, 'BUDGET_REVIEW_NEEDED');
  assert.equal(result.minimumCostCents, 177_300);
  assert.equal(result.additionalBudgetCents, 37_300);
  assert.deepEqual(result.budgetReview, {
    targetBudgetCents: 177_300, additionalCents: 37_300,
    withinExistingPolicy: true, action: 'REQUEST_BUYER_BUDGET_REVIEW',
  });
  assert.equal(result.adviceOnly, true);
  assert.equal(result.isQuote, false);
  assert.equal(result.grantsAuthority, false);
});

test('the exact-cent boundary is feasible and never implies permission to order', () => {
  const result = diagnose({ budgetCents: 177_300 });
  assert.equal(result.outcome, 'FEASIBLE_AT_SNAPSHOT');
  assert.equal(result.additionalBudgetCents, 0);
  assert.equal(result.budgetReview, null);
  assert.match(result.validity, /fresh server validation and approval/);
  assert.equal(diagnose({ budgetCents: 177_299 }).additionalBudgetCents, 1);
});

test('a cheaper incompatible or late product cannot repair a dietary/date constraint', () => {
  const result = diagnose();
  const family = result.perFamily[0];
  assert.deepEqual(family.lines.map((line) => line.sku), ['DEMO-LF-1', 'DEMO-LF-2']);
  assert.deepEqual(family.excludedProducts, [
    { sku: 'DEMO-LF-3', reasons: ['DELIVERY_TOO_LATE'] },
    { sku: 'DEMO-REG-1', reasons: ['DIETARY_MISMATCH'] },
  ]);
  assert.deepEqual(result.requirements, [milk]);
});

test('missing exact stock is not represented as a priceable complete basket', () => {
  const result = diagnose({ requirements: [{ ...milk, quantityLitres: 2000 }] });
  assert.equal(result.outcome, 'STOCK_SHORTFALL');
  assert.equal(result.missingLitres, 320);
  assert.equal(result.minimumCostCents, null);
  assert.equal(result.additionalBudgetCents, null);
  assert.equal(result.budgetReview, null);
  assert.equal(result.perFamily[0].partialBasketCostCents, 305_820);
  assert.match(result.explanation, /More budget cannot resolve/);
});

test('multi-family totals respect the existing policy ceiling without raising it', () => {
  const result = diagnose({ requirements: [milk, oat] });
  assert.equal(result.minimumCostCents, 339_300);
  assert.equal(result.outcome, 'POLICY_LIMIT_EXCEEDED');
  assert.equal(result.budgetReview.action, 'REFER_TO_POLICY_OWNER');
  assert.equal(result.budgetReview.withinExistingPolicy, false);
  assert.equal(result.policyBudgetCents, 250_000);
});

test('one family cannot consume another family stock, or reuse its own requirement twice', () => {
  const result = diagnose({
    catalog: FIXTURE_CATALOG.filter((p) => p.family === 'oat-drink'), requirements: [milk, oat],
  });
  assert.equal(result.missingLitres, 1000);
  assert.equal(result.perFamily[1].missingLitres, 0);
  assert.equal(result.minimumCostCents, null);
  assert.throws(() => diagnose({ requirements: [milk, milk] }), code('INVALID_REQUIREMENTS'));
});

test('unknown structured facts and duplicate SKUs fail instead of inventing a minimum', () => {
  for (const patch of [
    { lactoseFree: 'true' }, { version: undefined }, { priceCents: undefined },
    { unitsAvailable: -1 }, { priceCents: 1.1 }, { deliverBy: '2026-02-30' },
    { family: undefined }, { unitsAvailable: Number.MAX_SAFE_INTEGER },
  ]) {
    const catalog = structuredClone(FIXTURE_CATALOG);
    Object.assign(catalog[0], patch);
    assert.throws(() => diagnose({ catalog }), code('INVALID_CATALOG'));
  }
  assert.throws(() => diagnose({ catalog: [FIXTURE_CATALOG[0], FIXTURE_CATALOG[0]] }), code('INVALID_CATALOG'));
});

test('budget coercion, unsupported dates and hidden requirement fields are refused', () => {
  for (const budgetCents of ['140000', 1.5, NaN, -1, 0, 250_001]) {
    assert.throws(() => diagnose({ budgetCents }), code('INVALID_BUDGET'));
  }
  for (const need of [{ ...milk, quantityLitres: 1.5 }, { ...milk, approved: true },
    { ...milk, deliverBy: '2026-11-17' }, { ...milk, lactoseFree: undefined }]) {
    assert.throws(() => diagnose({ requirements: [need] }), code('INVALID_REQUIREMENTS'));
  }
});

test('empty and sold-out snapshots retain the precise missing quantity', () => {
  for (const catalog of [[], FIXTURE_CATALOG.map((p) => ({ ...p, unitsAvailable: 0 }))]) {
    const result = diagnose({ catalog });
    assert.equal(result.outcome, 'STOCK_SHORTFALL');
    assert.equal(result.missingLitres, 1000);
    assert.equal(result.minimumCostCents, null);
  }
});

test('minimum cost matches an exhaustive small-inventory oracle, including permutations', () => {
  for (let stockA = 0; stockA <= 2; stockA++) for (let stockB = 0; stockB <= 2; stockB++) {
    for (let priceA = 1; priceA <= 3; priceA++) for (let priceB = 1; priceB <= 3; priceB++) {
      for (let quantity = 1; quantity <= 4; quantity++) {
        const catalog = [
          { ...FIXTURE_CATALOG[0], sku: 'A', unitsAvailable: stockA, priceCents: priceA },
          { ...FIXTURE_CATALOG[0], sku: 'B', unitsAvailable: stockB, priceCents: priceB },
        ];
        const feasibleCosts = [];
        for (let a = 0; a <= stockA; a++) for (let b = 0; b <= stockB; b++) {
          if (a + b === quantity) feasibleCosts.push(a * priceA + b * priceB);
        }
        const input = { catalog, requirements: [{ ...milk, quantityLitres: quantity }] };
        const result = diagnose(input);
        assert.equal(result.minimumCostCents, feasibleCosts.length ? Math.min(...feasibleCosts) : null);
        assert.deepEqual(diagnose({ ...input, catalog: [...catalog].reverse() }), result);
      }
    }
  }
});

test('diagnosis is pure and carries the exact stock/price versions used', () => {
  const catalog = Object.freeze(FIXTURE_CATALOG.map((p) => Object.freeze({ ...p })));
  const before = structuredClone(catalog);
  const result = diagnose({ catalog });
  assert.deepEqual(catalog, before);
  assert.equal(result.sourceVersions.find((p) => p.sku === 'DEMO-LF-1').version, 1);
  const changed = diagnose({ catalog: before.map((p) => p.sku === 'DEMO-LF-1' ? { ...p, priceCents: 175, version: 2 } : p) });
  assert.equal(changed.minimumCostCents - result.minimumCostCents, 780);
  assert.equal(changed.sourceVersions.find((p) => p.sku === 'DEMO-LF-1').version, 2);
});

test('CLI options reject ambiguous, decimal, exponent, duplicated and empty requests', () => {
  assert.deepEqual(parseDiagnosticArgs([]), { milk: 1000, oat: 0, budgetCents: undefined });
  assert.deepEqual(parseDiagnosticArgs(['--oat-litres=240']), { milk: 0, oat: 240, budgetCents: undefined });
  for (const args of [['--milk-litres=1.5'], ['--milk-litres=1e3'], ['--milk-litres=-1'],
    ['--milk-litres=2', '--milk-litres=3'], ['--milk-litres=0', '--oat-litres=0'],
    ['--approve'], ['--budget-cents=0'], ['--oat-litres=10001']]) {
    assert.throws(() => parseDiagnosticArgs(args), code('INVALID_ARGUMENT'));
  }
});

async function withServer(server, run) {
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  try { await run('http://127.0.0.1:' + server.address().port); }
  finally { await new Promise((done) => server.close(done)); }
}

test('independent buyer process performs only four real GETs; stock, policy and audit stay unchanged', async () => {
  const service = createTradeService();
  const server = createTradeHttpServer(service);
  const received = [];
  server.on('request', (req) => received.push({ method: req.method, path: req.url, authorization: req.headers.authorization }));
  const before = { catalog: service.catalog(), policy: service.policy(), audit: service.audit() };
  await withServer(server, async (supplierUrl) => {
    const script = fileURLToPath(new URL('../src/diagnose-agent.mjs', import.meta.url));
    const { stdout, stderr } = await promisify(execFile)(process.execPath, [script, '--milk-litres=1000', '--budget-cents=140000'], {
      env: { ...process.env, SUPPLIER_URL: supplierUrl }, timeout: 10_000, maxBuffer: 262_144,
    });
    assert.equal(stderr, '');
    const result = JSON.parse(stdout);
    assert.equal(result.outcome, 'BUDGET_REVIEW_NEEDED');
    assert.equal(result.additionalBudgetCents, 37_300);
    assert.deepEqual(result.requests.map((req) => req.method), ['GET', 'GET', 'GET', 'GET']);
    assert.deepEqual(received.map((req) => req.path), ['/.well-known/trusted-trade', '/openapi.json', '/api/policy', '/api/catalog']);
    assert.ok(received.every((req) => req.method === 'GET' && req.authorization === undefined));
  });
  assert.deepEqual({ catalog: service.catalog(), policy: service.policy(), audit: service.audit() }, before);
});

test('diagnostic client refuses external origins and discovery redirection before following them', async () => {
  await assert.rejects(runDiagnostics({ supplierUrl: 'https://supplier-demo.invalid' }), code('LOCALHOST_ONLY'));
  await assert.rejects(runDiagnostics({ supplierUrl: 'http://user:pass@127.0.0.1:4177' }), code('LOCALHOST_ONLY'));
  let reads = 0;
  const server = createServer((req, res) => {
    reads++;
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ mode: 'SYNTHETIC_NONCOMMERCIAL', fixtureDeliveryDate: '2026-11-16',
      openapi: '//127.0.0.1:1/forged-spec' }));
  });
  await withServer(server, async (supplierUrl) => {
    await assert.rejects(runDiagnostics({ supplierUrl }), code('DISCOVERY_REFUSED'));
  });
  assert.equal(reads, 1);
});

test('HTTP redirects and unlabelled catalogs are never accepted as fixture evidence', async () => {
  let reads = 0;
  const redirect = createServer((req, res) => {
    reads++;
    res.writeHead(302, { Location: '/should-not-follow' });
    res.end();
  });
  await withServer(redirect, async (supplierUrl) => {
    await assert.rejects(runDiagnostics({ supplierUrl }));
  });
  assert.equal(reads, 1);
  const unlabelled = createServer((req, res) => {
    res.setHeader('Content-Type', 'application/json');
    const body = req.url === '/.well-known/trusted-trade' ? {
      mode: 'SYNTHETIC_NONCOMMERCIAL', fixtureDeliveryDate: '2026-11-16',
      openapi: '/openapi.json', endpoints: { catalog: '/api/catalog', policy: '/api/policy' },
    } : req.url === '/openapi.json' ? { paths: { '/api/catalog': { get: {} }, '/api/policy': { get: {} } } } :
      req.url === '/api/policy' ? { perOrderBudgetCents: 250_000 } : { products: FIXTURE_CATALOG };
    res.end(JSON.stringify(body));
  });
  await withServer(unlabelled, async (supplierUrl) => {
    await assert.rejects(runDiagnostics({ supplierUrl }), code('SUPPLIER_MODE_REFUSED'));
  });
});
