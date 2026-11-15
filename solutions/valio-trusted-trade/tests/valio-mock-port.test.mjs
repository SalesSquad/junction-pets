import test from 'node:test';
import assert from 'node:assert/strict';
import { createValioMockPort } from '../src/valio-mock-port.mjs';
const request = { products: ['1001'], requestedDate: '2026-11-16' };
const json = (value, status = 200, headers = {}) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json', ...headers } });
const port = (fetchImpl, extra = {}) => createValioMockPort({ customer: 'fixed-test-customer', apiKey: () => 'test-key', fetchImpl, timeoutMs: 100, ...extra });

test('sponsor request refuses caller authority/configuration and bulk or malformed reads', async () => {
  let calls = 0;
  const adapter = port(async () => { calls++; throw Error('must not call'); });
  for (const invalid of [{ ...request, customer: 'other' }, { ...request, apiKey: 'other' }, { ...request, endpoint: 'https://elsewhere.invalid' }, { ...request, products: [] }, { ...request, products: ['name@example.invalid'] }, { ...request, products: ['https://example.invalid'] }, { ...request, products: ['1234567890123'] }, { ...request, products: Array.from({ length: 21 }, (_, i) => String(i)) }, { ...request, products: ['1001', '1001'] }, { ...request, requestedDate: '2026-02-30' }]) await assert.rejects(adapter.observe(invalid), { code: 'INVALID_SPONSOR_REQUEST' });
  assert.equal(calls, 0);
  assert.equal(adapter.placeOrder, undefined);
});

test('sponsor reads bound bytes, reject malformed/media/status and redact transport secrets', async () => {
  for (const make of [() => json([]), () => new Response('bad', { headers: { 'Content-Type': 'text/html' } }), () => new Response('{', { headers: { 'Content-Type': 'application/json' } })]) await assert.rejects(port(async () => make()).observe(request), { code: 'SPONSOR_SCHEMA_INVALID' });
  await assert.rejects(port(async () => new Response(' '.repeat(524289), { headers: { 'Content-Type': 'application/json' } })).observe(request), { code: 'SPONSOR_RESPONSE_TOO_LARGE' });
  await assert.rejects(port(async () => { throw Error('test-key SECRET body'); }).observe(request), (error) => error.code === 'SPONSOR_UNAVAILABLE' && !JSON.stringify(error).includes('test-key') && !error.message.includes('SECRET'));
  await assert.rejects(port(async () => json({ secret: 'never expose' }, 429, { 'Retry-After': '999' })).observe(request), (error) => error.code === 'SPONSOR_UNAVAILABLE' && error.details.retryable && error.details.retryAfterSeconds === 60 && !error.message.includes('never expose'));
});

test('sponsor deadlines cover ignored abort on fetch, key provider and body without automatic retry', async () => {
  for (const fetchImpl of [() => new Promise(() => {}), async () => new Response(new ReadableStream({ start() {} }), { headers: { 'Content-Type': 'application/json' } })]) await assert.rejects(port(fetchImpl).observe(request), { code: 'SPONSOR_TIMEOUT' });
  await assert.rejects(port(async () => json({}), { apiKey: () => new Promise(() => {}) }).observe(request), { code: 'SPONSOR_TIMEOUT' });
});

test('transport uses fixed sponsor origin/customer, read POST, no redirects or retries', async () => {
  const calls = [];
  const adapter = port(async (url, init) => { calls.push({ url, init }); return json({}, 503); });
  await assert.rejects(adapter.observe(request), { code: 'SPONSOR_UNAVAILABLE' });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'https://junction26.valioaimo.fi/api/availability');
  assert.equal(calls[0].init.redirect, 'error');
  assert.equal(calls[0].init.method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].init.body), { customer: 'fixed-test-customer', ...request });
  await assert.rejects(port(async () => json({ echoedCredential: 'test-key' })).observe(request), { code: 'SPONSOR_SCHEMA_INVALID' });
});

const availabilityFixture = {"timeNow": "2026-11-15T05:53:06+0200", "requestedDate": "2026-11-16T00:00:00+0200", "products": [{"productId": "460032", "closingTime": "2026-11-12T15:00:00+0200", "salesBlock": false, "logisticModel": "Terminal", "scheduleLines": [{"salesBlock": false, "availableAmount": 999999, "availableDate": "2026-11-16", "salesUnit": "SK"}]}]};
const pricesFixture = {"customerId": "fixed-test-customer", "currency": "EUR", "pricingDate": "2026-11-16T00:00:00+0200", "products": [{"productId": "460032", "quantity": 1, "catalogPrice": {"value": 174.29, "valueWithTax": 197.82, "validFrom": "2025-09-01T00:00:00+0300", "validTo": "9999-12-31T00:00:00+0200", "currency": "EUR"}, "priceWithTax": {"value": 197.82, "validFrom": "2025-09-01T00:00:00+0300", "validTo": "9999-12-31T00:00:00+0200", "currency": "EUR"}, "comparisonPrice": {"value": 6.97, "valueWithTax": 7.91, "validFrom": "2025-09-01T00:00:00+0300", "validTo": "9999-12-31T00:00:00+0200", "currency": "EUR"}, "comparisonUnit": "KG", "tax": {"taxRate": 13.5, "taxValue": 23.53}, "listPrice": {"value": 205.05, "valueWithTax": 232.73, "validFrom": "2025-09-01T00:00:00+0300", "validTo": "9999-12-31T00:00:00+0200", "currency": "EUR"}, "netPriceFound": false, "error": false}]};

test('official sanitized sample remains opaque, date-bound and hash-provenanced', async () => {
  const calls = [];
  const adapter = port(async (url, init) => { calls.push({ url, init }); return json(url.endsWith('/availability') ? availabilityFixture : pricesFixture); }, { clock: () => Date.UTC(2026, 10, 15) });
  const result = await adapter.observe({ ...request, products: ['460032'] });
  assert.deepEqual(result.availability, availabilityFixture);
  assert.deepEqual(result.prices, pricesFixture);
  assert.equal(result.mode, 'SPONSOR_MOCK_READ_ONLY');
  assert.equal(result.requiresTradeCoreValidation, true);
  assert.equal(result.provenance.provider, 'VALIO_JUNCTION_MOCK_API');
  assert.match(result.provenance.availability.sha256, /^[a-f0-9]{64}$/);
  assert.match(result.provenance.prices.sha256, /^[a-f0-9]{64}$/);
  assert.equal(result.availability.products[0].scheduleLines[0].availableAmount, 999999);
  assert.equal(result.prices.products[0].netPriceFound, false);
  assert.equal(result.prices.products[0].catalogPrice.value, 174.29);
  assert.equal(result.stock, undefined);
  assert.equal(result.order, undefined);
  assert.equal(calls.length, 2);
  assert.equal(calls[1].url, 'https://junction26.valioaimo.fi/api/price');
  assert.equal(JSON.stringify(result).includes('test-key'), false);
});

test('source response binding refuses stale dates, foreign IDs/customer and typed fact corruption', async () => {
  const cases = [
    ['availability', (v) => { v.requestedDate = '2026-11-17'; }],
    ['availability', (v) => { v.requestedDate = '2026-11-16Tinvalid'; }],
    ['availability', (v) => { v.products[0].productId = 'foreign'; }],
    ['availability', (v) => { v.products[0].salesBlock = 'false'; }],
    ['availability', (v) => { v.products[0].scheduleLines[0].availableAmount = '999999'; }],
    ['prices', (v) => { v.customerId = 'foreign'; }],
    ['prices', (v) => { v.products[0].quantity = '1'; }],
    ['prices', (v) => { v.products[0].error = 'false'; }],
  ];
  for (const [target, mutate] of cases) {
    const a = structuredClone(availabilityFixture), p = structuredClone(pricesFixture);
    mutate(target === 'availability' ? a : p);
    await assert.rejects(port(async (url) => json(url.endsWith('/availability') ? a : p)).observe({ ...request, products: ['460032'] }), { code: 'SPONSOR_SCHEMA_INVALID' });
  }
});

test('untyped optional provider fields and decimal source quantities do not acquire inferred meanings', async () => {
  const a = structuredClone(availabilityFixture), p = structuredClone(pricesFixture);
  a.products[0].closingTime = null;
  a.products[0].scheduleLines[0].availableAmount = 0.01;
  p.products[0].catalogPrice = null;
  const result = await port(async (url) => json(url.endsWith('/availability') ? a : p)).observe({ ...request, products: ['460032'] });
  assert.equal(result.availability.products[0].scheduleLines[0].availableAmount, 0.01);
  assert.equal(result.prices.products[0].catalogPrice, null);
  assert.equal(result.requiresTradeCoreValidation, true);
});

test('sample classifications refuse sentinel stock/net-price/cutoff authority; cache is bounded and expires', async () => {
  let now = Date.UTC(2026, 10, 15), calls = 0;
  const adapter = port(async (url) => { calls++; return json(url.endsWith('/availability') ? availabilityFixture : pricesFixture); }, { clock: () => now });
  const input = { ...request, products: ['460032'] };
  const first = await adapter.observe(input);
  assert.equal(first.classifications[0].cutoff, 'PASSED');
  assert.equal(first.classifications[0].netPrice, 'UNCONFIRMED');
  assert.equal(first.classifications[0].scheduleFacts[0].stock, 'UNKNOWN_TERMINAL_SENTINEL');
  assert.equal(first.classifications[0].scheduleFacts[0].sourceUnit, 'SK');
  assert.equal(first.classifications[0].purchasingAuthority, 'NONE');
  first.availability.products[0].salesBlock = true;
  now += 1000;
  const second = await adapter.observe(input);
  assert.equal(calls, 2);
  assert.deepEqual(second.cache, { hit: true, ageMs: 1000, ttlMs: 30000 });
  assert.equal(second.availability.products[0].salesBlock, false);
  now += 30000;
  await adapter.observe(input);
  assert.equal(calls, 4);
});

test('cache retains at most 128 observations and coalesces identical pending reads', async () => {
  let calls = 0;
  const adapter = port(async (url, init) => {
    calls++;
    const id = JSON.parse(init.body).products[0];
    const value = structuredClone(url.endsWith('/availability') ? availabilityFixture : pricesFixture);
    value.products[0].productId = id;
    return json(value);
  });
  await Promise.all([adapter.observe(request), adapter.observe(request)]);
  assert.equal(calls, 2);
  for (let i = 0; i < 128; i++) await adapter.observe({ ...request, products: [String(10000 + i)] });
  const before = calls;
  await adapter.observe(request);
  assert.equal(calls, before + 2);
});

test('sales blocks and absent schedules are unorderable observations without modifying source facts', async () => {
  for (const mode of ['blocked', 'empty']) {
    const a = structuredClone(availabilityFixture);
    if (mode === 'blocked') a.products[0].salesBlock = true;
    else a.products[0].scheduleLines = [];
    const result = await port(async (url) => json(url.endsWith('/availability') ? a : pricesFixture)).observe({ ...request, products: ['460032'] });
    assert.equal(result.classifications[0].availability, 'UNORDERABLE');
    assert.deepEqual(result.availability, a);
  }
});
